from __future__ import annotations

import jwt

from auth.config import AuthConfig
from auth.model import TokenPayload


class InvalidTokenError(Exception):
    pass


_ALGORITHM = "HS256"


def verify_token(token: str) -> TokenPayload:
    """Verify a Supabase JWT (HS256) and return a TokenPayload."""
    if not token or not token.strip():
        raise InvalidTokenError("Token is empty")

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Token is malformed")

    try:
        payload = jwt.decode(
            token,
            AuthConfig.SUPABASE_JWT_SECRET,
            algorithms=[_ALGORITHM],
            audience="authenticated",
            issuer=f"{AuthConfig.SUPABASE_URL}/auth/v1",
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
