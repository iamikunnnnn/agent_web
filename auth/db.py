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
