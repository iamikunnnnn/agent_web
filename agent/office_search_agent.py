from __future__ import annotations

from agno.agent import Agent

from config.db_config import create_base_db, create_knowledge
from config.model_config import get_ai_model
from tools.office_search_toolkit import OfficeSearchToolkit

OFFICE_SEARCH_SYSTEM_MESSAGE = """
你是搜索专家Agent，是办公团队中的情报收集成员。

你的职责：
- 把 Leader 提供的研究主题、关键词和信息需求转成结构化搜索任务。
- 优先返回结构化信息情报，而不是松散段落。
- 结果要标明来源，避免无依据的推断。
- 搜索不足或存在冲突时，要明确说明。

输出要求：
- 尽量整理成主题、关键发现、数据点、来源链接。
- 不直接生成最终办公文档，只提供给文档专家使用的情报。
""".strip()


def create_office_search_agent(agent_id: str) -> Agent:
    agent = Agent(
        id=agent_id,
        name="搜索专家Agent",
        tools=[OfficeSearchToolkit()],
    )
    agent.system_message = OFFICE_SEARCH_SYSTEM_MESSAGE
    agent.description = "办公团队搜索专家，负责收集并整理结构化情报。"
    agent.model = get_ai_model()
    agent.db = create_base_db(agent_id)
    agent.knowledge = create_knowledge(
        id=agent_id,
        name=agent_id,
        description=f"Knowledge base for {agent_id}",
    )
    agent.search_knowledge = True
    agent.update_knowledge = True
    agent.add_history_to_context = True
    agent.add_datetime_to_context = True
    agent.markdown = True
    agent.retries = 3
    return agent
