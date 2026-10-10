"""Plotly charts for the dashboard."""
from __future__ import annotations

from collections import Counter

import plotly.graph_objects as go

AGREEMENT_ORDER = ["strong", "moderate", "single_source", "mixed", "contested"]
# Docs-style palette (brand blue, teal, amber, red, neutral grey).
AGREEMENT_HEX = {"strong": "#009588", "moderate": "#2f45e8", "single_source": "#a1a1a1", "mixed": "#f99c00",
                 "contested": "#dc2626"}
QUALITY_HEX = {"high": "#009588", "medium": "#2f45e8", "low": "#f99c00", "unknown": "#a1a1a1"}
PALETTE = ["#2f45e8", "#009588", "#f05100", "#fcbb00", "#104e64", "#f99c00", "#a1a1a1"]


def _layout(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=-0.2),
                      font=dict(family="Geist, sans-serif", size=12), colorway=PALETTE, bargap=0.45)
    fig.update_xaxes(gridcolor="rgba(127,127,127,.15)", zeroline=False, linecolor="rgba(127,127,127,.25)")
    fig.update_yaxes(gridcolor="rgba(127,127,127,.15)", zeroline=False, linecolor="rgba(127,127,127,.25)")
    return fig


def agreement_bar(rows) -> go.Figure:
    counts = Counter(r.agreement.value for r in rows)
    labels = [a for a in AGREEMENT_ORDER if counts.get(a)]
    fig = go.Figure(go.Bar(x=[l.replace("_", " ") for l in labels], y=[counts[l] for l in labels],
                           marker_color=[AGREEMENT_HEX[l] for l in labels]))
    fig.update_yaxes(title="evidence rows")
    return _layout(fig)


def source_types_pie(sources) -> go.Figure:
    counts = Counter(s.source_type.value.replace("_", " ") for s in sources)
    fig = go.Figure(go.Pie(labels=list(counts), values=list(counts.values()), hole=0.62, textinfo="value",
                           marker=dict(colors=PALETTE, line=dict(width=0)), sort=False))
    return _layout(fig)


def quality_relevance_scatter(sources, assessments) -> go.Figure:
    fig = go.Figure()
    for quality, colour in QUALITY_HEX.items():
        pts = [(assessments[s.id].relevance, (s.published_date.year if s.published_date else None), s.title)
               for s in sources if s.id in assessments and assessments[s.id].evidence_quality.value == quality]
        if pts:
            fig.add_scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers", name=f"{quality} quality",
                            marker=dict(size=10, color=colour, symbol="square", opacity=.85), text=[p[2] for p in pts],
                            hovertemplate="%{text}<br>relevance %{x:.2f}<br>%{y}<extra></extra>")
    fig.update_xaxes(title="relevance (heuristic)", range=[-0.05, 1.05])
    fig.update_yaxes(title="publication year")
    return _layout(fig, 340)


def flags_bar(assessments) -> go.Figure:
    counts = Counter(f.replace("_", " ") for a in assessments.values() for f in a.flags)
    fig = go.Figure(go.Bar(y=list(counts), x=list(counts.values()), orientation="h", marker_color="#dc2626"))
    fig.update_xaxes(title="sources")
    return _layout(fig, 260)


def data_points_bar(points, ref_numbers: dict[str, int], limit: int = 12) -> go.Figure | None:
    """Percentages from the evidence, labelled with their measure and citation (display only)."""
    pct = [p for p in points if p.unit == "%" and p.value is not None][:limit]
    if len(pct) < 2:
        return None
    labels = [f"{p.metric[:48]}{' [' + str(ref_numbers[p.source_id]) + ']' if p.source_id in ref_numbers else ''}" for p in pct]
    fig = go.Figure(go.Bar(x=[p.value for p in pct], y=labels, orientation="h",
                           marker_color=["#2f45e8" if p.kind == "level" else "#009588" for p in pct],
                           text=[p.value_text for p in pct], textposition="outside",
                           hovertext=[p.quote for p in pct], hoverinfo="text"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="% (blue = level, teal = change)")
    return _layout(fig, 60 + 32 * len(pct))
