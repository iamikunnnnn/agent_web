from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request

from auth.model import TokenPayload, CurrentUser
from auth.verify import verify_token, InvalidTokenError

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


def _sync_user_to_db(payload: TokenPayload) -> None:
    """Sync user to local DB on login. Non-blocking — errors are logged, not raised."""
    try:
        import psycopg
        from config.db_config import Config
        from auth.db import upsert_user
        from auth.model import LocalUser

        db_url = "{}://{}{}@{}:{}/{}".format(
            Config.DB_DRIVER, Config.DB_USER,
            f":{Config.DB_PASSWORD}" if Config.DB_PASSWORD else "",
            Config.DB_HOST, Config.DB_PORT, Config.DB_NAME,
        )
        with psycopg.connect(db_url) as conn:
            user = LocalUser(
                user_id=payload.sub,
                email=payload.email,
            )
            upsert_user(conn, user)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Failed to sync user to local DB", exc_info=True)


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_public_path(request.url.path):
            return await call_next(request)

        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing token"})

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

        _sync_user_to_db(payload)

        return await call_next(request)
