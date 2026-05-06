from __future__ import annotations

import os

from agno.tools.mcp import MCPTools


def create_computer_mcp_tools(timeout_seconds: int = 30) -> MCPTools:
    return MCPTools(
        transport="streamable-http",
        url=os.getenv("COMPUTER_MCP_URL", "http://localhost:8013/mcp"),
        timeout_seconds=timeout_seconds,
    )
