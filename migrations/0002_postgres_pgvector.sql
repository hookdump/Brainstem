-- Brainstem PostgreSQL + pgvector baseline schema.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_items (
    memory_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    text TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    salience DOUBLE PRECISION NOT NULL,
    source_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    tombstoned BOOLEAN NOT NULL DEFAULT FALSE,
    embedding VECTOR(1536)
);

CREATE INDEX IF NOT EXISTS idx_memory_tenant_created
    ON memory_items (tenant_id, created_at);

CREATE INDEX IF NOT EXISTS idx_memory_tenant_scope
    ON memory_items (tenant_id, scope);

CREATE TABLE IF NOT EXISTS idempotency_records (
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS graph_terms (
    tenant_id TEXT NOT NULL,
    term TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, term, memory_id)
);

CREATE INDEX IF NOT EXISTS idx_graph_terms_tenant_term
    ON graph_terms (tenant_id, term);

CREATE TABLE IF NOT EXISTS graph_edges (
    tenant_id TEXT NOT NULL,
    src_memory_id TEXT NOT NULL,
    dst_memory_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, src_memory_id, dst_memory_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_tenant_src
    ON graph_edges (tenant_id, src_memory_id);
