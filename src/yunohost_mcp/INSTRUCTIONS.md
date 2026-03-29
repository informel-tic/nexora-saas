# yunohost_mcp — AI-Facing Automation Interface

## Purpose

MCP (Model Context Protocol) server that exposes Nexora/YunoHost capabilities to AI agents. Acts as an adapter layer between AI models and the Nexora domain services.

## Entry Points

- `mcp` FastMCP instance in `server.py` — registers all 27 tool modules.
- CLI via `cli.py` — supports `run` (streamable-http/stdio/SSE) and `compatibility` subcommands.

## Module Map

| Module | Responsibility |
|--------|---------------|
| `server.py` | MCP server wiring, tool registration |
| `cli.py` | CLI entry point for launching the MCP server |
| `config.py` | `MCPSettings` dataclass (host, port, profile, log level) |
| `adapter.py` | `MCPAdapterContext` — shared context injected into handlers |
| `policy.py` | Dangerous-tool whitelist; mode-based tool gating |
| `utils/runner.py` | Command runner with audit logging |
| `utils/safety.py` | Input classification, path guards, safe-operation whitelist |

### Tool Modules (`tools/`)

27 domain-specific tool modules, each exposing a `register_*_tools(mcp)` function:

`app`, `automation`, `backup`, `blueprints`, `docker`, `documentation`, `domain`, `edge`, `failover`, `fleet`, `governance`, `hooks`, `migration`, `modes`, `monitoring`, `multitenant`, `notifications`, `packaging`, `portal`, `pra`, `security`, `sla`, `storage`, `sync`, `system`, `user`.

## Conventions

- Each tool domain is a **separate module** with a `register_*_tools(mcp)` entry point.
- **Mode-based gating**: `policy.tool_allowed()` controls which tools are available in the current runtime mode.
- **Transports**: streamable-http (default port), stdio, SSE.
- **Architecture rule**: MCP is an adapter — it delegates to domain services, never implements business logic directly.

## Testing

```bash
PYTHONPATH=src python -m pytest tests/ -v --tb=short
```

MCP tools are tested indirectly via interface parity tests (`test_interface_parity.py`).
