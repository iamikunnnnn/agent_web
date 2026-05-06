import os

from agno.run import RunContext
from agno.tools.mcp import MCPTools


def data_header_provider(run_context: RunContext) -> dict:
    """
    """
    headers = {}

    if run_context.metadata:
        user_id = run_context.metadata.get("user_id")
        if user_id:
            headers["user_id"] = f"{user_id}"
    return headers

def create_data_mcp_tools(timeout_seconds: int = 30) -> MCPTools:
    return MCPTools(
        transport="streamable-http",
        url=os.getenv("DATA_MCP_URL", "http://localhost:8085/mcp"),
        timeout_seconds=timeout_seconds,
        header_provider=data_header_provider,
    )
