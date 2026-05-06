from agno.agent import Agent

from tools.test_agent_tool import test_agent_tool


def create_test_agent(agent_id: str) -> Agent:
    """
    创建 sora2_test_agent 实例的工厂函数
    """

    return Agent(
        id=agent_id,
        name="Test Agent",
        tools=[test_agent_tool],
    )

