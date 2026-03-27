-- Nexora SQL/RLS — Migration 002: Row-Level Security Policies (J3)
-- Purpose  : Enable Postgres RLS on tenant_artifacts so each
--             application session can only read rows belonging to its
--             own tenant.  The control_plane_state table is NOT
--             RLS-protected (single-tenant singleton row).
-- Compatible: PostgreSQL 14+
-- Run as   : superuser (ALTER TABLE … ENABLE ROW LEVEL SECURITY requires it)
-- Prerequisite: 001_base_schema.sql must have been applied.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────
-- Application roles
-- ─────────────────────────────────────────────────────────────────────
-- nexora_app   : unprivileged application role; bound by RLS
-- nexora_owner : schema owner; bypasses RLS via BYPASSRLS
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexora_app') THEN
        CREATE ROLE nexora_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexora_owner') THEN
        CREATE ROLE nexora_owner NOLOGIN BYPASSRLS;
    END IF;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────
-- Grant table access to application role
-- ─────────────────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_artifacts    TO nexora_app;
GRANT SELECT, INSERT, UPDATE         ON control_plane_state TO nexora_app;
GRANT USAGE, SELECT ON SEQUENCE tenant_artifacts_id_seq     TO nexora_app;

-- ─────────────────────────────────────────────────────────────────────
-- Enable Row-Level Security on tenant_artifacts
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE tenant_artifacts ENABLE ROW LEVEL SECURITY;

-- Force RLS even for the table owner (defense-in-depth)
ALTER TABLE tenant_artifacts FORCE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────────
-- Isolation policy: restrict rows to current session tenant
--
-- The application layer sets the tenant context before any query:
--   SET LOCAL nexora.tenant_id = 'acme-corp';
--
-- This policy enforces that SELECT/INSERT/UPDATE/DELETE only affect
-- rows where tenant_id matches the session-level setting.
-- ─────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS tenant_isolation ON tenant_artifacts;

CREATE POLICY tenant_isolation
    ON  tenant_artifacts
    AS  PERMISSIVE
    FOR ALL
    TO  nexora_app
    USING (
        tenant_id = current_setting('nexora.tenant_id', true)
    )
    WITH CHECK (
        tenant_id = current_setting('nexora.tenant_id', true)
    );

COMMENT ON POLICY tenant_isolation ON tenant_artifacts IS
    'J3 RLS: restrict artifact access to current session''s nexora.tenant_id.';

-- ─────────────────────────────────────────────────────────────────────
-- Audit / cross-tenant read policy for platform-admin token
--
-- Operator/admin sessions that set nexora.platform_admin = ''true''
-- may read ALL tenant artifacts (for audit, drift detection, etc.)
-- Write operations are never permitted through this policy.
-- ─────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS platform_admin_read ON tenant_artifacts;

CREATE POLICY platform_admin_read
    ON  tenant_artifacts
    AS  PERMISSIVE
    FOR SELECT
    TO  nexora_app
    USING (
        current_setting('nexora.platform_admin', true) = 'true'
    );

COMMENT ON POLICY platform_admin_read ON tenant_artifacts IS
    'Allow cross-tenant SELECT for platform-admin sessions (audit only).';

-- ─────────────────────────────────────────────────────────────────────
-- Schema migration record
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO schema_migrations (version, description)
VALUES ('002_rls_policies', 'J3 RLS: tenant_isolation + platform_admin_read policies on tenant_artifacts')
ON CONFLICT (version) DO NOTHING;

COMMIT;
