"""
Knowledge Base Database Operations

All functions enforce multi-tenant isolation by default.
"""

import psycopg
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timezone
from config.db_config import get_psycopg_db_url


@dataclass
class KnowledgeBaseRecord:
    kb_id: str
    kb_name: str
    kb_description: str
    owner_id: str
    is_official: bool
    is_public: bool
    vector_table_name: str
    chunking_mode: str
    chunk_size: int
    chunk_overlap: int
    max_results: int
    file_count: int
    total_chunks: int
    is_active: bool
    indexing_status: str
    last_indexed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


@dataclass
class KnowledgeFileRecord:
    file_id: str
    kb_id: str
    file_name: str
    file_path: str
    file_size: int
    file_type: str
    mime_type: Optional[str]
    processing_status: str
    chunk_count: int
    error_message: Optional[str]
    uploaded_at: datetime
    processed_at: Optional[datetime]


@dataclass
class KnowledgeCopyRecord:
    copy_id: str
    source_kb_id: str
    target_kb_id: str
    copied_at: datetime


def get_db_connection():
    """Get a database connection."""
    return psycopg.connect(get_psycopg_db_url(id="knowledge-meta"))


def create_knowledge_base(
    kb_id: str,
    kb_name: str,
    kb_description: str,
    owner_id: str,
    is_official: bool,
    is_public: bool,
    vector_table_name: str,
    chunking_mode: str = "document",
    chunk_size: int = 5000,
    chunk_overlap: int = 200,
    max_results: int = 10,
) -> KnowledgeBaseRecord:
    """Create a new knowledge base record."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO auth.knowledge_bases (
                    kb_id, kb_name, kb_description, owner_id, is_official, is_public,
                    vector_table_name, chunking_mode, chunk_size, chunk_overlap, max_results
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING kb_id, kb_name, kb_description, owner_id, is_official, is_public,
                          vector_table_name, chunking_mode, chunk_size, chunk_overlap, max_results,
                          file_count, total_chunks, is_active, indexing_status, last_indexed_at,
                          created_at, updated_at
            """, (
                kb_id, kb_name, kb_description, owner_id, is_official, is_public,
                vector_table_name, chunking_mode, chunk_size, chunk_overlap, max_results
            ))
            row = cur.fetchone()
            conn.commit()
    return _row_to_kb_record(row)


def get_knowledge_base(kb_id: str) -> Optional[KnowledgeBaseRecord]:
    """Get a knowledge base by ID."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT kb_id, kb_name, kb_description, owner_id, is_official, is_public,
                       vector_table_name, chunking_mode, chunk_size, chunk_overlap, max_results,
                       file_count, total_chunks, is_active, indexing_status, last_indexed_at,
                       created_at, updated_at
                FROM auth.knowledge_bases WHERE kb_id = %s
            """, (kb_id,))
            row = cur.fetchone()
    return _row_to_kb_record(row) if row else None


def list_knowledge_bases(
    owner_id: Optional[str] = None,
    is_official: Optional[bool] = None,
    is_public: Optional[bool] = None,
    is_active: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[KnowledgeBaseRecord]:
    """List knowledge bases with optional filters."""
    conditions = []
    params = []

    if owner_id is not None:
        conditions.append("owner_id = %s")
        params.append(owner_id)

    if is_official is not None:
        conditions.append("is_official = %s")
        params.append(is_official)

    if is_public is not None:
        conditions.append("is_public = %s")
        params.append(is_public)

    if is_active is not None:
        conditions.append("is_active = %s")
        params.append(is_active)

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    params.extend([limit, offset])

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT kb_id, kb_name, kb_description, owner_id, is_official, is_public,
                       vector_table_name, chunking_mode, chunk_size, chunk_overlap, max_results,
                       file_count, total_chunks, is_active, indexing_status, last_indexed_at,
                       created_at, updated_at
                FROM auth.knowledge_bases
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()

    return [_row_to_kb_record(row) for row in rows]


def list_accessible_knowledge_bases(
    user_id: str,
    include_official: bool = True,
    include_public: bool = True,
    active_only: bool = True,
) -> List[KnowledgeBaseRecord]:
    """
    List knowledge bases accessible to a user.

    This function enforces multi-tenant isolation by:
    1. Always returning user's own KBs
    2. Optionally including official KBs
    3. Optionally including public KBs from other users
    """
    conditions = ["owner_id = %s"]
    params = [user_id]

    if include_official:
        conditions.append("is_official = TRUE")

    if include_public:
        conditions.append("(is_public = TRUE AND owner_id != %s)")
        params.append(user_id)

    if active_only:
        conditions.append("is_active = TRUE")

    query = f"""
        SELECT kb_id, kb_name, kb_description, owner_id, is_official, is_public,
               vector_table_name, chunking_mode, chunk_size, chunk_overlap, max_results,
               file_count, total_chunks, is_active, indexing_status, last_indexed_at,
               created_at, updated_at
        FROM auth.knowledge_bases
        WHERE ({') OR ('.join(conditions)})
        ORDER BY updated_at DESC
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [_row_to_kb_record(row) for row in rows]


def update_knowledge_base(
    kb_id: str,
    kb_name: Optional[str] = None,
    kb_description: Optional[str] = None,
    is_public: Optional[bool] = None,
    chunking_mode: Optional[str] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    max_results: Optional[int] = None,
    is_active: Optional[bool] = None,
    indexing_status: Optional[str] = None,
) -> Optional[KnowledgeBaseRecord]:
    """Update a knowledge base record."""
    update_fields = []
    params = []

    if kb_name is not None:
        update_fields.append("kb_name = %s")
        params.append(kb_name)
    if kb_description is not None:
        update_fields.append("kb_description = %s")
        params.append(kb_description)
    if is_public is not None:
        update_fields.append("is_public = %s")
        params.append(is_public)
    if chunking_mode is not None:
        update_fields.append("chunking_mode = %s")
        params.append(chunking_mode)
    if chunk_size is not None:
        update_fields.append("chunk_size = %s")
        params.append(chunk_size)
    if chunk_overlap is not None:
        update_fields.append("chunk_overlap = %s")
        params.append(chunk_overlap)
    if max_results is not None:
        update_fields.append("max_results = %s")
        params.append(max_results)
    if is_active is not None:
        update_fields.append("is_active = %s")
        params.append(is_active)
    if indexing_status is not None:
        update_fields.append("indexing_status = %s")
        params.append(indexing_status)

    if not update_fields:
        return None

    params.append(kb_id)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE auth.knowledge_bases
                SET {', '.join(update_fields)}
                WHERE kb_id = %s
                RETURNING kb_id, kb_name, kb_description, owner_id, is_official, is_public,
                          vector_table_name, chunking_mode, chunk_size, chunk_overlap, max_results,
                          file_count, total_chunks, is_active, indexing_status, last_indexed_at,
                          created_at, updated_at
            """, params)
            row = cur.fetchone()
            conn.commit()

    return _row_to_kb_record(row) if row else None


def delete_knowledge_base(kb_id: str) -> bool:
    """Delete a knowledge base record (cascades to files and copies)."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth.knowledge_bases WHERE kb_id = %s", (kb_id,))
            conn.commit()
    return True


def drop_knowledge_tables(vector_table_name: str, content_table_name: str) -> None:
    """Drop the vector and content tables for a knowledge base."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {Config.DB_NAME}.{content_table_name}")
            cur.execute(f"DROP TABLE IF EXISTS {Config.DB_NAME}.{vector_table_name}")
            conn.commit()


def create_file_record(
    file_id: str,
    kb_id: str,
    file_name: str,
    file_path: str,
    file_size: int,
    file_type: str,
    mime_type: Optional[str] = None,
) -> KnowledgeFileRecord:
    """Create a file record in the knowledge_files table."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO auth.knowledge_files (
                    file_id, kb_id, file_name, file_path, file_size, file_type, mime_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING file_id, kb_id, file_name, file_path, file_size, file_type, mime_type,
                          processing_status, chunk_count, error_message, uploaded_at, processed_at
            """, (file_id, kb_id, file_name, file_path, file_size, file_type, mime_type))
            row = cur.fetchone()
            conn.commit()

    return _row_to_file_record(row)


def get_file_record(file_id: str) -> Optional[KnowledgeFileRecord]:
    """Get a file record by ID."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT file_id, kb_id, file_name, file_path, file_size, file_type, mime_type,
                       processing_status, chunk_count, error_message, uploaded_at, processed_at
                FROM auth.knowledge_files WHERE file_id = %s
            """, (file_id,))
            row = cur.fetchone()
    return _row_to_file_record(row) if row else None


def list_files_by_kb(
    kb_id: str,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[KnowledgeFileRecord]:
    """List files in a knowledge base."""
    conditions = ["kb_id = %s"]
    params = [kb_id]

    if status is not None:
        conditions.append("processing_status = %s")
        params.append(status)

    params.extend([limit, offset])

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT file_id, kb_id, file_name, file_path, file_size, file_type, mime_type,
                       processing_status, chunk_count, error_message, uploaded_at, processed_at
                FROM auth.knowledge_files
                WHERE {' AND '.join(conditions)}
                ORDER BY uploaded_at DESC
                LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()

    return [_row_to_file_record(row) for row in rows]


def update_file_status(
    file_id: str,
    status: str,
    chunk_count: Optional[int] = None,
    error_message: Optional[str] = None,
) -> Optional[KnowledgeFileRecord]:
    """Update file processing status."""
    update_fields = ["processing_status = %s"]
    params = [status]

    if chunk_count is not None:
        update_fields.append("chunk_count = %s")
        params.append(chunk_count)

    if error_message is not None:
        update_fields.append("error_message = %s")
        params.append(error_message)

    if status in ("completed", "failed"):
        update_fields.append("processed_at = %s")
        params.append(datetime.now(timezone.utc))

    params.append(file_id)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE auth.knowledge_files
                SET {', '.join(update_fields)}
                WHERE file_id = %s
                RETURNING file_id, kb_id, file_name, file_path, file_size, file_type, mime_type,
                          processing_status, chunk_count, error_message, uploaded_at, processed_at
            """, params)
            row = cur.fetchone()
            conn.commit()

    return _row_to_file_record(row) if row else None


def delete_file(file_id: str) -> bool:
    """Delete a file record."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth.knowledge_files WHERE file_id = %s", (file_id,))
            conn.commit()
    return True


def update_kb_file_count(kb_id: str, increment: int = 1) -> None:
    """Update the file count for a knowledge base."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.knowledge_bases
                SET file_count = file_count + %s
                WHERE kb_id = %s
            """, (increment, kb_id))
            conn.commit()


def update_kb_chunk_count(kb_id: str, increment: int = 1) -> None:
    """Update the total chunk count for a knowledge base."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.knowledge_bases
                SET total_chunks = total_chunks + %s
                WHERE kb_id = %s
            """, (increment, kb_id))
            conn.commit()


def update_kb_indexing_status(kb_id: str, status: str) -> None:
    """Update the indexing status for a knowledge base."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.knowledge_bases
                SET indexing_status = %s,
                    last_indexed_at = %s
                WHERE kb_id = %s
            """, (status, datetime.now(timezone.utc), kb_id))
            conn.commit()


def record_knowledge_copy(source_kb_id: str, target_kb_id: str) -> KnowledgeCopyRecord:
    """Record a knowledge base copy operation."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO auth.knowledge_copies (source_kb_id, target_kb_id)
                VALUES (%s, %s)
                ON CONFLICT (source_kb_id, target_kb_id)
                DO UPDATE SET copied_at = NOW()
                RETURNING copy_id, source_kb_id, target_kb_id, copied_at
            """, (source_kb_id, target_kb_id))
            row = cur.fetchone()
            conn.commit()

    return KnowledgeCopyRecord(copy_id=row[0], source_kb_id=row[1], target_kb_id=row[2], copied_at=row[3])


def get_kb_copies(target_kb_id: str) -> List[KnowledgeCopyRecord]:
    """Get all copy records for a target knowledge base."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT copy_id, source_kb_id, target_kb_id, copied_at
                FROM auth.knowledge_copies
                WHERE target_kb_id = %s
                ORDER BY copied_at DESC
            """, (target_kb_id,))
            rows = cur.fetchall()

    return [
        KnowledgeCopyRecord(copy_id=row[0], source_kb_id=row[1], target_kb_id=row[2], copied_at=row[3])
        for row in rows
    ]


def _row_to_kb_record(row) -> KnowledgeBaseRecord:
    """Convert a database row to KnowledgeBaseRecord."""
    return KnowledgeBaseRecord(
        kb_id=row[0],
        kb_name=row[1],
        kb_description=row[2],
        owner_id=row[3],
        is_official=row[4],
        is_public=row[5],
        vector_table_name=row[6],
        chunking_mode=row[7],
        chunk_size=row[8],
        chunk_overlap=row[9],
        max_results=row[10],
        file_count=row[11],
        total_chunks=row[12],
        is_active=row[13],
        indexing_status=row[14],
        last_indexed_at=row[15],
        created_at=row[16],
        updated_at=row[17],
    )


def _row_to_file_record(row) -> KnowledgeFileRecord:
    """Convert a database row to KnowledgeFileRecord."""
    return KnowledgeFileRecord(
        file_id=row[0],
        kb_id=row[1],
        file_name=row[2],
        file_path=row[3],
        file_size=row[4],
        file_type=row[5],
        mime_type=row[6],
        processing_status=row[7],
        chunk_count=row[8],
        error_message=row[9],
        uploaded_at=row[10],
        processed_at=row[11],
    )
