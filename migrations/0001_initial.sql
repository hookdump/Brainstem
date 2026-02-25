-- Brainstem v0 initial schema (SQLite-compatible baseline).

CREATE TABLE IF NOT EXISTS memory_items (
    memory_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    text TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    confidence REAL NOT NULL,
    salience REAL NOT NULL,
    source_ref TEXT,
    created_at TEXT NOT NULL,
    tombstoned INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memory_tenant_created
    ON memory_items (tenant_id, created_at);

CREATE INDEX IF NOT EXISTS idx_memory_tenant_scope
    ON memory_items (tenant_id, scope);

CREATE TABLE IF NOT EXISTS idempotency_records (
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);
