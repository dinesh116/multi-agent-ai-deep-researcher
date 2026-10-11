# Plan: durable run execution and checkpointed workflow

Status: Phase 0 and Phase 1 implemented on `feature/run-jobs`; Phases 2–5 pending.

## Problem

Research runs execute in a thread started by the "Agents in action" page, which blocks in a polling loop while
the thread works. Progress lives only in that page's memory, and results are written once at the end. Consequences:
a user who navigates away or reconnects cannot reattach; there is no cancellation and no limit on concurrent runs;
and `mark_stale_runs()` failed *every* running row whenever any app process started, which kills live runs on other
instances sharing a Turso database. The LangGraph workflow has no checkpointer, so a run cannot resume after a
process restart and cannot pause for human input.

## Decision: in-process job runner behind an interface

The target host is Streamlit Community Cloud (single process, no separate worker service). Runs therefore execute
in one bounded, process-wide executor (`RunManager`), and **all progress is persisted** so pages only submit work
and read progress from the database. The `RunManager` interface allows an external worker later without changing
pages or agents.

Run lifecycle:

```
queued → running ⇄ awaiting_input → completed
            ↓              ↓
       cancelling →   cancelled          interrupted (process died) → [Resume] → running
            ↓
          failed
```

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Baseline tests; verify checkpoint serialisation of Pydantic state | Done |
| 1 | Persist progress incrementally: run heartbeat/progress/cancel columns, buffered event sink, heartbeat-based stale-run reaping | Done |
| 2 | `RunManager`: bounded executor, per-user and global limits, queued state, cooperative "stop & write report" cancel | Pending |
| 3 | DB-driven progress page (`st.fragment(run_every=…)`), reattach from sidebar/library, Stop button | Pending |
| 4 | `RepositoryCheckpointSaver` (SQLite + Turso), id-merging reducers, `RunBudget.restore`, Resume for interrupted runs | Pending |
| 5 | Optional plan review via `interrupt()`; paused runs release their worker slot | Pending |

## Phase 0 findings

- Baseline: 153 tests pass. One parametrised test produced a test id longer than Windows allows in
  `PYTEST_CURRENT_TEST`; it now uses short ids.
- `langgraph-checkpoint==4.2.0` `JsonPlusSerializer` round-trips every state channel (request, plan, sources,
  passages, assessments, claims, matrix, report, statuses, usage, search log, gaps, insights, charts) exactly; a
  full demo state is about 150 KB. Deserialising our classes currently logs "unregistered type … will be blocked in
  a future version", so Phase 4 must pass an explicit `allowed_msgpack_modules` list of `(module, class)` pairs for
  `src.models.*` and `src.orchestration.state` rather than relying on the default.

## Phase 1 design (implemented)

- `runs` gains `worker_id`, `heartbeat_at`, `cancel_requested` and `progress` (JSON) columns via additive migration,
  plus an index on `(status, heartbeat_at)`.
- `src/services/run_events.py`: `ProgressTracker` derives per-agent status from events (shared by the worker and
  the page); `EventSink` assigns sequence numbers, buffers events and writes them in batches (every
  `RUN_EVENT_FLUSH_SECONDS` or 20 events) together with progress and a heartbeat. A background heartbeat keeps
  long, silent steps (an LLM call) from looking stale.
- Repository: `append_events`, `update_progress`, `get_progress`, `request_cancel`, `is_cancel_requested`,
  `count_active_runs`, `reap_stale_runs`. `reap_stale_runs` replaces `mark_stale_runs` and only fails runs whose
  heartbeat is older than `RUN_STALE_AFTER_SECONDS`.
- `save_run_results` no longer rewrites events that the sink already persisted.

## Risks

- Turso write volume: batched event writes; checkpoints deleted after completion (Phase 4).
- Process restarts: heartbeat reaping now; `interrupted` + Resume in Phase 4.
- A resumed node restarts from its beginning; the 24 h search cache and restored budget bound the cost.
