# console — Subscriber Operator Console

## Purpose

Vanilla JavaScript SPA for Nexora tenant operators. Provides fleet monitoring, governance, PRA, scoring, and all operator-facing dashboards.

## Entry Point

- `index.html` — SPA shell (French UI, 25+ nav sections). Loads `app.js` as ES module.

## File Map

| File | Responsibility |
|------|---------------|
| `index.html` | HTML shell with navigation and section containers |
| `app.js` | Application controller — hash-based routing, global action helpers |
| `api.js` | API client — token management (`sessionStorage`), headers, fetch wrappers |
| `views.js` | View renderers — one function per section |
| `components.js` | Reusable UI primitives (stat cards, gauges, alerts, tables, badges) |
| `styles.css` | Stylesheet |
| `assets/` | SVG icons (favicon, nexora mark) |

## Conventions

- **No framework** — vanilla JavaScript with ES modules.
- **Token storage**: `sessionStorage` (not `localStorage`).
- **Routing**: hash-based (`#dashboard`, `#fleet`, `#governance`, etc.).
- **Language**: French UI throughout.
- **Served by**: control plane FastAPI as static file mount at `/console/`.

## Important Notes

- `api.js` is a JavaScript module loaded by the browser — do not confuse with API routes.
- Static asset requests (`*.js`, `*.css`, `*.svg`) must not require authentication.
