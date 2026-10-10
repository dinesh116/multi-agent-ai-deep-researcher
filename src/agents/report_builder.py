"""Agent G: Report Builder. Assembles a structured, cited report and validates every citation.

The report format adapts to the question. `REPORT_TEMPLATES` maps a template (chosen from the question type,
or by the user) to an ordered list of sections:

  outlook              forward-looking questions   (timeline, scenarios/hypotheses, implications)
  evidence_assessment  "does the evidence support X?"  (verdict, evidence for / against)
  literature_review    research-developments questions (methods & results table, open problems)
  landscape            market / general questions  (key players, comparison table)
  brief | full         executive brief, or every section

Every section is built deterministically from the plan, the evidence matrix, data points, entities,
contradictions, gaps and insights, so each statement traces to claims and sources. In live mode the LLM also
writes a short synthesis per subquestion and the executive summary. Its citation markers must refer to
existing references, and prose that introduces numbers absent from the evidence is rejected.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from src.agents.base import Agent, RunContext
from src.agents.planner import classify_question, topic_phrase
from src.analysis.datapoints import group_data_points, timeline
from src.analysis.text import content_terms, truncate
from src.evidence.citations import build_references, format_reference, strip_invalid_markers, validate_citations
from src.evidence.store import EvidenceStore
from src.models.evidence import (Agreement, EpistemicLabel, EvidenceQuality, InsightKind, ORIGIN_LABELS, Report,
                                 ReportSection)
from src.models.research import ReportFormat, ResearchMode
from src.orchestration.state import ResearchState
from src.retrieval.bm25 import BM25Index

AGREEMENT_LABEL = {Agreement.STRONG: "strong agreement", Agreement.MODERATE: "moderate agreement",
                   Agreement.SINGLE_SOURCE: "single source", Agreement.MIXED: "mixed evidence",
                   Agreement.CONTESTED: "contested"}

REPORT_TEMPLATES: dict[str, tuple[str, list[str]]] = {
    "outlook": ("Outlook report", ["scope", "executive_summary", "key_numbers", "key_findings", "detailed_analysis",
                                   "timeline", "trends", "implications", "risks", "next_steps", "evidence",
                                   "limitations", "references"]),
    "evidence_assessment": ("Evidence assessment", ["scope", "executive_summary", "verdict", "evidence_for",
                                                    "evidence_against", "key_numbers", "evidence", "risks",
                                                    "next_steps", "limitations", "references"]),
    "literature_review": ("Literature review", ["scope", "executive_summary", "key_findings", "methods", "key_numbers",
                                                "detailed_analysis", "open_problems", "trends", "evidence",
                                                "next_steps", "limitations", "references"]),
    "landscape": ("Landscape report", ["scope", "executive_summary", "key_findings", "players", "key_numbers",
                                       "comparison", "detailed_analysis", "trends", "implications", "risks",
                                       "next_steps", "evidence", "limitations", "references"]),
    "brief": ("Executive brief", ["executive_summary", "key_findings", "key_numbers", "risks", "next_steps",
                                  "limitations", "references"]),
    "full": ("Full report", ["scope", "executive_summary", "key_findings", "key_numbers", "detailed_analysis",
                             "evidence", "timeline", "players", "trends", "implications", "risks", "next_steps",
                             "limitations", "references"]),
}
QUESTION_TEMPLATE = {"forward_looking": "outlook", "evaluative": "evidence_assessment", "research": "literature_review",
                     "general": "landscape"}
SECTION_TITLES = {
    "scope": "Research scope and methodology", "executive_summary": "Executive summary", "key_findings": "Key findings",
    "key_numbers": "Key numbers", "detailed_analysis": "Detailed analysis", "evidence": "Supporting and contradicting evidence",
    "timeline": "Timeline of events and forecasts", "trends": "Emerging trends and hypotheses",
    "implications": "Implications and opportunities", "risks": "Risks and alternative interpretations",
    "next_steps": "Recommendations and next steps", "limitations": "Limitations and unresolved questions",
    "references": "References", "verdict": "Verdict", "evidence_for": "Evidence supporting the claim",
    "evidence_against": "Evidence against or qualifying the claim", "methods": "Methods and reported results",
    "open_problems": "Open problems", "players": "Key players and entities", "comparison": "Comparison",
}
QUALITY_RANK = {EvidenceQuality.HIGH: 0, EvidenceQuality.MEDIUM: 1, EvidenceQuality.LOW: 2, EvidenceQuality.UNKNOWN: 3}
OPEN_PROBLEM = re.compile(r"\b(open problem|remains? (?:the )?(?:main )?(?:open|unsolved|a challenge)|challenge|"
                          r"not yet|lack(?:s|ing)?|limitation|future work|unclear)\b", re.I)


def choose_template(question: str, report_format: ReportFormat) -> str:
    if report_format == ReportFormat.BRIEF:
        return "brief"
    if report_format == ReportFormat.FULL:
        return "full"
    return QUESTION_TEMPLATE[classify_question(question)]


class Citer:
    """Assigns reference numbers to sources in order of first citation."""

    def __init__(self, store: EvidenceStore):
        self.store, self.order = store, []

    def __call__(self, source_ids: list[str], limit: int = 4) -> str:
        markers = []
        for sid in list(dict.fromkeys(source_ids))[:limit]:
            if sid not in self.store.sources:
                continue
            if sid not in self.order:
                self.order.append(sid)
            markers.append(f"[{self.order.index(sid) + 1}]")
        return "".join(markers)


class ProseDraft(BaseModel):
    text: str


class Stance(BaseModel):
    id: str
    stance: str


class Stances(BaseModel):
    stances: list[Stance] = []


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", re.sub(r"\[\d+\]", "", text))}


def _cell(text: str, limit: int = 110) -> str:
    return truncate(re.sub(r"\s+", " ", text).replace("|", "/"), limit)


class ReportBuilderAgent(Agent):
    name = "report_builder"
    title = "Report Builder"
    responsibility = ("Synthesises a report whose format fits the question, with key numbers, comparisons, inline "
                      "citations, limitations and a validated reference list.")
    uses_llm = "optional"

    def run(self, state: ResearchState, ctx: RunContext) -> dict:
        report = self.build(state, ctx)
        invalid = [c for c in report.citation_checks if not c.valid]
        ctx.event(self.name, "completed", f"{REPORT_TEMPLATES[report.template][0]} with {len(report.sections)} sections "
                  f"and {len(report.references)} references; {len(report.citation_checks) - len(invalid)}/"
                  f"{len(report.citation_checks)} citations passed traceability checks.", state.get("iteration", 0),
                  references=len(report.references))
        return {"report": report}

    # ------------------------------------------------------------------ build
    def build(self, state: ResearchState, ctx: RunContext) -> Report:
        self.state, self.ctx = state, ctx
        self.request, self.plan = state["request"], state["plan"]
        self.store = EvidenceStore(state.get("sources", []), state.get("passages", []))
        self.claims = {c.id: c for c in state.get("claims", [])}
        self.rows = state.get("matrix", [])
        self.insights = state.get("insights", [])
        self.contradictions = state.get("contradictions", [])
        self.gaps = state.get("gaps", [])
        self.assessments = state.get("assessments", {})
        self.points = state.get("data_points", [])
        self.entities = state.get("entities", [])
        self.cite = Citer(self.store)
        self.demo = self.request.mode == ResearchMode.DEMO
        template = choose_template(self.request.question, self.request.report_format)
        self.template = template
        label, keys = REPORT_TEMPLATES[template]

        # Build the body in a fixed order so reference numbering follows first use in the executive summary.
        built: dict[str, str] = {}
        built["executive_summary"] = self._executive_summary()
        for key in keys:
            if key not in ("executive_summary", "references", "limitations"):
                built[key] = getattr(self, f"_sec_{key}")()
        built["limitations"] = self._sec_limitations()

        generated_by = "heuristic"
        if self.ctx.llm_enabled and self.rows:
            if "detailed_analysis" in built:
                synthesis = self._llm_subquestion_synthesis()
                if synthesis:
                    built["detailed_analysis"] = synthesis
                    generated_by = "llm (citations validated)"
            summary = self._llm_rewrite(built["executive_summary"], "executive summary for a decision maker: 4-7 "
                                        "sentences or bullets covering the answer, the strongest evidence, the main "
                                        "disagreement and the confidence level")
            if summary:
                built["executive_summary"] = summary
                generated_by = "llm (citations validated)"

        references = build_references([self.store.sources[sid] for sid in self.cite.order])
        if generated_by != "heuristic":  # LLM prose may attach markers loosely: keep only relevant ones
            for key in ("executive_summary", "detailed_analysis"):
                if key in built:
                    built[key] = self._prune_markers(built[key], references)
        built["references"] = "\n".join(format_reference(r) for r in references) or "_No sources cited._"
        sections = [ReportSection(key=k, title=SECTION_TITLES[k], content=(built.get(k) or "").strip() or "_No content._")
                    for k in keys]
        body = "\n\n".join(s.content for s in sections if s.key != "references")
        checks = validate_citations(body, references, self.store.sources, self.store.passages)
        return Report(title=f"{label}: {truncate(self.request.question, 120)}", question=self.request.question,
                      sections=sections, references=references, citation_checks=checks, generated_by=generated_by,
                      template=template)

    # ------------------------------------------------------------------ helpers
    def _row_line(self, row, limit: int = 280) -> str:
        line = (f"- {truncate(row.claim, limit)} {self.cite(row.supporting_source_ids)} ({AGREEMENT_LABEL[row.agreement]}, "
                f"{row.independent_sources} independent, strength {row.strength:g})")
        if row.contradicting_claim_ids:
            counter = self.claims.get(row.contradicting_claim_ids[0])
            if counter:
                line += f". Contradicted by: \"{truncate(counter.text, 200)}\" {self.cite(row.contradicting_source_ids)}"
        if row.weaknesses:
            line += f". Caveats: {'; '.join(row.weaknesses[:2])}"
        return line

    def _ranked_points(self, limit: int = 14):
        if not hasattr(self, "_point_relevance"):
            query = self.request.question + " " + " ".join(s.text for s in self.plan.subquestions)
            ranked = BM25Index(self.points, lambda p: f"{p.metric} {p.quote}").search(query, k=len(self.points) or 1)
            top = ranked[0][1] if ranked else 1.0
            self._point_relevance = {p.id: score / top for p, score in ranked}

        def score(p):
            a = self.assessments.get(p.source_id)
            relevance = round(self._point_relevance.get(p.id, 0.0), 1)  # coarse bands, then quality decides
            return (-relevance, QUALITY_RANK[a.evidence_quality] if a else 3, 0 if (p.subject or p.method) else 1)
        groups = self.store.independent_groups(list({p.source_id for p in self.points}))
        group_of = {sid: i for i, g in enumerate(groups) for sid in g}
        seen, ranked = set(), []
        for p in sorted(self.points, key=score):
            # the same figure counts once per independent source group (a reprint doesn't add a second row)
            keys = {(p.value_text, p.metric.lower()[:30]), (p.value_text, group_of.get(p.source_id, p.source_id))}
            if not keys & seen and (self.assessments.get(p.source_id) is None or
                                    self.assessments[p.source_id].relevance >= 0.15):
                seen |= keys
                ranked.append(p)
        return ranked[:limit]

    # ------------------------------------------------------------------ sections
    def _sec_scope(self) -> str:
        plan, state, usage = self.plan, self.state, self.state.get("usage")
        origins: dict[str, int] = {}
        for s in self.store.sources.values():
            origins[ORIGIN_LABELS[s.origin]] = origins.get(ORIGIN_LABELS[s.origin], 0) + 1
        full_text = sum(s.full_text_available for s in self.store.sources.values())
        mode_note = ("**Demo mode:** all sources are SYNTHETIC and fictional; findings illustrate the workflow and are "
                     "not real evidence." if self.demo else
                     "**Live research:** sources were retrieved from the configured providers during this run "
                     "(cached results are labelled).")
        return "\n".join([
            mode_note, "",
            f"- **Question:** {self.request.question}",
            f"- **Report format:** {REPORT_TEMPLATES[self.template][0]}"
            + (" (chosen automatically from the question type)" if self.request.report_format == ReportFormat.AUTO else ""),
            f"- **Timeframe:** {plan.scope.timeframe}" + (f" · **Geography:** {plan.scope.geography}" if plan.scope.geography else ""),
            "- **Objectives:** " + "; ".join(plan.objectives),
            f"- **Strategy:** {plan.search_strategy}", "",
            "**Subquestions investigated:**",
            *[f"- {sq.id} ({sq.perspective}, priority {sq.priority}, {sq.status.value}): {sq.text}" for sq in plan.subquestions],
            "",
            f"**Process:** {state.get('iteration', 0) + 1} research round(s), {usage.searches if usage else 0} searches, "
            f"{len(self.store.sources)} sources ({', '.join(f'{v} {k.lower()}' for k, v in origins.items()) or 'none'}; "
            f"{full_text} read in full text), {len(self.claims)} claims, {len(self.points)} data points and "
            f"{len(self.entities)} recurring entities extracted. Stopping rule: "
            f"{state.get('stop_reason') or state.get('route_reason', 'n/a')}", "",
            "_Source assessments are rule-based indicators (type, date, wording, duplication), not calibrated probabilities._",
        ])

    def _executive_summary(self) -> str:
        findings = [i for i in self.insights if i.kind == InsightKind.FINDING]
        disagreements = [i for i in self.insights if i.kind == InsightKind.DISAGREEMENT]
        hypotheses = [i for i in self.insights if i.label == EpistemicLabel.SPECULATIVE]
        answered = sum(sq.status.value == "answered" for sq in self.plan.subquestions)
        summary = [f"This investigation examined {len(self.plan.subquestions)} subquestions using "
                   f"{len(self.store.sources)} sources; {answered} subquestion(s) met the evidence threshold."]
        if self.template == "evidence_assessment":
            verdict, _, _ = self._verdict_numbers()
            summary.append(f"- **Verdict:** {verdict}")
        for f in findings[:3]:
            summary.append(f"- **Finding ({f.confidence} confidence):** {truncate(f.statement, 260)} {self.cite(f.source_ids)}")
        for p in self._ranked_points(2):
            summary.append(f"- **Key number:** {p.value_text} ({truncate(p.metric, 80)}"
                           + (f", {p.subject}" if p.subject else "") + f") {self.cite([p.source_id])}")
        for d in disagreements[:2]:
            summary.append(f"- **Disagreement:** {truncate(d.statement, 260)} {self.cite(d.source_ids)}")
        if hypotheses:
            summary.append(f"- **Hypothesis (speculative):** {truncate(hypotheses[0].statement.removeprefix('Hypothesis: '), 220)} "
                           f"{self.cite(hypotheses[0].source_ids)}")
        if not findings and not disagreements:
            summary.append("- The evidence gathered was too thin to support firm findings; see the gaps below.")
        return "\n".join(summary)

    def _sec_key_findings(self) -> str:
        findings = [i for i in self.insights if i.kind == InsightKind.FINDING]
        lines = [f"- {f.statement} {self.cite(f.source_ids)}  \n  _Observed · confidence {f.confidence}: "
                 f"{f.confidence_explanation}_" for f in findings]
        if not lines:
            best = sorted(self.rows, key=lambda r: -r.strength)[:4]
            lines = ["_No claim reached moderate or strong agreement across independent sources. The best-supported "
                     "single-source claims are:_"] + [self._row_line(r, 220) for r in best]
        return "\n".join(lines)

    def _sec_key_numbers(self) -> str:
        points = self._ranked_points()
        if not points:
            return "_No quantitative data points were extracted from the sources._"
        table = ["| Measure | Value | Population / sample | Period | Method | Source |", "|---|---|---|---|---|---|"]
        for p in points:
            table.append(f"| {_cell(p.metric, 70)} | **{_cell(p.value_text, 30)}** ({p.kind}) | {_cell(p.subject or '–', 40)} | "
                         f"{_cell(p.period or '–', 20)} | {_cell(p.method or '–', 30)} | {self.cite([p.source_id])} |")
        notes = []
        for group in group_data_points(points):
            values = {p.value for p in group if p.value is not None}
            sources = {p.source_id for p in group}
            if len(values) > 1 and len(sources) > 1 and self.store.independent_count(list(sources)) > 1:
                notes.append(f"- Different figures for '{truncate(group[0].metric, 70)}' "
                             f"({', '.join(p.value_text for p in group[:4])}) {self.cite(list(sources))}. "
                             "Check definitions, samples and dates before comparing.")
        return "\n".join(table + (["", "**Comparability notes:**"] + notes if notes else []))

    def _sec_detailed_analysis(self) -> str:
        detail = []
        for sq in self.plan.subquestions:
            sq_rows = sorted([r for r in self.rows if r.subquestion_id == sq.id], key=lambda r: -r.strength)
            detail.append(f"### {sq.text}\n_Status: {sq.status.value}_\n")
            if not sq_rows:
                detail.append("No relevant evidence was found for this subquestion.\n")
                continue
            detail += [self._row_line(row) for row in sq_rows[:5]]
            detail.append("")
        return "\n".join(detail)

    def _sec_evidence(self) -> str:
        table = ["| Claim | Supporting | Contradicting | Agreement | Strength | Quality |", "|---|---|---|---|---|---|"]
        for row in sorted(self.rows, key=lambda r: (r.agreement != Agreement.CONTESTED, -r.strength))[:18]:
            table.append(f"| {_cell(row.claim)} | {self.cite(row.supporting_source_ids) or '–'} | "
                         f"{self.cite(row.contradicting_source_ids) or '–'} | {AGREEMENT_LABEL[row.agreement]} | "
                         f"{row.strength:g} | {row.evidence_quality.value} |")
        if self.contradictions:
            table.append("\n**Contradictions identified:**")
            for con in self.contradictions[:8]:
                a, b = self.claims.get(con.claim_a_id), self.claims.get(con.claim_b_id)
                if a and b:
                    table.append(f"- ({con.nature}) \"{truncate(a.text, 140)}\" {self.cite([a.source_id])} vs "
                                 f"\"{truncate(b.text, 140)}\" {self.cite([b.source_id])}: {con.explanation}")
        return "\n".join(table)

    def _sec_timeline(self) -> str:
        events = timeline(list(self.claims.values()), self.store.sources, self.ctx.today)
        if not events:
            return "_No dated events or forecasts were found in the evidence._"
        return "\n".join(f"- **{e['year']}** ({'forecast' if e['kind'] == 'forecast' else 'reported'}): "
                         f"{truncate(e['text'], 220)} {self.cite([e['source_id']])}" for e in events)

    def _insight_lines(self, kinds: set) -> str:
        lines = []
        for i in self.insights:
            if i.kind in kinds:
                tag = {"observed": "Observed", "inferred": "Inferred", "speculative": "Speculative"}[i.label.value]
                lines.append(f"- **{tag}:** {i.statement} {self.cite(i.source_ids)}  \n  _Confidence {i.confidence}: "
                             f"{i.confidence_explanation}_" + (f"  \n  _Alternatives: {'; '.join(i.alternatives[:2])}_"
                                                               if i.alternatives else ""))
        return "\n".join(lines)

    def _sec_trends(self) -> str:
        return self._insight_lines({InsightKind.TREND, InsightKind.HYPOTHESIS}) or "No recurring trends or hypotheses emerged."

    def _sec_implications(self) -> str:
        return self._insight_lines({InsightKind.IMPLICATION, InsightKind.OPPORTUNITY}) or "No implications were derived."

    def _sec_risks(self) -> str:
        return self._insight_lines({InsightKind.RISK, InsightKind.DISAGREEMENT}) or "No specific risks were identified."

    def _sec_next_steps(self) -> str:
        steps = [f"- {g.description} Suggested searches: " + ", ".join(f"“{q}”" for q in g.follow_up_queries[:2])
                 for g in sorted(self.gaps, key=lambda g: -g.expected_value)[:5] if g.follow_up_queries]
        steps += [f"- {i.next_investigation}" for i in self.insights if i.next_investigation][:4]
        return "\n".join(dict.fromkeys(steps)) or "- No further research is recommended at this depth."

    # evidence assessment ------------------------------------------------
    def _premise_rows(self):
        """(row, stance) for rows that bear on the claim under assessment. Stance: +1 supports, -1 contradicts."""
        if hasattr(self, "_premise_cache"):
            return self._premise_cache
        stances = self._llm_stances() if self.ctx.llm_enabled else None
        premise = content_terms(topic_phrase(self.request.question))
        out = []
        for row in self.rows:
            if stances is not None:
                if row.id in stances and stances[row.id] != 0:
                    out.append((row, stances[row.id]))
                continue
            shared = content_terms(row.claim) & premise
            if premise and len(shared) >= max(2, len(premise) // 2):  # strict: must address the claim itself
                rep = self.claims.get(row.supporting_claim_ids[0]) if row.supporting_claim_ids else None
                out.append((row, rep.polarity if rep else 1))
        self._premise_method = "LLM stance classification" if stances is not None else "wording heuristics"
        self._premise_cache = out
        return out

    def _llm_stances(self) -> dict[str, int] | None:
        rows = sorted(self.rows, key=lambda r: -r.strength)[:40]
        listing = "\n".join(f"{r.id}: {truncate(r.claim, 220)}" for r in rows)
        prompt = (f"Claim under assessment: \"{topic_phrase(self.request.question)}\"\nFor each evidence row below, "
                  "classify its stance towards that claim: 'supports', 'contradicts' (including evidence that it is "
                  "overstated or only partly true) or 'neutral' (does not bear on it). Return {\"stances\": "
                  "[{\"id\": \"row_...\", \"stance\": \"supports|contradicts|neutral\"}]}.\n\n" + listing)
        result = self.ctx.llm.structured(prompt, Stances, self.ctx.budget, max_tokens=1500)
        if not result:
            return None
        valid = {r.id for r in rows}
        mapping = {"supports": 1, "contradicts": -1, "neutral": 0}
        return {s.id: mapping.get(s.stance.lower(), 0) for s in result.stances if s.id in valid}

    def _verdict_numbers(self) -> tuple[str, float, float]:
        weight_for = weight_against = 0.0
        for row, stance in self._premise_rows():
            if stance > 0:
                weight_for += row.strength
                weight_against += 0.6 * len(row.contradicting_claim_ids) if row.contradicting_claim_ids else 0
            else:
                weight_against += row.strength
        total = weight_for + weight_against
        if total == 0:
            return "The evidence gathered does not directly address the claim.", 0.0, 0.0
        margin = (weight_for - weight_against) / total
        lean = ("leans towards supporting the claim" if margin > 0.3 else
                "leans against the claim" if margin < -0.3 else "is mixed or contested")
        confidence = "high" if total >= 4 and abs(margin) > 0.5 else "medium" if total >= 2 else "low"
        return (f"The evidence {lean} (quality-weighted support {weight_for:.1f} vs {weight_against:.1f} against; "
                f"{confidence} confidence; stance assessed with {self._premise_method}).", weight_for, weight_against)

    def _sec_verdict(self) -> str:
        verdict, w_for, w_against = self._verdict_numbers()
        return (f"{verdict}\n\nWeights sum the quality-weighted strength of independent sources (high-quality 1.0, "
                "medium 0.6, low 0.25 per independent source group). Copies of the same original count once. "
                "This is a transparent heuristic summary, not a probability that the claim is true.")

    def _sec_evidence_for(self) -> str:
        rows = [r for r, stance in self._premise_rows() if stance > 0]
        return "\n".join(self._row_line(r) for r in sorted(rows, key=lambda r: -r.strength)[:8]) or "_No supporting evidence found._"

    def _sec_evidence_against(self) -> str:
        rows = [r for r, stance in self._premise_rows() if stance < 0]
        lines = [self._row_line(r) for r in sorted(rows, key=lambda r: -r.strength)[:8]]
        for r, stance in self._premise_rows():
            if stance > 0 and r.contradicting_claim_ids:
                counter = self.claims.get(r.contradicting_claim_ids[0])
                if counter:
                    lines.append(f"- {truncate(counter.text, 260)} {self.cite([counter.source_id])} (contradicts: "
                                 f"\"{truncate(r.claim, 100)}\")")
        return "\n".join(dict.fromkeys(lines)) or "_No contradicting evidence found. Absence of counter-evidence is not proof._"

    # literature review --------------------------------------------------
    def _sec_methods(self) -> str:
        method_terms = re.compile(r"\b(accura\w*|recall|precision|f1|exact[- ]match|benchmark\w*|outperform\w*|"
                                  r"improv\w*|latenc\w*|tokens?|baseline|score\w*|error rate|hallucinat\w*)\b", re.I)
        points = [p for p in self.points if method_terms.search(f"{p.metric} {p.quote}")
                  and not re.search(r"\b(market|revenue|valuation|billion|trillion)\b", f"{p.metric} {p.unit}", re.I)]
        if not points:
            return "_No quantitative method results were extracted._"
        table = ["| Study / source | Reported result | Context | Source |", "|---|---|---|---|"]
        for p in points[:14]:
            source = self.store.sources.get(p.source_id)
            table.append(f"| {_cell(source.title if source else '?', 60)} | **{_cell(p.value_text, 25)}** {_cell(p.metric, 50)} | "
                         f"{_cell(p.quote, 110)} | {self.cite([p.source_id])} |")
        return "\n".join(table)

    def _sec_open_problems(self) -> str:
        lines = [f"- {truncate(c.text, 240)} {self.cite([c.source_id])}" for c in self.claims.values()
                 if OPEN_PROBLEM.search(c.text)][:8]
        lines += [f"- Unanswered: {g.description}" for g in self.gaps if g.kind.value in ("unanswered", "thin_evidence")][:4]
        return "\n".join(dict.fromkeys(lines)) or "_No open problems were identified in the sources._"

    # landscape ------------------------------------------------------------
    def _sec_players(self) -> str:
        if not self.entities:
            return "_No recurring organisations, products or technologies were identified._"
        table = ["| Entity | Type | Sources | Example evidence |", "|---|---|---|---|"]
        for entity in self.entities[:14]:
            example = next((self.claims[c] for c in entity.claim_ids if c in self.claims), None)
            table.append(f"| **{_cell(entity.name, 40)}** | {entity.kind.replace('_', ' ')} | {len(entity.source_ids)} | "
                         + (f"{_cell(example.text, 120)} {self.cite([example.source_id])}" if example else "–") + " |")
        return "\n".join(table)

    def _sec_comparison(self) -> str:
        rows = []
        for entity in self.entities[:12]:
            for p in self.points:
                if entity.name.lower() in p.quote.lower():
                    rows.append(f"| **{_cell(entity.name, 40)}** | {_cell(p.metric, 60)} | **{_cell(p.value_text, 25)}** | "
                                f"{_cell(p.period or '–', 15)} | {self.cite([p.source_id])} |")
        if not rows:
            return "_Not enough entity-specific figures to compare._"
        return "\n".join(["| Entity | Measure | Value | Period | Source |", "|---|---|---|---|---|"] + list(dict.fromkeys(rows))[:16])

    # limitations ----------------------------------------------------------
    def _sec_limitations(self) -> str:
        abstract_only = sum(not s.full_text_available for s in self.store.sources.values())
        flagged = {f for a in self.assessments.values() for f in a.flags}
        limits = ["- Citations were checked for traceability (the source exists, the reference matches, the passage is "
                  "relevant). This does **not** verify that the claims are true.",
                  "- Source scores and evidence strength are heuristic indicators, not calibrated probabilities."]
        if self.demo:
            limits.insert(0, "- **All sources in this report are synthetic demo data.** No live research was performed.")
        if abstract_only:
            limits.append(f"- {abstract_only} source(s) were reviewed from a snippet or abstract only, not the full text.")
        if "repeats_other_source" in flagged:
            limits.append("- Some sources repeat other sources (e.g. news reprinting a press release); they were not "
                          "counted as independent corroboration.")
        if "prompt_injection_attempt" in flagged:
            limits.append("- At least one source contained instructions aimed at AI systems. They were ignored and the "
                          "source was down-weighted.")
        if any(p.extracted_by == "heuristic" for p in self.points):
            limits.append("- Some data points were extracted with heuristics; their measure labels are approximate. "
                          "Always read the quoted sentence.")
        if self.state.get("usage") and self.state["usage"].exhausted:
            limits.append(f"- Research stopped partly because limits were reached: {', '.join(self.state['usage'].exhausted)}.")
        unresolved = sorted({q for r in self.rows for q in r.unresolved_questions})
        if unresolved:
            limits.append("\n**Unresolved questions:**\n" + "\n".join(f"- {q}" for q in unresolved[:6]))
        if self.state.get("errors"):
            limits.append("\n**Errors during the run:**\n" + "\n".join(f"- {e}" for e in self.state["errors"][:5]))
        return "\n".join(limits)

    def _prune_markers(self, text: str, references: list[dict]) -> str:
        """Remove citation markers whose cited passages don't relate to the sentence they're attached to."""
        from src.evidence.citations import MARKER, passage_supports
        by_n = {r["n"]: r["source_id"] for r in references}
        out = []
        for line in text.split("\n"):
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z*\-(])", line)
            pruned = []
            for sentence in sentences:
                def keep(match, sentence=sentence):
                    sid = by_n.get(int(match.group(1)))
                    return match.group(0) if sid and passage_supports(sentence, self.store.passages.get(sid, [])) else ""
                pruned.append(MARKER.sub(keep, sentence))
            out.append(" ".join(pruned))
        return "\n".join(out)

    # ------------------------------------------------------------------ LLM prose (validated)
    def _validated(self, draft: str, source_text: str) -> str | None:
        valid = set(range(1, len(self.cite.order) + 1))
        allowed = _numbers(source_text + " ".join(s.content for s in self.store.sources.values()))
        new_numbers = {n for n in _numbers(draft) if n not in allowed and not (n.isdigit() and int(n) < 13)}
        if new_numbers:
            return None
        text, _ = strip_invalid_markers(draft, valid)
        return text

    def _llm_rewrite(self, draft: str, instruction: str) -> str | None:
        prompt = (f"Research question: {self.request.question}\nRewrite the draft below as an {instruction}. Keep every "
                  "citation marker like [3] next to the statement it supports; do not add new markers, facts or numbers. "
                  "Keep disagreements and uncertainty explicit and label hypotheses as speculative. Return {\"text\": ...} "
                  f"(markdown allowed).\n\nDRAFT:\n{draft[:8000]}")
        result = self.ctx.llm.structured(prompt, ProseDraft, self.ctx.budget, max_tokens=1500)
        if not result:
            return None
        text = self._validated(result.text, draft)
        if text is None:
            self.ctx.event(self.name, "info", "LLM summary rejected: it introduced numbers not present in the evidence.")
        return text

    def _llm_subquestion_synthesis(self) -> str | None:
        """One validated synthesis paragraph per subquestion (strong model), built on the deterministic evidence lines."""
        def draft_for(sq):
            sq_rows = sorted([r for r in self.rows if r.subquestion_id == sq.id], key=lambda r: -r.strength)[:8]
            lines = [self._row_line(r) for r in sq_rows]
            sq_sources = {sid for r in sq_rows for sid in r.supporting_source_ids}
            lines += [f"- Data: {p.value_text} {p.metric}" + (f" ({p.subject})" if p.subject else "") +
                      f" {self.cite([p.source_id])}" for p in self.points if p.source_id in sq_sources][:6]
            return sq, sq_rows, "\n".join(lines)

        drafts = [draft_for(sq) for sq in self.plan.subquestions]

        def synthesise(item):
            sq, sq_rows, draft = item
            if not sq_rows:
                return sq, None, draft
            prompt = (f"Research question: {self.request.question}\nSubquestion: {sq.text}\nEvidence (with citation "
                      "markers):\n" + draft + "\n\nWrite a synthesis of 1-2 short paragraphs answering the subquestion: "
                      "weigh agreement and strength, state disagreements and caveats, and keep each citation marker next "
                      "to the statement it supports. Do not add facts, numbers or markers that are not in the evidence. "
                      "Return {\"text\": ...}.")
            result = self.ctx.llm.structured(prompt, ProseDraft, self.ctx.budget, max_tokens=900)
            return sq, (self._validated(result.text, draft) if result else None), draft

        with ThreadPoolExecutor(max_workers=self.ctx.max_parallel) as pool:
            results = list(pool.map(synthesise, drafts))
        if not any(text for _, text, _ in results):
            return None
        parts = []
        for sq, text, draft in results:
            parts.append(f"### {sq.text}\n_Status: {sq.status.value}_\n")
            parts.append(text if text else (draft or "No relevant evidence was found for this subquestion."))
            if text:
                parts.append(f"\n_Evidence lines:_\n{draft}\n")
            parts.append("")
        return "\n".join(parts)
