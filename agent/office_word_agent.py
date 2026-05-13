from __future__ import annotations

from agno.agent import Agent

from config.db_config import create_base_db
from config.model_config import get_ai_model
from tools.office_file_toolkit import OfficeFileToolkit
from tools.mcp_tools.docx_use_mcp_tool import create_docx_use_mcp_tool
from tools.knowledge_query_tool import create_knowledge_query_tool, create_knowledge_list_tool

OFFICE_WORD_SYSTEM_MESSAGE = """
你是 Word文档专家Agent，负责生成和修改 `.docx` 办公文档。

执行原则：
- 所有内容必须基于 Leader 提供的信息素材。
- 如果是修改已有文档，先调用办公文件工具解析输入路径，再优先读取原文档内容和结构，再开始修改。
- 如果是生成新文档，先调用办公文件工具构造输出路径，再把绝对路径交给 docx 工具使用。
- 有附件内容时，附件是第一事实来源，不能用搜索结果覆盖附件原文。
- 输出前必须用办公文件工具检查目标 `.docx` 是否真的生成，失败时最多重试三次。

建议流程：
1. `resolve_input_path` 或 `build_output_path`
2. docx 工具读取或写入
3. `file_exists` 验证交付结果
""".strip()


def create_office_word_agent(agent_id: str) -> Agent:
    agent = Agent(
        id=agent_id,
        name="Word文档专家Agent",
        tools=[
            OfficeFileToolkit(),
            create_docx_use_mcp_tool(),
            create_knowledge_query_tool(),
            create_knowledge_list_tool(),
        ],
    )
    agent.system_message = OFFICE_WORD_SYSTEM_MESSAGE
    agent.description = "办公 Word 文档专家，负责读取、修改并交付 .docx 文件。"
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
