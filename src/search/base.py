"""Search-provider interface. Providers discover sources; they never synthesise or judge content."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """A provider failed (network, rate limit, bad response). The retriever records it and continues."""


@dataclass
class SearchResult:
    title: str
    provider: str  # demo | tavily | openalex | crossref | arxiv | upload
    url: str | None = None
    doc_ref: str | None = None  # DOI / arXiv id / document id
    snippet: str = ""
    content: str = ""  # full text when the provider returned it
    full_text_available: bool = False
    publisher: str | None = None
    authors: list[str] = field(default_factory=list)
    published_date: date | None = None
    source_type: str = "other"
    score: float = 0.0
    sections: list[tuple[str, str]] = field(default_factory=list)  # location-preserving content, if known
    metadata: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


class SearchProvider(Protocol):
    name: str
    label: str
    serves: set[str]  # SourcePreference values this provider can satisfy
    live: bool  # True if results come from the live internet

    @property
    def available(self) -> bool: ...

    @property
    def unavailable_reason(self) -> str: ...

    def search(self, query: str, max_results: int = 5, date_from: date | None = None,
               date_to: date | None = None) -> list[SearchResult]: ...


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = str(value).strip()[:10]
    for fmt_len, parts in ((10, 3), (7, 2), (4, 1)):
        try:
            if len(value) >= fmt_len:
                bits = [int(x) for x in value[:fmt_len].split("-")]
                if len(bits) == parts:
                    return date(*(bits + [1] * (3 - parts)))
        except ValueError:
            continue
    return None


def infer_web_source_type(url: str | None, title: str = "", topic: str = "general") -> str:
    host = (url or "").lower()
    title_l = title.lower()
    if any(d in host for d in (".gov", "europa.eu", "who.int", "oecd.org", "worldbank.org", "rbi.org.in", "imf.org",
                                "un.org", "nist.gov")):
        return "official"
    if "arxiv.org" in host:
        return "preprint"
    if any(d in host for d in ("doi.org", "nature.com", "sciencedirect", "springer", "acm.org", "ieee.org",
                                "aclanthology", "openreview")):
        return "academic_paper"
    if "/docs" in host or host.split("//")[-1].startswith("docs.") or "documentation" in title_l:
        return "documentation"
    if any(d in host for d in ("medium.com", "substack.com", "blog.", "/blog")):
        return "blog"
    if any(d in host for d in ("gartner", "mckinsey", "forrester", "idc.com", "bcg.com", "deloitte")):
        return "analyst"
    if any(w in title_l for w in ("opinion", "op-ed", "commentary", "column")):
        return "opinion"
    if any(w in host for w in ("press", "newsroom", "investor")):
        return "company"
    if topic == "news" or any(d in host for d in ("reuters", "bloomberg", "ft.com", "wsj", "economictimes", "techcrunch",
                                                    "theverge", "cnbc", "bbc.", "livemint", "nytimes")):
        return "news"
    return "other"


def result_to_dict(result: SearchResult) -> dict:
    from dataclasses import asdict

    data = asdict(result)
    data["published_date"] = result.published_date.isoformat() if result.published_date else None
    data["sections"] = [list(s) for s in result.sections]
    return data


def result_from_dict(data: dict) -> SearchResult:
    data = dict(data)
    data["published_date"] = parse_date(data.get("published_date"))
    data["sections"] = [tuple(s) for s in data.get("sections", [])]
    return SearchResult(**data)
