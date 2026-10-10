"""Landing-page graphics: the LangGraph workflow diagram and the agent team cards (theme-aware HTML/SVG).

Colours come from the CSS variables injected by `src.ui.theme`, so both graphics follow the active theme.
On phones the wide diagram is swapped for a vertical step list (see the responsive rules in theme.py).
"""
from __future__ import annotations

ICONS = {
    "checks": "M10 6h10M10 12h10M10 18h10M3.5 6l1.5 1.5L7.5 5M3.5 12l1.5 1.5 2.5-2.5M3.5 18l1.5 1.5 2.5-2.5",
    "search": "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4",
    "shield": "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4",
    "scale": "M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z",
    "branch": "M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9",
    "bulb": "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z",
    "file": "M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8zM14 3v5h5M9 13h6M9 17h6",
    "chat": "M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z",
}

# (number, name, icon, description, uses an LLM when configured)
AGENT_TEAM = [
    ("01", "Research Planner", "checks", "Breaks your question into prioritised subquestions, search queries and "
                                         "completion criteria.", True),
    ("02", "Contextual Retriever", "search", "Searches web, academic and uploaded sources, removes duplicates and "
                                             "follows cited leads.", False),
    ("03", "Source Evaluator", "shield", "Rates relevance, freshness and independence; flags bias, reprints and "
                                         "injected instructions.", False),
    ("04", "Critical Analyst", "scale", "Links claims to exact passages, builds the evidence matrix and surfaces "
                                        "contradictions.", True),
    ("05", "Gap Analyst", "branch", "Finds weak or unanswered areas and decides whether another research round is "
                                    "worth it.", False),
    ("06", "Insight Generator", "bulb", "Turns evidence into findings, trends and hypotheses, each labelled observed, "
                                        "inferred or speculative.", True),
    ("07", "Report Builder", "file", "Writes a structured report with inline citations, each checked for "
                                     "traceability.", True),
    ("08", "Research Q&A", "chat", "Answers your follow-up questions from the underlying evidence, with citations.", True),
]

# Workflow nodes: (number label, name, x, y, decides). Coordinates are in the SVG's 1040 x 304 viewBox.
_NODE_W, _NODE_H = 148, 64
_NODES = [
    ("01", "Planner", 88, 108, False), ("02", "Retriever", 276, 108, False), ("03", "Source evaluation", 464, 108, False),
    ("04", "Critical analysis", 652, 108, False), ("05 · DECIDES", "Gap & follow-up", 840, 108, True),
    ("06", "Insights", 840, 220, False), ("07", "Report", 652, 220, False),
]
_STEPS = ["Planner", "Retriever", "Source evaluation", "Critical analysis", "Gap & follow-up", "Insights", "Report"]


def _node(num: str, name: str, x: int, y: int, decides: bool) -> str:
    fill, stroke, num_color = (("var(--dr-tint)", "var(--dr-accent)", "var(--dr-accent)") if decides else
                               ("var(--dr-node)", "var(--dr-border)", "var(--dr-faint)"))
    return (f'<g><rect x="{x}" y="{y}" width="{_NODE_W}" height="{_NODE_H}" rx="14" style="fill:{fill};stroke:{stroke};'
            f'stroke-width:1" filter="url(#dr-soft)"/>'
            f'<text x="{x + 14}" y="{y + 26}" style="font:500 11px var(--dr-mono);fill:{num_color};letter-spacing:.04em">'
            f'{num}</text><text x="{x + 14}" y="{y + 46}" style="font:600 13.5px Geist, ui-sans-serif, system-ui, '
            f'sans-serif;fill:var(--dr-text)">{name.replace("&", "&amp;")}</text></g>')


def _terminal(cx: int, cy: int, label: str, fill: str, text: str) -> str:
    return (f'<circle cx="{cx}" cy="{cy}" r="24" style="fill:{fill}"/><text x="{cx}" y="{cy + 4}" text-anchor="middle" '
            f'style="font:500 10px var(--dr-mono);letter-spacing:.06em;fill:{text}">{label}</text>')


def workflow_html() -> str:
    """The LangGraph workflow as a scalable SVG, plus a vertical step list shown on narrow screens instead."""
    line, accent = "stroke:var(--dr-line);stroke-width:2;fill:none", "stroke:var(--dr-accent);stroke-width:2;fill:none"
    edges = [
        f'<path d="M48 140 H83" style="{line}" marker-end="url(#dr-arrow)"/>',
        f'<path d="M236 140 H271" style="{line}" marker-end="url(#dr-arrow)"/>',
        f'<path d="M424 140 H459" style="{line}" marker-end="url(#dr-arrow)"/>',
        f'<path d="M612 140 H647" style="{line}" marker-end="url(#dr-arrow)"/>',
        f'<path d="M800 140 H835" style="{line}" marker-end="url(#dr-arrow)"/>',
        f'<path d="M914 172 V215" style="{line}" marker-end="url(#dr-arrow)"/>',
        f'<path d="M840 252 H805" style="{line}" marker-end="url(#dr-arrow)"/>',
        f'<path d="M652 252 H617" style="{line}" marker-end="url(#dr-arrow)"/>',
        f'<path d="M914 108 V52 Q914 44 906 44 H358 Q350 44 350 52 V103" style="{accent};stroke-dasharray:6 6" '
        'marker-end="url(#dr-arrow-accent)"/>',
    ]
    labels = ('<text x="632" y="34" text-anchor="middle" style="font:500 11px var(--dr-mono);letter-spacing:.06em;'
              'fill:var(--dr-accent)">FOLLOW-UP ROUND · BOUNDED</text>'
              '<text x="926" y="200" style="font:500 11px var(--dr-mono);letter-spacing:.06em;fill:var(--dr-faint)">'
              'SYNTHESISE</text>')
    defs = ('<defs><marker id="dr-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" style="fill:var(--dr-line)"/></marker>'
            '<marker id="dr-arrow-accent" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" style="fill:var(--dr-accent)"/></marker>'
            '<filter id="dr-soft" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="4" '
            'stdDeviation="6" flood-opacity=".12"/></filter></defs>')
    svg = ('<svg viewBox="0 0 1040 304" role="img" aria-label="Research workflow: planner, retriever, source evaluation, '
           'critical analysis, then gap and follow-up, which either loops back to the retriever for a bounded follow-up '
           'round or continues to insights and the report.">' + defs + "".join(edges)
           + _terminal(24, 140, "START", "var(--dr-accent)", "var(--dr-on-accent)")
           + "".join(_node(*n) for n in _NODES)
           + _terminal(588, 252, "END", "var(--dr-text)", "var(--dr-bg)") + labels + "</svg>")
    steps = []
    for i, name in enumerate(_STEPS, start=1):
        decides = i == 5
        note = "<em>DECIDES</em>" if decides else ("<em>LOOP TARGET</em>" if i == 2 else "")
        link = '<div class="dr-link" aria-hidden="true"></div>' if i < len(_STEPS) else ""
        steps.append(f'<li><div class="dr-node{" decide" if decides else ""}"><small>0{i}</small>'
                     f'{name.replace("&", "&amp;")}{note}</div>{link}</li>')
    legend = ('<div class="dr-legend"><span><i style="border-top:2px solid var(--dr-line)"></i>Agent hand-off</span>'
              '<span><i style="border-top:2px dashed var(--dr-accent)"></i>Follow-up loop (bounded by your depth '
              'setting)</span><span><i style="width:12px;height:12px;border-radius:4px;border:1px solid var(--dr-accent);'
              'background:var(--dr-tint)"></i>Routing decision</span></div>')
    note = ('<p class="dr-flow-note">When evidence is thin, step 05 sends targeted follow-up queries back to step 02. '
            'Rounds are capped by your depth setting.</p>')
    return (f'<div class="dr-flow-wide">{svg}</div><ol class="dr-flow-steps">{"".join(steps)}</ol>{note}{legend}')


def agent_cards_html() -> str:
    cards = []
    for num, name, icon, desc, llm in AGENT_TEAM:
        tag = '<span class="dr-pill llm">LLM optional</span>' if llm else '<span class="dr-pill rules">Rule-based</span>'
        cards.append(
            f'<article class="dr-agent"><header><div class="dr-icon" aria-hidden="true"><svg width="20" height="20" '
            f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
            f'stroke-linejoin="round"><path d="{ICONS[icon]}"/></svg></div><small>{num}</small></header>'
            f'<h4>{name.replace("&", "&amp;")}</h4><p>{desc}</p>{tag}</article>')
    return f'<div class="dr-agents">{"".join(cards)}</div>'
