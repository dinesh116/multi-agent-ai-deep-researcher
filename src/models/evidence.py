"""Evidence-layer models: sources, passages, assessments, claims, contradictions, gaps, insights, reports.

Provenance rules:
- `Source.origin` says where content came from: live_search | cache | user_upload | demo.
  Demo content is always synthetic and labelled as such.
- `Source.full_text_available` is False when only a snippet or abstract was retrieved, so the
  app never implies that a full text was reviewed.
- Claims keep an exact `quote` from a passage. Quotes are validated as substrings of the passage,
  so the app never fabricates quotations.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.models.research import now


class SourceType(StrEnum):
    ACADEMIC_PAPER = "academic_paper"
    PREPRINT = "preprint"
    OFFICIAL = "official"  # government, regulator, standards body
    DOCUMENTATION = "documentation"
    COMPANY = "company"  # company reports, press releases, vendor material
    NEWS = "news"
    ANALYST = "analyst"  # industry/analyst research
    BLOG = "blog"
    OPINION = "opinion"
    DATASET = "dataset"
    USER_DOCUMENT = "user_document"
    OTHER = "other"


class Origin(StrEnum):
    LIVE = "live_search"
    CACHE = "cache"
    UPLOAD = "user_upload"
    DEMO = "demo"


ORIGIN_LABELS = {Origin.LIVE: "Live search", Origin.CACHE: "Cached search result", Origin.UPLOAD: "Your document",
                 Origin.DEMO: "Synthetic demo data"}


def content_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()[:16]


def stable_source_id(key: str) -> str:
    """Deterministic id from the canonical URL / DOI / document id."""
    return "src_" + hashlib.sha1(key.strip().lower().encode()).hexdigest()[:12]


class Source(BaseModel):
    id: str
    title: str
    url: str | None = None  # canonical URL, only if the provider supplied one
    doc_ref: str | None = None  # DOI, arXiv id or uploaded-document id
    publisher: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_date: date | None = None
    retrieved_at: datetime = Field(default_factory=now)
    source_type: SourceType = SourceType.OTHER
    origin: Origin
    retrieval_method: str  # demo | tavily | openalex | crossref | arxiv | upload | dataset
    content: str = ""
    full_text_available: bool = False
    content_hash: str = ""
    limitations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    references_found: list[str] = Field(default_factory=list)  # DOIs/URLs mentioned inside the content
    subquestion_ids: list[str] = Field(default_factory=list)
    query: str = ""
    duplicate_of: str | None = None
    related_ids: list[str] = Field(default_factory=list)  # e.g. syndicated copies of the same original
    iteration: int = 0

    @property
    def is_synthetic(self) -> bool:
        return self.origin == Origin.DEMO

    def is_primary_type(self) -> bool:
        return self.source_type in (SourceType.ACADEMIC_PAPER, SourceType.PREPRINT, SourceType.OFFICIAL,
                                    SourceType.DATASET, SourceType.DOCUMENTATION, SourceType.COMPANY,
                                    SourceType.USER_DOCUMENT)

    def citation_label(self) -> str:
        who = self.publisher or (", ".join(self.authors[:2]) + (" et al." if len(self.authors) > 2 else "")) or "Unknown"
        when = self.published_date.year if self.published_date else "n.d."
        return f"{who} ({when}). {self.title}"


class Passage(BaseModel):
    id: str
    source_id: str
    text: str
    location: str = ""  # "page 3", "section 2", "abstract", "row 12"
    index: int = 0
    score: float = 0.0  # retrieval relevance (BM25), relative within a run


class EvidenceQuality(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Freshness(StrEnum):
    CURRENT = "current"  # < 1 year
    RECENT = "recent"  # 1-3 years
    DATED = "dated"  # > 3 years
    UNKNOWN = "unknown"


class SourceAssessment(BaseModel):
    """Heuristic assessment. Scores are indicators for triage, NOT calibrated probabilities."""

    source_id: str
    relevance: float = Field(ge=0, le=1)
    evidence_quality: EvidenceQuality
    source_type: SourceType
    is_primary: bool
    authority_indicators: list[str] = Field(default_factory=list)
    freshness: Freshness
    age_days: int | None = None
    flags: list[str] = Field(default_factory=list)  # opinion, conflict_of_interest, weak_sourcing, outdated, ...
    limitations: list[str] = Field(default_factory=list)
    rationale: str
    method: str = "heuristic"


class ClaimType(StrEnum):
    FACT = "fact"
    STATISTIC = "statistic"
    FORECAST = "forecast"
    OPINION = "opinion"


class Stance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class Claim(BaseModel):
    id: str
    text: str  # the claim as stated (normalised sentence)
    quote: str  # exact supporting passage text
    claim_type: ClaimType
    polarity: int = 1  # +1 affirming / -1 negating or sceptical, relative to its topic
    source_id: str
    passage_id: str
    location: str = ""
    subquestion_id: str | None = None
    extracted_by: str = "heuristic"
    notes: list[str] = Field(default_factory=list)
    verified: bool | None = None  # LLM check that `text` faithfully restates `quote` (None = not checked)


class DataPoint(BaseModel):
    """A quantitative fact extracted from a passage (the raw material for key-number and comparison tables)."""

    id: str
    metric: str  # what is measured, e.g. "enterprises with agents in production"
    value: float | None  # numeric value when parseable
    value_text: str  # as written, e.g. "38%", "$1.2 billion", "3.2 times"
    unit: str = ""  # % | USD | x | count | months | ...
    kind: str = "level"  # level | change
    subject: str = ""  # population/sample, e.g. "1,200 enterprises"
    period: str = ""  # e.g. "2026", "next year"
    method: str = ""  # e.g. "self-reported survey", "benchmark"
    source_id: str
    passage_id: str
    quote: str
    location: str = ""
    extracted_by: str = "heuristic"


class Entity(BaseModel):
    """An organisation, product, technology or regulation recurring across sources."""

    id: str
    name: str
    kind: str = "named_entity"  # company | product | technology | regulation | organisation | named_entity
    mentions: int = 0
    source_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)


class EvidenceLink(BaseModel):
    claim_id: str
    row_id: str
    source_id: str
    passage_id: str
    relation: Stance
    note: str = ""


class Agreement(StrEnum):
    STRONG = "strong"  # >= 3 independent supporting sources, no contradiction
    MODERATE = "moderate"  # 2 independent sources, no contradiction
    SINGLE_SOURCE = "single_source"
    MIXED = "mixed"  # support and contradiction, support dominates
    CONTESTED = "contested"  # contradiction >= support


class MatrixRow(BaseModel):
    """One row of the evidence matrix: a canonical claim with supporting and contradicting evidence."""

    id: str
    claim: str
    subquestion_id: str | None
    claim_type: ClaimType
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    supporting_source_ids: list[str] = Field(default_factory=list)
    contradicting_source_ids: list[str] = Field(default_factory=list)
    independent_sources: int = 0
    evidence_quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    agreement: Agreement = Agreement.SINGLE_SOURCE
    unresolved_questions: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    assessment: str = ""
    strength: float = 0.0  # quality-weighted independent support (high=1, medium=.6, low=.25 per independent group)
    source_types: list[str] = Field(default_factory=list)
    grouped_by: str = "heuristic"  # heuristic | llm


class Contradiction(BaseModel):
    id: str
    row_id: str
    topic: str
    claim_a_id: str
    claim_b_id: str
    source_a_id: str
    source_b_id: str
    nature: str  # direct | numeric | interpretation | forecast
    explanation: str
    resolution: str = "unresolved"


class GapKind(StrEnum):
    UNANSWERED = "unanswered"
    THIN = "thin_evidence"
    SINGLE_SOURCE = "single_source"
    CONTESTED = "contested"
    OUTDATED = "outdated"
    LOW_QUALITY = "low_quality"
    UNCHALLENGED = "unchallenged"  # a key finding no search has yet tried to disprove


class ResearchGap(BaseModel):
    id: str
    subquestion_id: str | None
    kind: GapKind
    description: str
    follow_up_queries: list[str] = Field(default_factory=list)
    priority: int = 2
    expected_value: float = 0.0  # 0..1 heuristic: how much more searching is likely to help
    iteration: int = 0
    resolved: bool = False


class InsightKind(StrEnum):
    FINDING = "finding"  # directly observed in evidence
    TREND = "trend"
    HYPOTHESIS = "hypothesis"
    IMPLICATION = "implication"
    RISK = "risk"
    OPPORTUNITY = "opportunity"
    DISAGREEMENT = "disagreement"


class EpistemicLabel(StrEnum):
    OBSERVED = "observed"  # stated directly by sources
    INFERRED = "inferred"  # reasoned from several observations
    SPECULATIVE = "speculative"  # hypothesis to be tested


class Insight(BaseModel):
    id: str
    kind: InsightKind
    label: EpistemicLabel
    statement: str
    evidence_claim_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    reasoning: str
    alternatives: list[str] = Field(default_factory=list)
    confidence: str  # low | medium | high
    confidence_explanation: str
    limitations: list[str] = Field(default_factory=list)
    next_investigation: str = ""
    generated_by: str = "heuristic"


class CitationCheck(BaseModel):
    marker: str  # e.g. "[3]"
    source_id: str | None
    exists: bool
    reference_matches: bool
    passage_relevant: bool | None  # None when the citation is not attached to a specific claim
    renderable: bool
    note: str = ""

    @property
    def valid(self) -> bool:
        return self.exists and self.reference_matches and self.renderable and self.passage_relevant is not False


class ReportSection(BaseModel):
    key: str
    title: str
    content: str  # markdown with [n] citation markers


class Report(BaseModel):
    title: str
    question: str
    template: str = "standard"  # outlook | evidence_assessment | literature_review | landscape | brief | full
    sections: list[ReportSection]
    references: list[dict[str, Any]]  # {"n": 1, "source_id": ..., "label": ..., "url": ..., "origin": ...}
    citation_checks: list[CitationCheck] = Field(default_factory=list)
    generated_by: str = "heuristic"
    created_at: datetime = Field(default_factory=now)

    def section(self, key: str) -> ReportSection | None:
        return next((s for s in self.sections if s.key == key), None)


class AgentEvent(BaseModel):
    """Audit-trail entry emitted by the orchestration layer (never fabricated progress)."""

    timestamp: datetime = Field(default_factory=now)
    agent: str
    status: str  # started | completed | failed | info | decision | search
    message: str
    iteration: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentStatus(BaseModel):
    agent: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    runs: int = 0
    last_message: str = ""
    duration_ms: int = 0
