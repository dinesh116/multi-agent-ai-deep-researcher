"""Quantitative facts, named entities and timelines extracted from evidence.

Deterministic extraction works offline (demo mode). In live mode the LLM proposes data points and entities
too, and each data point is accepted only if its quote appears verbatim in a passage.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date

from src.analysis.text import INJECTION_PATTERNS, STOPWORDS, split_sentences, truncate
from src.models.evidence import Claim, DataPoint, Entity, Passage, Source

NUMBER = re.compile(
    r"(?P<cur>[$€£₹])?\s?(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?"
    r"(?P<unit>%|percent|per cent|x\b|times|billion|million|bn\b|mn\b|trillion|months?|years?|days?|"
    r"points?|tokens|tasks|enterprises|firms|companies|respondents|staff|customers)?", re.I)
CHANGE = re.compile(r"\b(grow|grew|growth|increase\w*|decrease\w*|reduc\w*|cut|rise|rose|fell|fall|decline\w*|"
                    r"improv\w*|higher|lower|faster|slower|more|less)\b", re.I)
METHOD = [("randomised/field experiment", r"\b(field experiment|randomi[sz]ed|rct|staggered rollout)\b"),
          ("survey", r"\b(survey|poll|respondents)\b"), ("benchmark", r"\bbenchmark\w*\b"),
          ("internal analysis", r"\binternal analysis\b"), ("review of deployments", r"\breview of \d+"),
          ("administrative/official data", r"\b(licensed|filings?|official statistics)\b")]
YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
UNIT_NORMAL = {"percent": "%", "per cent": "%", "times": "x", "x": "x", "bn": "billion", "mn": "million"}
ENTITY_SUFFIX = re.compile(r"\b(Inc|Ltd|Limited|Corp|Corporation|Bank|Holdings|Group|Finserv|Capital|LLC|GmbH|AG)\.?$")
REGULATION = re.compile(r"\b(Act|Regulation|Directive|Guidance|Guidelines|Mission|Framework|Policy|Rules)\b")
GENERIC_CAPS = {"The", "This", "These", "Those", "It", "Our", "We", "They", "However", "According", "In", "On", "For",
                "A", "An", "Of", "And", "Firms", "Most", "Some", "Several", "Only", "Customer", "Executives", "Analysts",
                "Investors", "Founders", "Respondents", "Agents", "AI", "Early", "Large", "Claims", "Critics", "Vendors",
                "Industry", "Payment", "Pricing", "Long", "Retrieval", "Graph", "Hybrid", "Evaluation", "Using", "Across",
                "SaaS", "LLM", "LLMs", "API", "APIs", "CRM", "ERP", "IT", "CIO", "CIOs", "GPU", "GPUs", "UI", "US", "EU"}


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


VERB_AFTER = re.compile(r"^\s*(?:of\s+[\w\s,\-]{0,40}?\s)?(have|has|use|uses|used|report|reports|reported|say|said|"
                        r"expect|expects|are|is|were|was|plan|run|consume|consumes|act|operate|resolve|resolves|"
                        r"complete|completes|reduced|increased|cited)\b", re.I)


FILLER = {"least", "around", "about", "roughly", "nearly", "almost", "approximately", "only", "some", "said"}


def _content(words: list[str]) -> list[str]:
    return [w for w in words if w.lower() not in STOPWORDS and w.lower() not in FILLER and not w.isdigit()]


def _metric_words(before: str, after: str) -> str:
    """Name the measured quantity from the words around the number (heuristic; the LLM does better)."""
    after_words = re.findall(r"[A-Za-z][A-Za-z\-]+", after)
    before_words = re.findall(r"[A-Za-z][A-Za-z\-]+", before)
    of_match = re.match(r"\s*(?:of|among)\s+((?:[A-Za-z\-]+\s?){1,4})", after)
    if VERB_AFTER.match(after):  # "38% (of firms) have agents in production" -> what follows is the measure
        rest = after[of_match.end():] if of_match else after
        tail = re.split(r"[,;.]| and | but ", rest, maxsplit=1)[0]
        words = _content(re.findall(r"[A-Za-z][A-Za-z\-]+", tail))
        subject = _content(of_match.group(1).split()) if of_match else []
        return truncate(" ".join(subject[:3] + words[:7]), 80)
    if of_match:  # "share of 72% of enterprises"
        return truncate(" ".join(_content(before_words)[-3:] + _content(of_match.group(1).split())), 80)
    return truncate(" ".join(_content(before_words)[-5:] or _content(after_words)[:5]), 80)


def parse_value(text: str) -> float | None:
    match = re.search(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", text or "")
    return float(match.group(0).replace(",", "")) if match else None


def heuristic_data_points(source: Source, passages: list[Passage], limit: int = 12) -> list[DataPoint]:
    """Numbers with units in assertive sentences (percentages, money, multiples, counts with nouns)."""
    found: list[DataPoint] = []
    for passage in passages:
        for sentence in split_sentences(passage.text):
            if INJECTION_PATTERNS.search(sentence) or len(sentence) > 400:
                continue
            for match in NUMBER.finditer(sentence):
                unit = (match.group("unit") or "").lower()
                currency = match.group("cur")
                number = match.group("num")
                if not unit and not currency:
                    continue  # bare numbers (years, ids) are not data points
                if YEAR.fullmatch(number) and unit in ("", "years"):
                    continue
                value = float(number.replace(",", ""))
                unit = UNIT_NORMAL.get(unit, unit)
                if currency:
                    unit = f"{ {'$': 'USD', '€': 'EUR', '£': 'GBP', '₹': 'INR'}[currency]} {unit}".strip()
                before, after = sentence[:match.start()], sentence[match.end():]
                metric = _metric_words(before, after)
                if not metric:
                    continue
                method = next((label for label, pattern in METHOD if re.search(pattern, sentence, re.I)), "")
                year = YEAR.search(sentence)
                found.append(DataPoint(
                    id=_id("dp", source.id, sentence, match.group(0)), metric=metric, value=value,
                    value_text=match.group(0).strip(), unit=unit,
                    kind="change" if ((CHANGE.search(before[-60:]) or re.search(r"\bby\s*$", before))
                                      and not re.match(r"\s*of\b", after)) else "level",
                    subject=_subject(after), period=year.group(0) if year else "", method=method,
                    source_id=source.id, passage_id=passage.id, quote=sentence, location=passage.location))
                if len(found) >= limit:
                    return found
    return found


def _subject(after: str) -> str:
    match = re.match(r"\s*(?:of|among|for)\s+((?:[A-Za-z0-9,\-]+\s?){1,5})", after)
    return match.group(1).strip(" ,") if match else ""


def heuristic_entities(claims: list[Claim], sources: dict[str, Source], min_sources: int = 2) -> list[Entity]:
    """Capitalised names recurring across independent claims/sources (organisations, products, rules)."""
    mentions: dict[str, dict] = defaultdict(lambda: {"sources": set(), "claims": set(), "count": 0})
    for claim in claims:
        for name in _capitalised_names(claim.quote):
            entry = mentions[name]
            entry["sources"].add(claim.source_id)
            entry["claims"].add(claim.id)
            entry["count"] += 1
    for source in sources.values():  # publishers that are organisations also count, once per source
        if source.publisher and ENTITY_SUFFIX.search(source.publisher.replace(" (synthetic)", "")):
            mentions[source.publisher.replace(" (synthetic)", "")]["sources"].add(source.id)
    entities = []
    for name, entry in mentions.items():
        if (len(entry["sources"]) < min_sources and entry["count"] < 3) or not is_named_entity(name):
            continue
        entities.append(Entity(id=_id("ent", name.lower()), name=name, kind=entity_kind(name),
                               mentions=entry["count"] or len(entry["sources"]), source_ids=sorted(entry["sources"]),
                               claim_ids=sorted(entry["claims"])))
    return sorted(entities, key=lambda e: (-len(e.source_ids), -e.mentions, e.name))[:30]


def _capitalised_names(text: str) -> list[str]:
    names = []
    for match in re.finditer(r"\b([A-Z][a-zA-Z0-9&\-]+(?:\s+(?:of\s+)?[A-Z][a-zA-Z0-9&\-]+){0,4})", text):
        name = match.group(1).strip()
        first = name.split()[0]
        if first in GENERIC_CAPS or len(name) < 3 or name.isupper() and len(name) < 3:
            continue
        if match.start() == 0 and " " not in name and not re.search(r"[A-Z].*[A-Z]", name):
            continue  # a capitalised sentence-starter word, not a name
        names.append(name)
    return names


GENERIC_ENTITY_WORDS = {"ai", "genai", "generative", "artificial", "intelligence", "agentic", "agents", "agent", "llm",
                        "llms", "industry", "sector", "market", "institutions", "companies", "firms", "banks",
                        "payments", "payment", "fintech", "technology", "technologies", "powered", "based", "saas",
                        "machine", "learning", "data", "cloud", "software", "enterprise", "enterprises", "model", "models"}


def is_named_entity(name: str) -> bool:
    """A proper name (has a capital letter) that is not just generic technology/industry vocabulary."""
    words = re.findall(r"[A-Za-z0-9]+", name)
    if not words or not re.search(r"[A-Z]", name):
        return False
    return any(w.lower() not in GENERIC_ENTITY_WORDS for w in words) and name not in GENERIC_CAPS


def entity_kind(name: str) -> str:
    if ENTITY_SUFFIX.search(name):
        return "company"
    if REGULATION.search(name):
        return "regulation"
    if re.search(r"\b(Bench|GPT|RAG|API|Platform|Cloud|AI)\b", name):
        return "product"
    if re.fullmatch(r"[A-Z][a-z]+[A-Z][A-Za-z]+", name):  # CamelCase brands, e.g. AgentForge
        return "company"
    return "named_entity"


def timeline(claims: list[Claim], sources: dict[str, Source], today: date, limit: int = 14) -> list[dict]:
    """Dated statements: events and forecasts with explicit years, ordered chronologically (duplicates removed)."""
    events, seen = [], set()
    for claim in claims:
        for year in YEAR.findall(claim.text):
            key = (year, re.sub(r"[^a-z0-9]", "", claim.text.lower())[:80])
            if key in seen:
                continue
            seen.add(key)
            y = int(year)
            source = sources.get(claim.source_id)
            published = source.published_date.year if source and source.published_date else None
            kind = "forecast" if y > today.year or (published and y > published) else "event"
            events.append({"year": y, "kind": kind, "text": claim.text, "source_id": claim.source_id,
                           "claim_id": claim.id})
    events.sort(key=lambda e: (e["year"], e["kind"]))
    return events[:limit]


COMMON_METRIC_WORDS = {"agent", "agents", "enterprise", "enterprises", "generative", "report", "reported",
                       "found", "said", "expect", "companies", "firms"}


def _metric_terms(metric: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", metric.lower()) if w not in COMMON_METRIC_WORDS and w not in STOPWORDS}


def group_data_points(points: list[DataPoint]) -> list[list[DataPoint]]:
    """Group data points that describe a comparable measure: same unit and kind, strongly overlapping metric words."""
    groups: list[list[DataPoint]] = []
    for point in points:
        words = _metric_terms(point.metric)
        for group in groups:
            ref = group[0]
            ref_words = _metric_terms(ref.metric)
            shared = words & ref_words
            smaller = max(1, min(len(words), len(ref_words)))
            if (ref.unit == point.unit and ref.kind == point.kind and shared and len(shared) / smaller >= 0.5
                    and (len(shared) >= 2 or smaller <= 2)):
                group.append(point)
                break
        else:
            groups.append([point])
    return groups
