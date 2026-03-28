from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="YunoHost MCP Server")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="Run the YunoHost MCP server")
    run.add_argument("--host")
    run.add_argument("--port", type=int)
    run.add_argument(
        "--transport",
        choices=["streamable-http", "stdio", "sse"],
        default="streamable-http",
    )
    compat = sub.add_parser("compatibility", help="Print Nexora ↔ YunoHost compatibility matrix")
    compat.add_argument("--matrix", default="")
    args = parser.parse_args()
    if args.command == "compatibility":
        from nexora_node_sdk.compatibility import (
            load_compatibility_matrix,
            resolve_compatibility_matrix_path,
        )

        matrix_path = (
            Path(args.matrix) if args.matrix else resolve_compatibility_matrix_path(Path(__file__).resolve().parents[2])
        )
        print(
            json.dumps(
                load_compatibility_matrix(matrix_path if matrix_path.exists() else None),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command != "run":
        parser.print_help()
        return 1
    from yunohost_mcp.config import load_settings

    settings = load_settings()
    host = args.host or settings.bind_host
    port = args.port or settings.bind_port
    from yunohost_mcp.server import mcp

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return 0
    app = mcp.streamable_http_app()
    import uvicorn

    uvicorn.run(app, host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
