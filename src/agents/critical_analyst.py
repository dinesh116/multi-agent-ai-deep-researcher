"""Agent D: Critical Analysis.

Per source it extracts claims, quantitative data points and named entities. In live mode it reads whole
documents in windows, using the fast model, with the most relevant sources first. Every LLM quote is checked
verbatim against the passage. It then:
- verifies that LLM restatements are faithful to their quotes (fast model),
- groups claims by proposition with the LLM (semantic agreement), falling back to lexical clustering,
- builds the evidence matrix with quality-weighted strength,
- records contradictions (stance-based and numeric). Heuristic candidates are adjudicated by the LLM.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from src.agents.base import Agent, RunContext
from src.analysis.claims import (ClaimDraftList, ExtractionDraft, SubquestionMatcher, heuristic_claims,
                                 validate_llm_claims, validate_llm_data_points)
from src.analysis.datapoints import _id, entity_kind, heuristic_data_points, heuristic_entities, is_named_entity
from src.analysis.matrix import build_matrix
from src.analysis.text import truncate
from src.evidence.store import EvidenceStore
from src.models.evidence import Claim, DataPoint, Entity, Passage, Source
from src.orchestration.state import ResearchState
from src.services.llm import wrap_untrusted

WINDOW_CHARS = 6000
MAX_GROUPING_CLAIMS = 140


class Verdict(BaseModel):
    index: int
    verdict: str
    explanation: str = ""


class Verdicts(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


class ClaimGroup(BaseModel):
    proposition: str
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)


class ClaimGroups(BaseModel):
    groups: list[ClaimGroup] = Field(default_factory=list)


def windows(passages: list[Passage], size: int = WINDOW_CHARS) -> list[list[Passage]]:
    """Split a document's passages into consecutive windows of roughly `size` characters."""
    out, current, length = [], [], 0
    for passage in passages:
        if current and length + len(passage.text) > size:
            out.append(current)
            current, length = [], 0
        current.append(passage)
        length += len(passage.text)
    if current:
        out.append(current)
    return out


class CriticalAnalystAgent(Agent):
    name = "critical_analyst"
    title = "Critical Analysis"
    responsibility = ("Extracts claims, numbers and entities linked to exact passages, compares them across independent "
                      "sources, and flags contradictions, weak methods and overstated conclusions.")
    uses_llm = "optional"

    def run(self, state: ResearchState, ctx: RunContext) -> dict:
        plan, request = state["plan"], state["request"]
        store = EvidenceStore(state.get("sources", []), state.get("passages", []))
        assessments = state.get("assessments", {})
        done = set(state.get("extracted_source_ids", []))
        matcher = SubquestionMatcher(plan)
        per_source = request.preset("claims_per_source")
        todo = [s for s in store.sources.values() if s.id not in done
                and "low_relevance" not in (assessments[s.id].flags if s.id in assessments else [])]
        todo.sort(key=lambda s: -(assessments[s.id].relevance if s.id in assessments else 0))
        claims: list[Claim] = list(state.get("claims", []))
        points: list[DataPoint] = list(state.get("data_points", []))
        llm_entities: list[tuple[str, str, str]] = []  # (name, kind, source_id)
        notes: list[str] = []
        rejected_claims = rejected_points = 0

        llm_results: dict[str, tuple[list[Claim], list[DataPoint]]] = {}
        if ctx.llm_enabled and todo:
            jobs = [(s, w) for s in todo
                    for w in windows(store.passages.get(s.id, []))[:request.preset("llm_windows_per_source")]]
            with ThreadPoolExecutor(max_workers=ctx.max_parallel) as pool:
                for source, window, result in pool.map(lambda j: (j[0], j[1], self._llm_extract(j[0], j[1], plan, ctx)),
                                                       jobs):
                    if result is None:
                        continue
                    new_claims, new_points, entities, rc, rp = self._validate(result, source, window, matcher)
                    rejected_claims, rejected_points = rejected_claims + rc, rejected_points + rp
                    bucket = llm_results.setdefault(source.id, ([], []))
                    bucket[0].extend(new_claims)
                    bucket[1].extend(new_points)
                    llm_entities += [(e.name, e.kind, source.id) for e in entities]
        if rejected_claims or rejected_points:
            notes.append(f"Rejected {rejected_claims} claim(s) and {rejected_points} data point(s) proposed by the LLM "
                         "because their quotes were not found verbatim in the source.")

        existing_claims, existing_points = {c.id for c in claims}, {p.id for p in points}
        for source in todo:
            passages = store.passages.get(source.id, [])
            if source.id in llm_results:
                new_claims, new_points = llm_results[source.id]
            else:
                new_claims = heuristic_claims(source, passages, plan, matcher, limit=per_source)
                new_points = heuristic_data_points(source, passages)
            for claim in new_claims[:per_source + 4]:
                if claim.id not in existing_claims:
                    existing_claims.add(claim.id)
                    claims.append(claim)
            for point in new_points:
                if point.id not in existing_points:
                    existing_points.add(point.id)
                    points.append(point)

        if ctx.llm_enabled:
            self._verify_claims([c for c in claims if c.extracted_by == "llm" and c.verified is None], ctx)

        groups = self._llm_groups(claims, ctx) if ctx.llm_enabled else None
        rows, links, contradictions = build_matrix(
            claims, store, assessments, heuristic=not ctx.llm_enabled, groups=groups,
            grouped_by="llm" if groups is not None else "heuristic")
        if ctx.llm_enabled and contradictions and groups is None:
            contradictions, dismissed = self._adjudicate(contradictions, {c.id: c for c in claims}, ctx)
            if dismissed:
                notes.append(f"LLM review dismissed {dismissed} candidate contradiction(s) as compatible statements.")
        entities = self._entities(claims, store, llm_entities, state.get("entities", []))

        contested = sum(r.agreement.value in ("contested", "mixed") for r in rows)
        corroborated = sum(r.independent_sources >= 2 for r in rows)
        ctx.event(self.name, "completed",
                  f"{len(claims)} claims, {len(points)} data points and {len(entities)} entities; {len(rows)} evidence "
                  f"rows ({corroborated} corroborated, {contested} contested/mixed); {len(contradictions)} contradiction(s)."
                  + (" Claims grouped by meaning with the LLM." if groups is not None else ""),
                  state.get("iteration", 0), claims=len(claims), rows=len(rows), contradictions=len(contradictions),
                  data_points=len(points))
        return {"claims": claims, "data_points": points, "entities": entities, "matrix": rows, "links": links,
                "contradictions": contradictions, "extracted_source_ids": list(done | {s.id for s in todo}),
                "warnings": sorted(set(notes))}

    # ------------------------------------------------------------------ LLM extraction
    def _llm_extract(self, source: Source, window: list[Passage], plan, ctx: RunContext) -> ExtractionDraft | None:
        text = "\n\n".join(f"[{p.location}] {p.text}" for p in window)
        prompt = (f"Research question: {plan.question}\nSubquestions: "
                  + "; ".join(f"{s.id}: {s.text}" for s in plan.subquestions)
                  + "\n\nFrom the source text below, extract:\n"
                    "1. claims: specific, checkable claims relevant to the research question (copy the supporting "
                    "sentence EXACTLY into 'quote'; set sceptical=true if the claim doubts or limits a premise);\n"
                    "2. data_points: every quantitative fact (percentages, money, multiples, counts, durations) with "
                    "the exact sentence as 'quote', what is measured, the population or sample, period and method;\n"
                    "3. entities: specific NAMED organisations, products and regulations (proper nouns such as company, "
                    "product or law names), not generic concepts like 'generative AI' or 'financial institutions'.\n"
                    "Return {\"claims\": [...], \"data_points\": [...], \"entities\": [...]}.\n\n"
                  + wrap_untrusted(source.id, text[:WINDOW_CHARS + 500]))
        return ctx.llm.structured(prompt, ExtractionDraft, ctx.budget, max_tokens=2200, fast=True)

    @staticmethod
    def _validate(result: ExtractionDraft, source: Source, window: list[Passage], matcher):
        claims, rejected_claims = validate_llm_claims(ClaimDraftList(claims=result.claims), source, window, matcher)
        points, rejected_points = validate_llm_data_points(result.data_points, source, window)
        text = " ".join(p.text for p in window).lower()
        entities = [e for e in result.entities if 2 < len(e.name) <= 80 and e.name.lower() in text  # must be mentioned
                    and is_named_entity(e.name)]
        return claims, points, entities, rejected_claims, rejected_points

    # ------------------------------------------------------------------ verification
    def _verify_claims(self, claims: list[Claim], ctx: RunContext) -> None:
        """Check LLM restatements against their verbatim quotes; unfaithful or overstated ones use the quote."""
        for start in range(0, min(len(claims), 90), 30):
            batch = claims[start:start + 30]
            listing = "\n".join(f'{i}. QUOTE: "{truncate(c.quote, 300)}" || CLAIM: "{truncate(c.text, 200)}"'
                                for i, c in enumerate(batch))
            prompt = ("For each numbered item, judge whether CLAIM faithfully restates QUOTE: 'faithful', 'overstated' "
                      "(claims more than the quote supports) or 'unfaithful'. Return {\"verdicts\": [{\"index\": 0, "
                      "\"verdict\": \"faithful|overstated|unfaithful\", \"explanation\": \"...\"}]}.\n\n" + listing)
            result = ctx.llm.structured(prompt, Verdicts, ctx.budget, max_tokens=1500, fast=True)
            if not result:
                return
            for v in result.verdicts:
                if not 0 <= v.index < len(batch):
                    continue
                claim, verdict = batch[v.index], v.verdict.lower()
                claim.verified = verdict == "faithful"
                if verdict == "unfaithful":
                    claim.notes.append("LLM restatement was unfaithful; the verbatim quote is used instead.")
                    claim.text = claim.quote
                elif verdict == "overstated":
                    claim.notes.append(f"Restatement overstated the source: {v.explanation[:160]}")
                    claim.text = claim.quote

    # ------------------------------------------------------------------ semantic grouping
    def _llm_groups(self, claims: list[Claim], ctx: RunContext):
        """Ask the LLM to group claims by proposition, with stance. Validated: ids must exist and appear once."""
        if len(claims) < 2:
            return None
        subset = claims[:MAX_GROUPING_CLAIMS]
        by_id = {c.id: c for c in subset}
        listing = "\n".join(f"{c.id}: {truncate(c.text, 220)}" for c in subset)
        prompt = ("Group the claims below by the proposition they address (claims from different sources saying the "
                  "same thing in different words belong together). For each group give the proposition, the claim ids "
                  "that SUPPORT it and the claim ids that CONTRADICT or seriously qualify it. Put each claim id in at "
                  "most one group; claims that match nothing may be omitted. Return {\"groups\": [{\"proposition\": ..., "
                  "\"supporting\": [ids], \"contradicting\": [ids]}]}.\n\n" + listing)
        result = ctx.llm.structured(prompt, ClaimGroups, ctx.budget, max_tokens=3500)
        if not result or not result.groups:
            ctx.event(self.name, "info", "LLM claim grouping unavailable; using lexical clustering.")
            return None
        used: set[str] = set()
        groups = []
        for group in result.groups:
            support = [i for i in group.supporting if i in by_id and i not in used]
            used |= set(support)
            contra = [i for i in group.contradicting if i in by_id and i not in used]
            used |= set(contra)
            if not support and contra:  # a group of only "contradicting" claims is a proposition stated negatively
                support, contra = contra, []
            if support:
                groups.append(([by_id[i] for i in support + contra], set(support)))
        for claim in claims:  # anything unassigned (or beyond the subset) becomes its own row
            if claim.id not in used:
                groups.append(([claim], {claim.id}))
        return groups

    # ------------------------------------------------------------------ adjudication (heuristic candidates)
    def _adjudicate(self, contradictions, claims, ctx: RunContext):
        items = [c for c in contradictions if c.claim_a_id in claims and c.claim_b_id in claims][:15]
        listing = "\n".join(f'{i}. A: "{claims[c.claim_a_id].quote}" || B: "{claims[c.claim_b_id].quote}"'
                            for i, c in enumerate(items))
        prompt = ("For each numbered pair of quoted statements from different sources, decide whether they genuinely "
                  "contradict each other (incompatible claims about the same thing), are compatible, or are about "
                  "different things. Return {\"verdicts\": [{\"index\": 0, \"verdict\": \"contradicts|compatible|"
                  "unrelated\", \"explanation\": \"one sentence\"}]}.\n\n" + listing)
        result = ctx.llm.structured(prompt, Verdicts, ctx.budget, max_tokens=1200, fast=True)
        if not result:
            return contradictions, 0
        verdicts = {v.index: v for v in result.verdicts if 0 <= v.index < len(items)}
        kept, dismissed = [], 0
        for i, con in enumerate(items):
            verdict = verdicts.get(i)
            if verdict and verdict.verdict in ("compatible", "unrelated"):
                dismissed += 1
                continue
            if verdict:
                con = con.model_copy(update={"explanation": verdict.explanation[:300] + " (LLM-reviewed)"})
            kept.append(con)
        return kept + contradictions[len(items):], dismissed

    # ------------------------------------------------------------------ entities
    @staticmethod
    def _entities(claims: list[Claim], store: EvidenceStore, llm_entities, previous: list[Entity]) -> list[Entity]:
        entities = {e.name.lower(): e for e in heuristic_entities(claims, store.sources)}
        for e in previous:
            entities.setdefault(e.name.lower(), e)
        for name, kind, source_id in llm_entities:
            key = name.strip().lower()
            entity = entities.get(key) or Entity(id=_id("ent", key), name=name.strip(),
                                                 kind=kind if kind != "named_entity" else entity_kind(name))
            if source_id not in entity.source_ids:
                entity.source_ids.append(source_id)
            entity.mentions += 1
            entity.claim_ids = sorted(set(entity.claim_ids) | {c.id for c in claims if c.source_id == source_id
                                                                and key in c.quote.lower()})
            entities[key] = entity
        ranked = sorted(entities.values(), key=lambda e: (-len(e.source_ids), -e.mentions, e.name))
        return [e for e in ranked if len(e.source_ids) >= 2 or e.mentions >= 3][:30]
