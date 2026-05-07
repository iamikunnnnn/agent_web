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