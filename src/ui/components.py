"""Reusable UI pieces: provenance badges, labels, source cards and helpers."""
from __future__ import annotations

from html import escape

import streamlit as st

from src.models.evidence import ORIGIN_LABELS, Origin, Source, SourceAssessment

CSS = """
<style>
/* Docs-style skin (inspired by docs.composio.dev): hairlines, square corners, mono eyebrows, quiet surfaces. */
:root { --dr-line: color-mix(in srgb, currentColor 13%, transparent); --dr-muted: color-mix(in srgb, currentColor 62%, transparent);
        --dr-brand: #4560f2; --dr-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }
.block-container { padding-top: 2.6rem; max-width: 1180px; }
h1, h2, h3 { letter-spacing: -0.02em; }
h1 { letter-spacing: -0.03em; }
[data-testid="stCaptionContainer"], .dr-muted { color: var(--dr-muted); }
.dr-muted { font-size: .86rem; }

/* page header */
.dr-header { border-bottom: 1px solid var(--dr-line); padding-bottom: 1.1rem; margin-bottom: 1.4rem; }
.dr-eyebrow { font-family: var(--dr-mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
              color: var(--dr-brand); margin-bottom: .55rem; display: flex; align-items: center; gap: .5rem; }
.dr-eyebrow::before { content: ""; width: 7px; height: 7px; background: var(--dr-brand); display: inline-block; }
.dr-header h1 { font-size: 2.35rem; font-weight: 500; line-height: 1.08; margin: 0; padding: 0; }
.dr-header p { margin: .55rem 0 0 0; color: var(--dr-muted); font-size: 1.02rem; max-width: 760px; line-height: 1.5; }
.dr-hero h1 { font-size: 3rem; }

/* badges: small mono uppercase tags */
.dr-badge { display:inline-block; padding: 2px 7px; border-radius: 3px; font-family: var(--dr-mono); font-size: 10.5px;
            font-weight: 500; letter-spacing: .04em; text-transform: uppercase; margin-right: .3rem; vertical-align: middle;
            border: 1px solid color-mix(in srgb, currentColor 28%, transparent);
            background: color-mix(in srgb, currentColor 7%, transparent); }
.dr-demo { color: #c2410c; } .dr-live { color: #00957a; } .dr-cache { color: var(--dr-brand); } .dr-upload { color: #7c3aed; }
.dr-observed { color: #00957a; } .dr-inferred { color: var(--dr-brand); } .dr-speculative { color: #db2777; }
.dr-flag { color: #dc2626; }

/* metrics: mono labels, medium values */
[data-testid="stMetricLabel"] p { font-family: var(--dr-mono); font-size: 11px !important; letter-spacing: .06em;
                                  text-transform: uppercase; color: var(--dr-muted); }
[data-testid="stMetricValue"] { letter-spacing: -0.02em; }

/* navigation section labels and sidebar */
[data-testid="stNavSectionHeader"] { font-family: var(--dr-mono); font-size: 10.5px !important; letter-spacing: .08em;
                                     text-transform: uppercase; color: var(--dr-muted); }
[data-testid="stSidebarNavLink"] { border-radius: 0; }
[data-testid="stSidebarNavLink"][aria-current="page"] { box-shadow: inset 2px 0 0 var(--dr-brand); }

/* quieter widgets */
[data-testid="stExpander"] summary p { font-weight: 500; }
[data-testid="stAlert"] { border: 1px solid var(--dr-line); }
.stButton button, .stDownloadButton button, .stLinkButton a { font-weight: 500; }
hr { border-color: var(--dr-line) !important; }

/* numbered step labels (agent cards) */
.dr-step { font-family: var(--dr-mono); font-size: 11px; color: var(--dr-brand); letter-spacing: .06em; margin-bottom: -.4rem; }

/* sidebar capability rows */
.dr-cap { display: grid; grid-template-columns: 10px 92px 1fr; align-items: center; gap: .45rem; padding: .32rem 0;
          border-bottom: 1px solid var(--dr-line); font-size: .84rem; }
.dr-cap-k { font-family: var(--dr-mono); font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--dr-muted); }
.dr-cap-v { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dr-dot { width: 7px; height: 7px; display: inline-block; }
.dr-dot.on { background: #00957a; } .dr-dot.off { background: transparent; border: 1px solid var(--dr-muted); }
</style>
"""

ORIGIN_CLASS = {Origin.DEMO: "dr-demo", Origin.LIVE: "dr-live", Origin.CACHE: "dr-cache", Origin.UPLOAD: "dr-upload"}
AGREEMENT_COLORS = {"strong": "green", "moderate": "blue", "single_source": "gray", "mixed": "orange", "contested": "red"}
QUALITY_COLORS = {"high": "green", "medium": "blue", "low": "orange", "unknown": "gray"}
STATUS_ICON = {"pending": "○", "running": "◐", "completed": "●", "failed": "✕", "skipped": "–"}
AGENT_TITLES = {"planner": "Research Planner", "retriever": "Contextual Retriever", "source_evaluator": "Source Evaluation",
                "critical_analyst": "Critical Analysis", "gap_analyst": "Gap & Follow-up",
                "insight_generator": "Insight Generation", "report_builder": "Report Builder",
                "orchestrator": "Orchestrator"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(eyebrow: str, title: str, subtitle: str = "", hero: bool = False) -> None:
    """Docs-style header: mono eyebrow, medium-weight title, muted lead paragraph, hairline rule."""
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
