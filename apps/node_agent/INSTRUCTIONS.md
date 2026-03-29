# node_agent — Node Agent

## Purpose

Passive FastAPI agent deployed on YunoHost nodes. Receives HMAC-signed commands pushed from the SaaS control plane. Does not initiate outbound connections.

## Entry Points

- `app` FastAPI instance in `api.py` — receives enrollment, heartbeat, and overlay mutation commands.
- `agent.py` — thin launcher that imports from `api.py`.

## Architecture

- **Push model**: the SaaS control plane pushes commands to the node agent; the agent never polls.
- All mutations require a valid `X-Nexora-SaaS-Signature` HMAC header.
- Persistent state stored in JSON at `NEXORA_NODE_STATE_PATH`.
- Max request payload: 128 KB.

## Conventions

- **HMAC verification** on every mutation request.
- **No outbound connections** — agent is a passive receiver.
- **Client-side only**: this agent is what clients install. It does not contain control-plane logic.

## Testing

```bash
PYTHONPATH=src python -m pytest tests/ -v --tb=short
```

Node agent behavior tested via `tests/test_node_connector.py` and enrollment flows.
