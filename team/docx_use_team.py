from agno.team import Team

from agent.docx_use_agent import create_docx_use_agent
from config.db_config import create_base_db
from config.model_config import get_ai_model

DOCX_TEAM_INSTRUCTIONS = """
你是一个办公文档团队 Leader，负责接收用户的办公文档需求，并将 `.docx` 相关任务编排给 Word 文档专家执行。

你的工作原则：
- 只处理最终交付物为 `.docx` 的任务。
- 超出办公文档范围的请求直接拒绝，不要勉强处理。
- 优先基于用户给出的材料、附件内容和当前会话信息组织文档。
- 信息不足时，只追问完成任务所需的最小关键信息。

你的执行流程：
1. 分析用户意图，明确是生成新文档、改写已有文档，还是提取整理内容。
2. 将具体文档执行任务委派给 Word 文档专家 Agent。
3. 检查成员是否实际生成或修改了 `.docx` 文件。
4. 如果执行失败，根据错误信息要求成员重试，最多三次。
5. 最终向用户返回面向交付的结果，不输出与任务无关的内部编排细节。

你的质量要求：
- 文档结构清晰，适合办公场景。
- 结果必须可交付，不能是空文档、半成品或仅有说明文字。
- 对已有文档的修改应尽量保持原有语义和格式意图。
""".strip()


def create_docx_use_team(team_id: str) -> Team:
    """创建对外暴露的 docx 办公文档 Team。"""

    word_specialist = create_docx_use_agent(agent_id="docx_word_specialist_agent")
    team = Team(
        id=team_id,
        name="办公文档团队Leader",
        model=get_ai_model(),
        db=create_base_db(team_id),
        members=[word_specialist],
    )
    team.instructions = DOCX_TEAM_INSTRUCTIONS
    team.description = "办公文档团队，负责编排 Word 专家处理 .docx 文档任务。"
    team.markdown = True
    team.retries = 3
    team.add_history_to_context = True
    team.add_datetime_to_context = True
    team.num_history_runs = 3
    team.store_member_responses = True
    team.share_member_interactions = True
    team.show_members_responses = True
    team.add_member_tools_to_context = True
    return team
