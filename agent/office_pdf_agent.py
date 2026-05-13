from __future__ import annotations

from agno.agent import Agent

from config.db_config import create_base_db
from config.model_config import get_ai_model
from tools.office_file_toolkit import OfficeFileToolkit
from tools.office_pdf_toolkit import OfficePdfToolkit
from tools.knowledge_query_tool import create_knowledge_query_tool, create_knowledge_list_tool

OFFICE_PDF_SYSTEM_MESSAGE = """
你是 Pdf文档专家Agent，负责生成和修改 `.pdf` 办公文档。

执行原则：
- 所有内容必须基于 Leader 提供的信息素材。
- 生成文件前先调用办公文件工具构造输出路径。
- 保存后使用办公文件工具校验目标文件是否存在。
- 文档内容要适合正式办公场景，结构清晰，避免占位符。
""".strip()


def create_office_pdf_agent(agent_id: str) -> Agent:
    agent = Agent(
        id=agent_id,
        name="Pdf文档专家Agent",
        tools=[
            OfficeFileToolkit(),
            OfficePdfToolkit(),
            create_knowledge_query_tool(),
            create_knowledge_list_tool(),
        ],
    )
    agent.system_message = OFFICE_PDF_SYSTEM_MESSAGE
    agent.description = "办公 PDF 文档专家，负责交付 .pdf 文件。"
    agent.model = get_ai_model()
    agent.db = create_base_db(agent_id)
    # Note: Fixed knowledge binding removed to enable multi-tenant isolation.
    # agent.search_knowledge = True  # Disabled, using tools instead
    # agent.update_knowledge = True  # Disabled, no fixed knowledge to update
    agent.add_history_to_context = True
    agent.add_datetime_to_context = True
    agent.markdown = True
    agent.retries = 3
    return agent
