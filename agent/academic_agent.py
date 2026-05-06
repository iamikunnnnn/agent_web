from __future__ import annotations

from agno.agent import Agent

from tools.academic_search_toolkit import AcademicSearchToolkit

ACADEMIC_AGENT_INSTRUCTIONS = [
    "你是一个学术检索助手，优先使用学术检索工具获取最新且可追溯的论文信息。",
    "当用户询问某个研究方向时，先检索相关论文，再基于工具返回结果总结，不要凭空补充文献信息。",
    "输出论文时优先包含标题、作者、发表时间、来源链接、PDF 链接和摘要要点。",
    "如果用户提到今年、最近、最新等相对时间，按当前年份理解并优先返回最近论文。",
]


def create_academic_agent(agent_id: str) -> Agent:
    return Agent(
        id=agent_id,
        name="Academic Search Agent",
        description="用于学术论文检索、论文摘要提取和研究资料查找的学术 Agent。",
        instructions=ACADEMIC_AGENT_INSTRUCTIONS,
        tools=[AcademicSearchToolkit()],
    )
