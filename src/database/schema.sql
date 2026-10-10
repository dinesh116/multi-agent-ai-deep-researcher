-- Deep Researcher AI persistence. Every per-run table references runs(id) ON DELETE CASCADE,
-- so deleting a run removes all of its stored evidence. No secrets are stored.
-- Indexed columns hold identifiers/relationships; `data` holds the full validated Pydantic record as JSON.

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    status TEXT NOT NULL,              -- running | completed | failed
    mode TEXT NOT NULL,                -- demo | live
    created_at TEXT NOT NULL,
    completed_at TEXT,
    parent_run_id TEXT,
    request TEXT NOT NULL,
    plan TEXT,
    usage TEXT,
    statuses TEXT,
    stop_reason TEXT,
    summary TEXT,
    warnings TEXT NOT NULL DEFAULT '[]',
    errors TEXT NOT NULL DEFAULT '[]',
    provider_notes TEXT NOT NULL DEFAULT '[]',
    counts TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sources (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    source_type TEXT NOT NULL,
    origin TEXT NOT NULL,
    published_date TEXT,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS passages (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    location TEXT,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS assessments (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, source_id)
);

CREATE TABLE IF NOT EXISTS claims (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    passage_id TEXT NOT NULL,
    subquestion_id TEXT,
    claim_type TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS matrix_rows (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    subquestion_id TEXT,
    agreement TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS evidence_links (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL,
    row_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, claim_id, row_id)
);

CREATE TABLE IF NOT EXISTS contradictions (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    claim_a_id TEXT NOT NULL,
    claim_b_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS gaps (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS insights (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS reports (
    run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    agent TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS search_log (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    provider TEXT NOT NULL,
    query TEXT NOT NULL,
    status TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS qa_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Uploaded documents are global (reusable across runs) and can be deleted independently.
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL,
    sections TEXT NOT NULL,
    warnings TEXT NOT NULL DEFAULT '[]',
    uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_cache (
    key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    query TEXT NOT NULL,
    results TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
