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
})


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


def _sync_user_to_db(user_id: str, email: str) -> None:
    try:
        import psycopg
        from auth.db import upsert_user
        from auth.model import LocalUser
        from config.db_config import Config

        db_url = "{}://{}{}@{}:{}/{}".format(
            Config.DB_DRIVER, Config.DB_USER,
            f":{Config.DB_PASSWORD}" if Config.DB_PASSWORD else "",
            Config.DB_HOST, Config.DB_PORT, Config.DB_NAME,
        )
        with psycopg.connect(db_url) as conn:
            user = LocalUser(user_id=user_id, email=email)
            upsert_user(conn, user)
    except Exception:
        logger.warning("同步认证用户到本地数据库失败，但不会中断当前请求", exc_info=True)


class GatewayAuthMiddleware(BaseHTTPMiddleware):
    """从网关注入的 X-User-* 请求头中读取用户信息。

    JWT 验签由 OpenResty 网关层完成，本中间件仅负责：
    1. 校验内部头是否存在（防御性检查）
    2. 构建 CurrentUser 并注入 request.state
    3. 同步用户到本地数据库
    """

    async def dispatch(self, request: Request, call_next):
        if _is_public_path(request.url.path):
            return await call_next(request)

        user_id = request.headers.get("X-User-Id")
        if not user_id:
            return JSONResponse(status_code=401, content={"detail": "未通过网关认证"})

        email = request.headers.get("X-User-Email", "")
        scopes_raw = request.headers.get("X-User-Scopes", "[]")
        try:
            scopes = json.loads(scopes_raw)
        except (json.JSONDecodeError, TypeError):
            scopes = []

        current_user = CurrentUser(
            user_id=user_id,
            email=email,
            scopes=scopes,
        )
        request.state.user = current_user
        request.state.user_id = current_user.user_id

        _sync_user_to_db(user_id, email)

        logger.info(f"网关鉴权通过: user_id={user_id} path={request.url.path}")

        return await call_next(request)
