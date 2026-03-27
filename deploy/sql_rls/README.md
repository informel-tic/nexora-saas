# SQL / RLS Migration Runbook

This directory contains the Postgres schema migration scripts for Nexora's
**J0→J3 persistence ladder**.

## Migration Ladder

| Stage | File | Description |
|-------|------|-------------|
| J0    | *(SQLite dual-write enabled)* | JSON + SQLite dual-write active — zero config |
| J1    | `001_base_schema.sql` | Postgres tables matching SQLite schema |
| J2    | `001_base_schema.sql` + `dual_write=False` in config | SQL-primary reads; JSON fallback disabled |
| J3    | `002_rls_policies.sql` | Row-Level Security per tenant on `tenant_artifacts` |
| J3+   | `003_rls_operator_bypass.sql` | Operator bypass role, service role, tenant context helpers |

## Steps

### 1 — Apply base schema (J1)

```bash
psql -U postgres -d nexora \
  -f deploy/sql_rls/init/001_base_schema.sql
```

This creates:
- `control_plane_state` — singleton control-plane payload
- `tenant_artifacts` — per-tenant artifact index
- `schema_migrations` — applied migration audit trail

### 2 — Apply RLS policies (J3)

Run **as a superuser** (RLS requires it):

```bash
psql -U postgres -d nexora \
  -f deploy/sql_rls/init/002_rls_policies.sql
```

This creates:
- Roles `nexora_app` (application, RLS-bound) and `nexora_owner` (BYPASSRLS)
- Table grants for `nexora_app`
- `ALTER TABLE tenant_artifacts ENABLE ROW LEVEL SECURITY`
- Policy `tenant_isolation` — reads/writes scoped to `nexora.tenant_id` session variable
- Policy `platform_admin_read` — cross-tenant SELECT for audit operations

### 3 — Apply operator bypass + service role (J3+)

```bash
psql -U postgres -d nexora \
  -f deploy/sql_rls/init/003_rls_operator_bypass.sql
```

This creates:
- Role `nexora_service` (read-only + insert for node agent)
- Helper SQL functions: `nexora_set_tenant()`, `nexora_clear_tenant()`, `nexora_set_platform_admin()`
- View `v_control_plane_state` (J2 SQL-primary read surface)

### 4 — Switch to SQL-primary reads (J2)

In `var/nexora-state.json` or environment:

```yaml
# config: disable JSON dual-write (reads now come from Postgres only)
NEXORA_PERSISTENCE_DUAL_WRITE=false
```

Or in code (`SqliteStateRepository` / future `PostgresStateRepository`):
```python
repo = SqliteStateRepository(db_path=..., fallback_path=..., dual_write=False)
```

`coherence_report()` will then show `mode: "sql-only"`.

## Setting Tenant Context in Queries

Before executing any query that touches `tenant_artifacts`:

```sql
-- Within a transaction:
SELECT nexora_set_tenant('acme-corp');

-- Your application queries …
SELECT * FROM tenant_artifacts WHERE kind = 'inventory_snapshot';

-- Clear at end of request:
SELECT nexora_clear_tenant();
```

For platform-admin cross-tenant audit:

```sql
SELECT nexora_set_platform_admin(true);
SELECT * FROM tenant_artifacts;  -- reads ALL tenants
SELECT nexora_set_platform_admin(false);
```

## Testing RLS (manual)

```sql
-- As nexora_app (no tenant set → empty result)
SET ROLE nexora_app;
SELECT * FROM tenant_artifacts;          -- 0 rows

-- Set tenant context
SELECT nexora_set_tenant('acme-corp');
SELECT * FROM tenant_artifacts;          -- only acme-corp rows

-- As nexora_owner (bypasses RLS)
SET ROLE nexora_owner;
SELECT * FROM tenant_artifacts;          -- ALL rows
```

## Rollback

```sql
-- Remove RLS policies
DROP POLICY IF EXISTS tenant_isolation   ON tenant_artifacts;
DROP POLICY IF EXISTS platform_admin_read ON tenant_artifacts;
ALTER TABLE tenant_artifacts DISABLE ROW LEVEL SECURITY;

-- Remove helper functions
DROP FUNCTION IF EXISTS nexora_set_tenant(TEXT);
DROP FUNCTION IF EXISTS nexora_clear_tenant();
DROP FUNCTION IF EXISTS nexora_set_platform_admin(BOOLEAN);

-- Drop view
DROP VIEW IF EXISTS v_control_plane_state;
```

## Notes

- These scripts are IDEMPOTENT (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).
- The `control_plane_state` table is NOT RLS-protected (single row, no tenant key).
- The `dual_write=True` default in `SqliteStateRepository` means JSON state is still
  written as backup during J1 → J2 transition.  Set `dual_write=False` only after
  confirming Postgres is the durable primary.
- Tracked in [docs/TECH_DEBT_REGISTER.md](../../docs/TECH_DEBT_REGISTER.md) as NEXT-25.
