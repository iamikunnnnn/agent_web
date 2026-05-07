"""

数据读取/更新接口暂未经测试，目前直接在sqliite写入的数据

"""

from agno.agent import Agent

from hook.preprocess import preprocess_hook
from tools.mcp_tools.data_mcp_tool import create_data_mcp_tools


def create_data_agent(agent_id: str) -> Agent:
    """创建 data_agent 实例的工厂函数
    """

    return Agent(
        id=agent_id,
        name="Data Analyse Agent",
        tools=[create_data_mcp_tools()],
        pre_hooks=[preprocess_hook,],
        send_media_to_model=False,
        store_media=True,
        system_message="""
        你负责读取、预处理和分析用户上传的数据文件。
        优先通过 data MCP 工具执行真实的数据处理操作，而不是只给出理论步骤。
        user_id 应来自请求鉴权上下文，不要假设固定用户。
        支持的 ML Model：["KNN", "线性回归", "逻辑回归", "决策树", "随机森林", "梯度提升", "支持向量机"]
        """
    )

