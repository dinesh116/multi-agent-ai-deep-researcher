"""Reusable UI pieces: provenance badges, labels, source cards and helpers."""
from __future__ import annotations

from html import escape

import streamlit as st

from src.models.evidence import ORIGIN_LABELS, Origin, Source, SourceAssessment
from src.ui.theme import inject_theme

ORIGIN_CLASS = {Origin.DEMO: "dr-demo", Origin.LIVE: "dr-live", Origin.CACHE: "dr-cache", Origin.UPLOAD: "dr-upload"}
AGREEMENT_COLORS = {"strong": "green", "moderate": "blue", "single_source": "gray", "mixed": "orange", "contested": "red"}
QUALITY_COLORS = {"high": "green", "medium": "blue", "low": "orange", "unknown": "gray"}
STATUS_ICON = {"pending": "○", "running": "◐", "completed": "●", "failed": "✕", "skipped": "–"}
AGENT_TITLES = {"planner": "Research Planner", "retriever": "Contextual Retriever", "source_evaluator": "Source Evaluation",
                "critical_analyst": "Critical Analysis", "gap_analyst": "Gap & Follow-up",
                "insight_generator": "Insight Generation", "report_builder": "Report Builder",
                "orchestrator": "Orchestrator"}


def inject_css() -> None:
    inject_theme()


def page_header(eyebrow: str, title: str, subtitle: str = "", hero: bool = False) -> None:
    """Page header: mono eyebrow, title, muted lead paragraph, hairline rule."""
    lead = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    st.markdown(f'<div class="dr-header{" dr-hero" if hero else ""}"><div class="dr-eyebrow">{escape(eyebrow)}</div>'
                f"<h1>{escape(title)}</h1>{lead}</div>", unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    page_header("Deep Researcher AI", title, subtitle, hero=True)


def badge(text: str, css: str) -> str:
    return f'<span class="dr-badge {css}">{escape(text)}</span>'


def origin_badge(origin: Origin) -> str:
    return badge(ORIGIN_LABELS[origin].upper(), ORIGIN_CLASS[origin])


def label_badge(label: str) -> str:
    return badge(label.upper(), f"dr-{label}")


def demo_banner(mode: str) -> None:
    if mode == "demo":
        st.warning("**Demo mode:** every source in this investigation is SYNTHETIC and fictional. Use it to explore the "
                   "workflow, not as evidence.", icon=":material/science:")


def source_header(source: Source, assessment: SourceAssessment | None, number: int | None = None) -> str:
    who = source.publisher or ", ".join(source.authors[:2]) or "Unknown publisher"
    when = source.published_date.strftime("%d %b %Y") if source.published_date else "date unknown"
    prefix = f"[{number}] " if number else ""
    quality = assessment.evidence_quality.value if assessment else "unknown"
    return f"{prefix}{source.title} · {who} · {when} · quality {quality}"


def link_for(source: Source):
    if not source.url:
        return None
    label = "Open source (synthetic placeholder URL)" if source.is_synthetic else "Open original source"
    return label, source.url


def flags_html(assessment: SourceAssessment | None) -> str:
    if not assessment or not assessment.flags:
        return ""
    return " ".join(badge(f.replace("_", " "), "dr-flag") for f in assessment.flags)
