# Deep Researcher AI: Architecture

## Principles

1. **Deterministic control, LLM language.** Routing, deduplication, budgets, agreement counting, contradiction
   candidates and citation validation are plain Python. The LLM (optional) plans, extracts claims, adjudicates
   candidate contradictions, generates insights and writes prose. Every LLM output is schema-validated and
   checked against the evidence, and the deterministic implementation is the fallback.
2. **Provenance everywhere.** Every source records its origin (`live_search`, `cache`, `user_upload`, `demo`),
   retrieval method and date, whether the full text was reviewed, and its limitations. Claims keep an exact quote
   and passage location.
3. **Honesty over fluency.** Demo content is always labelled synthetic. Unconfigured providers are reported as
   unavailable, never simulated. Citation traceability is kept distinct from factual verification.
4. **Bounded.** Iterations, searches, sources, wall-clock time, LLM calls and tokens are capped per run.

## Layers

```
app.py, pages/            Streamlit UI (8 pages). Research runs in a worker thread and reports through a queue
src/orchestration/        LangGraph StateGraph, typed state, budget tracker
src/agents/               planner, retriever, source_evaluator, critical_analyst, gap_analyst,
                          insight_generator, report_builder (graph nodes) + qa (follow-up Q&A)
src/search/               provider interface; Tavily, OpenAlex, Crossref, arXiv, demo corpus, uploads;
                          HTTP retries and SSRF-safe fetching
src/ingestion/            PDF/TXT/MD/CSV/HTML extraction, location-preserving chunking
src/evidence/             evidence store (normalisation, dedup, syndication links), citations
src/analysis/             text heuristics, claim extraction/validation, evidence matrix & contradictions
src/retrieval/            BM25 index (Retriever interface)
src/reporting/            Markdown / sanitised HTML / PDF export
src/database/             SQLite schema + repository (runs, evidence, documents, cache, settings)
src/services/             research service (wires everything), LLM client
src/models/               Pydantic models: request/plan, evidence, run bundle
```

## The LangGraph workflow

```
START → planner → retriever → source_evaluator → critical_analyst → gap_analyst
                                   ↑                                   │
                                   └─────── follow_up_retrieval ◄── follow_up
                                                                       │ synthesize
                                          insight_generator → report_builder → END
```

- **State** (`orchestration/state.py`) is a `TypedDict` of Pydantic objects: request, budget, plan, iteration,
  pending/searched queries, sources, passages, assessments, claims, evidence matrix, links, contradictions,
  gaps, insights, report, agent statuses, usage, route decision. The audit-trail channels (events, search log,
  warnings, errors) use an `add` reducer.
- **Routing** comes from `gap_analyst.decide_route`, a pure, unit-tested function. It returns `synthesize` when
  the iteration limit is reached, the search/source/time budget is exhausted, no gap has
  `expected_value ≥ 0.35`, or the previous follow-up round found no new sources (diminishing returns).
  Otherwise it returns `follow_up` with targeted queries for the most valuable gaps.
- **Plan adaptation**: the gap agent can add a subquestion to investigate a contested claim (the plan version
  and revision note are recorded).
- **Failure handling**: each node is wrapped. An exception becomes an `errors` entry and a `failed` status,
  the evidence gathered so far is preserved, and the run continues to a report that lists the error.
- **Concurrency**: searches within a retrieval round, full-page fetches, and per-source LLM claim extraction
  run in thread pools. Graph nodes run sequentially because they depend on each other.

## Agents (inputs → outputs)

| Agent | Reads | Writes | LLM? |
|---|---|---|---|
| Planner | request | plan, pending_queries | optional (validated `PlanDraft`) |
| Retriever | pending_queries, sources | sources, passages, search_log | no |
| Source Evaluation | sources, plan | assessments | no (transparent heuristics) |
| Critical Analysis | sources, passages, assessments, plan | claims, matrix, links, contradictions | optional (verbatim-quote check, contradiction adjudication) |
| Gap & Follow-up | plan, claims, matrix, budget | gaps, plan revisions, route, pending_queries | no |
| Insight Generation | claims, matrix, contradictions | insights (observed / inferred / speculative) | optional (claim ids must exist) |
| Report Builder | everything | report + citation checks | optional (prose rewrite; markers and numbers validated) |
| Research Q&A | stored run bundle | answer with citations | optional (cited ids must be in retrieved set) |

## Evidence integrity

- **Deduplication**: same canonical URL (tracking parameters stripped), same DOI/document id, same content
  hash, or a near-identical long title from the same publisher → one source.
- **Syndication**: near-duplicate content from different publishers is kept but linked (`related_ids`). The copy
  is identified by citation link, publication date and source type, and flagged `repeats_other_source`.
  Agreement counts *independent groups*, so repeated copies never look like corroboration.
- **Claims**: heuristic extraction picks assertive sentences. LLM-proposed claims are accepted only if the
  quote is found verbatim in a passage.
- **Matrix**: claims are clustered by overlap of non-common terms. The majority polarity counts as supporting,
  the minority as contradicting. Agreement levels are strong (≥3 independent), moderate (2), single source,
  mixed and contested.
- **Contradictions**: opposite polarity between independent sources, or numeric disagreement between figures
  of the same kind (share vs share, change vs change) with similar context. Heuristic contradictions are
  labelled as such. In live mode the LLM reviews each candidate and may dismiss it.
- **Citations**: the report numbers sources in order of first use. Validation checks that the source exists,
  the reference matches the record, the cited passage is lexically relevant to the citing sentence, and the
  marker renders. Invalid markers in LLM prose are removed, and prose that adds numbers not present in the
  evidence is rejected.

## Retrieval choice

BM25 is used for ranking passages, matching claims to subquestions, searching the demo corpus and uploads,
and Q&A. Research questions hinge on exact terms (product names, metrics, methods), and BM25 is offline,
deterministic and testable. A vector store (ChromaDB) was deliberately not added. It can be introduced
behind the `Retriever` protocol if paraphrase-heavy corpora require it.

## Security

- Retrieved and uploaded content is wrapped in `<untrusted_source>` tags for every LLM call, and the system
  policy forbids following instructions inside it. Instruction-like text is detected, excluded from claims,
  and the source is down-weighted.
- Agents have no general tools: they can call only the configured search APIs and fetch public `http(s)`
  pages from search results through `safe_fetch`. That function blocks private, loopback, link-local and
  metadata addresses, disables automatic redirects (each hop is re-checked), and caps size and content type.
- HTML export escapes all source markup before Markdown conversion.
- Secrets come only from `.env`. The settings table refuses keys that look like secrets, and the UI shows only
  masked status.
- Upload limits: file types, 15 MB, 300 PDF pages, 400k characters, 2,000 CSV rows.

## Persistence

SQLite (`data/research.db`, git-ignored). `runs` holds request, plan, usage, statuses and summary. Per-run
tables (`sources`, `passages`, `assessments`, `claims`, `matrix_rows`, `evidence_links`, `contradictions`,
`gaps`, `insights`, `reports`, `events`, `search_log`, `qa_messages`) cascade on delete. `documents`,
`search_cache` (24 h TTL) and `settings` are global. Source ids are stable hashes of canonical URL or DOI,
so the same source keeps the same id across runs.
