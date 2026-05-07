# Auth System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Supabase Auth-based JWT authentication with global middleware and local user table.

**Architecture:** JWTMiddleware intercepts all requests, verifies Supabase JWT via JWKS public key, writes user info to `request.state`. Local PostgreSQL table (`auth.users`) stores business fields, auto-created on first login. Agno's existing `os_security_key` auth is removed in favor of the new middleware.

**Tech Stack:** FastAPI, Supabase Auth (JWKS), PyJWT, httpx (for JWKS fetch), psycopg/SQLAlchemy (for local user table)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `auth/__init__.py` | Public API exports |
| Create | `auth/model.py` | @dataclass models: TokenPayload, CurrentUser, LocalUser |
| Create | `auth/config.py` | Supabase URL/env config |
| Create | `auth/verify.py` | JWT verification via JWKS |
| Create | `auth/middleware.py` | JWTMiddleware (global auth) |
| Create | `auth/permissions.py` | get_current_user, require_scope |
| Create | `auth/db.py` | Local user table DDL + upsert logic |
| Create | `tests/test_auth_verify.py` | Tests for verify.py |
| Create | `tests/test_auth_middleware.py` | Tests for middleware.py |
| Create | `tests/test_auth_permissions.py` | Tests for permissions.py |
| Create | `tests/test_auth_db.py` | Tests for db.py |
| Modify | `api/main.py:1-57` | Register JWTMiddleware, add startup hook |
| Modify | `api/monitor.py:857-859` | Remove Agno's auth_dep from prometheus endpoint |
| Modify | `.env` | Add SUPABASE_URL, SUPABASE_ANON_KEY |

---

### Task 1: Data Models

**Files:**
- Create: `auth/model.py`

- [ ] **Step 1: Create auth/model.py**

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TokenPayload:
    """Supabase JWT decoded payload."""
    sub: str
    email: str
    role: str
    scopes: list[str] = field(default_factory=list)
    issued_at: int = 0
    expires_at: int = 0


@dataclass(frozen=True)
class CurrentUser:
    """Written to request.state by JWTMiddleware."""
    user_id: str
    email: str
    scopes: list[str] = field(default_factory=list)


@dataclass
class LocalUser:
    """Local auth.users table row."""
    user_id: str
    email: str
    nickname: str = ""
    avatar_url: str = ""
    created_at: str = ""
    last_login_at: str = ""
    is_active: bool = True
```

- [ ] **Step 2: Commit**

```bash
git add auth/model.py
git commit -m "feat(auth): add data models for token, current user, and local user"
```

---

### Task 2: Supabase Config

**Files:**
- Create: `auth/config.py`

- [ ] **Step 1: Create auth/config.py**

```python
import os

from dotenv import load_dotenv

load_dotenv()


class AuthConfig:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")

    @classmethod
    @property
    def jwks_url(cls) -> str:
        return f"{cls.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

    @classmethod
    def validate(cls) -> None:
        if not cls.SUPABASE_URL:
            raise ValueError("SUPABASE_URL is required")
        if not cls.SUPABASE_ANON_KEY:
            raise ValueError("SUPABASE_ANON_KEY is required")
```

- [ ] **Step 2: Commit**

```bash
git add auth/config.py
git commit -m "feat(auth): add Supabase connection config"
```

---

### Task 3: JWT Verification

**Files:**
- Create: `auth/verify.py`
- Create: `tests/test_auth_verify.py`

- [ ] **Step 1: Write failing test for verify_token**

```python
# tests/test_auth_verify.py
import time
import json
import pytest
from unittest.mock import patch, MagicMock
from auth.verify import verify_token, _fetch_jwks, InvalidTokenError


def _make_payload(sub="user-123", email="a@b.com", role="authenticated", exp_offset=3600):
    return {
        "sub": sub,
        "email": email,
        "role": role,
        "aud": "authenticated",
        "iss": "https://xxx.supabase.co/auth/v1",
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
    }


def test_verify_token_missing_raises():
    with pytest.raises(InvalidTokenError):
        verify_token("")


def test_verify_token_malformed_raises():
    with pytest.raises(InvalidTokenError):
        verify_token("not.a.valid.token")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth_verify.py -v`
Expected: FAIL — module `auth.verify` not found

- [ ] **Step 3: Create auth/verify.py**

```python
from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from auth.config import AuthConfig
from auth.model import TokenPayload


class InvalidTokenError(Exception):
    pass


_jwks_client_cache: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client_cache
    if _jwks_client_cache is None:
        _jwks_client_cache = PyJWKClient(AuthConfig.jwks_url, cache_keys=True)
    return _jwks_client_cache


def _fetch_jwks() -> dict[str, Any]:
    """Fetch JWKS from Supabase. Used as fallback by PyJWKClient."""
    response = httpx.get(AuthConfig.jwks_url, timeout=10)
    response.raise_for_status()
    return response.json()


_ALGORITHMS = ["HS256", "RS256"]


def verify_token(token: str) -> TokenPayload:
    """Verify a Supabase JWT and return a TokenPayload."""
    if not token or not token.strip():
        raise InvalidTokenError("Token is empty")

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Token is malformed")

    try:
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            audience="authenticated",
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise InvalidTokenError("Token has expired") from e
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"Invalid token: {e}") from e

    return TokenPayload(
        sub=payload["sub"],
        email=payload.get("email", ""),
        role=payload.get("role", ""),
        scopes=payload.get("scopes", []),
        issued_at=payload.get("iat", 0),
        expires_at=payload.get("exp", 0),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auth_verify.py -v`
Expected: PASS

- [ ] **Step 5: Write additional test for valid token decode**

```python
# Append to tests/test_auth_verify.py

def test_verify_valid_token():
    import jwt as pyjwt

    payload = _make_payload()
    secret = "test-secret-for-unit-tests-only"
    token = pyjwt.encode(payload, secret, algorithm="HS256")

    with patch("auth.verify._get_jwks_client") as mock_client:
        mock_key = MagicMock()
        mock_key.key = secret
        mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key

        result = verify_token(token)
        assert result.sub == "user-123"
        assert result.email == "a@b.com"
        assert result.role == "authenticated"


def test_verify_expired_token():
    import jwt as pyjwt

    payload = _make_payload(exp_offset=-10)
    secret = "test-secret"
    token = pyjwt.encode(payload, secret, algorithm="HS256")

    with patch("auth.verify._get_jwks_client") as mock_client:
        mock_key = MagicMock()
        mock_key.key = secret
        mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key

        with pytest.raises(InvalidTokenError, match="expired"):
            verify_token(token)
```

- [ ] **Step 6: Run all verify tests**

Run: `python -m pytest tests/test_auth_verify.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add auth/verify.py tests/test_auth_verify.py
git commit -m "feat(auth): add JWT verification via JWKS with tests"
```

---

### Task 4: Local User Table

**Files:**
- Create: `auth/db.py`
- Create: `tests/test_auth_db.py`

- [ ] **Step 1: Write failing test for user upsert**

```python
# tests/test_auth_db.py
import pytest
from auth.db import upsert_user, create_user_table
from auth.model import LocalUser


@pytest.fixture
def mock_connection():
    """Mock psycopg connection for unit tests."""
    import psycopg
    from unittest.mock import MagicMock, patch

    conn = MagicMock(spec=psycopg.Connection)
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


def test_upsert_user_inserts_new(mock_connection):
    conn, cursor = mock_connection
    user = LocalUser(
        user_id="user-123",
        email="test@example.com",
        nickname="Test",
    )
    upsert_user(conn, user)
    assert cursor.execute.called
    sql = cursor.execute.call_args[0][0]
    assert "INSERT" in sql
    assert "ON CONFLICT" in sql


def test_create_user_table(mock_connection):
    conn, cursor = mock_connection
    create_user_table(conn)
    assert cursor.execute.called
    sql = cursor.execute.call_args[0][0]
    assert "CREATE TABLE" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth_db.py -v`
Expected: FAIL — module `auth.db` not found

- [ ] **Step 3: Create auth/db.py**

```python
from __future__ import annotations

from datetime import datetime, timezone

import psycopg

from auth.model import LocalUser


_CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    user_id     TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    nickname    TEXT NOT NULL DEFAULT '',
    avatar_url  TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);
"""


def create_user_table(conn: psycopg.Connection) -> None:
    """Create auth.users table if not exists. Call once on startup."""
    with conn.cursor() as cur:
        cur.execute(_CREATE_TABLE_SQL)
    conn.commit()


_UPSERT_SQL = """
INSERT INTO auth.users (user_id, email, nickname, avatar_url, last_login_at)
VALUES (%(user_id)s, %(email)s, %(nickname)s, %(avatar_url)s, %(last_login_at)s)
ON CONFLICT (user_id) DO UPDATE SET
    email = EXCLUDED.email,
    nickname = COALESCE(NULLIF(EXCLUDED.nickname, ''), auth.users.nickname),
    avatar_url = COALESCE(NULLIF(EXCLUDED.avatar_url, ''), auth.users.avatar_url),
    last_login_at = EXCLUDED.last_login_at
"""


def upsert_user(conn: psycopg.Connection, user: LocalUser) -> None:
    """Insert or update a local user record. Called on first login / each login."""
    now = datetime.now(timezone.utc).isoformat()
    with conn.cursor() as cur:
        cur.execute(_UPSERT_SQL, {
            "user_id": user.user_id,
            "email": user.email,
            "nickname": user.nickname,
            "avatar_url": user.avatar_url,
            "last_login_at": now,
        })
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auth_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auth/db.py tests/test_auth_db.py
git commit -m "feat(auth): add local user table DDL and upsert with tests"
```

---

### Task 5: JWT Middleware

**Files:**
- Create: `auth/middleware.py`
- Create: `tests/test_auth_middleware.py`

- [ ] **Step 1: Write failing test for middleware**

```python
# tests/test_auth_middleware.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from starlette.testclient import TestClient
from fastapi import FastAPI, Request
from auth.middleware import JWTMiddleware
from auth.verify import InvalidTokenError


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


def test_protected_route_missing_token(app):
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_protected_route_invalid_token(app):
    client = TestClient(app)
    resp = client.get("/protected", headers={"Authorization": "Bearer bad.token.here"})
    assert resp.status_code == 401


def test_protected_route_valid_token(app):
    from auth.model import TokenPayload, CurrentUser

    payload = TokenPayload(sub="user-1", email="a@b.com", role="authenticated")

    with patch("auth.middleware.verify_token", return_value=payload):
        with patch("auth.middleware._sync_user_to_db"):
            client = TestClient(app)
            resp = client.get("/protected", headers={"Authorization": "Bearer validtoken"})
            assert resp.status_code == 200
            assert resp.json()["user_id"] == "user-1"
            assert resp.json()["email"] == "a@b.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth_middleware.py -v`
Expected: FAIL — module `auth.middleware` not found

- [ ] **Step 3: Create auth/middleware.py**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auth_middleware.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add auth/middleware.py tests/test_auth_middleware.py
git commit -m "feat(auth): add JWTMiddleware with public route bypass and tests"
```

---

### Task 6: Permissions Layer

**Files:**
- Create: `auth/permissions.py`
- Create: `tests/test_auth_permissions.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_auth_permissions.py
import pytest
from fastapi import FastAPI, Request, Depends
from starlette.testclient import TestClient
from auth.permissions import get_current_user, require_scope
from auth.model import CurrentUser


@pytest.fixture
def app_with_user():
    _app = FastAPI()

    @_app.get("/me")
    async def me(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": user.user_id, "email": user.email}

    @_app.get("/admin")
    async def admin(request: Request, _=Depends(require_scope("admin"))):
        return {"ok": True}

    return _app


def test_get_current_user_success(app_with_user):
    client = TestClient(app_with_user)
    user = CurrentUser(user_id="u1", email="a@b.com")
    # Inject user into request.state directly (simulates middleware)
    from starlette.middleware.base import BaseHTTPMiddleware as _BH

    class InjectUser(_BH):
        async def dispatch(self, request, call_next):
            request.state.user = user
            return await call_next(request)

    app_with_user.add_middleware(InjectUser)
    client = TestClient(app_with_user)
    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u1"


def test_require_scope_allowed(app_with_user):
    user = CurrentUser(user_id="u1", email="a@b.com", scopes=["admin"])

    class InjectUser:
        async def __call__(self, request: Request, call_next):
            request.state.user = user
            return await call_next(request)

    from starlette.middleware.base import BaseHTTPMiddleware
    app_with_user.add_middleware(BaseHTTPMiddleware, dispatch=InjectUser().__call__)
    client = TestClient(app_with_user)
    resp = client.get("/admin")
    assert resp.status_code == 200


def test_get_current_user_missing(app_with_user):
    client = TestClient(app_with_user)
    resp = client.get("/me")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth_permissions.py -v`
Expected: FAIL — module `auth.permissions` not found

- [ ] **Step 3: Create auth/permissions.py**

```python
from __future__ import annotations

from fastapi import HTTPException, Request

from auth.model import CurrentUser


async def get_current_user(request: Request) -> CurrentUser:
    """Read current user from request.state (set by JWTMiddleware)."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auth_permissions.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add auth/permissions.py tests/test_auth_permissions.py
git commit -m "feat(auth): add get_current_user and require_scope with tests"
```

---

### Task 7: Public API Exports

**Files:**
- Create: `auth/__init__.py`

- [ ] **Step 1: Create auth/__init__.py**

```python
from auth.model import CurrentUser, LocalUser, TokenPayload
from auth.permissions import get_current_user, require_scope
from auth.middleware import JWTMiddleware

__all__ = [
    "CurrentUser",
    "LocalUser",
    "TokenPayload",
    "get_current_user",
    "require_scope",
    "JWTMiddleware",
]
```

- [ ] **Step 2: Commit**

```bash
git add auth/__init__.py
git commit -m "feat(auth): add public API exports"
```

---

### Task 8: Integrate into Main App

**Files:**
- Modify: `api/main.py`
- Modify: `api/monitor.py`

- [ ] **Step 1: Modify api/main.py to register middleware and create user table on startup**

Replace the current `api/main.py` with:

```python
from openinference.instrumentation.agno import AgnoInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(
    SimpleSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
)
AgnoInstrumentor().instrument(tracer_provider=tracer_provider)


import os
from contextlib import asynccontextmanager

from agno.os import AgentOS
from agno.utils.log import log_info
from dotenv import load_dotenv

from api.init_agent import all_agents
from api.init_team import all_teams
from api.init_workflow import all_workflows
from api.monitor import setup_prometheus_monitoring
from config import db_config

load_dotenv()
db_path = os.getenv("AGENT_DB")


def _init_auth_db():
    """Create auth.users table on startup."""
    try:
        import psycopg
        from config.db_config import Config
        from auth.db import create_user_table

        db_url = "{}://{}{}@{}:{}/{}".format(
            Config.DB_DRIVER, Config.DB_USER,
            f":{Config.DB_PASSWORD}" if Config.DB_PASSWORD else "",
            Config.DB_HOST, Config.DB_PORT, Config.DB_NAME,
        )
        with psycopg.connect(db_url) as conn:
            create_user_table(conn)
        log_info("Auth DB initialized")
    except Exception as e:
        log_info(f"Auth DB init skipped (DB unavailable): {e}")


@asynccontextmanager
async def lifespan(app):
    log_info("--------------------Starting My FastAPI App--------------------")
    _init_auth_db()
    yield
    log_info("--------------------Stopping My FastAPI App--------------------")


tracing_db = db_config.create_tracing_db(id="tracing")
agent_os = AgentOS(
    description="AgentOS v2.4",
    agents=all_agents,
    teams=all_teams,
    workflows=all_workflows,
    lifespan=lifespan,
    db=tracing_db,
    tracing=True,
)
app = agent_os.get_app()

# Register JWT middleware for all routes
from auth.middleware import JWTMiddleware
app.add_middleware(JWTMiddleware)

setup_prometheus_monitoring(
    app=app,
    agent_os=agent_os,
    endpoint="/prom-metrics",
    refresh_interval_s=30,
    dbs_id=[agent.id for agent in all_agents if agent.db.id == agent.id]
    + [workflow.id for workflow in all_workflows if workflow.db.id == workflow.id]
    + [team.id for team in all_teams if team.db.id == team.id],
)
```

- [ ] **Step 2: Modify api/monitor.py — remove Agno's auth_dep from prom-metrics endpoint**

In `api/monitor.py`, find the prom-metrics route definition (around line 859) and remove the `dependencies=[Depends(auth_dep)]` parameter. Also remove the unused import.

Change line 859 from:
```python
@app.get(endpoint, include_in_schema=True, tags=["monitoring"], dependencies=[Depends(auth_dep)])
```
to:
```python
@app.get(endpoint, include_in_schema=True, tags=["monitoring"])
```

Remove the `auth_dep` variable and the `get_authentication_dependency` import if no longer used.

- [ ] **Step 3: Commit**

```bash
git add api/main.py api/monitor.py
git commit -m "feat(auth): integrate JWTMiddleware into main app, remove Agno auth_dep"
```

---

### Task 9: Environment Variables

**Files:**
- Modify: `.env`

- [ ] **Step 1: Add Supabase env vars to .env**

Add these lines to `.env`:

```
# Supabase Auth
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
```

Do NOT commit real values. These are placeholders for local development.

- [ ] **Step 2: Verify .gitignore includes .env**

Run: `grep -q ".env" .gitignore && echo "OK" || echo "MISSING"`
Expected: OK

If MISSING, add `.env` to `.gitignore`.

- [ ] **Step 3: Commit (only if .gitignore was updated)**

```bash
git add .gitignore
git commit -m "chore: ensure .env is gitignored"
```

---

### Task 10: Run Full Test Suite

**Files:**
- None (verification only)

- [ ] **Step 1: Run all auth tests**

Run: `python -m pytest tests/test_auth_*.py -v`
Expected: All PASS

- [ ] **Step 2: Verify import chain works**

Run: `python -c "from auth import JWTMiddleware, get_current_user, require_scope, CurrentUser; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: auth module complete"
```
