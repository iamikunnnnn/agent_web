from __future__ import annotations

from agno.agent import Agent

from tools.git_diff_toolkit import GitDiffToolkit
from tools.mcp_tools.repo_monitor_mcp_tool import create_repo_monitor_mcp_tools

REPO_MONITOR_AGENT_INSTRUCTIONS = [
    "你是仓库监控 Agent，负责登记仓库、触发同步、读取同步日志并总结代码变更。",
    "优先使用 repo monitor MCP 工具获取仓库注册、同步与日志信息，再按需使用 GitDiffToolkit 深入分析。",
    "输出时应包含：变更摘要、影响范围、潜在风险，以及建议下一步关注点。",
]


def create_repo_monitor_agent(agent_id: str) -> Agent:
    return Agent(
        id=agent_id,
        name="Repo Monitor Agent",
        description="用于监控 GitHub/Gitee 仓库更新、分析变更并输出总结的 Agent",
        instructions=REPO_MONITOR_AGENT_INSTRUCTIONS,
        tools=[create_repo_monitor_mcp_tools(), GitDiffToolkit()],
    )
