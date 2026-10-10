"""Agent G: Report Builder. Assembles a structured, cited report and validates every citation.

Sections are built deterministically from the plan, evidence matrix, contradictions, gaps and insights,
so every statement traces back to claims and sources. In live mode the LLM may rewrite the executive
summary and detailed analysis as prose. Its citation markers must refer to existing references, and the
rewrite is rejected if it introduces numbers that do not appear in the evidence.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from src.agents.base import Agent, RunContext
from src.analysis.text import truncate
from src.evidence.citations import build_references, format_reference, strip_invalid_markers, validate_citations
from src.evidence.store import EvidenceStore
from src.models.evidence import (Agreement, EpistemicLabel, InsightKind, ORIGIN_LABELS, Report, ReportSection)
from src.models.research import ResearchMode
from src.orchestration.state import ResearchState
from src.services.llm import wrap_untrusted

AGREEMENT_LABEL = {Agreement.STRONG: "strong agreement", Agreement.MODERATE: "moderate agreement",
                   Agreement.SINGLE_SOURCE: "single source", Agreement.MIXED: "mixed evidence",
                   Agreement.CONTESTED: "contested"}


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
    executive_summary: str
    detailed_analysis: str


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", re.sub(r"\[\d+\]", "", text))}


class ReportBuilderAgent(Agent):
    name = "report_builder"
    title = "Report Builder"
    responsibility = "Synthesises a structured report with inline citations, limitations and a validated reference list."
    uses_llm = "optional"

    def run(self, state: ResearchState, ctx: RunContext) -> dict:
        report = self.build(state, ctx)
        invalid = [c for c in report.citation_checks if not c.valid]
        ctx.event(self.name, "completed", f"Report with {len(report.sections)} sections and {len(report.references)} "
                  f"references; {len(report.citation_checks) - len(invalid)}/{len(report.citation_checks)} citations "
                  "passed traceability checks.", state.get("iteration", 0), references=len(report.references))
        return {"report": report}

    def build(self, state: ResearchState, ctx: RunContext) -> Report:
        request, plan = state["request"], state["plan"]
        store = EvidenceStore(state.get("sources", []), state.get("passages", []))
        claims = {c.id: c for c in state.get("claims", [])}
        rows = state.get("matrix", [])
        insights = state.get("insights", [])
        contradictions = state.get("contradictions", [])
        gaps = state.get("gaps", [])
        assessments = state.get("assessments", {})
        usage = state.get("usage")
        cite = Citer(store)
        demo = request.mode == ResearchMode.DEMO
        sections: list[ReportSection] = []

        def add(key: str, title: str, content: str) -> None:
            sections.append(ReportSection(key=key, title=title, content=content.strip() or "_No content._"))

        # 1-2. Scope & methodology
        origins = {}
        for s in store.sources.values():
            origins[ORIGIN_LABELS[s.origin]] = origins.get(ORIGIN_LABELS[s.origin], 0) + 1
        mode_note = ("**Demo mode:** all sources are SYNTHETIC and fictional; findings illustrate the workflow and are "
                     "not real evidence." if demo else
                     "**Live research:** sources were retrieved from the configured providers during this run "
                     "(cached results are labelled).")
        add("scope", "Research scope and methodology", "\n".join([
            mode_note, "",
            f"- **Question:** {request.question}",
            f"- **Timeframe:** {plan.scope.timeframe}" + (f" · **Geography:** {plan.scope.geography}" if plan.scope.geography else ""),
            f"- **Objectives:** " + "; ".join(plan.objectives),
            f"- **Strategy:** {plan.search_strategy}", "",
            "**Subquestions investigated:**",
            *[f"- {sq.id} ({sq.perspective}, priority {sq.priority}, {sq.status.value}): {sq.text}" for sq in plan.subquestions],
            "",
            f"**Process:** {state.get('iteration', 0) + 1} research round(s), "
            f"{usage.searches if usage else 0} searches, {len(store.sources)} sources "
            f"({', '.join(f'{v} {k.lower()}' for k, v in origins.items()) or 'none'}), {len(claims)} claims extracted. "
            f"Stopping rule: {state.get('stop_reason') or state.get('route_reason', 'n/a')}", "",
            "_Source assessments are rule-based indicators (type, date, wording, duplication), not calibrated probabilities._",
        ]))

        # 3. Executive summary (deterministic draft)
        findings = [i for i in insights if i.kind == InsightKind.FINDING]
        disagreements = [i for i in insights if i.kind == InsightKind.DISAGREEMENT]
        hypotheses = [i for i in insights if i.label == EpistemicLabel.SPECULATIVE]
        answered = sum(sq.status.value == "answered" for sq in plan.subquestions)
        summary = [f"This investigation examined {len(plan.subquestions)} subquestions using {len(store.sources)} sources; "
                   f"{answered} subquestion(s) met the evidence threshold."]
        for f in findings[:3]:
            summary.append(f"- **Finding ({f.confidence} confidence):** {truncate(f.statement, 260)} {cite(f.source_ids)}")
        for d in disagreements[:2]:
            summary.append(f"- **Disagreement:** {truncate(d.statement, 260)} {cite(d.source_ids)}")
        if hypotheses:
            summary.append(f"- **Hypothesis (speculative):** {truncate(hypotheses[0].statement.removeprefix('Hypothesis: '), 220)} "
                           f"{cite(hypotheses[0].source_ids)}")
        if not findings and not disagreements:
            summary.append("- The evidence gathered was too thin to support firm findings; see the gaps below.")
        exec_summary = "\n".join(summary)

        # 4. Key findings
        key = []
        for f in findings:
            key.append(f"- {f.statement} {cite(f.source_ids)}  \n  _Observed · confidence {f.confidence}: "
                       f"{f.confidence_explanation}_")
        key_findings = "\n".join(key) or "No claim reached moderate or strong agreement across independent sources."

        # 5. Detailed analysis by subquestion
        detail = []
        for sq in plan.subquestions:
            sq_rows = sorted([r for r in rows if r.subquestion_id == sq.id], key=lambda r: -r.independent_sources)
            detail.append(f"### {sq.text}\n_Status: {sq.status.value}_\n")
            if not sq_rows:
                detail.append("No relevant evidence was found for this subquestion.\n")
                continue
            for row in sq_rows[:4]:
                line = f"- {truncate(row.claim, 280)} {cite(row.supporting_source_ids)} ({AGREEMENT_LABEL[row.agreement]}"
                line += f", evidence quality {row.evidence_quality.value})"
                if row.contradicting_claim_ids:
                    counter = claims.get(row.contradicting_claim_ids[0])
                    if counter:
                        line += f". Contradicted by: \"{truncate(counter.text, 200)}\" {cite(row.contradicting_source_ids)}"
                if row.weaknesses:
                    line += f". Caveats: {'; '.join(row.weaknesses[:2])}"
                detail.append(line)
            detail.append("")
        detailed = "\n".join(detail)

        # 6. Supporting and contradicting evidence (matrix)
        table = ["| Claim | Supporting | Contradicting | Agreement | Quality |", "|---|---|---|---|---|"]
        for row in sorted(rows, key=lambda r: (r.agreement != Agreement.CONTESTED, -r.independent_sources))[:15]:
            table.append(f"| {truncate(row.claim, 110).replace('|', '/')} | {cite(row.supporting_source_ids) or '–'} | "
                         f"{cite(row.contradicting_source_ids) or '–'} | {AGREEMENT_LABEL[row.agreement]} | "
                         f"{row.evidence_quality.value} |")
        if contradictions:
            table.append("\n**Contradictions identified:**")
            for con in contradictions[:8]:
                a, b = claims.get(con.claim_a_id), claims.get(con.claim_b_id)
                if a and b:
                    table.append(f"- ({con.nature}) \"{truncate(a.text, 140)}\" {cite([a.source_id])} vs "
                                 f"\"{truncate(b.text, 140)}\" {cite([b.source_id])}: {con.explanation}")
        evidence_section = "\n".join(table)

        # 7-9. Trends & hypotheses; implications; risks & alternatives
        def insight_lines(kinds: set, prefix: str = "") -> str:
            lines = []
            for i in insights:
                if i.kind in kinds:
                    tag = {"observed": "Observed", "inferred": "Inferred", "speculative": "Speculative"}[i.label.value]
                    lines.append(f"- **{tag}{prefix}:** {i.statement} {cite(i.source_ids)}  \n  _Confidence {i.confidence}: "
                                 f"{i.confidence_explanation}_" + (f"  \n  _Alternatives: {'; '.join(i.alternatives[:2])}_"
                                                                   if i.alternatives else ""))
            return "\n".join(lines)
        trends = insight_lines({InsightKind.TREND, InsightKind.HYPOTHESIS}) or "No recurring trends or hypotheses emerged."
        implications = insight_lines({InsightKind.IMPLICATION, InsightKind.OPPORTUNITY}) or "No implications were derived."
        risks = insight_lines({InsightKind.RISK, InsightKind.DISAGREEMENT}) or "No specific risks were identified."

        # 10. Next steps
        steps = [f"- {g.description} Suggested searches: " + ", ".join(f"“{q}”" for q in g.follow_up_queries[:2])
                 for g in sorted(gaps, key=lambda g: -g.expected_value)[:5] if g.follow_up_queries]
        steps += [f"- {i.next_investigation}" for i in insights if i.next_investigation][:4]
        next_steps = "\n".join(dict.fromkeys(steps)) or "- No further research is recommended at this depth."

        # 11. Limitations
        abstract_only = sum(not s.full_text_available for s in store.sources.values())
        flagged = {f for a in assessments.values() for f in a.flags}
        limits = [
            "- Citations were checked for traceability (the source exists, the reference matches, the passage is "
            "relevant). This does **not** verify that the claims are true.",
            "- Source scores are heuristic triage indicators, not calibrated probabilities.",
        ]
        if demo:
            limits.insert(0, "- **All sources in this report are synthetic demo data.** No live research was performed.")
        if abstract_only:
            limits.append(f"- {abstract_only} source(s) were reviewed from a snippet or abstract only, not the full text.")
        if "repeats_other_source" in flagged:
            limits.append("- Some sources repeat other sources (e.g. news reprinting a press release); they were not "
                          "counted as independent corroboration.")
        if "prompt_injection_attempt" in flagged:
            limits.append("- At least one source contained instructions aimed at AI systems. They were ignored and the "
                          "source was down-weighted.")
        if state.get("usage") and state["usage"].exhausted:
            limits.append(f"- Research stopped partly because limits were reached: {', '.join(state['usage'].exhausted)}.")
        unresolved = sorted({q for r in rows for q in r.unresolved_questions})
        if unresolved:
            limits.append("\n**Unresolved questions:**\n" + "\n".join(f"- {q}" for q in unresolved[:6]))
        if state.get("errors"):
            limits.append("\n**Errors during the run:**\n" + "\n".join(f"- {e}" for e in state["errors"][:5]))
        limitations = "\n".join(limits)

        # Optional LLM prose for summary + analysis, validated.
        generated_by = "heuristic"
        if ctx.llm_enabled and rows:
            prose = self._llm_prose(request.question, exec_summary, detailed, store, cite, ctx)
            if prose:
                exec_summary, detailed = prose
                generated_by = "llm (citations validated)"

        add("executive_summary", "Executive summary", exec_summary)
        add("key_findings", "Key findings", key_findings)
        add("detailed_analysis", "Detailed analysis", detailed)
        add("evidence", "Supporting and contradicting evidence", evidence_section)
        add("trends", "Emerging trends and hypotheses", trends)
        add("implications", "Implications and opportunities", implications)
        add("risks", "Risks and alternative interpretations", risks)
        add("next_steps", "Recommendations and next steps", next_steps)
        add("limitations", "Limitations and unresolved questions", limitations)

        chart_lines = []
        for chart in state.get("charts", []):
            chart_lines.append(f"### {chart.title}" + (" — SYNTHETIC" if chart.synthetic else ""))
            chart_lines.append(f"Unit: {chart.unit}. {chart.limitation}")
            for point in chart.points:
                label = point.label.replace("\n", " ")
                chart_lines.append(f"- {label}: **{point.value:g} {chart.unit}** "
                                   f"{cite([point.source_id])} ({point.location})")
        add("visualizations", "Numeric evidence behind the charts", "\n\n".join(chart_lines)
            or "No unambiguous numeric dataset was available; no chart values were invented.")
        references = build_references([store.sources[sid] for sid in cite.order])
        add("references", "References", "\n".join(format_reference(r) for r in references) or "_No sources cited._")

        body = "\n\n".join(s.content for s in sections if s.key != "references")
        checks = validate_citations(body, references, store.sources, store.passages)
        return Report(title=f"Research report: {truncate(request.question, 120)}", question=request.question,
                      sections=sections, references=references, citation_checks=checks, generated_by=generated_by)

    def _llm_prose(self, question: str, summary: str, detailed: str, store: EvidenceStore, cite: Citer,
                   ctx: RunContext) -> tuple[str, str] | None:
        valid = set(range(1, len(cite.order) + 1))
        prompt = ("Research question:\n" + wrap_untrusted("research_question", question)
                  + "\nRewrite the two draft sections below into clear, balanced prose for a "
                  "decision maker. Keep every citation marker like [3] next to the statement it supports; do not add "
                  "new markers, facts or numbers. Keep disagreements and uncertainty explicit, and keep speculative "
                  "statements labelled as hypotheses. Return {\"executive_summary\": ..., \"detailed_analysis\": ...} "
                  "(markdown allowed; keep the ### subquestion headings in the analysis).\n\n"
                  "DRAFT EXECUTIVE SUMMARY:\n" + wrap_untrusted("draft_summary", summary)
                  + "\n\nDRAFT DETAILED ANALYSIS:\n" + wrap_untrusted("draft_analysis", detailed[:9000]))
        draft = ctx.llm.structured(prompt, ProseDraft, ctx.budget, max_tokens=3000)
        if not draft:
            return None
        for original, rewritten in ((summary, draft.executive_summary), (detailed[:9000], draft.detailed_analysis)):
            if set(re.findall(r"\[\d+\]", original)) != set(re.findall(r"\[\d+\]", rewritten)):
                ctx.event(self.name, "info", "LLM rewrite rejected: citation markers were changed or removed.")
                return None
        allowed_numbers = _numbers(summary + detailed + " ".join(s.content for s in store.sources.values()))
        new_numbers = {n for n in _numbers(draft.executive_summary + draft.detailed_analysis)
                       if n not in allowed_numbers and not (n.isdigit() and int(n) < 13)}
        if new_numbers:
            ctx.event(self.name, "info", "LLM rewrite rejected: it introduced numbers not present in the evidence.")
            return None
        es, removed_a = strip_invalid_markers(draft.executive_summary, valid)
        da, removed_b = strip_invalid_markers(draft.detailed_analysis, valid)
        if removed_a + removed_b:
            ctx.event(self.name, "info", f"Removed {removed_a + removed_b} citation marker(s) that matched no reference.")
        return es, da
