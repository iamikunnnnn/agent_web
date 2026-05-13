from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from agno.utils.log import logger
from starlette.middleware.base import BaseHTTPMiddleware

from auth.model import CurrentUser, TokenPayload
from auth.verify import InvalidTokenError, verify_token

# WARNING: /config and /models may expose sensitive information in production.
# Ensure these endpoints only return non-sensitive configuration (e.g., frontend setup).
# Do NOT expose: API keys, provider details, internal service addresses, database/OSS configs, debug info.
PUBLIC_PATHS: frozenset[str] = frozenset({
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/info",
    "/config",  # REVIEW: Confirm this endpoint doesn't expose sensitive data
    "/models",  # REVIEW: Confirm this endpoint doesn't expose sensitive data
})


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


# User sync cache to avoid repeated DB operations for the same user within a short time
# Format: {user_id: (last_sync_time, last_email)}
_USER_SYNC_CACHE: dict[str, tuple[float, str]] = {}
_SYNC_CACHE_TTL = 300  # 5 minutes


async def _sync_user_to_db(user_id: str, email: str) -> None:
    """异步同步用户到数据库，避免阻塞事件循环。

    使用 asyncio.to_thread 将同步 DB 操作放到线程池执行。
    使用缓存避免同一用户在短时间内重复同步。

    TODO: 更好的方案是使用连接池 + asyncpg/async psycopg，减少连接开销。
    """
    cache_key = user_id
    now = time.time()

    # Check cache to avoid repeated sync
    if cache_key in _USER_SYNC_CACHE:
        last_sync, last_email = _USER_SYNC_CACHE[cache_key]
        if now - last_sync < _SYNC_CACHE_TTL and last_email == email:
            return  # Already synced recently, skip

    async def _do_sync() -> None:
        try:
            import psycopg
            from auth.db import upsert_user
            from auth.model import LocalUser
            from config.db_config import get_psycopg_db_url

            db_url = get_psycopg_db_url(id="auth-user-sync")
            with psycopg.connect(db_url) as conn:
                user = LocalUser(user_id=user_id, email=email)
                upsert_user(conn, user)
            _USER_SYNC_CACHE[cache_key] = (now, email)
            logger.debug(f"同步用户到数据库成功: user_id={user_id}")
        except Exception:
            logger.warning("同步认证用户到本地数据库失败，但不会中断当前请求", exc_info=True)

    # Run in thread pool to avoid blocking the event loop
    await asyncio.to_thread(_do_sync)


def _normalize_scopes(scopes_raw: str) -> list[str]:
    """规范化 X-User-Scopes 头，确保返回字符串列表。

    输入可能是:
    - "[]" (空列表)
    - '["admin", "user"]' (JSON 数组)
    - '{"admin": true}' (JSON 对象，非法，应过滤)
    - 任意垃圾字符串 (解析失败，返回空列表)

    Returns:
        字符串列表，非法输入返回空列表
    """
    if not scopes_raw:
        return []

    try:
        parsed = json.loads(scopes_raw)
    except (json.JSONDecodeError, TypeError):
        return []

    # Ensure it's a list and all elements are strings
    if not isinstance(parsed, list):
        return []

    # Convert all elements to strings, filter out None
    return [str(scope) for scope in parsed if scope is not None]


def _inject_user(request: Request, user_id: str, email: str, scopes: list) -> None:
    current_user = CurrentUser(user_id=user_id, email=email, scopes=scopes)
    request.state.user = current_user
    request.state.user_id = current_user.user_id
    # Schedule user sync as a background task (fire and forget in async context)
    asyncio.create_task(_sync_user_to_db(user_id, email))


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件，根据 APP_ENV 和 ENABLE_APP_JWT_AUTH 自动切换认证模式。

    APP_ENV=production: 从 nginx 网关注入的 X-User-* 头读取（强制）
    APP_ENV=development + ENABLE_APP_JWT_AUTH=true: 本地解析 JWT token
    APP_ENV=development + ENABLE_APP_JWT_AUTH=false: 无认证（开发调试）

    NOTE: 此中间件不处理 WebSocket 连接认证。
    WebSocket 路径如 /agui/ws, /workflows/ws, /copilotkit/ws 需要在各自 endpoint 中单独校验 token。
    """

    def __init__(self, app):
        super().__init__(app)
        # Read config at init time (not at module import)
        self._use_gateway: bool = os.getenv("APP_ENV", "development") == "production"
        self._enable_auth: bool = os.getenv("ENABLE_APP_JWT_AUTH", "true").lower() in {"1", "true", "yes", "y", "on"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1. Allow CORS preflight requests (OPTIONS) to pass through
        # Browsers send OPTIONS without auth headers, which would otherwise fail 401
        if request.method == "OPTIONS":
            return await call_next(request)

        # 2. Public paths bypass authentication
        if _is_public_path(path):
            return await call_next(request)

        # 3. Apply auth based on configuration
        if self._use_gateway:
            return await self._gateway_auth(request, call_next)
        if self._enable_auth:
            return await self._local_jwt_auth(request, call_next)

        # 4. Dev mode: no auth, pass through
        return await call_next(request)

    async def _gateway_auth(self, request: Request, call_next):
        user_id = request.headers.get("X-User-Id")
        if not user_id:
            return JSONResponse(status_code=401, content={"detail": "未通过网关认证"})

        email = request.headers.get("X-User-Email", "")
        scopes_raw = request.headers.get("X-User-Scopes", "[]")
        scopes = _normalize_scopes(scopes_raw)

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


JWTMiddleware = AuthMiddleware
