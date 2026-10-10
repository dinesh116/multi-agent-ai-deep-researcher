"""Search providers (mocked HTTP), academic parsing, retries and SSRF protection."""
import json
from datetime import date

import httpx
import pytest

from src.search.base import ProviderError
from src.search.http import HttpClient, is_public_http_url, with_retries
from src.search.local import DemoProvider
from src.search.providers import (ArxivProvider, CrossrefProvider, OpenAlexProvider, TavilyProvider,
                                  parse_arxiv_feed, reconstruct_abstract)


def client_with(handler) -> HttpClient:
    return HttpClient(timeout=5, transport=httpx.MockTransport(handler))


def test_tavily_request_and_parsing():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": [
            {"title": "Agents in the enterprise", "url": "https://www.reuters.com/tech/agents?utm_source=x",
             "content": "Enterprises are piloting AI agents.", "score": 0.9, "published_date": "2026-03-01"},
            {"title": "No URL result"}]})

    provider = TavilyProvider("tvly-test-key", client_with(handler), topic="news")
    results = provider.search("ai agents enterprise", max_results=3, date_from=date(2025, 1, 1))
    assert seen["auth"] == "Bearer tvly-test-key" and seen["body"]["topic"] == "news"
    assert seen["body"]["start_date"] == "2025-01-01"
    assert len(results) == 1 and results[0].source_type == "news" and results[0].published_date == date(2026, 3, 1)
    assert not results[0].full_text_available


def test_tavily_unavailable_without_key():
    provider = TavilyProvider(None, client_with(lambda r: httpx.Response(500)))
    assert not provider.available and "TAVILY_API_KEY" in provider.unavailable_reason
    with pytest.raises(ProviderError):
        provider.search("anything")


def test_openalex_parsing_and_abstract_reconstruction():
    work = {"display_name": "Hybrid retrieval study", "doi": "https://doi.org/10.5555/x.1", "publication_date": "2025-06-02",
            "type": "article", "abstract_inverted_index": {"Hybrid": [0], "retrieval": [1], "helps": [2]},
            "authorships": [{"author": {"display_name": "A. Author"}}], "cited_by_count": 12,
            "primary_location": {"source": {"display_name": "Journal of IR"}}}
    provider = OpenAlexProvider(client_with(lambda r: httpx.Response(200, json={"results": [work]})), "me@example.org")
    [result] = provider.search("hybrid retrieval")
    assert result.content == "Hybrid retrieval helps" and result.doc_ref == "10.5555/x.1"
    assert result.publisher == "Journal of IR" and result.metadata["cited_by_count"] == 12
    assert any("Abstract only" in l for l in result.limitations)
    assert reconstruct_abstract(None) == ""


def test_crossref_parsing_and_doi_resolution():
    item = {"title": ["A <i>study</i> of agents"], "DOI": "10.5555/abc", "URL": "https://doi.org/10.5555/abc",
            "author": [{"given": "B.", "family": "Writer"}], "container-title": ["Review of AI"],
            "published-print": {"date-parts": [[2024, 5]]}, "abstract": "<jats:p>Agents <b>improve</b> work.</jats:p>",
            "type": "journal-article"}

    def handler(request):
        if request.url.path.endswith("/10.5555/abc"):
            return httpx.Response(200, json={"message": item})
        return httpx.Response(200, json={"message": {"items": [item]}})

    provider = CrossrefProvider(client_with(handler))
    [result] = provider.search("agents")
    assert result.title == "A study of agents" and result.content == "Agents improve work."
    assert result.published_date == date(2024, 5, 1) and result.authors == ["B. Writer"]
    assert provider.resolve_doi("10.5555/abc").doc_ref == "10.5555/abc"


ARXIV_XML = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/2509.01234v1</id><title>EntBench:
 Evaluating Agents</title><summary>We introduce a benchmark.</summary><published>2025-09-15T00:00:00Z</published>
<author><name>H. Zhou</name></author></entry></feed>"""


def test_arxiv_parsing_and_malformed_feed():
    [result] = parse_arxiv_feed(ARXIV_XML)
    assert result.title == "EntBench: Evaluating Agents" and result.doc_ref == "arXiv:2509.01234v1"
    assert result.source_type == "preprint" and "not peer reviewed" in result.limitations[0]
    provider = ArxivProvider(client_with(lambda r: httpx.Response(200, text=ARXIV_XML)))
    assert provider.search("agents benchmark", date_from=date(2026, 1, 1)) == []  # date filter applied
    with pytest.raises(ProviderError):
        parse_arxiv_feed("<not xml")


def test_retries_transient_errors_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503 if len(calls) == 1 else 429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"results": []})

    client = client_with(handler)
    sleeps = []
    import src.search.http as http_module
    original = http_module.time.sleep
    http_module.time.sleep = sleeps.append
    try:
        assert client.get_json("https://api.example.org/x") == {"results": []}
    finally:
        http_module.time.sleep = original
    assert len(calls) == 3 and sleeps == [1.0, 1.0]


def test_non_transient_error_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404)
    with pytest.raises(ProviderError, match="HTTP 404"):
        client_with(handler).get_json("https://api.example.org/missing")
    assert len(calls) == 1


def test_with_retries_gives_up_after_attempts():
    def boom():
        raise httpx.ConnectError("down")
    with pytest.raises(ProviderError, match="after 2 attempts"):
        with_retries(boom, attempts=2, sleep=lambda s: None)


@pytest.mark.parametrize("url", ["http://localhost/admin", "http://127.0.0.1:8080/", "file:///etc/passwd",
                                 "ftp://example.org/x", "http://169.254.169.254/latest/meta-data", "http://intranet.local/"])
def test_ssrf_protection_blocks_non_public_urls(url):
    assert not is_public_http_url(url)
    assert client_with(lambda r: httpx.Response(200, text="<html>secret</html>")).safe_fetch(url) is None


def test_demo_provider_is_offline_and_labelled():
    results = DemoProvider().search("agents replace SaaS workflows", max_results=3)
    assert results and all(r.metadata["synthetic"] for r in results)
    assert all("SYNTHETIC" in r.limitations[0] for r in results)
    assert all(r.url.startswith("https://example.org/synthetic/") for r in results)
