from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

agno_pkg = types.ModuleType("agno")
agno_tools_pkg = types.ModuleType("agno.tools")
agno_tools_mcp_pkg = types.ModuleType("agno.tools.mcp")


class _PlaceholderMCPTools:
    def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - replaced by mock in tests
        pass


agno_tools_mcp_pkg.MCPTools = _PlaceholderMCPTools
sys.modules.setdefault("agno", agno_pkg)
sys.modules.setdefault("agno.tools", agno_tools_pkg)
sys.modules.setdefault("agno.tools.mcp", agno_tools_mcp_pkg)

from tools.mcp_tools.data_mcp_tool import create_data_mcp_tools


class DataMcpToolTests(unittest.TestCase):
    def test_create_data_mcp_tools_reads_url_from_env(self) -> None:
        with patch.dict(os.environ, {"DATA_MCP_URL": "http://data-mcp:8085/mcp"}, clear=False):
            with patch("tools.mcp_tools.data_mcp_tool.MCPTools") as mock_mcp_tools:
                create_data_mcp_tools(timeout_seconds=45)

        mock_mcp_tools.assert_called_once_with(
            transport="streamable-http",
            url="http://data-mcp:8085/mcp",
            timeout_seconds=45,
        )


if __name__ == "__main__":
    unittest.main()
