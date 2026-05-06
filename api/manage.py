from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent_manage.save_agent import save_agent
from api.init_agent import all_agents

manage_router = APIRouter(
    prefix="/manage",  # 统一前缀，所有用户接口路径都会以 /manage 开头
    tags=["agent管理"],
    responses={404: {"description": "未找到资源"}},  # 统一响应状态码说明（可选）
)
class AgentSaveResponse(BaseModel):
    """
    保存 Agent 接口的返回数据模型（约束返回字段、类型、注释）
    """
    status: str = Field(..., description="请求处理状态，如 complete/error")
    message: str = Field(..., description="处理结果提示信息")
    agent_id: Optional[str] = Field(None, description="新增 Agent 的唯一标识")

@manage_router.post("/save")
async def save(id:str)-> AgentSaveResponse:
    agent = save_agent(id=id)
    all_agents.append(agent)
    return AgentSaveResponse(
        status="complete",
        message=f"已添加 agent {agent}",
        agent_id=id
    )
# 4. 挂载路由到app，这一步已放在main



