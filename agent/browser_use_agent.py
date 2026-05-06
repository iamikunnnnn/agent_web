from agno.agent import Agent
from agno.skills import LocalSkills, Skills

from tools.web_driver_monitor_toolkit import (
    clear_browser_transient_state,
    webDriverMonitorToolkit,
)


def create_browser_use_agent(agent_id: str) -> Agent:
    agent = Agent(
        id=agent_id,
        name="browser use agent",
        system_message="""
        你通过浏览器工具直接驱动浏览器执行操作，不要先输出抽象动作对象。
        每次需要操作时，直接调用对应浏览器工具。
        当前轮浏览器的原始 DOM 和截图只会出现在 session_state['_browser_current_round'] 中。
        该原始快照只对当前轮有效，不要假设它会跨轮持久化。
        其他浏览器状态摘要会保存在 session_state['browser_state'] 中。
        """,
        tools=[webDriverMonitorToolkit()],
        skills=Skills(loaders=[LocalSkills("./skills/agent-browser")]),
        pre_hooks=[clear_browser_transient_state],
    )
    agent.add_session_state_to_context = True
    return agent

