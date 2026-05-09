import pytest
from unittest.mock import patch
from starlette.testclient import TestClient
from fastapi import FastAPI, Request
from auth.middleware import JWTMiddleware
from auth.model import TokenPayload


@pytest.fixture
def app():
    _app = FastAPI()
    _app.add_middleware(JWTMiddleware)

    @_app.get("/health")
    async def health():
        return {"status": "ok"}

    @_app.get("/openapi.json")
    async def openapi():
        return {}

    @_app.get("/docs")
    async def docs():
        return {}

    @_app.get("/config")
    async def config():
        return {"ok": True}

    @_app.get("/models")
    async def models():
        return {"ok": True}

    @_app.get("/protected")
    async def protected(request: Request):
        return {
            "user_id": request.state.user.user_id,
            "email": request.state.user.email,
        }

    return _app


def test_public_routes_bypass_auth(app):
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_config_route_bypasses_auth(app):
    client = TestClient(app)
    resp = client.get("/config")
    assert resp.status_code == 200


def test_models_route_bypasses_auth(app):
    client = TestClient(app)
    resp = client.get("/models")
    assert resp.status_code == 200


def test_protected_route_missing_token(app):
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_protected_route_invalid_token(app):
    client = TestClient(app)
    resp = client.get("/protected", headers={"Authorization": "Bearer bad.token.here"})
    assert resp.status_code == 401


def test_protected_route_valid_token(app):
    payload = TokenPayload(sub="user-1", email="a@b.com", role="authenticated")

    with patch("auth.middleware.verify_token", return_value=payload):
        with patch("auth.middleware._sync_user_to_db"):
            client = TestClient(app)
            resp = client.get("/protected", headers={"Authorization": "Bearer validtoken"})
            assert resp.status_code == 200
            assert resp.json()["user_id"] == "user-1"
            assert resp.json()["email"] == "a@b.com"
