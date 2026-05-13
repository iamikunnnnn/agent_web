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

_CREATE_KNOWLEDGE_TABLES_SQL = """
-- Knowledge Base Metadata Table
CREATE TABLE IF NOT EXISTS auth.knowledge_bases (
    kb_id              TEXT PRIMARY KEY,
    kb_name            TEXT NOT NULL,
    kb_description     TEXT NOT NULL DEFAULT '',

    -- Ownership and access control
    owner_id           TEXT NOT NULL,
    is_official        BOOLEAN NOT NULL DEFAULT FALSE,
    is_public          BOOLEAN NOT NULL DEFAULT FALSE,

    -- Configuration
    vector_table_name  TEXT NOT NULL,
    chunking_mode      TEXT NOT NULL DEFAULT 'document',
    chunk_size         INTEGER DEFAULT 5000,
    chunk_overlap      INTEGER DEFAULT 200,
    max_results        INTEGER DEFAULT 10,

    -- File tracking
    file_count         INTEGER DEFAULT 0,
    total_chunks       INTEGER DEFAULT 0,

    -- Status tracking
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    indexing_status    TEXT DEFAULT 'idle',
    last_indexed_at    TIMESTAMPTZ,

    -- Timestamps
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uk_owner_name UNIQUE (owner_id, kb_name),
    CONSTRAINT valid_chunking_mode CHECK (chunking_mode IN ('fixed', 'semantic', 'document')),
    CONSTRAINT valid_indexing_status CHECK (indexing_status IN ('idle', 'indexing', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_bases_owner_id ON auth.knowledge_bases(owner_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_is_official ON auth.knowledge_bases(is_official) WHERE is_official = TRUE;
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_is_public ON auth.knowledge_bases(is_public) WHERE is_public = TRUE;

-- Knowledge Files Table
CREATE TABLE IF NOT EXISTS auth.knowledge_files (
    file_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id              UUID NOT NULL REFERENCES auth.knowledge_bases(kb_id) ON DELETE CASCADE,

    file_name          TEXT NOT NULL,
    file_path          TEXT NOT NULL,
    file_size          BIGINT NOT NULL,
    file_type          TEXT NOT NULL,
    mime_type          TEXT,

    processing_status  TEXT DEFAULT 'pending',
    chunk_count        INTEGER DEFAULT 0,
    error_message      TEXT,

    uploaded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at       TIMESTAMPTZ,

    CONSTRAINT valid_processing_status CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_files_kb_id ON auth.knowledge_files(kb_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_files_status ON auth.knowledge_files(processing_status);

-- Knowledge Copies Table
CREATE TABLE IF NOT EXISTS auth.knowledge_copies (
    copy_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_kb_id       UUID NOT NULL REFERENCES auth.knowledge_bases(kb_id) ON DELETE CASCADE,
    target_kb_id       UUID NOT NULL REFERENCES auth.knowledge_bases(kb_id) ON DELETE CASCADE,
    copied_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_copy UNIQUE (source_kb_id, target_kb_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_copies_source ON auth.knowledge_copies(source_kb_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_copies_target ON auth.knowledge_copies(target_kb_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION auth.update_knowledge_bases_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for updated_at
DROP TRIGGER IF EXISTS trg_knowledge_bases_updated_at ON auth.knowledge_bases;
CREATE TRIGGER trg_knowledge_bases_updated_at
    BEFORE UPDATE ON auth.knowledge_bases
    FOR EACH ROW
    EXECUTE FUNCTION auth.update_knowledge_bases_updated_at();
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


def create_knowledge_tables(conn: psycopg.Connection) -> None:
    """Create knowledge base tables if not exists. Call once on startup."""
    with conn.cursor() as cur:
        cur.execute(_CREATE_KNOWLEDGE_TABLES_SQL)
    conn.commit()
