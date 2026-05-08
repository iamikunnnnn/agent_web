from __future__ import annotations

import json
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from agno.utils.log import logger
from starlette.middleware.base import BaseHTTPMiddleware

from auth.model import CurrentUser, TokenPayload
from auth.verify import InvalidTokenError, verify_token

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


def _inject_user(request: Request, user_id: str, email: str, scopes: list) -> None:
    current_user = CurrentUser(user_id=user_id, email=email, scopes=scopes)
    request.state.user = current_user
    request.state.user_id = current_user.user_id
    _sync_user_to_db(user_id, email)


class AuthMiddleware(BaseHTTPMiddleware):
    """根据 APP_ENV 自动切换认证模式。

    - development（默认）: 本地解析 JWT token
    - production: 从 nginx 网关注入的 X-User-* 头读取
    """

    _use_gateway: bool = os.getenv("APP_ENV", "development") == "production"

    async def dispatch(self, request: Request, call_next):
        if _is_public_path(request.url.path):
            return await call_next(request)

        if self._use_gateway:
            return await self._gateway_auth(request, call_next)
        return await self._local_jwt_auth(request, call_next)

    async def _gateway_auth(self, request: Request, call_next):
        user_id = request.headers.get("X-User-Id")
        if not user_id:
            return JSONResponse(status_code=401, content={"detail": "未通过网关认证"})

        email = request.headers.get("X-User-Email", "")
        scopes_raw = request.headers.get("X-User-Scopes", "[]")
        try:
            scopes = json.loads(scopes_raw)
        except (json.JSONDecodeError, TypeError):
            scopes = []

        _inject_user(request, user_id, email, scopes)
        logger.info(f"网关鉴权通过: user_id={user_id} path={request.url.path}")
        return await call_next(request)

    async def _local_jwt_auth(self, request: Request, call_next):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "缺少 Bearer Token"})

        token = auth.removeprefix("Bearer ").strip()

        try:
            payload: TokenPayload = verify_token(token)
        except InvalidTokenError as e:
            return JSONResponse(status_code=401, content={"detail": str(e)})

        _inject_user(request, payload.sub, payload.email, payload.scopes)
        logger.info(f"本地 JWT 鉴权通过: user_id={payload.sub} path={request.url.path}")
        return await call_next(request)
