-- Nexora SQL/RLS — Migration 001: Base Schema (J0/J1)
-- Purpose  : Create the canonical Postgres tables that mirror the
--             SQLite SqliteStateRepository schema.  This is the
--             foundation for J2 (SQL-primary reads) and J3 (RLS).
-- Compatible: PostgreSQL 14+
-- Run as   : nexora_owner (table owner role)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────
-- Control-plane singleton state
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS control_plane_state (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    payload    TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  control_plane_state IS
    'Singleton row holding the full control-plane state payload (JSON).';
COMMENT ON COLUMN control_plane_state.payload IS
    'JSON blob — mirrors SqliteStateRepository.save() output.';

-- ─────────────────────────────────────────────────────────────────────
-- Per-tenant artifact index (J1 isolation surface)
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenant_artifacts (
    id         BIGSERIAL   PRIMARY KEY,
    tenant_id  TEXT        NOT NULL,
    kind       TEXT        NOT NULL,
    payload    TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_artifacts_tenant_kind
    ON tenant_artifacts (tenant_id, kind);

COMMENT ON TABLE  tenant_artifacts IS
    'Per-tenant artifact index (inventory snapshots, security events, …).';
COMMENT ON COLUMN tenant_artifacts.tenant_id IS
    'Opaque tenant identifier; used for RLS policy filtering (J3).';
COMMENT ON COLUMN tenant_artifacts.kind IS
    'Artifact type: inventory_snapshot | security_event | …';

-- ─────────────────────────────────────────────────────────────────────
-- Persistence metadata (schema version audit trail)
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT        PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    description TEXT
);

INSERT INTO schema_migrations (version, description)
VALUES ('001_base_schema', 'Base schema: control_plane_state + tenant_artifacts')
ON CONFLICT (version) DO NOTHING;

COMMIT;
