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
app.py, app_pages/        Streamlit UI (welcome and five task pages). Pages submit research to the job runner and poll its progress from the database
src/orchestration/        LangGraph StateGraph, typed state, budget tracker
src/agents/               planner, retriever, source_evaluator, critical_analyst, gap_analyst,
                          insight_generator, data_visualizer, report_builder (eight graph agents) + qa (follow-up Q&A)
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
                                          insight_generator → data_visualizer → report_builder → END
```

- **State** (`orchestration/state.py`) is a `TypedDict` of Pydantic objects: request, budget, plan, iteration,
  pending/searched queries, sources, passages, assessments, claims, evidence matrix, links, contradictions,
  gaps, insights, charts, visualization_notes, report, agent statuses, usage, route decision. The audit-trail channels (events, search log,
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
| Data Visualization | CSV metadata, passages, claims | charts, extraction notes | no (deterministic provenance checks) |
| Report Builder | everything | report + citation checks | optional (prose rewrite; markers and numbers validated) |
| Research Q&A | stored run bundle | answer with citations | optional (cited ids must be in retrieved set) |

## Evidence integrity

- **Deduplication**: same canonical URL (tracking parameters stripped), same DOI/document id, same content
  hash, or a near-identical long title from the same publisher → one source.
- **Syndication**: near-duplicate content from different publishers is kept but linked (`related_ids`). The copy
  is identified by citation link, publication date and source type, and flagged `repeats_other_source`.
  Agreement counts *independent groups*, so repeated copies never look like corroboration.
- **Claims**: heuristic extraction picks assertive sentences. LLM-proposed claims are accepted only if the
  quote is found verbatim in a passage, numeric/unit/negation/forecast/uncertainty checks pass, and the canonical text is the quotation.
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
- Secrets come from `.env` or deployed Streamlit Secrets. The settings table refuses keys that look like secrets, and the UI shows only
  masked status.
- Upload limits: file types, 15 MB, 300 PDF pages, 400k characters, 2,000 CSV rows.

- Production defaults to requiring Google authentication and stops before opening shared storage if authentication
  is missing, unreadable or incomplete. Only explicit `APP_ENV=local` permits a local administrator.
- Evidence-derived matrices and report drafts are wrapped as untrusted input. Report rewrites must preserve their
  citation-marker sets, contradiction verdicts are restricted to supported values, and unknown insight IDs are rejected.
  Prompt boundaries reduce injection risk; they are not a guarantee of complete prevention.

## Persistence

SQLite (`data/research.db`, git-ignored). `runs` holds request, plan, usage, statuses and summary. Per-run
tables (`sources`, `passages`, `assessments`, `claims`, `matrix_rows`, `evidence_links`, `contradictions`,
`gaps`, `insights`, `charts`, `reports`, `events`, `search_log`, `qa_messages`) cascade on delete. `documents` are owner-scoped, as are runs and their children; `search_cache` (24 h TTL) is shared, while settings are scoped according to the repository API. Source ids are stable hashes of canonical URL or DOI,
so the same source keeps the same id across runs.

## Run execution

`services/jobs.RunManager` is a process-wide job runner (one per app process, created with `st.cache_resource`).
`submit` validates the request, enforces per-user (`MAX_ACTIVE_RUNS_PER_USER`) and overall (`MAX_QUEUED_RUNS`)
limits counted in the database, creates a `queued` run and returns its id at once. A fixed pool of
`MAX_CONCURRENT_RUNS` daemon worker threads claims queued runs (`queued → running`) and executes the workflow. Run
states are `queued`, `running`, `completed`, `cancelled` and `failed`. Pages never execute research: the progress page
polls the database in an `st.fragment(run_every=…)`, so any session can reattach to a run.

Stopping is cooperative. A queued run is cancelled at once. For a running run the stop flag is stored, and the
budget is cancelled: no further searches or LLM calls, `decide_route` routes to synthesis, and the remaining agents
write a partial report from the evidence gathered so far with deterministic logic; the run ends as `cancelled`. In
the same process the budget is cancelled immediately; from another instance the flag arrives with the worker's next
progress write. A maintenance thread heartbeats this process's queued runs, reaps abandoned ones and purges old guest
data. Active runs cannot be deleted from the library; "Delete my data" stops them first, and a run deleted while it
executed is not re-created by its final save.

Run execution is observable while it happens: `services/run_events.EventSink` numbers each agent event,
buffers it and writes batches (with a progress snapshot and a heartbeat on `runs`) so any session can read progress
with `Repository.get_progress`. Startup reaps only runs whose heartbeat is older than `RUN_STALE_AFTER_SECONDS`, so a
restart never fails live runs on other instances sharing the database. See `docs/plans/run-execution.md` for the
remaining phases (checkpoints and resume, plan review).

## Upgrade contracts

Charts are persisted as validated JSON in a run-owned `charts` table and cascade on run deletion. Source row metadata is stored with uploaded documents; visualization notes are stored with runs. Additive migrations preserve existing databases, and old runs load with empty chart defaults. Existing uploads without structured metadata must be uploaded again. CSV extraction limits remain in force. Both SQLite and the local libSQL backend have persistence and ownership tests; hosted Turso connectivity is not established by those tests.

The chart extractor produces a series only within a single source and compatible unit. Each point must resolve to an exact stored passage quotation. It does not perform joins, currency conversion, inferred data filling, or automatic chart extraction from PDF/web tables. Narrative percentages remain individual indicators, preserving their source wording and synthetic status.

The budget tracker reserves estimated tokens under a lock before each API attempt, counts retries against actual request limits, releases successful reservations into reported usage, and retains unknown usage conservatively. Costs use explicitly configured input/output rates. This is per-run accounting; concurrency is bounded separately by the job runner (see Run execution). HTTP fetches already in progress are bounded by HTTP timeouts rather than forcibly cancelled at the run deadline.

See `docs/deployment.md` for the hosted workflow checklist and `docs/security.md` for the authentication and trust-boundary controls.

## Configurable LangSmith observability

`src/services/observability.py` provides optional request spans, an explicit research tracing context and worker helpers that copy `contextvars` separately for each submitted job. `research_service.py` gives the graph its `research-investigation` name and research run ID, mode and depth metadata. The LLM retry loop traces each actual attempt; provider/HTTP operations and page-fetch hops have nested spans. Existing budgets and persistence contracts remain in control.

`LANGSMITH_TRACING=false` disables research tracing; `APP_API_TRACING=false` retains graph tracing while disabling application request spans. Default graph input/output hiding and metadata-only custom spans limit exported content, but graph errors and metadata require separate review. Tracing setup/cleanup exceptions are isolated; failure behavior still requires runtime verification.

See [observability.md](observability.md) for configuration, span contracts, usage interpretation and the current verification record. The local user screenshots confirm agent/model/provider/HTTP traces, not exhaustive parallel-context or retry correctness.
