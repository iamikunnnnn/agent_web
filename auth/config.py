import os

from dotenv import load_dotenv

load_dotenv()


class AuthConfig:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")

    @classmethod
    def validate(cls) -> None:
        if not cls.SUPABASE_URL:
            raise ValueError("SUPABASE_URL is required")
        if not cls.SUPABASE_JWT_SECRET:
            raise ValueError("SUPABASE_JWT_SECRET is required")