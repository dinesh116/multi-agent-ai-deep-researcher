"""Agent base class and run context (dependencies, event emission, budget)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, ClassVar

from src.config import Settings
from src.models.evidence import AgentEvent
from src.orchestration.budget import RunBudget
from src.orchestration.state import ResearchState
from src.search.registry import ProviderSet, ProviderSettings
from src.services.llm import LLMClient


@dataclass
class RunContext:
    settings: Settings
    budget: RunBudget
    providers: ProviderSet
    llm: LLMClient | None = None
    use_llm: bool = False
    cache: Any = None  # Repository-like object with get_cached/put_cached (None disables caching)
    emit: Callable[[AgentEvent], None] = lambda event: None
    today: date = field(default_factory=date.today)
    provider_settings: ProviderSettings = field(default_factory=ProviderSettings)
    max_parallel: int = 4

    @property
    def llm_enabled(self) -> bool:
        return bool(self.use_llm and self.llm and self.llm.available)

    def event(self, agent: str, status: str, message: str, iteration: int = 0, **metrics) -> AgentEvent:
        event = AgentEvent(agent=agent, status=status, message=message, iteration=iteration, metrics=metrics)
        self.emit(event)
        return event


class Agent(ABC):
    name: ClassVar[str]
    title: ClassVar[str]
    responsibility: ClassVar[str]
    uses_llm: ClassVar[str] = "no"  # no | optional

    @abstractmethod
    def run(self, state: ResearchState, ctx: RunContext) -> dict:
        """Return a partial state update. Must not mutate `state` in place."""
