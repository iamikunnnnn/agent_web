from __future__ import annotations

from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from auth.config import AuthConfig
from auth.model import TokenPayload


class InvalidTokenError(Exception):
    pass


_ASYMMETRIC_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"})
_HMAC_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})
_jwks_client_cache: PyJWKClient | None = None


def reset_jwks_cache() -> None:
    global _jwks_client_cache
    _jwks_client_cache = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client_cache
    if _jwks_client_cache is None:
        _jwks_client_cache = PyJWKClient(AuthConfig.jwks_url(), cache_keys=True)
    return _jwks_client_cache


def _fetch_jwks() -> dict[str, Any]:
    response = httpx.get(AuthConfig.jwks_url(), timeout=10)
    response.raise_for_status()
    return response.json()


def _decode_with_secret(token: str, algorithm: str) -> dict[str, Any]:
    AuthConfig.validate(require_secret=True)
    return jwt.decode(
        token,
        AuthConfig.SUPABASE_JWT_SECRET,
        algorithms=[algorithm],
        audience=AuthConfig.SUPABASE_JWT_AUDIENCE,
        issuer=AuthConfig.issuer(),
        options={"require": ["exp", "sub", "iss"]},
    )


def _decode_with_jwks(token: str, algorithm: str) -> dict[str, Any]:
    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=[algorithm],
        audience=AuthConfig.SUPABASE_JWT_AUDIENCE,
        issuer=AuthConfig.issuer(),
        options={"require": ["exp", "sub", "iss"]},
    )


def verify_token(token: str) -> TokenPayload:
    """Verify a Supabase JWT and return a TokenPayload."""
    AuthConfig.validate()

    if not token or not token.strip():
        raise InvalidTokenError("Token 为空")

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Token 格式不正确")

    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if not algorithm:
            raise InvalidTokenError("Token 缺少 alg")

        if algorithm in _ASYMMETRIC_ALGORITHMS:
            payload = _decode_with_jwks(token, algorithm)
        elif algorithm in _HMAC_ALGORITHMS:
            payload = _decode_with_secret(token, algorithm)
        else:
            raise InvalidTokenError(f"Unsupported algorithm {algorithm}")
    except jwt.ExpiredSignatureError as e:
        raise InvalidTokenError("Token 已过期") from e
    except jwt.PyJWKClientError as e:
        raise InvalidTokenError(f"JWKS 获取失败: {e}") from e
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"Token 校验失败: {e}") from e

    return TokenPayload(
        sub=payload["sub"],
        email=payload.get("email", ""),
        role=payload.get("role", ""),
        scopes=payload.get("scopes", []),
        issued_at=payload.get("iat", 0),
        expires_at=payload.get("exp", 0),
    )
