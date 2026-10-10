"""Location-preserving chunking: passages never span two pages/sections, so citations keep a usable location."""
from __future__ import annotations

from src.analysis.text import split_sentences
from src.models.evidence import Passage


def chunk_sections(source_id: str, sections: list[tuple[str, str]], max_chars: int = 900,
                   overlap_sentences: int = 1) -> list[Passage]:
    passages: list[Passage] = []
    for location, text in sections:
        sentences = split_sentences(text) or [text]
        current: list[str] = []
        for sentence in sentences:
            if current and sum(len(s) + 1 for s in current) + len(sentence) > max_chars:
                passages.append(_passage(source_id, len(passages), location, current))
                current = current[-overlap_sentences:] if overlap_sentences else []
            current.append(sentence[:max_chars])
        if current:
            passages.append(_passage(source_id, len(passages), location, current))
    return passages


def _passage(source_id: str, index: int, location: str, sentences: list[str]) -> Passage:
    return Passage(id=f"{source_id}#p{index}", source_id=source_id, text=" ".join(sentences), location=location,
                   index=index)
