"""Plotly charts for the dashboard."""
from __future__ import annotations

from collections import Counter

import plotly.graph_objects as go

AGREEMENT_ORDER = ["strong", "moderate", "single_source", "mixed", "contested"]
AGREEMENT_HEX = {"strong": "#10b981", "moderate": "#3b82f6", "single_source": "#9ca3af", "mixed": "#f59e0b",
                 "contested": "#ef4444"}
QUALITY_HEX = {"high": "#10b981", "medium": "#3b82f6", "low": "#f59e0b", "unknown": "#9ca3af"}


def _layout(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=-0.2))
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
    fig = go.Figure(go.Pie(labels=list(counts), values=list(counts.values()), hole=0.5, textinfo="label+value"))
    return _layout(fig)


def quality_relevance_scatter(sources, assessments) -> go.Figure:
    fig = go.Figure()
    for quality, colour in QUALITY_HEX.items():
        pts = [(assessments[s.id].relevance, (s.published_date.year if s.published_date else None), s.title)
               for s in sources if s.id in assessments and assessments[s.id].evidence_quality.value == quality]
        if pts:
            fig.add_scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers", name=f"{quality} quality",
                            marker=dict(size=12, color=colour, opacity=.8), text=[p[2] for p in pts],
                            hovertemplate="%{text}<br>relevance %{x:.2f}<br>%{y}<extra></extra>")
    fig.update_xaxes(title="relevance (heuristic)", range=[-0.05, 1.05])
    fig.update_yaxes(title="publication year")
    return _layout(fig, 340)


def flags_bar(assessments) -> go.Figure:
    counts = Counter(f.replace("_", " ") for a in assessments.values() for f in a.flags)
    fig = go.Figure(go.Bar(y=list(counts), x=list(counts.values()), orientation="h", marker_color="#ef4444"))
    fig.update_xaxes(title="sources")
    return _layout(fig, 260)
