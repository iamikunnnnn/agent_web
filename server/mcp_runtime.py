from __future__ import annotations

import os
from typing import Any

VALID_TRANSPORTS = {"stdio", "streamable-http", "sse"}


def get_mcp_run_config(
    *,
    default_port: int,
    default_host: str = "0.0.0.0",
    default_path: str = "/mcp",
    default_sse_path: str = "/sse",
    default_transport: str = "stdio",
) -> dict[str, Any]:
    transport = os.getenv("MCP_TRANSPORT", default_transport).strip().lower()
    if transport not in VALID_TRANSPORTS:
        transport = default_transport
    return {
        "transport": transport,
        "host": os.getenv("MCP_HOST", default_host),
        "port": int(os.getenv("PORT", os.getenv("MCP_PORT", str(default_port)))),
        "path": os.getenv("MCP_PATH", default_path),
        "sse_path": os.getenv("MCP_SSE_PATH", default_sse_path),
    }


def run_mcp_server(
    mcp: Any,
    *,
    default_port: int,
    default_host: str = "0.0.0.0",
    default_path: str = "/mcp",
    default_sse_path: str = "/sse",
    default_transport: str = "stdio",
) -> None:
    config = get_mcp_run_config(
        default_port=default_port,
        default_host=default_host,
        default_path=default_path,
        default_sse_path=default_sse_path,
        default_transport=default_transport,
    )

    if config["transport"] == "stdio":
        mcp.run(transport="stdio")
        return

    if config["transport"] == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=config["host"],
            port=config["port"],
            path=config["path"],
        )
        return

    mcp.run(
        transport="sse",
        host=config["host"],
        port=config["port"],
        path=config["sse_path"],
    )
