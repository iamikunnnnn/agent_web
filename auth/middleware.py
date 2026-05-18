from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import JSONResponse
from agno.utils.log import logger
from starlette.middleware.base import BaseHTTPMiddleware

from auth.model import CurrentUser

PUBLIC_PATHS: frozenset[str] = frozenset({
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/info",
    "/config",
    "/models",
})


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """
    认证中间件，从 nginx 网关注入的 X-User-* 头读取用户信息。

    nginx 网关已经完成：
    - JWT token 校验
    - 注入 X-User-Id, X-User-Email, X-User-Scopes 头

    应用层只需：
    1. 从请求头读取用户信息
    2. 将用户信息注入到 request.state 供后续使用
    3. 提供 OPTIONS 预检请求放行
    4. 公开路径绕过认证
    """

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1. Allow CORS preflight requests (OPTIONS) to pass through
        if request.method == "OPTIONS":
            return await call_next(request)

        # 2. Public paths bypass authentication
        if _is_public_path(path):
            return await call_next(request)

        # 3. Read user info from nginx-injected headers
        user_id = request.headers.get("X-User-Id")
        if not user_id:
            return JSONResponse(status_code=401, content={"detail": "未通过网关认证"})

        current_user = _build_current_user(
            user_id=user_id,
            email=request.headers.get("X-User-Email", ""),
            scopes_raw=request.headers.get("X-User-Scopes", "[]"),
        )
        request.state.user = current_user
        request.state.user_id = current_user.user_id

        logger.info(f"网关鉴权通过: user_id={user_id} path={path}")
        return await call_next(request)


def _build_current_user(*, user_id: str, email: str, scopes_raw: str) -> CurrentUser:
    return CurrentUser(user_id=user_id, email=email, scopes=_normalize_scopes(scopes_raw))


def _normalize_scopes(scopes_raw: str) -> list[str]:
    """规范化 X-User-Scopes 头，确保返回字符串列表。"""
    if not scopes_raw:
        return []

    try:
        parsed = json.loads(scopes_raw)
    except (json.JSONDecodeError, TypeError):
        return []

    # Ensure it's a list and all elements are strings
    if not isinstance(parsed, list):
        return []

    return [str(scope) for scope in parsed if scope is not None]

