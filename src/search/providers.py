"""Live search providers: Tavily (web/news), OpenAlex, Crossref and arXiv (academic).

Each provider normalises its API's response into `SearchResult`. Snippets and abstracts are marked as
such (`full_text_available=False`), so downstream agents never imply they read a full text.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

from src.search.base import ProviderError, SearchResult, infer_web_source_type, parse_date
from src.search.http import HttpClient


def _strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


class TavilyProvider:
    name, label, live = "tavily", "Tavily web search", True
    serves = {"web", "news", "official"}
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str | None, http: HttpClient, topic: str = "general"):
        self.api_key, self.http, self.topic = api_key, http, topic

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def unavailable_reason(self) -> str:
        return "" if self.api_key else "TAVILY_API_KEY is not set, so live web search is disabled."

    def search(self, query: str, max_results: int = 5, date_from: date | None = None,
               date_to: date | None = None) -> list[SearchResult]:
        if not self.api_key:
            raise ProviderError(self.unavailable_reason)
        payload = {"query": query[:400], "max_results": max_results, "search_depth": "basic", "topic": self.topic,
                   "include_answer": False, "include_raw_content": False}
        if date_from:
            payload["start_date"] = date_from.isoformat()
        if date_to:
            payload["end_date"] = date_to.isoformat()
        data = self.http.post_json(self.endpoint, payload, headers={"Authorization": f"Bearer {self.api_key}"})
        return [parse_tavily_item(item, self.topic) for item in data.get("results", []) if item.get("url")]


def parse_tavily_item(item: dict, topic: str = "general") -> SearchResult:
    url, title = item["url"], (item.get("title") or item["url"]).strip()
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return SearchResult(
        title=title, provider="tavily", url=url, snippet=(item.get("content") or "").strip(),
        content=(item.get("content") or "").strip(), publisher=host,
        published_date=parse_date(item.get("published_date")), source_type=infer_web_source_type(url, title, topic),
        score=float(item.get("score") or 0), limitations=["Search snippet only unless the full page could be fetched."])


class OpenAlexProvider:
    name, label, live = "openalex", "OpenAlex (scholarly works)", True
    serves = {"academic"}
    endpoint = "https://api.openalex.org/works"

    def __init__(self, http: HttpClient, contact_email: str | None = None):
        self.http, self.contact_email = http, contact_email

    available = True
    unavailable_reason = ""

    def search(self, query: str, max_results: int = 5, date_from: date | None = None,
               date_to: date | None = None) -> list[SearchResult]:
        filters = []
        if date_from:
            filters.append(f"from_publication_date:{date_from.isoformat()}")
        if date_to:
            filters.append(f"to_publication_date:{date_to.isoformat()}")
        params = {"search": query[:300], "per-page": max_results}
        if filters:
            params["filter"] = ",".join(filters)
        if self.contact_email:
            params["mailto"] = self.contact_email
        data = self.http.get_json(self.endpoint, params=params)
        return [parse_openalex_work(w) for w in data.get("results", []) if w.get("display_name") or w.get("title")]


def reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    positions = [(pos, word) for word, poss in inverted.items() for pos in poss]
    return " ".join(word for _, word in sorted(positions))


def parse_openalex_work(work: dict) -> SearchResult:
    doi = (work.get("doi") or "").replace("https://doi.org/", "") or None
    location = work.get("primary_location") or {}
    venue = (location.get("source") or {}).get("display_name")
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    is_preprint = (work.get("type") in ("preprint", "posted-content")) or "arxiv" in (venue or "").lower()
    limitations = ["Abstract only: the full text was not retrieved."] if abstract else [
        "Metadata only: no abstract available."]
    return SearchResult(
        title=(work.get("display_name") or work.get("title")).strip(), provider="openalex",
        url=work.get("doi") or location.get("landing_page_url") or work.get("id"), doc_ref=doi,
        snippet=abstract[:600], content=abstract, publisher=venue,
        authors=[a["author"]["display_name"] for a in work.get("authorships", [])[:8] if a.get("author")],
        published_date=parse_date(work.get("publication_date")), source_type="preprint" if is_preprint else "academic_paper",
        metadata={"cited_by_count": work.get("cited_by_count"), "openalex_id": work.get("id"),
                  "referenced_works": len(work.get("referenced_works") or [])},
        sections=[("abstract", abstract)] if abstract else [], limitations=limitations)


class CrossrefProvider:
    name, label, live = "crossref", "Crossref (DOI metadata)", True
    serves = {"academic", "official"}
    endpoint = "https://api.crossref.org/works"

    def __init__(self, http: HttpClient, contact_email: str | None = None):
        self.http, self.contact_email = http, contact_email

    available = True
    unavailable_reason = ""

    def search(self, query: str, max_results: int = 5, date_from: date | None = None,
               date_to: date | None = None) -> list[SearchResult]:
        filters = []
        if date_from:
            filters.append(f"from-pub-date:{date_from.isoformat()}")
        if date_to:
            filters.append(f"until-pub-date:{date_to.isoformat()}")
        params = {"query": query[:300], "rows": max_results}
        if filters:
            params["filter"] = ",".join(filters)
        if self.contact_email:
            params["mailto"] = self.contact_email
        data = self.http.get_json(self.endpoint, params=params)
        return [parse_crossref_item(i) for i in data.get("message", {}).get("items", []) if i.get("title")]

    def resolve_doi(self, doi: str) -> SearchResult | None:
        try:
            data = self.http.get_json(f"{self.endpoint}/{doi}")
        except ProviderError:
            return None
        item = data.get("message")
        return parse_crossref_item(item) if item and item.get("title") else None


def parse_crossref_item(item: dict) -> SearchResult:
    parts = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            break
    published = None
    if parts and parts[0] and parts[0][0]:
        bits = list(parts[0]) + [1, 1]
        try:
            published = date(int(bits[0]), int(bits[1] or 1), int(bits[2] or 1))
        except (TypeError, ValueError):
            published = None
    abstract = _strip_tags(item.get("abstract", ""))
    doi = item.get("DOI")
    kind = item.get("type", "")
    source_type = "preprint" if kind == "posted-content" else ("official" if kind == "report" else "academic_paper")
    return SearchResult(
        title=_strip_tags(item["title"][0]), provider="crossref", url=item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        doc_ref=doi, snippet=abstract[:600], content=abstract,
        publisher=(item.get("container-title") or [item.get("publisher")])[0] if item.get("container-title") or item.get("publisher") else None,
        authors=[" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in item.get("author", [])[:8]],
        published_date=published, source_type=source_type,
        metadata={"type": kind, "is_referenced_by_count": item.get("is-referenced-by-count")},
        sections=[("abstract", abstract)] if abstract else [],
        limitations=["Abstract only: the full text was not retrieved."] if abstract else ["Metadata only: no abstract available."])


class ArxivProvider:
    name, label, live = "arxiv", "arXiv (preprints)", True
    serves = {"academic"}
    endpoint = "https://export.arxiv.org/api/query"

    def __init__(self, http: HttpClient):
        self.http = http

    available = True
    unavailable_reason = ""

    def search(self, query: str, max_results: int = 5, date_from: date | None = None,
               date_to: date | None = None) -> list[SearchResult]:
        terms = " AND ".join(f"all:{w}" for w in re.findall(r"[A-Za-z0-9\-]{3,}", query)[:8]) or "all:research"
        xml = self.http.get_text(self.endpoint, params={"search_query": terms, "max_results": max_results * 2,
                                                         "sortBy": "relevance"})
        results = parse_arxiv_feed(xml)
        if date_from:
            results = [r for r in results if not r.published_date or r.published_date >= date_from]
        if date_to:
            results = [r for r in results if not r.published_date or r.published_date <= date_to]
        return results[:max_results]


ATOM = {"a": "http://www.w3.org/2005/Atom"}


def parse_arxiv_feed(xml: str) -> list[SearchResult]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ProviderError(f"Malformed arXiv response: {exc}") from exc
    results = []
    for entry in root.findall("a:entry", ATOM):
        title = " ".join((entry.findtext("a:title", "", ATOM) or "").split())
        abs_url = (entry.findtext("a:id", "", ATOM) or "").strip()
        summary = " ".join((entry.findtext("a:summary", "", ATOM) or "").split())
        if not title or not abs_url:
            continue
        arxiv_id = abs_url.rsplit("/abs/", 1)[-1]
        results.append(SearchResult(
            title=title, provider="arxiv", url=abs_url, doc_ref=f"arXiv:{arxiv_id}", snippet=summary[:600],
            content=summary, publisher="arXiv", source_type="preprint",
            authors=[a.findtext("a:name", "", ATOM) for a in entry.findall("a:author", ATOM)][:8],
            published_date=parse_date(entry.findtext("a:published", "", ATOM)), sections=[("abstract", summary)],
            limitations=["Preprint: not peer reviewed.", "Abstract only: the full text was not retrieved."]))
    return results
