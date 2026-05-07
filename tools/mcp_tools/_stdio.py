from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from agno.tools.mcp import MCPTools

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _python_command() -> str:
    return os.getenv("AGENT_WEB_MCP_PYTHON", sys.executable or "python")


def build_python_command(*args: str) -> str:
    return subprocess.list2cmdline([_python_command(), *args])


def create_stdio_mcp_tools(
    *,
    command_args: Iterable[str],
    timeout_seconds: int = 30,
    env: dict[str, str] | None = None,
) -> MCPTools:
    merged_env = {"PYTHONUNBUFFERED": "1"}
    if env:
        merged_env.update(env)
    return MCPTools(
        transport="stdio",
        command=build_python_command(*command_args),
        env=merged_env,
        timeout_seconds=timeout_seconds,
    )
