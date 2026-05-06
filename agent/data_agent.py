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
        send_media_to_model=False,# 不将媒体直接发送给模型
        store_media=True, # 禁用媒体存储以避免 File 对象序列化问题
        system_message="""
        测试阶段，user_id默认使用: "JinDong"
        你能够根据你的mcp_tools读取数据并对数据进行处理
        支持的ML Model：["KNN", "线性回归", "逻辑回归", "决策树", "随机森林", "梯度提升", "支持向量机"] 
        
        """
    )

