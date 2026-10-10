"""BM25 ranking over passages (the retrieval layer used for evidence ranking, Q&A and the demo corpus).

BM25 works well here because research questions hinge on specific terms (technologies, companies, metrics).
It is local, deterministic and testable. `Retriever` is a small interface: a semantic/vector retriever
(e.g. ChromaDB) can be added behind it later without changing the agents.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from src.analysis.text import tokenize

T = TypeVar("T")


class Retriever(Protocol[T]):
    def search(self, query: str, k: int = 5) -> list[tuple[T, float]]: ...


@dataclass
class _Doc(Generic[T]):
    item: T
    tokens: list[str]
    tf: Counter


class BM25Index(Generic[T]):
    def __init__(self, items: list[T], text_of, k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [_Doc(item, toks, Counter(toks)) for item in items for toks in [tokenize(text_of(item))]]
        self.avg_len = sum(len(d.tokens) for d in self.docs) / len(self.docs) if self.docs else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d.tokens))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query_terms: list[str], doc: _Doc) -> float:
        score = 0.0
        length = len(doc.tokens)
        for term in query_terms:
            freq = doc.tf.get(term)
            if freq:
                norm = freq * (self.k1 + 1) / (freq + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1)))
                score += self.idf.get(term, 0.0) * norm
        return score

    def search(self, query: str, k: int = 5) -> list[tuple[T, float]]:
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms:
            return []
        scored = [(d.item, self.score(terms, d)) for d in self.docs]
        scored = [(item, round(s, 4)) for item, s in scored if s > 0]
        scored.sort(key=lambda pair: -pair[1])
        return scored[:k]
