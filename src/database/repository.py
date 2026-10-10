"""SQLite repository: research runs, evidence, documents, search cache and settings.

All SQL lives here. A short-lived connection is opened per operation (safe with Streamlit's threads).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.models.evidence import (AgentEvent, AgentStatus, Claim, Contradiction, EvidenceLink, Insight, MatrixRow,
                                 Passage, Report, ResearchGap, Source, SourceAssessment)
from src.models.research import BudgetUsage, ResearchPlan, ResearchRequest, new_id, now
from src.models.run import RunBundle, RunSummary

SCHEMA = Path(__file__).with_name("schema.sql")


def _dump(model) -> str:
    return model.model_dump_json() if hasattr(model, "model_dump_json") else json.dumps(model, default=str)


class Repository:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA.read_text())

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ runs
    def create_run(self, run_id: str, request: ResearchRequest) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO runs (id, question, status, mode, created_at, parent_run_id, request) "
                         "VALUES (?, ?, 'running', ?, ?, ?, ?)",
                         (run_id, request.question, request.mode.value, now().isoformat(), request.parent_run_id,
                          request.model_dump_json()))

    def save_run_results(self, run_id: str, state: dict, status: str) -> None:
        report: Report | None = state.get("report")
        exec_summary = report.section("executive_summary").content if report and report.section("executive_summary") else ""
        counts = {"sources": len(state.get("sources", [])), "claims": len(state.get("claims", [])),
                  "contradictions": len(state.get("contradictions", [])), "insights": len(state.get("insights", [])),
                  "iterations": state.get("iteration", 0) + 1, "gaps": len(state.get("gaps", []))}
        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not exists:
                request = state["request"]
                conn.execute("INSERT INTO runs (id, question, status, mode, created_at, request) VALUES (?, ?, ?, ?, ?, ?)",
                             (run_id, request.question, status, request.mode.value, now().isoformat(),
                              request.model_dump_json()))
            conn.execute(
                "UPDATE runs SET status = ?, completed_at = ?, plan = ?, usage = ?, statuses = ?, stop_reason = ?, "
                "summary = ?, warnings = ?, errors = ?, provider_notes = ?, counts = ? WHERE id = ?",
                (status, now().isoformat(), _dump(state["plan"]) if state.get("plan") else None,
                 _dump(state["usage"]) if state.get("usage") else None,
                 json.dumps({k: v.model_dump(mode="json") for k, v in state.get("statuses", {}).items()}),
                 state.get("stop_reason", ""), exec_summary[:4000], json.dumps(list(dict.fromkeys(state.get("warnings", [])))),
                 json.dumps(state.get("errors", [])), json.dumps(state.get("provider_notes", [])), json.dumps(counts),
                 run_id))
            for table in ("sources", "passages", "assessments", "claims", "matrix_rows", "evidence_links",
                          "contradictions", "gaps", "insights", "reports", "events", "search_log"):
                conn.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
            conn.executemany("INSERT OR IGNORE INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (run_id, s.id, s.title, s.url, s.source_type.value, s.origin.value,
                 s.published_date.isoformat() if s.published_date else None, _dump(s)) for s in state.get("sources", [])])
            conn.executemany("INSERT OR IGNORE INTO passages VALUES (?, ?, ?, ?, ?)", [
                (run_id, p.id, p.source_id, p.location, _dump(p)) for p in state.get("passages", [])])
            conn.executemany("INSERT OR IGNORE INTO assessments VALUES (?, ?, ?)", [
                (run_id, sid, _dump(a)) for sid, a in state.get("assessments", {}).items()])
            conn.executemany("INSERT OR IGNORE INTO claims VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (run_id, c.id, c.source_id, c.passage_id, c.subquestion_id, c.claim_type.value, _dump(c))
                for c in state.get("claims", [])])
            conn.executemany("INSERT OR IGNORE INTO matrix_rows VALUES (?, ?, ?, ?, ?)", [
                (run_id, r.id, r.subquestion_id, r.agreement.value, _dump(r)) for r in state.get("matrix", [])])
            conn.executemany("INSERT OR IGNORE INTO evidence_links VALUES (?, ?, ?, ?, ?, ?)", [
                (run_id, l.claim_id, l.row_id, l.source_id, l.relation.value, _dump(l)) for l in state.get("links", [])])
            conn.executemany("INSERT OR IGNORE INTO contradictions VALUES (?, ?, ?, ?, ?)", [
                (run_id, c.id, c.claim_a_id, c.claim_b_id, _dump(c)) for c in state.get("contradictions", [])])
            conn.executemany("INSERT OR IGNORE INTO gaps VALUES (?, ?, ?)", [
                (run_id, g.id, _dump(g)) for g in state.get("gaps", [])])
            conn.executemany("INSERT OR IGNORE INTO insights VALUES (?, ?, ?, ?, ?)", [
                (run_id, i.id, i.kind.value, i.label.value, _dump(i)) for i in state.get("insights", [])])
            if report:
                conn.execute("INSERT INTO reports VALUES (?, ?, ?, ?)",
                             (run_id, report.title, _dump(report), report.created_at.isoformat()))
            conn.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (run_id, n, e.timestamp.isoformat(), e.agent, e.status, e.message, _dump(e))
                for n, e in enumerate(state.get("events", []))])
            conn.executemany("INSERT INTO search_log VALUES (?, ?, ?, ?, ?, ?)", [
                (run_id, n, r.provider, r.query, r.status, _dump(r)) for n, r in enumerate(state.get("search_log", []))])

    def list_runs(self, limit: int = 100) -> list[RunSummary]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, question, status, mode, created_at, completed_at, summary, counts, "
                                "parent_run_id FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [RunSummary(id=r["id"], question=r["question"], status=r["status"], mode=r["mode"],
                           created_at=r["created_at"], completed_at=r["completed_at"], summary=r["summary"] or "",
                           counts=json.loads(r["counts"] or "{}"), parent_run_id=r["parent_run_id"]) for r in rows]

    def load_run(self, run_id: str) -> RunBundle | None:
        with self._connect() as conn:
            run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not run:
                return None

            def rows(table: str, order: str = "rowid") -> list[str]:
                return [r["data"] for r in conn.execute(f"SELECT data FROM {table} WHERE run_id = ? ORDER BY {order}",
                                                        (run_id,)).fetchall()]
            report_row = conn.execute("SELECT data FROM reports WHERE run_id = ?", (run_id,)).fetchone()
            summary = RunSummary(id=run["id"], question=run["question"], status=run["status"], mode=run["mode"],
                                 created_at=run["created_at"], completed_at=run["completed_at"],
                                 summary=run["summary"] or "", counts=json.loads(run["counts"] or "{}"),
                                 parent_run_id=run["parent_run_id"])
            return RunBundle(
                summary=summary, request=ResearchRequest.model_validate_json(run["request"]),
                plan=ResearchPlan.model_validate_json(run["plan"]) if run["plan"] else None,
                usage=BudgetUsage.model_validate_json(run["usage"]) if run["usage"] else None,
                statuses={k: AgentStatus.model_validate(v) for k, v in json.loads(run["statuses"] or "{}").items()},
                stop_reason=run["stop_reason"] or "",
                sources=[Source.model_validate_json(d) for d in rows("sources")],
                passages=[Passage.model_validate_json(d) for d in rows("passages")],
                assessments={a.source_id: a for a in (SourceAssessment.model_validate_json(d) for d in rows("assessments"))},
                claims=[Claim.model_validate_json(d) for d in rows("claims")],
                matrix=[MatrixRow.model_validate_json(d) for d in rows("matrix_rows")],
                links=[EvidenceLink.model_validate_json(d) for d in rows("evidence_links")],
                contradictions=[Contradiction.model_validate_json(d) for d in rows("contradictions")],
                gaps=[ResearchGap.model_validate_json(d) for d in rows("gaps")],
                insights=[Insight.model_validate_json(d) for d in rows("insights")],
                report=Report.model_validate_json(report_row["data"]) if report_row else None,
                events=[AgentEvent.model_validate_json(d) for d in rows("events", "seq")],
                search_log=[json.loads(d) for d in rows("search_log", "seq")],
                warnings=json.loads(run["warnings"] or "[]"), errors=json.loads(run["errors"] or "[]"),
                provider_notes=json.loads(run["provider_notes"] or "[]"))

    def delete_run(self, run_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))  # cascades to every per-run table

    def mark_stale_runs(self) -> None:
        """Runs left 'running' by a closed app session are marked failed on startup."""
        with self._connect() as conn:
            conn.execute("UPDATE runs SET status = 'failed', errors = ? WHERE status = 'running'",
                         (json.dumps(["The app stopped before this run finished."]),))

    # ------------------------------------------------------------------ Q&A history
    def save_qa(self, run_id: str, question: str, answer: dict) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO qa_messages (run_id, question, data, created_at) VALUES (?, ?, ?, ?)",
                         (run_id, question, json.dumps(answer, default=str), now().isoformat()))

    def list_qa(self, run_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT question, data, created_at FROM qa_messages WHERE run_id = ? ORDER BY id",
                                (run_id,)).fetchall()
        return [{"question": r["question"], "answer": json.loads(r["data"]), "created_at": r["created_at"]} for r in rows]

    # ------------------------------------------------------------------ documents
    def save_document(self, filename: str, title: str, kind: str, data: bytes, sections: list[tuple[str, str]],
                      warnings: list[str]) -> tuple[str, bool]:
        """Returns (document id, created). Identical files are stored once."""
        digest = hashlib.sha256(data).hexdigest()
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM documents WHERE sha256 = ?", (digest,)).fetchone()
            if existing:
                return existing["id"], False
            doc_id = new_id("doc")
            conn.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (doc_id, filename, title, kind, digest, len(data), json.dumps(sections), json.dumps(warnings),
                          now().isoformat()))
            return doc_id, True

    def list_documents(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, filename, title, kind, size_bytes, warnings, uploaded_at, sections "
                                "FROM documents ORDER BY uploaded_at DESC").fetchall()
        return [{"id": r["id"], "filename": r["filename"], "title": r["title"], "kind": r["kind"],
                 "size_bytes": r["size_bytes"], "warnings": json.loads(r["warnings"]), "uploaded_at": r["uploaded_at"],
                 "sections": len(json.loads(r["sections"]))} for r in rows]

    def get_documents(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM documents WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
        return [{"id": r["id"], "filename": r["filename"], "title": r["title"], "kind": r["kind"],
                 "sections": [tuple(s) for s in json.loads(r["sections"])]} for r in rows]

    def delete_document(self, doc_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # ------------------------------------------------------------------ search cache
    def get_cached(self, key: str, ttl_hours: int = 24) -> list[dict] | None:
        cutoff = (datetime.now() - timedelta(hours=ttl_hours)).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT results FROM search_cache WHERE key = ? AND created_at >= ?", (key, cutoff)).fetchone()
        return json.loads(row["results"]) if row else None

    def put_cached(self, key: str, provider: str, query: str, results: list[dict]) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?, ?, ?)",
                         (key, provider, query, json.dumps(results, default=str), now().isoformat()))

    def clear_cache(self) -> int:
        with self._connect() as conn:
            return conn.execute("DELETE FROM search_cache").rowcount

    def cache_size(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM search_cache").fetchone()[0]

    # ------------------------------------------------------------------ settings (non-secret only)
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        if any(word in key.lower() for word in ("key", "secret", "token", "password")):
            raise ValueError("Secrets must be configured in .env, not stored in the database.")
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
