"""A persisted research run, reloaded from the database for the dashboard (no re-research needed)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models.evidence import (AgentEvent, AgentStatus, Claim, Contradiction, EvidenceLink, Insight, MatrixRow,
                                 Passage, Report, ResearchGap, Source, SourceAssessment)
from src.models.research import BudgetUsage, ResearchPlan, ResearchRequest


class RunSummary(BaseModel):
    id: str
    user_id: str | None = None  # owner; None only for runs created before accounts existed
    question: str
    status: str
    mode: str
    created_at: datetime
    completed_at: datetime | None = None
    summary: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    parent_run_id: str | None = None


class RunBundle(BaseModel):
    summary: RunSummary
    request: ResearchRequest
    plan: ResearchPlan | None = None
    usage: BudgetUsage | None = None
    statuses: dict[str, AgentStatus] = Field(default_factory=dict)
    stop_reason: str = ""
    sources: list[Source] = Field(default_factory=list)
    passages: list[Passage] = Field(default_factory=list)
    assessments: dict[str, SourceAssessment] = Field(default_factory=dict)
    claims: list[Claim] = Field(default_factory=list)
    matrix: list[MatrixRow] = Field(default_factory=list)
    links: list[EvidenceLink] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    gaps: list[ResearchGap] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)
    report: Report | None = None
    events: list[AgentEvent] = Field(default_factory=list)
    search_log: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    provider_notes: list[str] = Field(default_factory=list)

    def source(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.id == source_id), None)

    def claim(self, claim_id: str) -> Claim | None:
        return next((c for c in self.claims if c.id == claim_id), None)

    def passages_for(self, source_id: str) -> list[Passage]:
        return [p for p in self.passages if p.source_id == source_id]
