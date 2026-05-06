from __future__ import annotations

from agno.agent import Agent

from tools.mcp_tools.computer_mcp_tool import create_computer_mcp_tools

DESKTOP_CONTROL_AGENT_INSTRUCTIONS = [
    "你是桌面操控 Agent，当前首版优先处理浏览器环境中的可视化 UI 操作。",
    "优先通过 computer MCP 工具执行截图、点击、输入、滚动、按键和等待，不要把动作停留在抽象计划层。",
    "遇到删除数据、修改权限、发送敏感信息、金融交易等高风险操作时，应先要求人工确认。",
]


def create_desktop_control_agent(agent_id: str) -> Agent:
    return Agent(
        id=agent_id,
        name="Desktop Control Agent",
        description="用于浏览器优先的桌面/界面操控 Agent",
        instructions=DESKTOP_CONTROL_AGENT_INSTRUCTIONS,
        tools=[create_computer_mcp_tools()],
    )
