"""Reusable UI pieces for the "Synthora"-style skin: cards, tags, headers, provenance badges and helpers.

Layout notes: Streamlit gives every keyed container the CSS class `st-key-<key>`, so cards are containers whose key
starts with "card" and are styled by `[class*="st-key-card"]`. Widgets that need a special look (demo question
cards, depth cards, suggestion pills) are targeted the same way through their key.
"""
from __future__ import annotations

from datetime import datetime
from html import escape

import streamlit as st

from src.models.evidence import ORIGIN_LABELS, Origin, Source, SourceAssessment

CSS = """
<style>
:root { --ink:#1d2038; --muted:#777b91; --line:#e9eaf1; --paper:#f7f7fb; --violet:#7159dc; --violet-2:#9a78f4;
        --navy:#111329; --green:#27876e; --shadow:0 10px 35px #25234a0b; --soft:#f1effd; }
.block-container { padding-top: 4.5rem; max-width: 1240px; }  /* clears the 3.75rem sticky header */
h1, h2, h3 { letter-spacing: -0.02em; color: var(--ink); }
h1 em, h2 em, .ds-title em { font-style: normal; color: #7459d5; }
[data-testid="stCaptionContainer"], .ds-muted { color: var(--muted); }
[data-testid="stHeader"] { background: #f7f7fbd9; backdrop-filter: blur(12px); }
/* cards: keyed containers */
[class*="st-key-card"] { background:#fff; border:1px solid #ececf3; border-radius:12px; box-shadow:var(--shadow);
                         padding: 18px 22px; }
[class*="st-key-card-flat"] { box-shadow:none; }
.ds-card { background:#fff; border:1px solid #ececf3; border-radius:12px; box-shadow:var(--shadow); padding:18px 22px; }
/* eyebrow + page heading */
.ds-eyebrow { font-size:10.5px; font-weight:700; letter-spacing:1.6px; color:#7660d4; text-transform:uppercase;
              display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.ds-eyebrow i { display:inline-block; width:7px; height:7px; border-radius:50%; background:#8c70e6; }
.ds-heading { margin: 0 0 1.3rem 0; }
.ds-title { font-family: Manrope, sans-serif; font-weight:800; font-size: 2rem; letter-spacing:-.4px; line-height:1.28;
            margin:.25rem 0 .55rem 0; color: var(--ink); }
.ds-report-head { margin-bottom: 1.6rem; }
.ds-report-head .ds-eyebrow { margin-bottom:16px; }
.ds-report-head .ds-title { margin-bottom:16px; }
.ds-report-head .ds-meta { row-gap:10px; }
[data-baseweb="tab-list"] { gap:24px; flex-wrap:wrap; }
.ds-report-head .ds-title { font-size:1.65rem; font-weight:700; letter-spacing:-.2px; line-height:1.35; max-width: 900px; }
.ds-sub { color:#85889a; font-size:.95rem; margin:0; max-width: 760px; line-height:1.55; }
.ds-hero-title { font-family: Manrope, sans-serif; font-weight:800; font-size: clamp(32px,3.6vw,48px); line-height:1.12;
                 letter-spacing:-2px; margin: 1rem 0; color:#181a31; }
.ds-hero-title em { font-style:normal; color:#7459d5; }
.ds-lead { max-width:470px; color:#777b8f; font-size:1rem; line-height:1.75; }
.ds-label { font-size:10px; letter-spacing:1px; color:#85879a; font-weight:700; text-transform:uppercase; margin: 2px 0 6px 0; }
/* tags & badges */
.ds-tag { display:inline-block; border-radius:4px; padding:3px 7px; font-size:9.5px; font-weight:700; letter-spacing:.5px;
          text-transform:uppercase; vertical-align:middle; }
.ds-complete { background:#e9f6f0; color:#39906f; } .ds-running { background:#f2edff; color:#795bd2; }
.ds-failed { background:#fdecec; color:#c0392b; } .ds-draft { background:#f2f2f5; color:#858795; }
.ds-demo-tag { background:#fff3dc; color:#a7741d; } .ds-live-tag { background:#e4f1ff; color:#3d78b4; }
.dr-badge { display:inline-block; padding:2px 7px; border-radius:4px; font-size:10px; font-weight:700; letter-spacing:.4px;
            text-transform:uppercase; margin-right:.3rem; vertical-align:middle; background:#f5f4fa; }
.dr-demo { color:#a7741d; background:#fff3dc; } .dr-live { color:#27876e; background:#e7f5ef; }
.dr-cache { color:#6751cc; background:#f1effd; } .dr-upload { color:#9a60bd; background:#f5ebfa; }
.dr-observed { color:#27876e; background:#e7f5ef; } .dr-inferred { color:#6751cc; background:#f1effd; }
.dr-speculative { color:#c0568c; background:#fde9f3; } .dr-flag { color:#c0392b; background:#fdecec; }
.dr-muted { color: var(--muted); font-size:.86rem; }
/* demo banner */
.ds-banner { display:flex; align-items:center; gap:11px; margin:0 0 18px; padding:10px 14px; border:1px solid #e6e0fb;
             background:#f4f1ff; color:#7158cf; border-radius:8px; font-size:11px; font-weight:700; letter-spacing:.6px; }
.ds-banner span { font-weight:400; letter-spacing:0; color:#77768b; }
/* buttons */
[data-testid="stBaseButton-primary"] { border:0; background:linear-gradient(105deg,#7059dc,#8d69e9);
                                       box-shadow:0 5px 12px #755bdc2b; font-weight:700; }
[data-testid="stBaseButton-primary"]:hover { filter:brightness(1.05); transform:translateY(-1px); }
[data-testid="stBaseButton-secondary"] { font-weight:600; color:#403e60; border-color:#dfdeea; }
[data-testid="stBaseButton-secondary"]:hover { border-color:#a89ae5; background:#faf9ff; color:#403e60; }
.stButton button, .stDownloadButton button { font-weight:600; }
/* tabs like the wireframe: underline, violet active */
[data-testid="stTab"] p { color:#858798; }
[data-testid="stTab"][aria-selected="true"] p { color:#694fce; font-weight:700; }
/* sidebar */
[data-testid="stSidebar"] { border-right:1px solid var(--line); }
[data-testid="stSidebarNavLink"] { border-radius:7px; }
[data-testid="stSidebarNavLink"][aria-current="page"] { background:#f1effd; }
[data-testid="stSidebarNavLink"][aria-current="page"] span { color:#644dcc; font-weight:700; }
[data-testid="stNavSectionHeader"] { font-size:10px !important; font-weight:700; letter-spacing:1.25px; color:#a2a4b1;
                                     text-transform:uppercase; }
.st-key-side_new button { background:#111329; color:#fff; border:0; justify-content:flex-start; padding:10px 15px; }
.st-key-side_new button:hover { background:#1d2038; color:#fff; }
[class*="st-key-recent_"] { margin-bottom: -0.75rem; }
[class*="st-key-recent_"] button { border:0; background:transparent; justify-content:flex-start; color:#6e7187;
                                   font-weight:500; padding:6px 9px; min-height:0; }
[class*="st-key-recent_"] button:hover { background:#f7f6fc; color:#644dcc; }
[class*="st-key-recent_"] button p { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:12.5px; }
.ds-profile { display:flex; align-items:center; gap:10px; padding:6px 2px; }
.ds-avatar { width:34px; height:34px; display:grid; place-items:center; border-radius:50%; background:#e9e5fa;
             color:#6754c4; font-weight:700; font-size:12px; flex:0 0 34px; overflow:hidden; }
.ds-avatar img { width:100%; height:100%; object-fit:cover; }
.ds-profile b { display:block; font-size:12.5px; } .ds-profile small { display:block; color:#999bad; font-size:11px; }
/* selectable cards built from radios (demo questions, depth): each option wrapper becomes a card */
[class*="st-key-pick_"] [data-testid="stElementContainer"], [class*="st-key-pick_"] .stRadio { width: 100%; }
[class*="st-key-pick_"] [role="radiogroup"] { gap: 9px; width: 100%; }
[class*="st-key-pick_"] [role="radiogroup"] > div { flex: 1 1 0; background:#fff; border:1px solid #e6e5ed; border-radius:8px;
                                                   padding:11px 14px; margin:0; cursor:pointer; transition:.15s; }
[class*="st-key-pick_"] [role="radiogroup"] > div:hover { border-color:#c9beef; }
[class*="st-key-pick_"] [role="radiogroup"] > div[data-selected="true"] { border-color:#9d89e2; background:#f9f7ff;
                                                                         box-shadow: inset 0 0 0 1px #9d89e2; }
[class*="st-key-pick_"] [data-testid="stRadioOption"] { width:100%; margin:0; }
[class*="st-key-pick_"] [data-testid="stRadioOption"] > div > div:first-child { display:none; }  /* hide the dot */
[class*="st-key-pick_"] [data-testid="stRadioOption"] p { font-weight:600; font-size:.92rem; color:#25283e; }
[class*="st-key-pick_"] [data-testid="stRadioCaption"] { padding-left:0; margin-left:0; }
[class*="st-key-pick_"] [data-testid="stRadioCaption"] p { font-size:11.5px; }
.st-key-pick_demo [role="radiogroup"] { flex-direction: column; align-items: stretch; }
.st-key-pick_demo [role="radiogroup"] > div { width: 100%; }
.st-key-pick_demo [role="radiogroup"] > div[data-selected="true"] [data-testid="stRadioOption"] p::before {
  content:"✓  "; color:#7159dc; }
/* suggestion pills */
[class*="st-key-sugg_"] button { border:1px solid #e8e7ef; background:#fafaff; border-radius:20px; padding:4px 12px;
                                 color:#676a7e; font-weight:500; min-height:0; }
[class*="st-key-sugg_"] button:hover { background:#f1edff; border-color:#cfc5f2; color:#674fc4; }
[class*="st-key-sugg_"] button p { font-size:12px; }
/* hero visual (landing) */
.ds-visual { position:relative; height:400px; display:grid; place-items:center;
             background:radial-gradient(ellipse,#eee9ff 0%,#f4f1ff 37%,transparent 69%); }
.ds-orb { position:absolute; border:1px solid #d8d0f6; border-radius:50%; transform:rotate(-22deg); }
.ds-orb.one { height:275px; width:420px; } .ds-orb.two { height:345px; width:490px; border-color:#e5e0f8; }
.ds-vcard { position:relative; z-index:2; width:min(390px,90%); border:1px solid #e7e5f2; background:#fff; border-radius:13px;
            padding:20px 22px; box-shadow:0 20px 60px #49406e1c; }
.ds-vtop { font-size:9px; font-weight:700; letter-spacing:1px; color:#77798c; }
.ds-dot { display:inline-block; background:#41bb94; width:7px; height:7px; border-radius:50%; margin-right:6px; }
.ds-vlive { float:right; color:#3a9c7b; }
.ds-vcard h3 { font:700 15px/1.5 Manrope, sans-serif; margin:18px 0; }
.ds-vrow { border-top:1px solid #f0eff5; display:flex; align-items:center; padding:10px 0; font-size:12px; gap:10px; }
.ds-vrow b { margin-left:auto; color:#7e7e91; font-size:11px; font-weight:500; }
.ds-vfoot { border-top:1px solid #f0eff5; padding-top:12px; color:#888a9b; font-size:11px; display:flex; justify-content:space-between; }
.ds-chip { position:absolute; z-index:3; background:#fff; border:1px solid #eeedf4; border-radius:8px; padding:10px 13px;
           box-shadow:0 7px 25px #3b376116; font-size:11px; font-weight:700; color:#6254b5; }
.ds-chip.a { top:4px; right:-6px; } .ds-chip.b { bottom:2px; left:-6px; color:#4b8175; }
.ds-foot { display:flex; justify-content:space-between; border-top:1px solid #e8e7ef; padding:18px 0; color:#999aaa;
           font-size:10px; letter-spacing:1px; margin-top:8px; }
.ds-foot div { display:flex; gap:30px; color:#73768b; font-size:12px; letter-spacing:0; }
.ds-proof { display:flex; align-items:center; gap:13px; margin-top:26px; font-size:12px; }
.ds-proof small { display:block; color:#9294a3; margin-top:3px; font-size:11px; }
.ds-avatars { display:flex; } .ds-avatars span { width:26px; height:26px; display:grid; place-items:center; margin-right:-6px;
  border:2px solid #fff; border-radius:50%; background:#d9d1f5; color:#5949af; font-size:10px; font-weight:700; }
.ds-avatars span:nth-child(2) { background:#c9e3dc; color:#387665; } .ds-avatars span:nth-child(3) { background:#f1d8ca; color:#875640; }
.ds-avatars span:nth-child(4) { background:#eeeef4; color:#72768b; }
.ds-feature { padding:22px; border:1px solid var(--line); background:#fff; border-radius:11px; height:100%; }
.ds-feature h3 { font:700 15px Manrope, sans-serif; margin:12px 0 6px; }
.ds-feature p { font-size:13px; line-height:1.7; color:#84879a; margin:0; }
/* agent icons, rows and activity timeline */
.ds-icon { width:28px; height:28px; border-radius:8px; display:grid; place-items:center; font-size:13px; flex:0 0 28px; }
.ds-purple { background:#eee9ff; color:#7858d2; } .ds-blue { background:#e4f1ff; color:#4181bf; }
.ds-green { background:#e3f5ed; color:#31946d; } .ds-indigo { background:#e8e8ff; color:#6864c5; }
.ds-gold { background:#fff2d9; color:#b78127; } .ds-pink { background:#fde9f3; color:#c0568c; } .ds-teal { background:#e0f4f3; color:#389592; }
.ds-agent { display:flex; align-items:center; gap:11px; border-top:1px solid #f0eff4; padding:11px 0; }
.ds-agent:first-of-type { border-top:0; }
.ds-agent > div { min-width:0; } .ds-agent b { display:block; font-size:13px; }
.ds-agent small { display:block; font-size:11.5px; color:#9092a0; margin-top:3px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ds-state { margin-left:auto; font-size:11px; color:#9294a4; white-space:nowrap; }
.ds-agent.done .ds-state { color:#328e70; } .ds-agent.working .ds-state { color:#7559d3; font-weight:700; }
.ds-agent.failed .ds-state { color:#c0392b; }
.ds-act { position:relative; display:flex; gap:11px; padding:12px 0 6px 4px; }
.ds-act:not(:last-child)::before { content:''; position:absolute; top:24px; left:7px; bottom:-8px; width:1px; background:#e9e6f4; }
.ds-act > i { position:relative; z-index:1; width:8px; height:8px; flex:0 0 8px; background:#8d76db; border:2px solid #eee9fb;
              border-radius:50%; margin-top:4px; }
.ds-act.current > i { background:#55b391; }
.ds-act b { display:block; font-size:12px; } .ds-act small { display:block; font-size:11px; color:#898b9c; margin:3px 0; }
.ds-act time { font-size:10px; color:#aaa; }
.ds-progress { height:6px; background:#eeeaf8; border-radius:6px; margin-top:16px; overflow:hidden; }
.ds-progress i { display:block; height:100%; background:linear-gradient(90deg,#7159dc,#a582ee); border-radius:6px; }
.ds-progress-cap { display:flex; justify-content:space-between; margin-top:7px; font-size:11px; color:#888a9c; }
.ds-meta { display:flex; flex-wrap:wrap; align-items:center; row-gap:4px; color:#87899a; font-size:13px; line-height:1.6; }
.ds-meta span + span::before { content:"·"; margin:0 10px; color:#c2c3ce; }
.ds-live { font-size:10.5px; color:#328f72; background:#e7f5ef; border-radius:20px; padding:7px 12px; font-weight:700;
           display:inline-flex; align-items:center; gap:7px; }
.ds-live i { width:7px; height:7px; border-radius:50%; background:#41bb94; display:inline-block; }
/* results */
.ds-finding { display:flex; gap:12px; border-top:1px solid #f0eff4; padding:12px 0; }
.ds-finding > span { font:700 12px Manrope, sans-serif; color:#9079de; }
.ds-finding p { font-size:13.5px; line-height:1.65; color:#676a7b; margin:0; } .ds-finding b { color:#303249; }
.ds-stat { display:flex; justify-content:space-between; font-size:13px; color:#777a8e; padding:6px 0; }
.ds-stat b { color:#303249; } .ds-stat .ok { color:#328e70; } .ds-stat .warn { color:#b78127; }
.ds-pills { display:flex; flex-wrap:wrap; gap:6px; padding-bottom:4px; } .ds-pills span { background:#f5f3fb; color:#77718c; padding:5px 8px;
            border-radius:5px; font-size:11.5px; }
.ds-meter { height:6px; background:#efedf6; border-radius:6px; margin:16px 0 7px; } .ds-meter i { display:block; height:100%;
            background:#62b798; border-radius:6px; }
.ds-num { display:block; font:700 26px Manrope, sans-serif; color:#e0daf4; margin-bottom:8px; }
/* library rows */
.ds-row-title b { display:block; font-size:14px; color:#34364b; } .ds-row-title small { display:block; font-size:12px; color:#9698a6; margin-top:3px; }
.ds-cell { font-size:13px; color:#727589; padding-top:6px; }
.ds-colhead { font-size:10px; letter-spacing:.8px; color:#9a9baa; font-weight:700; padding:4px 0 0 0; }
[data-testid="stMetricLabel"] p { font-size:11px !important; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
[data-testid="stExpander"] details { border-radius:10px; background:#fff; }
[data-testid="stExpander"] summary p { font-weight:600; }
hr { border-color: var(--line) !important; }
</style>
"""

ORIGIN_CLASS = {Origin.DEMO: "dr-demo", Origin.LIVE: "dr-live", Origin.CACHE: "dr-cache", Origin.UPLOAD: "dr-upload"}
AGREEMENT_COLORS = {"strong": "green", "moderate": "blue", "single_source": "gray", "mixed": "orange", "contested": "red"}
QUALITY_COLORS = {"high": "green", "medium": "blue", "low": "orange", "unknown": "gray"}
STATUS_ICON = {"pending": "○", "running": "◐", "completed": "●", "failed": "✕", "skipped": "–"}
AGENT_TITLES = {"planner": "Research Planner", "retriever": "Contextual Retriever", "source_evaluator": "Source Evaluation",
                "critical_analyst": "Critical Analysis", "gap_analyst": "Gap & Follow-up",
                "insight_generator": "Insight Generation", "data_visualizer": "Data Visualization", "report_builder": "Report Builder",
                "orchestrator": "Orchestrator"}
# icon, colour class, what the agent does (shown while it is queued)
AGENT_INFO = {
    "planner": ("⌕", "ds-purple", "Splits the question into research threads and queries"),
    "retriever": ("◎", "ds-blue", "Searches web, academic and document sources"),
    "source_evaluator": ("▤", "ds-indigo", "Rates relevance, credibility and freshness"),
    "critical_analyst": ("⌁", "ds-green", "Links claims to passages and finds contradictions"),
    "gap_analyst": ("◈", "ds-gold", "Finds gaps and decides whether to dig deeper"),
    "insight_generator": ("✧", "ds-pink", "Finds patterns, implications and hypotheses"),
    "data_visualizer": ("▥", "ds-blue", "Charts extracted values and links every point to its source"),
    "report_builder": ("✓", "ds-teal", "Writes the cited report and validates citations"),
}
STATUS_TAG = {"completed": ("Complete", "ds-complete"), "running": ("In progress", "ds-running"),
              "queued": ("Queued", "ds-running"), "failed": ("Failed", "ds-failed"),
              "cancelled": ("Stopped", "ds-draft")}
DEPTH_LABELS = {"quick": "Quick", "standard": "Standard", "deep": "Deep"}


def inject_css() -> None:
    # no blank lines allowed inside CSS: Markdown would end the <style> block at the first one
    st.markdown(CSS, unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def eyebrow(text: str, center: bool = False) -> str:
    style = ' style="justify-content:center"' if center else ""
    return f'<div class="ds-eyebrow"{style}><i></i>{escape(text)}</div>'


def page_header(eyebrow_text: str, title: str, subtitle: str = "", accent: str = "") -> None:
    """Wireframe page heading: dotted eyebrow, bold title with an optional violet accent, muted lead."""
    accent_html = f" <em>{escape(accent)}</em>" if accent else ""
    lead = f'<p class="ds-sub">{escape(subtitle)}</p>' if subtitle else ""
    html(f'<div class="ds-heading">{eyebrow(eyebrow_text)}<div class="ds-title">{escape(title)}{accent_html}</div>{lead}</div>')


def card(key: str, flat: bool = False):
    """A white rounded card (a keyed container styled via CSS)."""
    return st.container(key=f"card-{'flat-' if flat else ''}{key}")


def tag(text: str, css: str) -> str:
    return f'<span class="ds-tag {css}">{escape(text)}</span>'


def status_tag(status: str) -> str:
    label, css = STATUS_TAG.get(status, (status, "ds-draft"))
    return tag(label, css)


def mode_tag(mode: str) -> str:
    return tag("Demo", "ds-demo-tag") if mode == "demo" else tag("Live", "ds-live-tag")


def ago(when: datetime | None) -> str:
    if when is None:
        return ""
    seconds = (datetime.now() - when).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    if seconds < 172800:
        return "yesterday"
    return f"{when:%b %d, %Y}"


def badge(text: str, css: str) -> str:
    return f'<span class="dr-badge {css}">{escape(text)}</span>'


def origin_badge(origin: Origin) -> str:
    return badge(ORIGIN_LABELS[origin].upper(), ORIGIN_CLASS[origin])


def label_badge(label: str) -> str:
    return badge(label.upper(), f"dr-{label}")


def demo_banner(mode: str) -> None:
    if mode == "demo":
        html('<div class="ds-banner">DEMO PREVIEW <span>Synthetic sample dataset: every source is fictional. Use it to '
             'explore the workflow, not as evidence. Sign in and switch to Live research for real sources.</span></div>')


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
