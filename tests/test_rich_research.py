"""Richer research: full texts, snowballing, Semantic Scholar, data points, entities, LLM grouping/strategy,
two-model routing and adaptive report templates."""
from datetime import date

import httpx
import pymupdf
import pytest

from src.agents.base import RunContext
from src.agents.critical_analyst import CriticalAnalystAgent, windows
from src.agents.gap_analyst import GapAnalystAgent, clean_query
from src.agents.report_builder import REPORT_TEMPLATES, choose_template
from src.analysis.claims import DataPointDraft, validate_llm_data_points
from src.analysis.datapoints import group_data_points, heuristic_data_points, heuristic_entities, timeline
from src.evidence.store import EvidenceStore
from src.models.evidence import Claim, ClaimType, DataPoint, Origin, Passage
from src.models.research import ReportFormat, ResearchBudget, ResearchRequest
from src.orchestration.budget import RunBudget
from src.search import http as http_module
from src.search.http import HttpClient
from src.search.providers import OpenAlexProvider, parse_openalex_work, parse_semantic_scholar, parse_tavily_item
from src.search.registry import ProviderSet
from src.services.llm import LLMClient
from src.services.research_service import run_research
from tests.conftest import QUESTION, TODAY, FakeProvider, fake_openai, live_request, make_result, provider_set


def passage(text, sid="src_a", loc="page 1", idx=0):
    return Passage(id=f"{sid}#p{idx}", source_id=sid, text=text, location=loc, index=idx)


def store_with(*results):
    store = EvidenceStore()
    sources = [store.add_result(r, Origin.LIVE, "sq1", "q", 0)[0] for r in results]
    return store, sources


# ------------------------------------------------------------------ data points & entities
def test_heuristic_data_points_extracts_measures_and_skips_years():
    text = ("A survey of 1,200 enterprises found that 38% have at least one AI agent in production. "
            "The assistant increased resolutions per hour by 14% in 2025. The study ran from 2019 to 2024.")
    store, [source] = store_with(make_result("Survey", text))
    points = heuristic_data_points(source, store.passages[source.id])
    by_value = {p.value_text: p for p in points}
    assert "38%" in by_value and by_value["38%"].unit == "%" and by_value["38%"].method == "survey"
    assert "agent" in by_value["38%"].metric.lower() and by_value["38%"].kind == "level"
    assert by_value["14%"].kind == "change" and by_value["14%"].period == "2025"
    assert not any(p.value_text in ("2019", "2024") for p in points)  # bare years are not data points
    assert all(p.quote in store.passages[source.id][0].text for p in points)


def test_llm_data_points_require_verbatim_quote_and_number():
    p = passage("The best agent completes 34.7% of tasks end to end. Studies were published between 2020 and 2024.")
    from src.models.evidence import Source
    source = Source(id="src_a", title="t", origin=Origin.LIVE, retrieval_method="x")
    drafts = [DataPointDraft(quote="The best agent completes 34.7% of tasks end to end.", metric="task success",
                             value_text="34.7%", unit="%"),
              DataPointDraft(quote="Agents complete 90% of tasks.", metric="invented", value_text="90%"),
              DataPointDraft(quote="The best agent completes 34.7% of tasks end to end.", metric="wrong number",
                             value_text="55%"),
              DataPointDraft(quote="Studies were published between 2020 and 2024.", metric="studies", value_text="2")]
    points, rejected = validate_llm_data_points(drafts, source, [p])
    assert [d.value for d in points] == [34.7] and rejected == 3 and points[0].extracted_by == "llm"


def test_group_data_points_is_strict():
    def dp(i, metric, value):
        return DataPoint(id=f"d{i}", metric=metric, value=value, value_text=f"{value}%", unit="%", source_id=f"s{i}",
                         passage_id="p", quote="q")
    groups = group_data_points([dp(1, "enterprises with AI agents in production", 38),
                                dp(2, "enterprises deploying AI agents in production", 72),
                                dp(3, "vendors with outcome-based pricing for agents", 41)])
    assert sorted(len(g) for g in groups) == [1, 2]


def test_entities_and_timeline():
    claims = [Claim(id=f"c{i}", text=t, quote=t, claim_type=ClaimType.FORECAST, source_id=s, passage_id="p")
              for i, (t, s) in enumerate([("AgentForge expects agents to lead by 2028.", "s1"),
                                          ("AgentForge expects agents to lead by 2028.", "s2"),
                                          ("SaaS vendors embed agents; AgentForge disagrees.", "s3"),
                                          ("In 2025 the regulator issued the Autonomous Systems Guidance.", "s4")])]
    entities = heuristic_entities(claims, {})
    names = {e.name: e for e in entities}
    assert "AgentForge" in names and names["AgentForge"].kind == "company" and "SaaS" not in names
    events = timeline(claims, {}, TODAY)
    assert [e["year"] for e in events] == [2025, 2028]  # duplicate 2028 forecast collapsed
    assert events[1]["kind"] == "forecast" and events[0]["kind"] == "event"


# ------------------------------------------------------------------ providers
def test_tavily_raw_content_becomes_full_text():
    item = {"title": "Agents report", "url": "https://example.com/a", "content": "Short snippet.",
            "raw_content": "Full page text about agents. " * 60}
    result = parse_tavily_item(item)
    assert result.full_text_available and result.content.startswith("Full page text")
    assert result.metadata["full_text_via"] == "Tavily raw content" and result.sections


def test_semantic_scholar_parsing():
    paper = {"title": "Agentic RAG", "abstract": None, "tldr": {"text": "Planning improves multi-hop QA."},
             "venue": "arXiv.org", "externalIds": {"ArXiv": "2603.00001"}, "year": 2026, "authors": [{"name": "L. M"}],
             "citationCount": 12, "influentialCitationCount": 3, "openAccessPdf": {"url": "https://arxiv.org/pdf/2603.00001"}}
    result = parse_semantic_scholar(paper)
    assert result.source_type == "preprint" and result.doc_ref == "arXiv:2603.00001"
    assert "TLDR" in result.content and result.metadata["oa_pdf_url"].endswith(".00001")
    assert any("TLDR" in l for l in result.limitations)


def test_openalex_oa_pdf_and_snowball_request():
    work = {"display_name": "Paper", "id": "https://openalex.org/W123", "best_oa_location": {"pdf_url": "https://x.org/p.pdf"}}
    assert parse_openalex_work(work).metadata["oa_pdf_url"] == "https://x.org/p.pdf"
    seen = {}

    def handler(request):
        seen["filter"] = request.url.params["filter"]
        return httpx.Response(200, json={"results": [{"display_name": "Cited work", "id": "https://openalex.org/W9"}]})
    provider = OpenAlexProvider(HttpClient(transport=httpx.MockTransport(handler)))
    assert provider.related("https://openalex.org/W123", "cited_by")[0].title == "Cited work"
    assert seen["filter"] == "cites:W123"
    provider.related("https://openalex.org/W123", "references")
    assert seen["filter"] == "cited_by:W123"


def test_safe_fetch_pdf(monkeypatch):
    monkeypatch.setattr(http_module, "is_public_http_url", lambda url: True)
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Full text")
    data = pdf.tobytes()

    def handler(request):
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, content=data, headers={"content-type": "application/pdf"})
        return httpx.Response(200, text="<html>not a pdf</html>", headers={"content-type": "text/html"})
    client = HttpClient(transport=httpx.MockTransport(handler))
    assert client.safe_fetch_pdf("https://example.org/paper.pdf").startswith(b"%PDF")
    assert client.safe_fetch_pdf("https://example.org/page") is None


# ------------------------------------------------------------------ retriever: full text + snowballing
class FakeHttp:
    def __init__(self, pdf_bytes):
        self.pdf_bytes, self.pdf_calls = pdf_bytes, []

    def safe_fetch_pdf(self, url):
        self.pdf_calls.append(url)
        return self.pdf_bytes

    def safe_fetch(self, url):
        return None


class FakeOpenAlex:
    name, label, live, serves, available, unavailable_reason = "openalex", "Fake OpenAlex", True, {"academic"}, True, ""

    def __init__(self, results):
        self.results, self.related_calls = results, []

    def search(self, query, max_results=5, date_from=None, date_to=None):
        return self.results[:max_results]

    def related(self, openalex_id, direction, limit=2):
        self.related_calls.append(direction)
        return [make_result(f"{direction} work {len(self.related_calls)}",
                            f"Agentic AI enterprise software study {direction} {len(self.related_calls)}. " * 3)]


def test_open_access_full_text_and_snowballing(settings):
    doc = pymupdf.open()
    for i in range(3):
        doc.new_page().insert_text((72, 72), f"Page {i + 1}: agentic AI in enterprise software improves output by 14%.")
    pdf = doc.tobytes()
    seed = make_result("Seed paper on agentic AI enterprise software", "Abstract about agentic AI enterprise software.",
                       metadata={"openalex_id": "https://openalex.org/W1", "oa_pdf_url": "https://x.org/seed.pdf"})
    seed.full_text_available = False
    openalex = FakeOpenAlex([seed])
    http = FakeHttp(pdf)
    providers = ProviderSet(providers=[openalex], http=http, openalex=openalex)
    state = run_research(live_request(use_llm=False), settings, today=TODAY, providers=providers)
    seed_source = next(s for s in state["sources"] if s.title.startswith("Seed paper"))
    assert seed_source.full_text_available and seed_source.metadata["full_text_via"] == "open-access PDF"
    assert {p.location for p in state["passages"] if p.source_id == seed_source.id} >= {"page 1", "page 2", "page 3"}
    assert openalex.related_calls  # snowballing ran in the follow-up round
    snowballed = [s for s in state["sources"] if s.metadata.get("snowball")]
    assert snowballed and any(r.provider == "openalex_snowball" for r in state["search_log"])


# ------------------------------------------------------------------ critical analysis with the LLM
class ScriptedLLM:
    """Answers by schema: extraction per source, verification verdicts, and claim grouping."""

    available, model, fast_model = True, "strong", "fast"

    def __init__(self, extraction: dict, unfaithful_index: int, contradicting_ids: set):
        self.extraction, self.unfaithful_index, self.contradicting_ids = extraction, unfaithful_index, contradicting_ids
        self.calls = []

    def structured(self, prompt, schema, budget, max_tokens=1800, fast=False):
        import re
        self.calls.append((schema.__name__, fast))
        if schema.__name__ == "ExtractionDraft":
            source_id = re.search(r'untrusted_source id="(src_\w+)"', prompt).group(1)
            return schema.model_validate(self.extraction[source_id])
        if schema.__name__ == "Verdicts":
            count = len(re.findall(r"^\d+\. QUOTE", prompt, re.M))
            return schema.model_validate({"verdicts": [
                {"index": i, "verdict": "unfaithful" if i == self.unfaithful_index else "faithful"} for i in range(count)]})
        if schema.__name__ == "ClaimGroups":
            ids = re.findall(r"^(clm_[0-9a-f]+):", prompt, re.M)
            return schema.model_validate({"groups": [{"proposition": "Agents will replace SaaS",
                                                      "supporting": [i for i in ids if i not in self.contradicting_ids],
                                                      "contradicting": [i for i in ids if i in self.contradicting_ids]}]})
        return None


def test_llm_extraction_grouping_and_verification(settings):
    from src.agents.planner import PlannerAgent
    from src.analysis.claims import claim_id
    texts = {"A": "AI agents will replace traditional SaaS workflows within five years, says AgentForge Inc.",
             "B": "AgentForge Inc. expects agents to take over most SaaS workflows soon.",
             "C": "Claims that agents will replace SaaS workflows are overstated, a review of 85 deployments found."}
    store, sources = store_with(*[make_result(f"Source {k}", v, source_type="analyst") for k, v in texts.items()])
    extraction, sceptical_ids = {}, set()
    for source in sources:
        key = source.title[-1]
        quote = texts[key]
        extraction[source.id] = {
            "claims": [{"quote": quote, "claim": f"Restated claim from source {key}", "claim_type": "forecast",
                        "sceptical": key == "C"}],
            "data_points": [{"quote": quote, "metric": "deployments reviewed", "value_text": "85", "unit": "count"}]
            if key == "C" else [],
            "entities": [{"name": "AgentForge Inc.", "kind": "company"}]}
        if key == "C":
            sceptical_ids.add(claim_id(source.id, quote))
    llm = ScriptedLLM(extraction, unfaithful_index=1, contradicting_ids=sceptical_ids)
    request = live_request(question="What evidence supports or contradicts the claim that AI agents will replace SaaS workflows?")
    ctx = RunContext(settings=settings, budget=RunBudget(ResearchBudget()), providers=ProviderSet(), llm=llm, use_llm=True)
    state = {"plan": PlannerAgent().heuristic_plan(request), "request": request, "sources": list(store.sources.values()),
             "passages": store.all_passages(), "assessments": {}, "claims": [], "extracted_source_ids": []}
    update = CriticalAnalystAgent().run(state, ctx)

    assert len(update["claims"]) == 3 and all(c.extracted_by == "llm" for c in update["claims"])
    unfaithful = [c for c in update["claims"] if c.verified is False]
    assert len(unfaithful) == 1 and unfaithful[0].text == unfaithful[0].quote  # restatement replaced by the quote
    [row] = [r for r in update["matrix"] if len(r.supporting_claim_ids) + len(r.contradicting_claim_ids) == 3]
    assert row.grouped_by == "llm" and row.contradicting_claim_ids == list(sceptical_ids)
    assert row.independent_sources == 2 and row.strength > 0
    assert update["contradictions"] and "LLM" in update["contradictions"][0].explanation
    assert [d.value for d in update["data_points"]] == [85.0]
    assert any(e.name == "AgentForge Inc." for e in update["entities"])
    assert ("ExtractionDraft", True) in llm.calls and ("ClaimGroups", False) in llm.calls  # fast vs strong model


def test_windows_cover_whole_document():
    passages = [passage("x" * 2500, idx=i) for i in range(7)]
    chunks = windows(passages, size=6000)
    assert sum(len(w) for w in chunks) == 7 and all(sum(len(p.text) for p in w) <= 7500 for w in chunks)


# ------------------------------------------------------------------ research strategy
def test_llm_strategy_queries_are_validated(settings):
    from src.agents.planner import PlannerAgent
    request = live_request()
    plan = PlannerAgent().heuristic_plan(request)
    searched = [plan.subquestions[0].queries[0]]
    client, _ = fake_openai([{"queries": [
        {"subquestion_id": "sq1", "query": "Meridian Analyst Group agent survey methodology", "kind": "original_source"},
        {"subquestion_id": "sq99", "query": "agent adoption definitions copilots", "kind": "definition"},
        {"subquestion_id": "sq2", "query": searched[0], "kind": "gap"},
        {"subquestion_id": "sq2", "query": "x", "kind": "gap"}]}])
    ctx = RunContext(settings=settings, budget=RunBudget(ResearchBudget()), providers=provider_set(FakeProvider()),
                     llm=LLMClient(settings, client=client), use_llm=True)
    state = {"plan": plan, "matrix": [], "claims": [], "contradictions": [], "entities": [], "searched_queries": searched}
    tasks = GapAnalystAgent()._strategy_tasks(state, [], plan, ctx)
    assert [t.query for t in tasks] == ["Meridian Analyst Group agent survey methodology", "agent adoption definitions copilots"]
    assert tasks[0].purpose == "original_source" and tasks[1].subquestion_id is None  # invalid subquestion id dropped
    assert clean_query("agents evidence evidence survey") == "agents evidence survey"


def test_unchallenged_findings_get_counter_evidence_search(settings):
    from src.agents.planner import PlannerAgent
    from src.models.evidence import Agreement, EvidenceQuality, MatrixRow
    request = live_request()
    plan = PlannerAgent().heuristic_plan(request)
    row = MatrixRow(id="row_1", claim="Support assistants increase resolutions per hour by fourteen percent",
                    subquestion_id="sq1", claim_type=ClaimType.STATISTIC, supporting_claim_ids=["c1", "c2"],
                    supporting_source_ids=["s1", "s2"], independent_sources=2, agreement=Agreement.MODERATE,
                    evidence_quality=EvidenceQuality.HIGH, strength=1.6)
    ctx = RunContext(settings=settings, budget=RunBudget(ResearchBudget()), providers=provider_set(FakeProvider()))
    state = {"plan": plan, "request": request, "budget": request.budget(), "iteration": 0, "sources": [], "passages": [],
             "assessments": {}, "matrix": [row], "claims": [], "searched_queries": [], "new_sources_last_iteration": 3}
    update = GapAnalystAgent().run(state, ctx)
    unchallenged = [g for g in update["gaps"] if g.kind.value == "unchallenged"]
    assert unchallenged and "criticism" in unchallenged[0].follow_up_queries[0]
    assert any(t.purpose == "counter_evidence" for t in update["pending_queries"])


# ------------------------------------------------------------------ two models
def test_fast_model_is_used_for_extraction(settings):
    from dataclasses import replace
    two_models = replace(settings, openrouter_model="strong/model", openrouter_fast_model="fast/model")
    models = []
    client, completions = fake_openai(['{"claims": [], "data_points": [], "entities": []}'] * 40)
    original = completions.create

    def create(**kwargs):
        models.append(kwargs["model"])
        return original(**kwargs)
    completions.create = create
    provider = FakeProvider(results=[make_result("Agentic AI in enterprise software",
                                                 "Agentic AI in enterprise software improves productivity by 14%. " * 3)])
    run_research(live_request(), two_models, today=TODAY, providers=provider_set(provider), llm=LLMClient(two_models, client=client))
    assert models[0] == "strong/model"  # planning uses the strong model
    assert "fast/model" in models  # extraction uses the fast model


# ------------------------------------------------------------------ adaptive reports
@pytest.mark.parametrize("question,fmt,template", [
    (QUESTION, ReportFormat.AUTO, "outlook"),
    ("What evidence supports or contradicts the claim that AI agents will replace SaaS?", ReportFormat.AUTO, "evidence_assessment"),
    ("What are the latest research developments in retrieval-augmented generation?", ReportFormat.AUTO, "literature_review"),
    ("Which companies lead generative AI adoption in payments?", ReportFormat.AUTO, "landscape"),
    (QUESTION, ReportFormat.BRIEF, "brief"),
    (QUESTION, ReportFormat.FULL, "full"),
])
def test_template_selection(question, fmt, template):
    assert choose_template(question, fmt) == template


@pytest.mark.parametrize("question,fmt,must_have", [
    ("What evidence supports or contradicts the claim that AI agents will replace traditional SaaS workflows?",
     ReportFormat.AUTO, ["verdict", "evidence_for", "evidence_against", "key_numbers"]),
    ("What are the latest research developments in retrieval-augmented generation?", ReportFormat.AUTO,
     ["methods", "open_problems", "key_numbers"]),
    ("Which companies lead generative AI adoption in payments?", ReportFormat.AUTO, ["players", "comparison"]),
    (QUESTION, ReportFormat.BRIEF, ["executive_summary", "key_numbers", "references"]),
])
def test_adaptive_reports_render_with_valid_citations(settings, question, fmt, must_have):
    state = run_research(ResearchRequest(question=question, report_format=fmt), settings, today=TODAY)
    report = state["report"]
    keys = [s.key for s in report.sections]
    assert keys == REPORT_TEMPLATES[report.template][1] and set(must_have) <= set(keys)
    assert report.citation_checks and all(c.valid for c in report.citation_checks)
    if "key_numbers" in keys:
        assert "| Measure | Value |" in report.section("key_numbers").content
    if "verdict" in keys:
        assert "quality-weighted support" in report.section("verdict").content
