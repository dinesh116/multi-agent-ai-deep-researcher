"""Agent F: Research Gap & Follow-up. Finds gaps, proposes targeted queries, and decides whether to continue.

The continue/stop decision is deterministic and explained. Research stops when:
  1. the iteration limit is reached, or
  2. the search, source or time budget is exhausted, or
  3. the completion criteria are met (no gap worth pursuing), or
  4. the previous follow-up round found no new sources (diminishing returns).
"""
from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from src.agents.base import Agent, RunContext
from src.agents.planner import topic_phrase
from src.analysis.text import STOPWORDS, truncate
from src.evidence.store import EvidenceStore
from src.models.evidence import Agreement, EvidenceQuality, Freshness, GapKind, ResearchGap
from src.models.research import SubQuestion, SubQuestionStatus
from src.orchestration.state import QueryTask, ResearchState

PRIORITY_WEIGHT = {1: 1.0, 2: 0.8, 3: 0.6}
VALUE_THRESHOLD = 0.35
MODIFIERS = {
    GapKind.UNANSWERED: ["evidence", "report data"],
    GapKind.THIN: ["study data", "independent analysis"],
    GapKind.SINGLE_SOURCE: ["independent study", "survey data"],
    GapKind.CONTESTED: ["criticism evidence", "comparison methodology"],
    GapKind.OUTDATED: ["{year}", "latest {year}"],
    GapKind.LOW_QUALITY: ["peer-reviewed study", "official report"],
    GapKind.UNCHALLENGED: ["criticism evidence against", "limitations failed study"],
}
BASE_VALUE = {GapKind.UNANSWERED: 0.9, GapKind.THIN: 0.7, GapKind.SINGLE_SOURCE: 0.65, GapKind.CONTESTED: 0.55,
              GapKind.OUTDATED: 0.45, GapKind.LOW_QUALITY: 0.45, GapKind.UNCHALLENGED: 0.45}
SOURCE_CHASE = re.compile(r"\b(?:according to|survey by|report by|study by|data from|analysis by)\s+"
                          r"((?:the\s)?[A-Z][\w&\-]+(?:\s+[A-Z][\w&\-]+){0,4})")
QUERY_KINDS = {"gap", "original_source", "contradiction", "entity", "counter_evidence", "data", "definition"}


class StrategyQuery(BaseModel):
    subquestion_id: str | None = None
    query: str
    kind: str = "gap"
    rationale: str = ""


class StrategyPlan(BaseModel):
    queries: list[StrategyQuery] = Field(default_factory=list, max_length=12)


def clean_query(query: str) -> str:
    """Drop repeated words ("evidence evidence") while keeping order."""
    seen, words = set(), []
    for word in query.split():
        if word.lower() not in seen:
            seen.add(word.lower())
            words.append(word)
    return " ".join(words)


def key_terms(text: str, limit: int = 5) -> str:
    return " ".join(list(dict.fromkeys(w for w in tokenize_plain(text)))[:limit])


def tokenize_plain(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower()) if w not in STOPWORDS]


def _gap_id(*parts: str) -> str:
    return "gap_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def decide_route(iteration: int, max_iterations: int, budget_exhausted: list[str], gaps: list[ResearchGap],
                 new_sources_last_iteration: int) -> tuple[str, str]:
    """Pure function: returns ("follow_up" | "synthesize", reason)."""
    if iteration >= max_iterations:
        return "synthesize", f"Iteration limit reached ({max_iterations} follow-up round(s))."
    hard = [b for b in budget_exhausted if b in ("searches", "time", "sources")]
    if hard:
        return "synthesize", f"Research budget exhausted ({', '.join(hard)})."
    worthwhile = [g for g in gaps if not g.resolved and g.expected_value >= VALUE_THRESHOLD and g.follow_up_queries]
    if not worthwhile:
        return "synthesize", "Completion criteria met: no remaining gap is likely to change the conclusions."
    if iteration > 0 and new_sources_last_iteration == 0:
        return "synthesize", "Diminishing returns: the last follow-up round found no new sources."
    return "follow_up", f"{len(worthwhile)} gap(s) worth pursuing; starting follow-up round {iteration + 1}."


class GapAnalystAgent(Agent):
    name = "gap_analyst"
    title = "Research Gap & Follow-up"
    responsibility = "Identifies unanswered or weakly supported subquestions and decides whether more research is worthwhile."

    def run(self, state: ResearchState, ctx: RunContext) -> dict:
        plan = state["plan"].model_copy(deep=True)
        iteration = state.get("iteration", 0)
        budget = state["budget"]
        store = EvidenceStore(state.get("sources", []), state.get("passages", []))
        assessments = state.get("assessments", {})
        rows = state.get("matrix", [])
        claims = state.get("claims", [])
        searched = {q.lower() for q in state.get("searched_queries", [])}
        year = ctx.today.year
        gaps: list[ResearchGap] = []

        for sq in plan.subquestions:
            # Evidence for a subquestion: claims matched to it, plus claim-bearing sources retrieved for it.
            claim_sources = {c.source_id for c in claims}
            source_ids = list(dict.fromkeys(
                [c.source_id for c in claims if c.subquestion_id == sq.id]
                + [s.id for s in store.sources.values() if sq.id in s.subquestion_ids and s.id in claim_sources
                   and assessments.get(s.id) and assessments[s.id].relevance >= 0.15]))
            independent = store.independent_count(source_ids) if source_ids else 0
            sq_rows = [r for r in rows if r.subquestion_id == sq.id]
            qualities = [assessments[s].evidence_quality for s in source_ids if s in assessments]
            fresh = [assessments[s].freshness for s in source_ids if s in assessments]

            if independent >= budget.min_sources_per_subquestion and any(
                    q in (EvidenceQuality.HIGH, EvidenceQuality.MEDIUM) for q in qualities):
                sq.status = SubQuestionStatus.ANSWERED
            elif independent:
                sq.status = SubQuestionStatus.PARTIAL
            else:
                sq.status = SubQuestionStatus.OPEN

            kinds: list[tuple[GapKind, str]] = []
            if independent == 0:
                kinds.append((GapKind.UNANSWERED, "No evidence has been found yet."))
            elif independent == 1:
                kinds.append((GapKind.SINGLE_SOURCE, "Evidence depends on a single independent source."))
            elif independent < budget.min_sources_per_subquestion:
                kinds.append((GapKind.THIN, f"Only {independent} independent sources."))
            if any(r.agreement in (Agreement.CONTESTED, Agreement.MIXED) for r in sq_rows):
                kinds.append((GapKind.CONTESTED, "Sources disagree on at least one claim."))
            if fresh and all(f == Freshness.DATED for f in fresh):
                kinds.append((GapKind.OUTDATED, "All evidence is more than three years old."))
            if qualities and all(q == EvidenceQuality.LOW for q in qualities):
                kinds.append((GapKind.LOW_QUALITY, "Only low-quality evidence (opinion, unsourced or flagged)."))

            for kind, description in kinds:
                queries = self._follow_up_queries(sq, kind, searched, year)
                value = BASE_VALUE[kind] * PRIORITY_WEIGHT[sq.priority]
                if iteration > 0 and state.get("new_sources_last_iteration", 0) < 2:
                    value *= 0.6  # recent rounds added little: lower the expected value of more searching
                gaps.append(ResearchGap(
                    id=_gap_id(sq.id, kind.value), subquestion_id=sq.id, kind=kind,
                    description=f"{sq.text}: {description}", follow_up_queries=queries, priority=sq.priority,
                    expected_value=round(value, 2), iteration=iteration))

        # Key findings nobody has tried to disprove yet: one counter-evidence search each (first round only).
        if iteration == 0:
            strong = sorted((r for r in rows if r.independent_sources >= 2 and not r.contradicting_claim_ids),
                            key=lambda r: -r.strength)[:2]
            for row in strong:
                terms = key_terms(row.claim)
                queries = [clean_query(f"{terms} {m}") for m in MODIFIERS[GapKind.UNCHALLENGED]
                           if clean_query(f"{terms} {m}").lower() not in searched]
                sq = plan.get(row.subquestion_id) if row.subquestion_id else None
                gaps.append(ResearchGap(
                    id=_gap_id(row.id, "unchallenged"), subquestion_id=row.subquestion_id, kind=GapKind.UNCHALLENGED,
                    description=f"Key finding not yet tested against counter-evidence: {truncate(row.claim, 140)}",
                    follow_up_queries=queries[:1], priority=sq.priority if sq else 2,
                    expected_value=round(BASE_VALUE[GapKind.UNCHALLENGED] * PRIORITY_WEIGHT[sq.priority if sq else 2], 2),
                    iteration=iteration))

        revision = self._adapt_plan(plan, rows, iteration)
        route, reason = decide_route(iteration, budget.max_iterations, ctx.budget.snapshot().exhausted, gaps,
                                     state.get("new_sources_last_iteration", 0))
        update = {"plan": plan, "gaps": gaps, "route": route, "route_reason": reason,
                  "usage": ctx.budget.snapshot(iteration)}
        if route == "follow_up":
            tasks = self._strategy_tasks(state, gaps, plan, ctx) if ctx.llm_enabled else None
            tasks = tasks or self._tasks(gaps, plan, ctx, state)
            if not tasks:
                route, reason = "synthesize", "No new follow-up queries could be formed (all variants already searched)."
                update.update(route=route, route_reason=reason)
            else:
                update.update(pending_queries=tasks, iteration=iteration + 1)
        if route == "synthesize":
            update["stop_reason"] = reason
        open_count = sum(1 for g in gaps if g.expected_value >= VALUE_THRESHOLD)
        ctx.event(self.name, "decision", f"{len(gaps)} gap(s), {open_count} worth pursuing. Decision: "
                  f"{'follow-up research' if route == 'follow_up' else 'synthesise'}: {reason}"
                  + (f" Plan revised: {revision}" if revision else ""), iteration, gaps=len(gaps), route=route)
        return update

    def _follow_up_queries(self, sq: SubQuestion, kind: GapKind, searched: set[str], year: int) -> list[str]:
        base = sq.queries[0]
        core = " ".join(w for w in base.split() if w.lower() not in {"or", "and"})
        out = []
        for modifier in MODIFIERS[kind]:
            query = clean_query(f"{core} {modifier.format(year=year)}".strip())
            if query.lower() not in searched:
                out.append(query)
        return out[:2]

    def _limit(self, ctx: RunContext) -> int:
        remaining = ctx.budget.budget.max_searches - ctx.budget.snapshot().searches
        providers = max(1, min(2, len([p for p in ctx.providers.providers if p.name != "upload"])))
        return max(0, min(remaining // providers, 10))

    def _tasks(self, gaps: list[ResearchGap], plan, ctx: RunContext, state: ResearchState | None = None) -> list[QueryTask]:
        """Deterministic follow-up: gap queries, then source-chasing and recurring-entity queries."""
        tasks, seen = [], {q.lower() for q in (state or {}).get("searched_queries", [])}

        def add(query: str, sq_id: str | None, purpose: str) -> None:
            query = clean_query(query)
            if query.lower() not in seen and len(query.split()) >= 2:
                seen.add(query.lower())
                sq = plan.get(sq_id) if sq_id else None
                tasks.append(QueryTask(subquestion_id=sq_id, query=query[:200], purpose=purpose,
                                       source_types=sq.source_types if sq else []))

        for gap in sorted(gaps, key=lambda g: -g.expected_value):
            if gap.expected_value >= VALUE_THRESHOLD:
                for query in gap.follow_up_queries:
                    add(query, gap.subquestion_id, "follow_up" if gap.kind != GapKind.UNCHALLENGED else "counter_evidence")
        if state:
            topic = " ".join(topic_phrase(plan.question).split()[:4])
            for claim in state.get("claims", []):  # chase original sources named in secondary reporting
                match = SOURCE_CHASE.search(claim.quote)
                if match and len(match.group(1)) > 3:
                    add(f"{match.group(1)} report {topic}", claim.subquestion_id, "original_source")
            for entity in state.get("entities", [])[:4]:  # research recurring organisations/products directly
                if entity.kind in ("company", "product", "technology", "organisation") and len(entity.source_ids) >= 2:
                    add(f"{entity.name} {topic}", None, "entity")
        # Reserve up to two slots for counter-evidence so strong findings are always tested, not crowded out.
        limit = self._limit(ctx)
        counter = [t for t in tasks if t.purpose == "counter_evidence"][:2]
        others = [t for t in tasks if t not in counter]
        return others[:max(0, limit - len(counter))] + counter[:limit]

    def _strategy_tasks(self, state: ResearchState, gaps: list[ResearchGap], plan, ctx: RunContext) -> list[QueryTask] | None:
        """LLM research strategy: follow-up searches that build on what has been found (validated)."""
        rows = sorted(state.get("matrix", []), key=lambda r: -r.strength)[:12]
        claims = {c.id: c for c in state.get("claims", [])}
        contradictions = state.get("contradictions", [])[:5]
        lines = ["Subquestions:"] + [f"- {s.id} [{s.status.value}] {s.text}" for s in plan.subquestions]
        lines += ["Gaps:"] + [f"- ({g.kind.value}, {g.subquestion_id}) {g.description}" for g in gaps[:10]]
        lines += ["Strongest findings so far:"] + [f"- [{r.agreement.value}] {truncate(r.claim, 200)}" for r in rows]
        lines += ["Contradictions:"] + [
            f"- \"{truncate(claims[c.claim_a_id].text, 120)}\" vs \"{truncate(claims[c.claim_b_id].text, 120)}\""
            for c in contradictions if c.claim_a_id in claims and c.claim_b_id in claims]
        lines += ["Recurring entities: " + ", ".join(e.name for e in state.get("entities", [])[:10])]
        lines += ["Already searched: " + "; ".join(state.get("searched_queries", [])[-30:])]
        limit = self._limit(ctx)
        prompt = (f"Research question: {plan.question}\n" + "\n".join(lines) +
                  f"\n\nPropose up to {limit} new search queries for the next research round that would most improve "
                  "the answer. Build on the findings: chase original sources behind secondary reports, resolve "
                  "contradictions (definitions, samples, dates), research recurring entities, look for counter-evidence "
                  "to strong findings, and find hard data. Queries must be short (3-10 words), specific and different "
                  "from those already searched. kind is one of: gap, original_source, contradiction, entity, "
                  "counter_evidence, data, definition. Return {\"queries\": [{\"subquestion_id\": ..., \"query\": ..., "
                  "\"kind\": ..., \"rationale\": ...}]}.")
        result = ctx.llm.structured(prompt, StrategyPlan, ctx.budget, max_tokens=1200)
        if not result:
            return None
        searched = {q.lower() for q in state.get("searched_queries", [])}
        valid_sq = {s.id for s in plan.subquestions}
        tasks, seen = [], set()
        for item in result.queries:
            query = re.sub(r"\s+", " ", item.query).strip()[:200]
            if not 2 <= len(query.split()) <= 14 or query.lower() in searched or query.lower() in seen:
                continue
            seen.add(query.lower())
            sq_id = item.subquestion_id if item.subquestion_id in valid_sq else None
            sq = plan.get(sq_id) if sq_id else None
            tasks.append(QueryTask(subquestion_id=sq_id, query=query,
                                   purpose=item.kind if item.kind in QUERY_KINDS else "gap",
                                   source_types=sq.source_types if sq else []))
        if tasks:
            ctx.event(self.name, "info", "LLM research strategy for the next round: " +
                      "; ".join(f"{t.purpose}: '{t.query}'" for t in tasks[:6]), state.get("iteration", 0))
        return tasks[:limit] or None

    def _adapt_plan(self, plan, rows, iteration: int) -> str:
        """Add one subquestion per round to investigate the most significant disagreement."""
        if len(plan.subquestions) >= 10:
            return ""
        contested = [r for r in rows if r.agreement == Agreement.CONTESTED and r.subquestion_id]
        existing = " ".join(s.text for s in plan.subquestions)
        for row in contested:
            topic = " ".join(row.claim.split()[:10])
            if topic[:40] in existing:
                continue
            parent = plan.get(row.subquestion_id)
            new_id = f"sq{len(plan.subquestions) + 1}"
            plan.subquestions.append(SubQuestion(
                id=new_id, text=f"Why do sources disagree about: \"{topic}…\"?", perspective="disagreement",
                priority=2, queries=[f"{parent.queries[0]} evidence disagreement" if parent else topic],
                source_types=["academic", "analyst", "official"],
                expected_evidence="Primary data or methodology that explains the disagreement",
                added_in_iteration=iteration))
            plan.version += 1
            note = f"v{plan.version}: added {new_id} to investigate a contested claim."
            plan.revisions.append(note)
            return note
        return ""
