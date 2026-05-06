from __future__ import annotations

from agno.team import Team

from agent.office_markdown_agent import create_office_markdown_agent
from agent.office_pdf_agent import create_office_pdf_agent
from agent.office_search_agent import create_office_search_agent
from agent.office_word_agent import create_office_word_agent
from config.db_config import create_base_db
from config.model_config import get_ai_model
from tools.office_file_toolkit import OfficeFileToolkit

OFFICE_TEAM_INSTRUCTIONS = """
你是办公Agent团队Leader，负责规划、分派和验收办公文档任务。

团队职责范围：
- 只处理内容生成、修改、扩充类办公任务。
- 最终交付物限定为 `.docx`、`.md`、`.pdf`。
- 超出此范围的请求要直接拒绝。

工作流程：
1. 如果任务涉及已有文件，先让对应专家通过办公文件工具定位输入路径。
2. 如果任务需要外部资料，先委派给 搜索专家Agent 收集结构化情报。
3. 按格式把文档任务委派给对应专家：
- `.docx` -> Word文档专家Agent
- `.md` 或未指定格式 -> Markdown文档专家Agent
- `.pdf` -> Pdf文档专家Agent
4. 交付后使用办公文件工具检查目标文件是否存在。
5. 如果未生成，基于错误结果重试，最多三次。

关键约束：
- 有附件时，附件内容是第一事实来源。
- 搜索只能作为补充信息，不能覆盖附件原文。
- 每次会话默认只产出一种格式，除非用户明确要求多种格式。
""".strip()


def create_office_team(team_id: str) -> Team:
    team = Team(
        id=team_id,
        name="办公Agent团队Leader",
        model=get_ai_model(),
        db=create_base_db(team_id),
        members=[
            create_office_search_agent(agent_id="office_search_agent"),
            create_office_word_agent(agent_id="office_word_agent"),
            create_office_markdown_agent(agent_id="office_markdown_agent"),
            create_office_pdf_agent(agent_id="office_pdf_agent"),
        ],
        tools=[OfficeFileToolkit()],
    )
    team.instructions = OFFICE_TEAM_INSTRUCTIONS
    team.description = "办公文档处理团队，包含搜索、Word、Markdown、PDF 四类专家成员。"
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
