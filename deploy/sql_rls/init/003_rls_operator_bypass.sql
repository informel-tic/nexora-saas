-- Nexora SQL/RLS — Migration 003: Operator Bypass & Service Account Setup (J3+)
-- Purpose  : Configure the nexora_owner superuser bypass and the
--             nexora_service read-only role used by the node agent.
--             Also creates helper functions for setting tenant context
--             safely from the application layer.
-- Compatible: PostgreSQL 14+
-- Run as   : superuser
-- Prerequisite: 001_base_schema.sql and 002_rls_policies.sql applied.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────
-- Read-only service role (node agent, metrics scraper)
-- ─────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexora_service') THEN
        CREATE ROLE nexora_service NOLOGIN;
    END IF;
END;
$$;

GRANT SELECT ON tenant_artifacts    TO nexora_service;
GRANT SELECT ON control_plane_state TO nexora_service;

-- node-agent also needs to INSERT tenant artifacts
GRANT INSERT ON tenant_artifacts                   TO nexora_service;
GRANT USAGE, SELECT ON SEQUENCE tenant_artifacts_id_seq TO nexora_service;

-- ─────────────────────────────────────────────────────────────────────
-- Tenant-context helper functions
--
-- Usage from the application:
--   SELECT nexora_set_tenant('acme-corp');
--   -- run queries …
--   SELECT nexora_clear_tenant();
-- ─────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION nexora_set_tenant(p_tenant_id TEXT)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Validate tenant_id is a non-empty string (basic injection guard)
    IF p_tenant_id IS NULL OR trim(p_tenant_id) = '' THEN
        RAISE EXCEPTION 'nexora_set_tenant: tenant_id must not be empty';
    END IF;
    -- LOCAL scope: setting is reverted at end of transaction
    PERFORM set_config('nexora.tenant_id', p_tenant_id, true);
END;
$$;

COMMENT ON FUNCTION nexora_set_tenant(TEXT) IS
    'Set session-local nexora.tenant_id for RLS policy evaluation.';

CREATE OR REPLACE FUNCTION nexora_clear_tenant()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    PERFORM set_config('nexora.tenant_id', '', true);
END;
$$;

COMMENT ON FUNCTION nexora_clear_tenant() IS
    'Clear session nexora.tenant_id (used at end of request).';

CREATE OR REPLACE FUNCTION nexora_set_platform_admin(p_enabled BOOLEAN DEFAULT true)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    PERFORM set_config('nexora.platform_admin', CASE WHEN p_enabled THEN 'true' ELSE '' END, true);
END;
$$;

COMMENT ON FUNCTION nexora_set_platform_admin(BOOLEAN) IS
    'Enable/disable platform-admin cross-tenant read bypass for current transaction.';

-- Grant execution rights to application role
GRANT EXECUTE ON FUNCTION nexora_set_tenant(TEXT)        TO nexora_app;
GRANT EXECUTE ON FUNCTION nexora_clear_tenant()          TO nexora_app;
GRANT EXECUTE ON FUNCTION nexora_set_platform_admin(BOOLEAN) TO nexora_app;

-- ─────────────────────────────────────────────────────────────────────
-- J2 read-switch: view for application code
--
-- Provides a clean SQL surface for SqliteStateRepository.load()
-- to switch from dual-write JSON+SQL to SQL-primary mode.
-- The view is a thin alias — no separate storage.
-- ─────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_control_plane_state AS
    SELECT id, payload, updated_at FROM control_plane_state;

COMMENT ON VIEW v_control_plane_state IS
    'J2 SQL-primary read surface for control plane state (replaces JSON fallback).';

GRANT SELECT ON v_control_plane_state TO nexora_app, nexora_service;

-- ─────────────────────────────────────────────────────────────────────
-- Schema migration record
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO schema_migrations (version, description)
VALUES (
    '003_rls_operator_bypass',
    'Operator BYPASSRLS role, nexora_service read role, tenant context helpers, J2 view'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
