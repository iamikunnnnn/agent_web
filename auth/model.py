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