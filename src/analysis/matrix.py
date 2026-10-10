"""Evidence matrix and contradiction detection (deterministic).

1. Claims about the same subquestion are clustered by term overlap. Each cluster becomes a matrix row.
2. Within a row, the majority polarity is "supporting"; claims with the opposite polarity are "contradicting".
3. Agreement counts *independent* sources: copies of the same original (syndication) count once.
4. Contradictions are recorded for opposite-polarity claims from independent sources, and for numeric
   disagreements (e.g. 38% vs 72%) between similar statistical claims, even when they fall in different rows.
"""
from __future__ import annotations

import hashlib

from collections import Counter

from src.analysis.text import WEAKNESS_CUES, content_terms, overlap, percent_mentions, truncate
from src.evidence.store import EvidenceStore
from src.models.evidence import (Agreement, Claim, ClaimType, Contradiction, EvidenceLink, EvidenceQuality,
                                 MatrixRow, SourceAssessment, Stance)

CLUSTER_THRESHOLD = 0.34  # overlap coefficient on non-topic terms
MIN_SHARED_TERMS = 3
QUALITY_ORDER = {EvidenceQuality.HIGH: 3, EvidenceQuality.MEDIUM: 2, EvidenceQuality.LOW: 1, EvidenceQuality.UNKNOWN: 0}


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def cluster_claims(claims: list[Claim], assessments: dict[str, SourceAssessment],
                   topic_terms: set[str] | None = None) -> list[list[Claim]]:
    """Greedy clustering of claims that talk about the same thing (terms shared beyond the question's own topic)."""
    topic_terms = topic_terms or set()

    def quality(c: Claim) -> int:
        a = assessments.get(c.source_id)
        return QUALITY_ORDER[a.evidence_quality] if a else 0

    clusters: list[tuple[set[str], list[Claim]]] = []
    for claim in sorted(claims, key=lambda c: (-quality(c), c.id)):
        terms = content_terms(claim.text) - topic_terms
        best, best_score = None, 0.0
        for cluster in clusters:
            for member in cluster[1]:  # single linkage: similar to any member
                member_terms = content_terms(member.text) - topic_terms
                score = overlap(terms, member_terms)
                if len(terms & member_terms) >= MIN_SHARED_TERMS and score > best_score:
                    best, best_score = cluster, score
        if best is not None and best_score >= CLUSTER_THRESHOLD:
            best[1].append(claim)
        else:
            clusters.append((set(terms), [claim]))
    return [members for _, members in clusters]


def agreement_for(support: int, contra: int) -> Agreement:
    if contra and contra >= support:
        return Agreement.CONTESTED
    if contra:
        return Agreement.MIXED
    if support >= 3:
        return Agreement.STRONG
    if support == 2:
        return Agreement.MODERATE
    return Agreement.SINGLE_SOURCE


def frequent_terms(claims: list[Claim], share: float = 0.35) -> set[str]:
    """Terms present in a large share of all claims (e.g. the research topic itself): they don't discriminate."""
    if len(claims) < 6:
        return set()
    counts = Counter(t for c in claims for t in content_terms(c.text))
    return {t for t, n in counts.items() if n / len(claims) > share}


QUALITY_WEIGHT = {EvidenceQuality.HIGH: 1.0, EvidenceQuality.MEDIUM: 0.6, EvidenceQuality.LOW: 0.25,
                  EvidenceQuality.UNKNOWN: 0.3}


def quality_weighted_strength(source_ids: list[str], store: EvidenceStore,
                              assessments: dict[str, SourceAssessment]) -> float:
    """Sum over independent source groups of the best quality weight in each group."""
    total = 0.0
    for group in store.independent_groups(list(dict.fromkeys(source_ids))):
        total += max((QUALITY_WEIGHT[assessments[s].evidence_quality] for s in group if s in assessments), default=0.3)
    return round(total, 2)


def heuristic_groups(claims: list[Claim], assessments: dict[str, SourceAssessment]) -> list[tuple[list[Claim], set[str]]]:
    """Lexical clusters; the majority polarity is treated as the supporting side."""
    groups = []
    for members in cluster_claims(claims, assessments, frequent_terms(claims)):
        majority = 1 if sum(c.polarity for c in members) >= 0 else -1
        groups.append((members, {c.id for c in members if c.polarity == majority}))
    return groups


def build_matrix(claims: list[Claim], store: EvidenceStore, assessments: dict[str, SourceAssessment],
                 heuristic: bool = True, groups: list[tuple[list[Claim], set[str]]] | None = None,
                 grouped_by: str = "heuristic") -> tuple[list[MatrixRow], list[EvidenceLink], list[Contradiction]]:
    """Build evidence rows from claim groups. `groups` (members, supporting claim ids) may come from an LLM that
    grouped claims by proposition; otherwise lexical clustering with polarity cues is used."""
    rows, links, contradictions = [], [], []
    caveat = " Detected from wording cues; read both passages to confirm." if heuristic and groups is None else ""
    for members, support_ids in (groups if groups is not None else heuristic_groups(claims, assessments)):
        support = [c for c in members if c.id in support_ids] or members[:1]
        contra = [c for c in members if c not in support]
        rep = support[0]
        row_id = _id("row", *sorted(c.id for c in members))
        support_sources = list(dict.fromkeys(c.source_id for c in support))
        contra_sources = list(dict.fromkeys(c.source_id for c in contra if c.source_id not in support_sources))
        independent = store.independent_count(support_sources)
        independent_contra = store.independent_count(contra_sources) if contra_sources else 0
        qualities = [assessments[s].evidence_quality for s in support_sources if s in assessments]
        quality = max(qualities, key=lambda q: QUALITY_ORDER[q]) if qualities else EvidenceQuality.UNKNOWN

        weaknesses, unresolved = [], []
        for c in members:
            for label, pattern in WEAKNESS_CUES.items():
                if pattern.search(c.quote) and label not in weaknesses:
                    weaknesses.append(label)
        for sid in support_sources:
            a = assessments.get(sid)
            if a:
                for flag in a.flags:
                    note = {"conflict_of_interest": "supporting source has a conflict of interest",
                            "opinion": "supporting source is opinion", "outdated": "supporting source may be outdated",
                            "repeats_other_source": "some support repeats another source",
                            "weak_sourcing": "supporting source cites no methodology"}.get(flag)
                    if note and note not in weaknesses:
                        weaknesses.append(note)
        if rep.claim_type == ClaimType.FORECAST and independent <= 1 and not contra:
            weaknesses.append("forecast supported by a single source; may be overstated")
        if len(support_sources) > independent:
            weaknesses.append(f"{len(support_sources)} supporting sources but only {independent} independent")

        agreement = agreement_for(independent, independent_contra)
        if agreement in (Agreement.CONTESTED, Agreement.MIXED):
            unresolved.append("Why do the sources disagree, and do they measure the same thing?")
        if agreement == Agreement.SINGLE_SOURCE:
            unresolved.append("Is this corroborated by an independent source?")
        if rep.claim_type == ClaimType.FORECAST:
            unresolved.append("What leading indicators would confirm or refute this forecast?")

        strength = quality_weighted_strength(support_sources, store, assessments)
        types = sorted({assessments[s].source_type.value for s in support_sources if s in assessments})
        assessment = (f"{agreement.value.replace('_', ' ').title()} evidence: {independent} independent supporting "
                      f"source(s), {independent_contra} contradicting; best supporting quality "
                      f"{quality.value}; quality-weighted strength {strength}.")
        row = MatrixRow(
            id=row_id, claim=rep.text,
            subquestion_id=Counter(c.subquestion_id for c in members).most_common(1)[0][0], claim_type=rep.claim_type,
            supporting_claim_ids=[c.id for c in support], contradicting_claim_ids=[c.id for c in contra],
            supporting_source_ids=support_sources, contradicting_source_ids=contra_sources,
            independent_sources=independent, evidence_quality=quality, agreement=agreement,
            unresolved_questions=unresolved, weaknesses=weaknesses, assessment=assessment, strength=strength,
            source_types=types, grouped_by=grouped_by)
        rows.append(row)
        links += [EvidenceLink(claim_id=c.id, row_id=row_id, source_id=c.source_id, passage_id=c.passage_id,
                               relation=Stance.SUPPORTS if c in support else Stance.CONTRADICTS) for c in members]
        groups = store.independent_groups(list(dict.fromkeys(c.source_id for c in members)))
        group_of = {sid: i for i, g in enumerate(groups) for sid in g}
        seen_pairs: set[tuple[int, int]] = set()
        for a in support:
            for b in contra:
                pair = (group_of.get(a.source_id, -1), group_of.get(b.source_id, -2))
                if pair in seen_pairs:
                    continue
                source_a = store.sources.get(a.source_id)
                syndicated = bool(source_a and b.source_id in source_a.related_ids)
                if b.source_id != a.source_id and not syndicated:
                    seen_pairs.add(pair)
                    contradictions.append(Contradiction(
                        id=_id("con", a.id, b.id), row_id=row_id, topic=truncate(rep.text, 120), claim_a_id=a.id,
                        claim_b_id=b.id, source_a_id=a.source_id, source_b_id=b.source_id,
                        nature="forecast" if ClaimType.FORECAST in (a.claim_type, b.claim_type) else "direct",
                        explanation=("Grouped by the LLM as opposing positions on the same proposition."
                                     if grouped_by == "llm" else
                                     "One source affirms what the other disputes or qualifies." + caveat)))
                    break
    contradictions += numeric_contradictions(claims, rows, store)
    return rows, links, contradictions


def numeric_contradictions(claims: list[Claim], rows: list[MatrixRow], store: EvidenceStore) -> list[Contradiction]:
    """Same kind of figure (share vs share, change vs change), similar context, values differing by >= 1.5x."""
    row_of = {cid: r.id for r in rows for cid in r.supporting_claim_ids + r.contradicting_claim_ids}
    common = frequent_terms(claims)
    stats = [(c, percent_mentions(c.text), content_terms(c.text)) for c in claims]
    stats = [s for s in stats if s[1]]
    found = []
    for i, (a, nums_a, terms_a) in enumerate(stats):
        for b, nums_b, terms_b in stats[i + 1:]:
            if a.source_id == b.source_id:
                continue
            related = a.source_id in store.sources and b.source_id in store.sources[a.source_id].related_ids
            if related or len(terms_a & terms_b) < 3 or overlap(terms_a, terms_b) < 0.25:
                continue
            match = None
            for va, kind_a, near_a in nums_a:
                for vb, kind_b, near_b in nums_b:
                    if kind_a == kind_b and (near_a & near_b) - common and min(va, vb) > 0 and max(va, vb) / min(va, vb) >= 1.5:
                        match = (va, vb)
                        break
                if match:
                    break
            if match:
                va, vb = match
                found.append(Contradiction(
                    id=_id("con", a.id, b.id, "num"), row_id=row_of.get(a.id, ""),
                    topic=", ".join(sorted((terms_a & terms_b) - common)[:5]) or "similar measure",
                    claim_a_id=a.id, claim_b_id=b.id, source_a_id=a.source_id, source_b_id=b.source_id, nature="numeric",
                    explanation=(f"Different figures ({va:g}% vs {vb:g}%) for what appears to be a similar measure. This "
                                 "may reflect different definitions, samples or time periods rather than an error.")))
    return found
