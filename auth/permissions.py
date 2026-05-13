from __future__ import annotations

from fastapi import HTTPException, Request

from auth.model import CurrentUser


async def get_current_user(request: Request) -> CurrentUser:
    """Read current user from request.state (set by AuthMiddleware)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_scope(scope: str):
    """Check if current user has the required scope. Reserved for future RBAC."""
    async def check(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        user_scopes = getattr(user, "scopes", [])
        if scope not in user_scopes and "admin" not in user_scopes:
            raise HTTPException(status_code=403, detail=f"Requires scope: {scope}")

    return check
