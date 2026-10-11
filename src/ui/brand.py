"""Brand visuals rendered as HTML: the hero, the agents team tiles and the LangGraph workflow graph.

Images are served by Streamlit static serving (`static/` → `app/static/`, enabled in .streamlit/config.toml).
All colours come from the CSS tokens in `components.CSS`, so every visual follows the active light or dark theme.
Animations stop for visitors who ask their system for reduced motion.
"""
from __future__ import annotations

from html import escape
from urllib.parse import quote

HERO_IMAGE = "app/static/hero.jpg"
LOGO_IMAGE = "app/static/logo.png"
HERO_ALT = "The Deep Research Agent robot in a lab coat, surrounded by small helper robots in a research lab"


def _icon(name: str, size: int = 20) -> str:
    """An icon drawn as a CSS mask (see ICON_CSS): st.html strips inline <svg>, and a mask keeps theme colours."""
    return f'<i class="dr-i dr-i-{name}" aria-hidden="true" style="width:{size}px;height:{size}px"></i>'


ICONS = {
    "planner": '<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>',
    "retriever": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "source_evaluator": '<path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    "critical_analyst": '<path d="M12 3v18M7 21h10M5 7h14M5 7l-3 6a3 3 0 0 0 6 0zM19 7l-3 6a3 3 0 0 0 6 0z"/>',
    "gap_analyst": '<path d="M16 3h5v5M8 21H3v-5M21 3l-7 7M3 21l7-7"/>',
    "insight_generator": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.7 1 1.5 1 2.5h6c0-1 .2-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
    "data_visualizer": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "report_builder": '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "team": '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M15 14.5c3 .2 6 2.2 6 5.5"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
}



def _icon_css() -> str:
    rules = [".dr-i { display: inline-block; flex: none; background: currentColor; }"]
    for name, paths in ICONS.items():
        svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' "
               f"stroke-linecap='round' stroke-linejoin='round'>{paths}</svg>").replace('"', "'")
        url = 'url("data:image/svg+xml,' + quote(svg, safe=" '=:/,.-") + '")'
        rules.append(f".dr-i-{name} {{ -webkit-mask: {url} center / contain no-repeat; mask: {url} center / contain no-repeat; }}")
    return "\n".join(rules)
ICON_CSS = _icon_css()

# (agent, name, a couple of words) in pipeline order
TEAM = [
    ("planner", "Research Planner", "Breaks the question down"),
    ("retriever", "Contextual Retriever", "Finds the sources"),
    ("source_evaluator", "Source Evaluator", "Weighs credibility"),
    ("critical_analyst", "Critical Analyst", "Tests every claim"),
    ("gap_analyst", "Gap & Follow-up", "Chases what's missing"),
    ("insight_generator", "Insight Generator", "Connects the dots"),
    ("data_visualizer", "Data Visualizer", "Charts the evidence"),
    ("report_builder", "Report Builder", "Writes the cited report"),
]


def public_hero_html() -> str:
    """The lab-scene image in a glass frame with two floating facts."""
    return (f'<div class="dr-hero"><div class="dr-hero-frame"><img src="{HERO_IMAGE}" alt="{HERO_ALT}"></div>'
            f'<div class="dr-float a">{_icon("team", 18)}8 specialist agents</div>'
            f'<div class="dr-float b">{_icon("check", 18)}Every claim linked to its source</div></div>')


def landing_figure_html() -> str:
    return (f'<figure class="dr-figure"><img src="{HERO_IMAGE}" alt="{HERO_ALT}"><figcaption>'
            "<b>DR-01 and the team</b><span>8 agents · every claim cited</span></figcaption></figure>")


def signin_brand_html(heading: str, subheading: str) -> str:
    return (f'<div class="dr-signin-brand"><img src="{LOGO_IMAGE}" alt="Deep Research Agent">'
            f"<h1>{escape(heading)}</h1><p>{escape(subheading)}</p></div>")


def agents_team_html() -> str:
    """Eight tiles; a highlight passes from tile to tile in pipeline order while each icon's ring turns."""
    tiles = []
    for i, (agent, name, words) in enumerate(TEAM):
        violet = " violet" if i % 2 else ""
        tiles.append(
            f'<article class="dr-tile{violet}"><div class="relay" aria-hidden="true" style="animation-delay:{i * 0.8:.1f}s"></div>'
            f'<div class="dr-tile-top"><span class="dr-badge-icon"><span class="ring" aria-hidden="true" '
            f'style="animation-duration:{7 + (i * 5) % 6}s"></span><span class="core">{_icon(agent, 18)}</span></span>'
            f'<span class="dr-tile-num">{i + 1:02d}</span></div><div><h3>{escape(name)}</h3><p>{escape(words)}</p></div></article>')
    return ('<section aria-labelledby="team-title"><div class="dr-section-head"><h2 id="team-title">Get to know your Agents '
            'team</h2><p>Eight specialists, each with one job. They hand the work along, and work in parallel where '
            f'they can.</p></div><div class="dr-team">{"".join(tiles)}</div></section>')


# ------------------------------------------------------------------ workflow graph
# Seven columns: planner, retriever, source evaluator, critical analyst, gap & follow-up, the parallel synthesis
# column (insight generator on the rail, data visualizer below it), report builder. Column centres are at
# (i + 0.5) / 7 of the width; the parallel branch splits at 5/7 and joins at 6/7.
_GRAPH_NODES = [
    ("planner", "Research<br>Planner", "subquestions", ""),
    ("retriever", "Contextual<br>Retriever", "sources", ""),
    ("source_evaluator", "Source<br>Evaluator", "credibility", ""),
    ("critical_analyst", "Critical<br>Analyst", "claims", ""),
    ("gap_analyst", "Gap &amp;<br>Follow-up", "route", "decision"),
    ("insight_generator", "Insight<br>Generator", "insights", ""),
    ("report_builder", "Report<br>Builder", "cited report", "final"),
]


def _node(agent: str, label: str, output: str, kind: str, delay: float) -> str:
    out_class = {"decision": " v", "final": " final"}.get(kind, "")
    return (f'<li class="dr-node"><span class="dr-node-icon {kind}"><span class="relay" aria-hidden="true" '
            f'style="animation-delay:{delay:.1f}s"></span>{_icon(agent)}</span><b>{label}</b>'
            f'<span class="dr-out{out_class}">{output}</span></li>')


def _lanes(title: str, labels: list[str]) -> str:
    lanes = "".join(f'<span class="dr-lane"><i aria-hidden="true" style="animation-delay:-{n * 0.3:.1f}s"></i>'
                    f"<span>{escape(label)}</span></span>" for n, label in enumerate(labels))
    return f'<span>{escape(title)}</span>{lanes}'


def _vrow(agent: str, name: str, note: str, note_class: str = "", kind: str = "") -> str:
    return (f'<div class="dr-vrow"><span class="dr-node-icon {kind}">{_icon(agent, 18)}</span><span><b>{name}</b>'
            f'<small class="{note_class}">{note}</small></span></div>')


def workflow_graph_html() -> str:
    """The LangGraph workflow: stages, a flowing evidence rail, in-step fan-out, the parallel synthesis branch and
    the bounded follow-up loop. A desktop layout and a stacked phone layout (switched by CSS)."""
    nodes = "".join(_node(agent, label, output, kind, i * 0.9)
                    for i, (agent, label, output, kind) in enumerate(_GRAPH_NODES))
    dots = 'class="dr-abs dr-dots {cls}" aria-hidden="true"'
    horizontal = f"""<div class="dr-wf-h">
<div class="dr-abs dr-grid7" aria-hidden="true" style="inset:0">
<div class="dr-band" style="grid-column:1/span 1;margin-right:5px"></div>
<div class="dr-band" style="grid-column:2/span 4;margin:0 5px"></div>
<div class="dr-band" style="grid-column:6/span 2;margin-left:5px"></div></div>
<div class="dr-abs dr-grid7" style="left:0;right:0;top:12px">
<span class="dr-band-title" style="grid-column:1/span 1">1 · Plan</span>
<span class="dr-band-title" style="grid-column:2/span 4">2 · Gather &amp; verify</span>
<span class="dr-band-title" style="grid-column:6/span 2">3 · Synthesise</span></div>
<div class="dr-abs" aria-hidden="true" style="left:7.14%;right:7.14%;top:64px;height:4px;border-radius:4px;background:var(--dr-line)"></div>
<div {dots.format(cls="flow-x")} style="left:7.14%;right:7.14%;top:64px;height:4px"></div>
<div class="dr-abs dr-glow" aria-hidden="true" style="top:58px;width:9%;height:16px"></div>
<div class="dr-abs" style="left:64.29%;width:14.29%;top:36px;display:flex;justify-content:center"><span class="dr-pill">synthesise →</span></div>
<div {dots.format(cls="col flow-yd")} style="left:calc(71.43% - 2px);top:66px;width:4px;height:132px"></div>
<div {dots.format(cls="flow-x")} style="left:71.43%;width:14.29%;top:194px;height:4px"></div>
<div {dots.format(cls="col flow-yu")} style="left:calc(85.71% - 2px);top:66px;width:4px;height:132px"></div>
<span class="dr-abs dr-joint" aria-hidden="true" style="left:calc(71.43% - 7px);top:59px"></span>
<span class="dr-abs dr-joint" aria-hidden="true" style="left:calc(85.71% - 7px);top:59px"></span>
<div class="dr-abs" style="left:71.43%;width:14.29%;top:300px;display:flex;justify-content:center"><span class="dr-pill a">∥ run side by side</span></div>
<div class="dr-abs dr-lanes" style="left:14.29%;width:14.29%;top:164px">{_lanes("∥ parallel searches", ["OpenAlex", "arXiv", "Tavily web"])}</div>
<div class="dr-abs dr-lanes" style="left:42.86%;width:14.29%;top:164px">{_lanes("∥ one per source", ["source 1", "source 2", "source n"])}</div>
<div {dots.format(cls="v col flow-yd")} style="left:calc(64.29% - 2px);top:154px;width:4px;height:166px"></div>
<div {dots.format(cls="v flow-xr")} style="left:7.5%;width:56.79%;top:316px;height:4px"></div>
<div {dots.format(cls="v col flow-yu")} style="left:7.5%;top:272px;width:4px;height:48px"></div>
<div {dots.format(cls="v flow-x")} style="left:7.5%;width:7.5%;top:272px;height:4px"></div>
<div class="dr-abs" aria-hidden="true" style="left:calc(15% - 2px);top:267px;width:0;height:0;border-top:7px solid transparent;border-bottom:7px solid transparent;border-left:10px solid var(--dr-violet)"></div>
<div class="dr-abs" style="left:21.43%;width:35.71%;top:306px;display:flex;justify-content:center"><span class="dr-pill v">↺ follow-up round · bounded by budget</span></div>
<ol class="dr-abs dr-nodes dr-grid7" style="left:0;right:0;top:42px">{nodes}</ol>
<div class="dr-abs" style="left:71.43%;width:14.29%;top:172px">{_node("data_visualizer", "Data<br>Visualizer", "charts", "", 4.5).replace("<li", "<div").replace("</li>", "</div>")}</div>
</div>"""
    vertical = ('<div class="dr-wf-v"><div class="dr-abs dr-dots col flow-yd" aria-hidden="true" '
                'style="left:21px;top:40px;bottom:30px;width:4px"></div>'
                '<span class="dr-vband">1 · Plan</span>'
                + _vrow("planner", "Research Planner", "subquestions")
                + '<span class="dr-vband">2 · Gather &amp; verify</span>'
                + _vrow("retriever", "Contextual Retriever", "∥ searches OpenAlex, arXiv, Crossref and Tavily at once", "acc")
                + _vrow("source_evaluator", "Source Evaluator", "credibility")
                + _vrow("critical_analyst", "Critical Analyst", "∥ extracts claims from each source in parallel", "acc")
                + _vrow("gap_analyst", "Gap &amp; Follow-up", "↺ back to the Retriever while a gap is worth it", "vio",
                        "decision")
                + '<span class="dr-vband">3 · Synthesise</span><div class="dr-vpair">'
                + f'<div><span class="dr-node-icon">{_icon("insight_generator", 16)}</span>Insight Generator</div>'
                + f'<div><span class="dr-node-icon">{_icon("data_visualizer", 16)}</span>Data Visualizer</div>'
                + "<em>∥ run side by side</em></div>"
                + _vrow("report_builder", "Report Builder", "waits for both, then writes the cited report", "acc", "final")
                + "</div>")
    legend = ('<div class="dr-legend">'
              '<span><span class="dr-dots flow-x" style="width:26px;height:4px;background-size:9px 4px"></span>Evidence flow</span>'
              '<span><span style="display:flex;flex-direction:column;gap:3px"><span class="dr-dots flow-x" '
              'style="width:22px;height:3px;background-size:8px 3px"></span><span class="dr-dots flow-x" '
              'style="width:22px;height:3px;background-size:8px 3px"></span></span>Runs in parallel</span>'
              '<span><span class="dr-dots v flow-xr" style="width:26px;height:4px;background-size:9px 4px"></span>Follow-up loop</span>'
              '<span><span class="dr-diamond"></span>Decision</span></div>')
    return (f'<section class="dr-wf" aria-labelledby="wf-title"><div class="dr-wf-head"><div><h2 id="wf-title">How an '
            "investigation flows</h2><p>The LangGraph workflow behind every run. Work fans out where it can, and "
            f"follow-up rounds repeat only while a gap is worth pursuing.</p></div>{legend}</div>{horizontal}{vertical}</section>")
