# 🔬 Deep Researcher AI

A multi-agent research assistant for complex, multi-hop questions. It plans an investigation, searches web,
academic and uploaded sources, evaluates credibility, extracts claims linked to exact passages, detects
contradictions, runs bounded follow-up research on gaps, generates clearly labelled insights and hypotheses,
and compiles a cited report you can export, reopen and question.

Built with **LangGraph** (orchestration), **Streamlit** (dashboard), **OpenRouter** via the OpenAI SDK (optional
LLM), **OpenAlex / Crossref / arXiv / Tavily** (sources), **SQLite**, **PyMuPDF**, **Trafilatura** and **Plotly**.

> Demo mode uses a **synthetic, fictional** corpus and is labelled as such everywhere. A citation that passes
> validation is *traceable*, which is not the same as *true*. Always check important conclusions against the
> original sources.

---

## Quick start

Requires Python 3.12+ (developed on 3.13). From this folder:

```bash
uv venv --python 3.13                 # or: python3.13 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt    # or: pip install -r requirements.txt

cp .env.example .env                  # optional: add keys for live research (see below)
streamlit run app.py                  # http://localhost:8501
pytest                                # 87 tests, offline, no API keys needed
```

**From VS Code:** open this folder, select the `.venv` interpreter, then use **Run and Debug → "Deep Researcher AI
(Streamlit)"**. Tests appear in the Testing panel.

## Demo mode vs live research

| | Demo mode (default) | Live research |
|---|---|---|
| Sources | 27 bundled **synthetic** sources (`data/sample_research/corpus.json`) | OpenAlex, Crossref, arXiv (no key), Tavily web/news (`TAVILY_API_KEY`), your uploads |
| Network | none | search APIs + bounded fetching of public result pages |
| Agents | deterministic | deterministic, plus LLM planning, extraction, adjudication, insights and prose when `OPENROUTER_API_KEY` is set |
| Labels | every source, reference and export says SYNTHETIC | live / cached / uploaded origin shown per source |

The demo corpus deliberately includes contradictions (e.g. 38% vs 72% agent adoption), a vendor press release
reprinted by a news site, an outdated 2019 forecast, opinion pieces, conflict-of-interest material and a
prompt-injection attempt, so every analysis feature has something to find. Try *"How will agentic AI transform
enterprise software over the next five years?"* or *"What evidence supports or contradicts the claim that AI agents
will replace traditional SaaS workflows?"*

## Configuration

Edit `.env` (never committed):

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Enables LLM features. Without it, agents run deterministically. |
| `OPENROUTER_MODEL` | Default `openai/gpt-4o-mini`; any OpenRouter model with JSON output. Can be overridden on the Settings page. |
| `OPENROUTER_BASE_URL` | Default `https://openrouter.ai/api/v1` |
| `TAVILY_API_KEY` | Enables live web and news search (<https://tavily.com>) |
| `CONTACT_EMAIL` | Sent to OpenAlex/Crossref for polite API use (recommended) |
| `APP_DB_PATH`, `HTTP_TIMEOUT_SECONDS`, `LLM_TIMEOUT_SECONDS`, `MAX_UPLOAD_MB` | Optional |

OpenRouter only handles language tasks. It is **not** used for web search; source discovery is done by the search
providers, which you can toggle on the **Settings** page. Without Tavily, live mode still searches the academic
sources and your uploads, and says so in the run log.

## The pages

1. **Research Workspace**: question, context, objectives, depth, source types, date range, follow-up rounds, mode, document uploads, recent runs.
2. **Research Progress**: live orchestrator events (current agent and subquestion, searches, sources, claims, round), then the stored audit trail, search log, budget usage and stopping decision.
3. **Evidence Explorer**: filterable sources with provenance, assessments, flags, passages, claims and duplicate links.
4. **Critical Analysis**: evidence matrix, contradictions side by side, agreement vs uncertainty, gaps, coverage, quality flags.
5. **Insights & Hypotheses**: findings, trends, hypotheses, risks and opportunities, each labelled observed/inferred/speculative, with confidence, alternatives, limitations and evidence.
6. **Research Report**: 12-section cited report, citation-traceability table, Markdown/HTML/PDF export, follow-up Q&A, "Refine investigation".
7. **Research History**: reopen or delete persisted runs.
8. **Settings**: model, providers, defaults and limits, masked key status, cache and document management.

## How it works (summary)

```
START → Planner → Retriever → Source Evaluation → Critical Analysis → Gap & Follow-up ─┬─ follow_up → Retriever (loop, bounded)
                                                                                      └─ synthesize → Insights → Report → END
```

The follow-up decision is deterministic. Research stops at the iteration limit, when the search, source or time
budget is exhausted, when no gap is worth pursuing, or when a round finds no new sources. See
[docs/architecture.md](docs/architecture.md) for agent contracts, the evidence model and the security design.

## Project structure

```
app.py                     entry point, navigation, home
pages/                     8 Streamlit pages
src/config.py              settings from .env (secrets masked)
src/models/                research, evidence and run models (Pydantic)
src/orchestration/         LangGraph graph, typed state, budget tracker
src/agents/                planner, retriever, source_evaluator, critical_analyst, gap_analyst,
                           insight_generator, report_builder, qa
src/search/                provider interface, Tavily/OpenAlex/Crossref/arXiv, demo & upload providers, HTTP safety
src/ingestion/             document extraction and chunking
src/evidence/              evidence store (dedup, syndication) and citations
src/analysis/              text heuristics, claims, evidence matrix
src/retrieval/             BM25
src/reporting/             Markdown/HTML/PDF rendering
src/database/              SQLite schema and repository
src/services/              research service, LLM client
src/ui/                    shared UI state, components, charts
data/sample_research/      synthetic demo corpus
tests/                     pytest suite (mocked providers, fake LLM, network blocked)
docs/architecture.md
```

## Testing

`pytest` runs 87 tests offline. An autouse fixture **fails any test that touches the network**; providers use
`httpx.MockTransport`, and the LLM is a fake OpenAI client. The tests cover question validation, plan
generation and schema, provider parsing (Tavily, OpenAlex, Crossref, arXiv), retries and rate limits, SSRF
blocking, document extraction, normalisation and dedup, syndication, claims and verbatim-quote validation, the
evidence matrix and contradictions, citation validation, conditional routing, iteration, search and source
limits, provider and agent failures, missing credentials, caching, persistence and history, report export,
Q&A citation validation, and prompt-injection handling.

## Known limitations

- Heuristic (demo/no-LLM) analysis uses wording cues. Claim clustering and polarity can miss paraphrased
  agreement or flag false contradictions, and those contradictions are labelled as heuristic. The LLM mode
  reviews each candidate.
- Academic results are usually abstracts only. This is shown per source and in the report.
- Retrieval is keyword-based (BM25); paraphrased questions may retrieve less well than with embeddings.
- Full-text fetching is limited to 6 pages per round and skips non-HTML content.
- Scanned PDFs need OCR (not included). Model costs are tracked as calls and tokens, not money.
- Single local user; no authentication.

## Troubleshooting

- **"Web search unavailable"**: set `TAVILY_API_KEY` in `.env` and restart, or rely on academic sources.
- **Live runs return few sources**: widen the date range, enable more providers, or choose *Deep*.
- **LLM output rejected** (in the progress log): the app fell back to deterministic logic. Try a stronger model on the Settings page.
- **A run is stuck as "running"** after closing the app: it is marked failed on next start.
- **Start fresh**: delete `data/research.db`.

## Recommended next steps

Hybrid BM25 plus embedding retrieval, LLM-assisted source evaluation with calibration studies, OCR, more providers
(Semantic Scholar, news APIs), scheduled re-runs to track how evidence changes, and cost estimation per model.
