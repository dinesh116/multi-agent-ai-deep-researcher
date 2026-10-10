"""Runs investigations end to end: providers → LangGraph workflow → persistence."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from src.agents.base import RunContext
from src.config import Settings
from src.models.evidence import AgentEvent, AgentStatus
from src.models.research import ResearchMode, ResearchRequest, is_demo_question, new_id
from src.orchestration.budget import RunBudget
from src.orchestration.graph import build_graph
from src.orchestration.state import AGENT_ORDER, ResearchState
from src.search.registry import ProviderSettings, build_providers
from src.services.llm import LLMClient
from src.services.observability import research_trace

logger = logging.getLogger(__name__)


def initial_state(request: ResearchRequest, run_id: str) -> ResearchState:
    return ResearchState(
        run_id=run_id, request=request, budget=request.budget(), plan=None, iteration=0, pending_queries=[],
        searched_queries=[], sources=[], passages=[], assessments={}, claims=[], extracted_source_ids=[], matrix=[],
        links=[], contradictions=[], gaps=[], insights=[], charts=[], visualization_notes=[], report=None,
        statuses={a: AgentStatus(agent=a) for a in AGENT_ORDER}, route="", route_reason="", stop_reason="",
        new_sources_last_iteration=0, provider_notes=[], events=[], search_log=[], warnings=[], errors=[])


@research_trace
def run_research(request: ResearchRequest, settings: Settings, repo=None, on_event: Callable[[AgentEvent], None] | None = None,
                 provider_settings: ProviderSettings | None = None, llm: LLMClient | None = None,
                 uploaded_documents: list[dict] | None = None, today: date | None = None,
                 run_id: str | None = None, providers=None, owner_id: str = "local") -> ResearchState:
    """Execute one investigation. Persists the run (if `repo` is given) and returns the final state."""
    if owner_id.startswith("guest:") and request.mode == ResearchMode.LIVE:
        raise PermissionError("Live research requires signing in. Guests can use demo mode.")
    if request.mode == ResearchMode.DEMO and not is_demo_question(request.question):
        raise ValueError("Demo mode only runs the preselected demo questions. Sign in and use live research for "
                         "your own question.")
    run_id = run_id or new_id("run")
    provider_settings = provider_settings or ProviderSettings()
    documents = uploaded_documents
    if documents is None and repo is not None and request.document_ids:
        documents = repo.get_documents(request.document_ids, owner_id)  # only the owner's own documents
    providers = providers or build_providers(settings, request.mode, {p.value for p in request.source_preferences},
                                             documents or [], provider_settings)
    if llm is None and request.use_llm and request.mode == ResearchMode.LIVE:
        llm = LLMClient(settings)
    budget = RunBudget(request.budget())
    events: list[AgentEvent] = []

    def emit(event: AgentEvent) -> None:
        events.append(event)
        if on_event:
            on_event(event)

    ctx = RunContext(settings=settings, budget=budget, providers=providers, llm=llm,
                     use_llm=request.use_llm and request.mode == ResearchMode.LIVE, cache=repo, emit=emit,
                     today=today or date.today(), provider_settings=provider_settings)
    state = initial_state(request, run_id)
    state["provider_notes"] = providers.notes
    for note in providers.notes:
        ctx.event("orchestrator", "info", note)
    if request.mode == ResearchMode.LIVE and not providers.providers:
        ctx.event("orchestrator", "info", "No search provider is available, so no live research can run. "
                                          "The report will state that no evidence was gathered.")
    if ctx.use_llm and not ctx.llm_enabled:
        ctx.event("orchestrator", "info", "OPENROUTER_API_KEY is not configured: agents use deterministic logic only.")
    if repo is not None:
        repo.create_run(run_id, request, owner_id)
        repo.log_activity(owner_id, "run_started", run_id, {"question": request.question, "mode": request.mode.value,
                                                           "depth": request.depth.value})

    graph = build_graph(ctx)
    final: ResearchState = dict(state)
    try:
        for update in graph.stream(state, stream_mode="updates", config={"recursion_limit": 100,
                "run_name": "research-investigation", "tags": ["deep-researcher", request.mode.value],
                "metadata": {"research_run_id": run_id, "mode": request.mode.value, "depth": request.depth.value}}):
            for node_output in update.values():
                for key, value in (node_output or {}).items():
                    if key in ("events", "search_log", "warnings", "errors"):
                        final[key] = final.get(key, []) + list(value)
                    else:
                        final[key] = value
        status = "completed" if final.get("report") else "failed"
    except Exception as exc:  # the graph itself failed: keep whatever evidence exists
        logger.exception("Research run failed")
        final["errors"] = final.get("errors", []) + [f"Workflow error: {type(exc).__name__}: {str(exc)[:200]}"]
        status = "failed"
    final["usage"] = budget.snapshot(final.get("iteration", 0))
    ctx.event("orchestrator", "completed" if status == "completed" else "failed",
              f"Research {status} in {final['usage'].elapsed_seconds}s.")
    final["events"] = events
    if repo is not None:
        repo.save_run_results(run_id, final, status, owner_id)
        repo.log_activity(owner_id, "run_completed" if status == "completed" else "run_failed", run_id,
                          {"sources": len(final.get("sources", [])), "seconds": final["usage"].elapsed_seconds})
    return final
