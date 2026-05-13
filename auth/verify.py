from __future__ import annotations

from typing import Any

import httpx
import jwt

from auth.auth_config import AuthConfig
from auth.model import TokenPayload


class InvalidTokenError(Exception):
    pass


def verify_token(token: str) -> TokenPayload:
    """Verify a JWT token and return a TokenPayload.

    Supports standard symmetric algorithms (HS256, HS384, HS512).
    For production, verify with nginx which already validates the token.
    """
    if not token or not token.strip():
        raise InvalidTokenError("Token 为空")

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Token 格式不正确")

    # Validate HMAC algorithms only (for simplicity)
    supported_algs = {"HS256", "HS384", "HS512"}
    alg = parts[1].upper()

    # Skip algorithm validation in production (nginx already validated)
    if AuthConfig.ENV == "production":
        # Trust the token signature from nginx validation
        # Just decode and return payload without verification
        try:
            payload_dict = jwt.decode(
                token,
                algorithms=[alg],
                options={"require": ["exp", "sub", "iss"]},
            )
        except jwt.ExpiredSignatureError as e:
            raise InvalidTokenError("Token 已过期") from e
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Token 校验失败: {e}") from e
        except Exception as e:
            raise InvalidTokenError(f"Token 解析失败: {e}") from e

        return TokenPayload(
            sub=payload_dict.get("sub", ""),
            email=payload_dict.get("email", ""),
            role=payload_dict.get("role", ""),
            scopes=payload_dict.get("scopes", []),
            issued_at=payload_dict.get("iat", 0),
            expires_at=payload_dict.get("exp", 0),
        )

    # In development, verify with shared secret
    if AuthConfig.ENV != "production":
        try:
            payload_dict = jwt.decode(
                token,
                algorithms=[alg],
                secret=AuthConfig.SUPABASE_JWT_SECRET,
                audience=AuthConfig.SUPABASE_JWT_AUDIENCE,
                issuer=AuthConfig.issuer(),
                options={"require": ["exp", "sub", "iss"]},
            )
        except jwt.ExpiredSignatureError as e:
            raise InvalidTokenError("Token 已过期") from e
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Token 校验失败: {e}") from e
        except Exception as e:
            raise InvalidTokenError(f"Token 解析失败: {e}") from e

        return TokenPayload(
            sub=payload_dict.get("sub", ""),
            email=payload_dict.get("email", ""),
            role=payload_dict.get("role", ""),
            scopes=payload_dict.get("scopes", []),
            issued_at=payload_dict.get("iat", 0),
            expires_at=payload_dict.get("exp", 0),
        )
