from __future__ import annotations

from typing import Optional

from agno.utils.log import logger
from fastapi import HTTPException, Request


def resolve_request_user_id(request: Request, payload_user_id: Optional[str]) -> str:
    # 优先使用 JWT 验证后的 user_id
    if hasattr(request.state, "user_id"):
        if payload_user_id and payload_user_id != request.state.user_id:
            logger.warning(
                f"user_id 不匹配，使用 JWT 验证后的 user_id: "
                f"JWT={request.state.user_id} payload={payload_user_id} path={request.url.path}"
            )
        return request.state.user_id

    # 降级到请求头（仅用于调试，不应在生产环境依赖）
    header_user_id = request.headers.get("x-user-id") or request.headers.get("user_id")
    if header_user_id:
        logger.warning(
            f"使用未经验证的请求头 user_id（绕过了 JWT 验证）: "
            f"header={header_user_id} path={request.url.path}"
        )
        return header_user_id

    raise HTTPException(status_code=401, detail="未授权访问，请先登录")
