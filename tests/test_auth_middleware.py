import pytest
from unittest.mock import patch
from starlette.testclient import TestClient
from fastapi import FastAPI, Request
from auth.middleware import AuthMiddleware
from auth.model import TokenPayload


@pytest.fixture
def app():
    _app = FastAPI()
    _app.add_middleware(AuthMiddleware)

    @_app.get("/health")
    async def health():
        return {"status": "ok"}

    @_app.get("/openapi.json")
    async def openapi():
        return {}

    @_app.get("/docs")
    async def docs():
        return {}

    @_app.get("/protected")
    async def protected(request: Request):
        return {
            "user_id": request.state.user.user_id,
            "email": request.state.user.email,
        }

    return _app


def test_public_routes_bypass_auth(app):
    client = TestClient(app)
    assert client.get("/health").status_code == 200


def test_local_jwt_auth_missing_token(app):
    # development 模式（默认），缺少 Bearer token 应返回 401
    with patch.object(AuthMiddleware, "_use_gateway", False):
        client = TestClient(app)
        assert client.get("/protected").status_code == 401


def test_local_jwt_auth_valid_token(app):
    payload = TokenPayload(sub="user-1", email="a@b.com", role="authenticated")
    with patch.object(AuthMiddleware, "_use_gateway", False), \
         patch("auth.middleware.verify_token", return_value=payload), \
         patch("auth.middleware._sync_user_to_db"):
        client = TestClient(app)
        resp = client.get("/protected", headers={"Authorization": "Bearer validtoken"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "user-1"


def test_gateway_auth_missing_header(app):
    with patch.object(AuthMiddleware, "_use_gateway", True):
        client = TestClient(app)
        assert client.get("/protected").status_code == 401


def test_gateway_auth_valid_headers(app):
    with patch.object(AuthMiddleware, "_use_gateway", True), \
         patch("auth.middleware._sync_user_to_db"):
        client = TestClient(app)
        resp = client.get(
            "/protected",
            headers={
                "X-User-Id": "user-1",
                "X-User-Email": "a@b.com",
                "X-User-Scopes": '["read"]',
            },
        )
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "user-1"
