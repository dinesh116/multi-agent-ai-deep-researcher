"""Claim extraction: deterministic sentence-level extraction, and validation of LLM-proposed claims.

Every claim keeps an exact quote. LLM-proposed claims are accepted only if the quote is found verbatim
(ignoring whitespace/case) in one of the source's passages. This blocks invented quotations.
"""
from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from src.analysis.text import (CLAIM_CUES, FORECAST_CUES, INJECTION_PATTERNS, OPINION_CUES, STAT_CUES, polarity,
                               split_sentences)
from src.models.evidence import Claim, ClaimType, Passage, Source
from src.models.research import ResearchPlan
from src.retrieval.bm25 import BM25Index

MAX_CLAIMS_PER_SOURCE = 10  # default; depth presets override this


def classify_claim(sentence: str) -> ClaimType:
    if OPINION_CUES.search(sentence):
        return ClaimType.OPINION
    if FORECAST_CUES.search(sentence):
        return ClaimType.FORECAST
    if STAT_CUES.search(sentence):
        return ClaimType.STATISTIC
    return ClaimType.FACT


def claim_id(source_id: str, quote: str) -> str:
    return "clm_" + hashlib.sha1(f"{source_id}|{quote.lower()}".encode()).hexdigest()[:12]


def _norm(text: str) -> str:
    """Words only: quotes must match the source word for word, but markdown, punctuation and line breaks are ignored."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


PERSPECTIVE_VOCAB = {
    "barrier": "barrier risk limitation reliability fail failure constraint regulation governance oversight audit "
               "integration cost error liability concern",
    "driver": "productivity benefit gain improve reduce cost faster growth increase capability",
    "forecast": "will expect forecast predict by 2028 2030 future replace estimate",
    "current": "survey adoption percent deploy production use today report",
    "implication": "pricing business model revenue seat outcome usage market",
    "contradict": "overstated not evidence limited fail rather than criticism",
    "evaluation": "evaluation metric benchmark faithfulness measure judge",
    "techniques": "improve accuracy recall retrieval hybrid graph rerank",
    "risk": "risk concern constraint regulation compliance liability",
}


def _vocab(perspective: str) -> str:
    return " ".join(v for k, v in PERSPECTIVE_VOCAB.items() if k in perspective)


class SubquestionMatcher:
    def __init__(self, plan: ResearchPlan):
        self.subquestions = plan.subquestions
        self.index = BM25Index(plan.subquestions,
                               lambda s: f"{s.text} {' '.join(s.queries)} {s.perspective} {_vocab(s.perspective)}")

    def best(self, text: str, fallback: list[str]) -> str | None:
        hits = self.index.search(text, k=1)
        if hits and hits[0][1] > 0.5:
            return hits[0][0].id
        return fallback[0] if fallback else (self.subquestions[0].id if self.subquestions else None)


def heuristic_claims(source: Source, passages: list[Passage], plan: ResearchPlan,
                     matcher: SubquestionMatcher, limit: int = MAX_CLAIMS_PER_SOURCE) -> list[Claim]:
    """Sentences that assert something checkable (numbers, findings, forecasts), ranked by relevance."""
    candidates: list[tuple[Passage, str]] = []
    for passage in passages:
        for sentence in split_sentences(passage.text):
            if not 40 <= len(sentence) <= 360 or sentence.endswith("?"):
                continue
            if INJECTION_PATTERNS.search(sentence):
                continue  # instruction-like text is never treated as a claim
            if CLAIM_CUES.search(sentence) or STAT_CUES.search(sentence) or OPINION_CUES.search(sentence):
                candidates.append((passage, sentence))
    if not candidates:
        return []
    query = plan.question + " " + " ".join(s.text + " " + " ".join(s.queries) for s in plan.subquestions)
    scores = {id(c): score for c, score in BM25Index(candidates, lambda c: c[1]).search(query, k=len(candidates))}
    order = {id(c): i for i, c in enumerate(candidates)}
    chosen = sorted(candidates, key=lambda c: (-scores.get(id(c), 0.0), order[id(c)]))[:limit]
    claims = []
    for passage, sentence in sorted(chosen, key=lambda c: order[id(c)]):
        claims.append(Claim(
            id=claim_id(source.id, sentence), text=sentence, quote=sentence, claim_type=classify_claim(sentence),
            polarity=polarity(sentence), source_id=source.id, passage_id=passage.id, location=passage.location,
            subquestion_id=matcher.best(sentence, source.subquestion_ids), extracted_by="heuristic"))
    return claims


class ClaimDraft(BaseModel):
    quote: str = Field(description="Exact sentence copied from the source text")
    claim: str = Field(description="The claim restated concisely")
    claim_type: str = Field(description="fact | statistic | forecast | opinion")
    sceptical: bool = Field(False, description="True if the claim doubts, negates or limits a premise")


class ClaimDraftList(BaseModel):
    claims: list[ClaimDraft] = Field(default_factory=list, max_length=16)


class DataPointDraft(BaseModel):
    quote: str = Field(description="Exact sentence containing the number, copied from the source text")
    metric: str = Field(description="What is measured, e.g. 'enterprises with AI agents in production'")
    value_text: str = Field(description="The number as written, e.g. '38%', '$1.2 billion', '3.2 times'")
    unit: str = Field("", description="%, USD, x, count, months, ...")
    kind: str = Field("level", description="level (a state) or change (an increase/decrease)")
    subject: str = Field("", description="Population or sample, e.g. '1,200 enterprises'")
    period: str = Field("", description="Year or period the number refers to")
    method: str = Field("", description="How it was measured: survey, benchmark, experiment, internal analysis...")


class EntityDraft(BaseModel):
    name: str
    kind: str = Field("named_entity", description="company | product | technology | regulation | organisation")


class ExtractionDraft(BaseModel):
    """One LLM pass over a window of a source: claims, quantitative data points and named entities."""

    claims: list[ClaimDraft] = Field(default_factory=list, max_length=16)
    data_points: list[DataPointDraft] = Field(default_factory=list, max_length=16)
    entities: list[EntityDraft] = Field(default_factory=list, max_length=20)


def validate_llm_claims(drafts: ClaimDraftList, source: Source, passages: list[Passage],
                        matcher: SubquestionMatcher) -> tuple[list[Claim], int]:
    """Keep only drafts whose quote appears verbatim in a passage. Returns (claims, rejected_count)."""
    accepted, rejected = [], 0
    for draft in drafts.claims:
        quote = draft.quote.strip().strip('"“”')
        passage = next((p for p in passages if len(quote) >= 25 and _norm(quote) in _norm(p.text)), None)
        if passage is None or INJECTION_PATTERNS.search(quote):
            rejected += 1
            continue
        try:
            ctype = ClaimType(draft.claim_type.lower())
        except ValueError:
            ctype = classify_claim(quote)
        accepted.append(Claim(
            id=claim_id(source.id, quote), text=draft.claim.strip()[:400] or quote, quote=quote, claim_type=ctype,
            polarity=-1 if draft.sceptical else polarity(quote), source_id=source.id, passage_id=passage.id,
            location=passage.location, subquestion_id=matcher.best(quote + " " + draft.claim, source.subquestion_ids),
            extracted_by="llm"))
    return accepted, rejected


def validate_llm_data_points(drafts: list[DataPointDraft], source: Source, passages: list[Passage]) -> tuple[list, int]:
    """Accept data points whose quote is verbatim in a passage and whose number appears in that quote."""
    from src.analysis.datapoints import _id, parse_value
    from src.models.evidence import DataPoint

    accepted, rejected = [], 0
    for draft in drafts:
        quote = draft.quote.strip().strip('"“”')
        passage = next((p for p in passages if len(quote) >= 20 and _norm(quote) in _norm(p.text)), None)
        number = re.search(r"\d[\d,.]*", draft.value_text or "")
        digits = number.group(0).rstrip(".,") if number else ""
        # the number must appear as a whole number in the quote ("2" must not match "2020")
        whole = bool(digits) and re.search(rf"(?<![\d.,]){re.escape(digits)}(?![\d]|[.,]\d)", quote)
        if passage is None or not whole or INJECTION_PATTERNS.search(quote):
            rejected += 1
            continue
        accepted.append(DataPoint(
            id=_id("dp", source.id, quote, draft.value_text), metric=draft.metric.strip()[:90] or "unspecified",
            value=parse_value(draft.value_text), value_text=draft.value_text.strip()[:40], unit=draft.unit.strip()[:20],
            kind="change" if draft.kind.lower().startswith("change") else "level", subject=draft.subject.strip()[:80],
            period=draft.period.strip()[:30], method=draft.method.strip()[:60], source_id=source.id,
            passage_id=passage.id, quote=quote, location=passage.location, extracted_by="llm"))
    return accepted, rejected
