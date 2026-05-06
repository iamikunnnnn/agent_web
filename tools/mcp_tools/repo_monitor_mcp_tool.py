from __future__ import annotations

import os

from agno.tools.mcp import MCPTools


def create_repo_monitor_mcp_tools(timeout_seconds: int = 30) -> MCPTools:
    return MCPTools(
        transport="streamable-http",
        url=os.getenv("REPO_MONITOR_MCP_URL", "http://localhost:8012/mcp"),
        timeout_seconds=timeout_seconds,
    )
