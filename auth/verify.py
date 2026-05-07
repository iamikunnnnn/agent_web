from __future__ import annotations

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
