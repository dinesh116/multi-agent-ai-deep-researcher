"""Reusable UI pieces: provenance badges, labels, source cards and helpers."""
from __future__ import annotations

from html import escape

import streamlit as st

from src.models.evidence import ORIGIN_LABELS, Origin, Source, SourceAssessment

CSS = """
<style>
.block-container { padding-top: 2rem; max-width: 1280px; }
.dr-hero { padding: 1.3rem 1.5rem; border-radius: 16px; margin-bottom: 1rem;
           background: linear-gradient(135deg, rgba(99,102,241,.16), rgba(14,165,233,.12));
           border: 1px solid rgba(127,127,127,.18); }
.dr-hero h1 { margin: 0 0 .25rem 0; font-size: 1.9rem; } .dr-hero p { margin: 0; opacity: .85; }
.dr-badge { display:inline-block; padding:.05rem .5rem; border-radius:999px; font-size:.72rem; font-weight:600;
            margin-right:.3rem; vertical-align:middle; }
.dr-demo { background: rgba(245,158,11,.18); color: rgb(180,83,9); }
.dr-live { background: rgba(16,185,129,.16); color: rgb(4,120,87); }
.dr-cache { background: rgba(59,130,246,.15); color: rgb(37,99,235); }
.dr-upload { background: rgba(139,92,246,.16); color: rgb(109,40,217); }
.dr-observed { background: rgba(16,185,129,.16); color: rgb(4,120,87); }
.dr-inferred { background: rgba(59,130,246,.15); color: rgb(37,99,235); }
.dr-speculative { background: rgba(236,72,153,.15); color: rgb(190,24,93); }
.dr-flag { background: rgba(239,68,68,.13); color: rgb(185,28,28); }
.dr-muted { opacity:.72; font-size:.88rem; }
</style>
"""

ORIGIN_CLASS = {Origin.DEMO: "dr-demo", Origin.LIVE: "dr-live", Origin.CACHE: "dr-cache", Origin.UPLOAD: "dr-upload"}
AGREEMENT_COLORS = {"strong": "green", "moderate": "blue", "single_source": "gray", "mixed": "orange", "contested": "red"}
QUALITY_COLORS = {"high": "green", "medium": "blue", "low": "orange", "unknown": "gray"}
STATUS_ICON = {"pending": "⚪", "running": "🔵", "completed": "✅", "failed": "❌", "skipped": "⏭️"}
AGENT_TITLES = {"planner": "Research Planner", "retriever": "Contextual Retriever", "source_evaluator": "Source Evaluation",
                "critical_analyst": "Critical Analysis", "gap_analyst": "Gap & Follow-up",
                "insight_generator": "Insight Generation", "report_builder": "Report Builder",
                "orchestrator": "Orchestrator"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="dr-hero"><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>', unsafe_allow_html=True)


def badge(text: str, css: str) -> str:
    return f'<span class="dr-badge {css}">{escape(text)}</span>'


def origin_badge(origin: Origin) -> str:
    return badge(ORIGIN_LABELS[origin].upper(), ORIGIN_CLASS[origin])


def label_badge(label: str) -> str:
    return badge(label.upper(), f"dr-{label}")


def demo_banner(mode: str) -> None:
    if mode == "demo":
        st.warning("**Demo mode:** every source in this investigation is SYNTHETIC and fictional. Use it to explore the "
                   "workflow, not as evidence.", icon="🧪")


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
