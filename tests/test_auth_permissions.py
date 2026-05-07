import pytest
from fastapi import FastAPI, Request, Depends
from starlette.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from auth.permissions import get_current_user, require_scope
from auth.model import CurrentUser


def _make_app_with_injected_user(user: CurrentUser | None = None):
    _app = FastAPI()

    @_app.get("/me")
    async def me(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": user.user_id, "email": user.email}

    @_app.get("/admin")
    async def admin(request: Request, _=Depends(require_scope("admin"))):
        return {"ok": True}

    if user is not None:
        class InjectUser(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = user
                return await call_next(request)
        _app.add_middleware(InjectUser)

    return _app


def test_get_current_user_success():
    user = CurrentUser(user_id="u1", email="a@b.com")
    app = _make_app_with_injected_user(user)
    client = TestClient(app)
    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u1"


def test_get_current_user_missing():
    app = _make_app_with_injected_user(user=None)
    client = TestClient(app)
    resp = client.get("/me")
    assert resp.status_code == 401


def test_require_scope_allowed():
    user = CurrentUser(user_id="u1", email="a@b.com", scopes=["admin"])
    app = _make_app_with_injected_user(user)
    client = TestClient(app)
    resp = client.get("/admin")
    assert resp.status_code == 200


def test_require_scope_denied():
    user = CurrentUser(user_id="u1", email="a@b.com", scopes=["read"])
    app = _make_app_with_injected_user(user)
    client = TestClient(app)
    resp = client.get("/admin")
    assert resp.status_code == 403


def test_require_scope_not_authenticated():
    app = _make_app_with_injected_user(user=None)
    client = TestClient(app)
    resp = client.get("/admin")
    assert resp.status_code == 401
