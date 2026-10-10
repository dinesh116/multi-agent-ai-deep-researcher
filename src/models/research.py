"""Research request, budget and plan models."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


class Depth(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class SourcePreference(StrEnum):
    WEB = "web"
    ACADEMIC = "academic"
    NEWS = "news"
    OFFICIAL = "official"
    UPLOADED = "uploaded"
    DATASET = "dataset"


class ResearchMode(StrEnum):
    DEMO = "demo"  # synthetic offline corpus, deterministic agents
    LIVE = "live"  # configured live providers (+ LLM if configured)


class ResearchBudget(BaseModel):
    """Hard limits that bound every investigation."""

    max_iterations: int = Field(2, ge=1, le=6)  # follow-up research rounds after the initial one
    max_searches: int = Field(24, ge=1, le=200)
    max_sources: int = Field(30, ge=1, le=300)
    max_seconds: int = Field(240, ge=10, le=3600)
    max_llm_calls: int = Field(40, ge=0, le=500)
    max_llm_tokens: int = Field(200_000, ge=0, le=5_000_000)
    min_sources_per_subquestion: int = Field(2, ge=1, le=10)


DEPTH_PRESETS: dict[Depth, dict] = {
    Depth.QUICK: dict(subquestions=4, queries_per_subquestion=1, results_per_search=4,
                      budget=ResearchBudget(max_iterations=1, max_searches=10, max_sources=15, max_seconds=120,
                                            max_llm_calls=20)),
    Depth.STANDARD: dict(subquestions=5, queries_per_subquestion=2, results_per_search=5,
                         budget=ResearchBudget(max_iterations=2, max_searches=24, max_sources=30, max_seconds=240,
                                               max_llm_calls=40)),
    Depth.DEEP: dict(subquestions=7, queries_per_subquestion=2, results_per_search=6,
                     budget=ResearchBudget(max_iterations=3, max_searches=48, max_sources=60, max_seconds=480,
                                           max_llm_calls=80, max_llm_tokens=400_000)),
}

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ResearchRequest(BaseModel):
    question: str
    context: str = ""
    objectives: list[str] = Field(default_factory=list)
    depth: Depth = Depth.STANDARD
    source_preferences: list[SourcePreference] = Field(
        default_factory=lambda: [SourcePreference.WEB, SourcePreference.ACADEMIC, SourcePreference.NEWS,
                                 SourcePreference.OFFICIAL, SourcePreference.UPLOADED])
    date_from: date | None = None
    date_to: date | None = None
    max_iterations: int | None = Field(None, ge=1, le=6)
    mode: ResearchMode = ResearchMode.DEMO
    use_llm: bool = True
    document_ids: list[str] = Field(default_factory=list)  # uploaded documents to include
    parent_run_id: str | None = None  # set when refining a previous investigation

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        value = re.sub(r"\s+", " ", _CONTROL_CHARS.sub("", value or "")).strip()
        if len(value) < 12:
            raise ValueError("Please enter a research question of at least 12 characters.")
        if len(value) > 600:
            raise ValueError("Research questions are limited to 600 characters. Put extra detail in the context field.")
        if len(re.findall(r"[A-Za-z]{3,}", value)) < 3:
            raise ValueError("The question needs at least three words to plan an investigation.")
        return value

    @field_validator("context")
    @classmethod
    def _clean_context(cls, value: str) -> str:
        return _CONTROL_CHARS.sub("", value or "").strip()[:4000]

    @field_validator("objectives")
    @classmethod
    def _clean_objectives(cls, value: list[str]) -> list[str]:
        return [o.strip()[:300] for o in value if o and o.strip()][:8]

    @model_validator(mode="after")
    def _check_dates(self) -> ResearchRequest:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("The publication start date must be before the end date.")
        return self

    def budget(self) -> ResearchBudget:
        budget = DEPTH_PRESETS[self.depth]["budget"].model_copy()
        if self.max_iterations:
            budget.max_iterations = self.max_iterations
        return budget

    def preset(self, key: str):
        return DEPTH_PRESETS[self.depth][key]


class BudgetUsage(BaseModel):
    iterations: int = 0
    searches: int = 0
    sources: int = 0
    llm_calls: int = 0
    llm_tokens: int = 0
    cache_hits: int = 0
    elapsed_seconds: float = 0.0
    exhausted: list[str] = Field(default_factory=list)  # which limits were hit


class ResearchScope(BaseModel):
    timeframe: str = "not specified"
    entities: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    geography: str | None = None
    exclusions: list[str] = Field(default_factory=list)
    intended_outcome: str = ""


class SubQuestionStatus(StrEnum):
    OPEN = "open"
    PARTIAL = "partial"
    ANSWERED = "answered"


class SubQuestion(BaseModel):
    id: str
    text: str
    perspective: str
    priority: int = Field(2, ge=1, le=3)  # 1 = highest
    queries: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    expected_evidence: str = ""
    status: SubQuestionStatus = SubQuestionStatus.OPEN
    added_in_iteration: int = 0

    @field_validator("queries")
    @classmethod
    def _queries(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(q.strip()[:200] for q in value if q and q.strip()))
        if not cleaned:
            raise ValueError("Each subquestion needs at least one search query.")
        return cleaned[:4]


class ResearchPlan(BaseModel):
    question: str
    objectives: list[str]
    scope: ResearchScope
    subquestions: list[SubQuestion]
    search_strategy: str
    completion_criteria: list[str]
    version: int = 1
    revisions: list[str] = Field(default_factory=list)
    generated_by: str = "heuristic"  # heuristic | llm

    @field_validator("subquestions")
    @classmethod
    def _subquestions(cls, value: list[SubQuestion]) -> list[SubQuestion]:
        if not 2 <= len(value) <= 12:
            raise ValueError("A plan needs between 2 and 12 subquestions.")
        if len({s.id for s in value}) != len(value):
            raise ValueError("Subquestion ids must be unique.")
        return value

    def get(self, subquestion_id: str) -> SubQuestion | None:
        return next((s for s in self.subquestions if s.id == subquestion_id), None)
