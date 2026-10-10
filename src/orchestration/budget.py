"""Thread-safe research budget tracker: searches, sources, LLM calls/tokens and wall-clock time."""
from __future__ import annotations

import threading
import time

from src.models.research import BudgetUsage, ResearchBudget


class BudgetExceeded(RuntimeError):
    pass


class RunBudget:
    def __init__(self, budget: ResearchBudget, clock=time.monotonic):
        self.budget = budget
        self.clock = clock
        self.started = clock()
        self._lock = threading.Lock()
        self.usage = BudgetUsage()

    # ------------------------------------------------------------------ checks
    @property
    def elapsed(self) -> float:
        return self.clock() - self.started

    def time_left(self) -> float:
        return self.budget.max_seconds - self.elapsed

    def out_of_time(self) -> bool:
        return self.time_left() <= 0

    def _mark(self, reason: str) -> None:
        if reason not in self.usage.exhausted:
            self.usage.exhausted.append(reason)

    def try_search(self) -> bool:
        """Reserve one search. Returns False (and records why) when a limit is reached."""
        with self._lock:
            if self.out_of_time():
                self._mark("time")
                return False
            if self.usage.searches >= self.budget.max_searches:
                self._mark("searches")
                return False
            self.usage.searches += 1
            return True

    def record_cache_hit(self) -> None:
        with self._lock:
            self.usage.cache_hits += 1

    def sources_left(self) -> int:
        return max(0, self.budget.max_sources - self.usage.sources)

    def add_sources(self, count: int) -> int:
        """Admit up to `count` new sources; returns how many were admitted."""
        with self._lock:
            admitted = min(count, self.budget.max_sources - self.usage.sources)
            admitted = max(0, admitted)
            self.usage.sources += admitted
            if admitted < count:
                self._mark("sources")
            return admitted

    def try_llm(self) -> bool:
        with self._lock:
            if self.out_of_time():
                self._mark("time")
                return False
            if self.usage.llm_calls >= self.budget.max_llm_calls:
                self._mark("llm_calls")
                return False
            if self.usage.llm_tokens >= self.budget.max_llm_tokens:
                self._mark("llm_tokens")
                return False
            self.usage.llm_calls += 1
            return True

    def record_tokens(self, tokens: int) -> None:
        with self._lock:
            self.usage.llm_tokens += max(0, int(tokens or 0))

    def snapshot(self, iterations: int | None = None) -> BudgetUsage:
        with self._lock:
            usage = self.usage.model_copy(deep=True)
        usage.elapsed_seconds = round(self.elapsed, 1)
        if iterations is not None:
            usage.iterations = iterations
        return usage
