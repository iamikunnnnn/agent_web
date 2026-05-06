import os

from agno.tools.mcp import MCPTools
from dotenv import load_dotenv

load_dotenv()
def create_docx_use_mcp_tool():
    return MCPTools(
        transport="streamable-http",
        url=os.getenv("DOCX_USE_MCP_URL"),
        timeout_seconds=30,
    )
