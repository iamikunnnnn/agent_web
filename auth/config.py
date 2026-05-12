import os

from dotenv import load_dotenv

load_dotenv()


class AuthConfig:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
    SUPABASE_JWKS_URL: str = os.getenv("SUPABASE_JWKS_URL", "")
    SUPABASE_JWT_AUDIENCE: str = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    SUPABASE_JWT_ISSUER: str = os.getenv("SUPABASE_JWT_ISSUER", "")

    @classmethod
    def issuer(cls) -> str:
        return cls.SUPABASE_JWT_ISSUER or f"{cls.SUPABASE_URL}/auth/v1"

    @classmethod
    def jwks_url(cls) -> str:
        return cls.SUPABASE_JWKS_URL or f"{cls.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

    @classmethod
    def validate(cls, *, require_secret: bool = False) -> None:
        if not cls.SUPABASE_URL:
            raise ValueError("缺少环境变量 SUPABASE_URL")
        if require_secret and not cls.SUPABASE_JWT_SECRET:
            raise ValueError("缺少环境变量 SUPABASE_JWT_SECRET")
