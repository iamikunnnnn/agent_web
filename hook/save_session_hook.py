"""
Session 持久化 Hook
在对话开始时立即将 session 保存到数据库，避免前端查询时出现 404 错误
"""
from typing import Optional

from agno.agent import Agent
from agno.session import AgentSession
from agno.utils.log import logger


def save_session_hook(
    agent: Optional[Agent] = None,
    session: Optional[AgentSession] = None,
    **kwargs
) -> None:
    """
    在对话开始时立即保存 session 到数据库
    
    解决长时间任务中 session 还未保存到数据库时前端查询导致的 404 错误
    Session 在对话开始时创建（内存中），只有在 run 执行完成后才保存到数据库
    前端每5分钟调用 get_session_by_id，此时 session 还在运行中，未保存到数据库，导致 404
    
    Args:
        agent: Agent 实例（由 AgentOS 自动传递）
        session: Session 实例（由 AgentOS 自动传递）
        **kwargs: 其他参数
    """
    if not agent or not session or not agent.db:
        return

    try:
        # 直接通过 db.upsert_session 保存，绕过 save_session 的 team_id 检查
        # 这样可以在对话开始时就在数据库中创建 session 记录（即使内容为空）
        agent.db.upsert_session(session=session)
        logger.debug(f"✅ Session 已立即保存到数据库: {session.session_id}")
    except Exception as e:
        # 如果保存失败，记录警告但不中断流程
        logger.warning(f"⚠️ 保存 session 到数据库时出现错误（不影响流程）: {str(e)}")

