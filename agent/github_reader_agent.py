from agno.agent import Agent

from tools.github_reader_toolkit import GitHubReaderToolkit


## todo 可以把clone来的仓库的目录用同一个，避免的每个目录不同导致文件无限堆积的情况
def create_github_reader_agent(agent_id: str) -> Agent:
    """
    创建 sora2_test_agent 实例的工厂函数
    """

    return Agent(
        id=agent_id,
        name="GitHubReaderToolkit",
        tools=[GitHubReaderToolkit()],
    )

