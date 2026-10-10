"""Offline providers: the synthetic demo corpus and the user's uploaded documents."""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from src.config import SAMPLE_DIR
from src.retrieval.bm25 import BM25Index
from src.search.base import SearchResult, parse_date

DEMO_LIMITATION = "SYNTHETIC demo source: fictional content for demonstration only. Not real evidence."


@lru_cache(maxsize=4)
def load_corpus(path: str = str(SAMPLE_DIR / "corpus.json")) -> tuple[dict, ...]:
    return tuple(json.loads(Path(path).read_text())["sources"])


class DemoProvider:
    """Searches the bundled synthetic corpus. Works with no network and no keys."""

    name, label, live = "demo", "Synthetic demo corpus (offline)", False
    serves = {"web", "academic", "news", "official"}
    available = True
    unavailable_reason = ""

    def __init__(self, corpus_path: str | None = None):
        self.records = load_corpus(corpus_path) if corpus_path else load_corpus()
        self.index = BM25Index(list(self.records), lambda r: f"{r['title']} {r['title']} {r['content']}")

    def search(self, query: str, max_results: int = 5, date_from: date | None = None,
               date_to: date | None = None) -> list[SearchResult]:
        results = []
        for record, score in self.index.search(query, k=max_results * 3):
            published = parse_date(record.get("published_date"))
            if (date_from and published and published < date_from) or (date_to and published and published > date_to):
                continue
            results.append(SearchResult(
                title=record["title"], provider="demo", url=record.get("url"), doc_ref=record.get("doi"),
                snippet=record["content"][:400], content=record["content"], full_text_available=True,
                publisher=record.get("publisher"), authors=record.get("authors", []), published_date=published,
                source_type=record.get("source_type", "other"), score=score,
                metadata={"synthetic": True, "corpus_key": record["key"], "references": record.get("references", [])},
                limitations=[DEMO_LIMITATION]))
            if len(results) >= max_results:
                break
        return results


class UploadedDocumentProvider:
    """Searches documents the user uploaded (passages keep page/section locations)."""

    name, label, live = "upload", "Your uploaded documents", False
    serves = {"uploaded", "dataset"}
    available = True
    unavailable_reason = ""

    def __init__(self, documents: list[dict]):
        # documents: [{"id", "title", "kind", "sections": [(location, text)], "filename"}]
        self.documents = documents
        self.sections = [(doc, loc, text) for doc in documents for loc, text in doc["sections"]]
        self.index = BM25Index(self.sections, lambda s: f"{s[0]['title']} {s[2]}")

    def search(self, query: str, max_results: int = 5, date_from: date | None = None,
               date_to: date | None = None) -> list[SearchResult]:
        best: dict[str, tuple[float, list]] = {}
        for (doc, location, text), score in self.index.search(query, k=40):
            entry = best.setdefault(doc["id"], (score, []))
            entry[1].append((location, text))
        results = []
        for doc_id, (score, _) in sorted(best.items(), key=lambda kv: -kv[1][0])[:max_results]:
            doc = next(d for d in self.documents if d["id"] == doc_id)
            results.append(SearchResult(
                title=doc["title"], provider="upload", doc_ref=doc["id"], snippet=doc["sections"][0][1][:400],
                content="\n\n".join(t for _, t in doc["sections"]), full_text_available=True,
                publisher=f"Uploaded file: {doc['filename']}", source_type="dataset" if doc["kind"] == "csv" else "user_document",
                score=score, sections=list(doc["sections"]), metadata={"filename": doc["filename"], "kind": doc["kind"],
                    "table_columns": doc.get("metadata", {}).get("columns", []),
                    "table_records": doc.get("metadata", {}).get("records", [])},
                limitations=["User-provided document: provenance and accuracy not independently checked."]))
        return results
