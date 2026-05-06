from agno.agent import Agent


def create_test_agent_2(agent_id: str) -> Agent:
    """创建 sora2_test_agent 实例的工厂函数
    """

    return Agent(
        id=agent_id,
        name="Test Agent 2",
    )

