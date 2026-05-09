from __future__ import annotations

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
    "/config",
    "/models",
})


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


def _sync_user_to_db(payload: TokenPayload) -> None:
    """将登录用户同步到本地用户表。"""
    try:
        import psycopg
        from auth.db import upsert_user
        from auth.model import LocalUser
        from config.db_config import get_psycopg_db_url

        db_url = get_psycopg_db_url(id="auth-user-sync")
        with psycopg.connect(db_url) as conn:
            user = LocalUser(
                user_id=payload.sub,
                email=payload.email,
            )
            upsert_user(conn, user)
    except Exception:
        logger.warning("同步认证用户到本地数据库失败，但不会中断当前请求", exc_info=True)


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_public_path(request.url.path):
            return await call_next(request)

        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "缺少 Bearer Token"})

        token = auth.removeprefix("Bearer ").strip()

        try:
            payload = verify_token(token)
        except InvalidTokenError as e:
            return JSONResponse(status_code=401, content={"detail": str(e)})

        current_user = CurrentUser(
            user_id=payload.sub,
            email=payload.email,
            scopes=payload.scopes,
        )
        request.state.user = current_user
        request.state.user_id = current_user.user_id

        _sync_user_to_db(payload)

        logger.info(f"鉴权通过，已注入 user_id 到请求上下文: user_id={current_user.user_id} path={request.url.path}")

        return await call_next(request)
