# owner_console — Owner Console (Passphrase-Auth)

## Purpose

Alternative console variant for the Nexora platform owner. Uses passphrase-based session authentication instead of API tokens. Provides unrestricted access to all platform surfaces.

## Entry Point

- `index.html` — SPA shell with purple branding and passphrase login form.

## File Map

| File | Responsibility |
|------|---------------|
| `index.html` | HTML shell — purple-branded owner variant |
| `app.js` | Application controller — reuses `../console/views.js` and `../console/components.js` |
| `api.js` | API client — passphrase → session token flow (stored in `sessionStorage`) |

## Conventions

- **Inherits views/components** from the subscriber console (`../console/`).
- **Separate auth flow**: passphrase-based, not API token.
- **Purple branding** overrides to visually distinguish from subscriber console.
- **No access restrictions**: owner has full platform access.
- **Served by**: control plane FastAPI as static file mount at `/owner-console/`.
