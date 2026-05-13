from __future__ import annotations

from typing import Optional

from agno.utils.log import logger
from fastapi import HTTPException, Request


def resolve_request_user_id(request: Request, payload_user_id: Optional[str]) -> str:
    # 优先使用认证中间件验证后的 user_id
    if hasattr(request.state, "user_id"):
        if payload_user_id and payload_user_id != request.state.user_id:
            logger.warning(
                f"user_id 不匹配，使用认证后的 user_id: "
                f"auth={request.state.user_id} payload={payload_user_id} path={request.url.path}"
            )
        return request.state.user_id

    raise HTTPException(status_code=401, detail="未授权访问，请先登录")
