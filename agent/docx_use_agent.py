from agno.agent import Agent

from config.db_config import create_base_db
from config.model_config import get_ai_model
from tools.mcp_tools.docx_use_mcp_tool import create_docx_use_mcp_tool
from tools.knowledge_query_tool import create_knowledge_query_tool, create_knowledge_list_tool

DOCX_WORD_SYSTEM_MESSAGE = """
你是一个专业的 Word 文档专家，负责处理办公文档生成、改写、扩写、润色和结构化整理任务。

你的工作边界：
- 只处理最终产物为 `.docx` 的办公文档任务。
- 优先使用用户提供的材料和当前会话信息，不要捏造事实。
- 超出 `.docx` 办公文档范围的请求要明确拒绝。

你的执行要求：
- 先理解文档目标、受众、结构和语气，再开始操作。
- 涉及已有文档时，先读取和理解原文档，再进行修改。
- 优先调用 docx MCP 工具实际生成或修改文档，而不是只给文字建议。
- 输出前检查文档是否已经成功生成；如果失败，基于错误信息重试，最多三次。
- 需要排版时，使用清晰的标题层级、段落结构、表格和列表，保持办公文档风格。
- 结果必须面向交付，不能输出占位符、半成品或无关解释。

如果用户信息不足，你只追问完成文档所必需的最小信息。
""".strip()


def create_docx_use_agent(agent_id: str) -> Agent:
    """创建负责 docx 文档处理的 Word 专家 Agent。"""

    agent = Agent(
        id=agent_id,
        name="Word文档专家Agent",
        tools=[
            create_docx_use_mcp_tool(),
            create_knowledge_query_tool(),
            create_knowledge_list_tool(),
        ],
    )
    agent.system_message = DOCX_WORD_SYSTEM_MESSAGE
    agent.description = "办公 Word 文档专家，负责生成、改写和整理 .docx 文档。"
    agent.model = get_ai_model()
    agent.db = create_base_db(agent_id)
    # Note: Fixed knowledge binding removed to enable multi-tenant isolation.
    # Agents now query user knowledge bases through tools.
    # agent.search_knowledge = True  # Disabled, using tools instead
    agent.update_knowledge = False  # Disabled, no fixed knowledge to update
    agent.add_history_to_context = True
    agent.add_datetime_to_context = True
    agent.markdown = True
    agent.retries = 3
    return agent
