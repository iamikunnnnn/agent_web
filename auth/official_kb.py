"""
Official Knowledge Base Management

Provides utilities for creating and managing official knowledge bases.
Official KBs are read-only to non-admin users and provide default knowledge for all users.
"""

import uuid
import hashlib
import logging
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)

from auth.kb_metadata import (
    create_knowledge_base,
    get_knowledge_base,
    KnowledgeBaseRecord,
    list_knowledge_bases,
)
from config.db_config import Config, create_knowledge_vector, create_knowledge, get_psycopg_db_url

OFFICIAL_KB_PREFIX = "official_"


def generate_official_kb_id(name: str) -> str:
    """
    Generate a stable ID for an official knowledge base.

    Uses a hash of the name to ensure consistency across deployments.
    """
    name_hash = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"{OFFICIAL_KB_PREFIX}{name_hash}"


def create_official_knowledge_base(
    name: str,
    description: str,
    initial_documents: Optional[List[str]] = None,
    max_results: int = 10,
) -> Optional[KnowledgeBaseRecord]:
    """
    Create an official knowledge base.

    Official KBs:
    - Are marked as is_official=True
    - Have a special ID prefix
    - Can be read by all authenticated users
    - Can only be modified by admins
    - Provide default knowledge for the system

    Note: Chunking strategy is automatically selected based on file type by FileDetector.
    Each document in the KB will use its optimal reader and chunker.

    Args:
        name: Name of the official KB
        description: Description of the KB content
        initial_documents: List of file paths to initially populate the KB
        max_results: Max search results

    Returns:
        The created KnowledgeBaseRecord, or None if already exists
    """
    kb_id = generate_official_kb_id(name)

    # Check if already exists
    existing = get_knowledge_base(kb_id)
    if existing:
        logger.info(f"Official knowledge base '{name}' already exists with ID {kb_id}")
        return existing

    # Derive table names
    safe_kb_id = kb_id.replace("-", "_")
    vector_table_name = f"{safe_kb_id}_knowledge_vectors"
    content_table_name = f"{safe_kb_id}_knowledge_contents"

    # Create database record
    # Note: chunking_mode, chunk_size, chunk_overlap are set to defaults
    # The actual chunking strategy is automatically selected per file by FileDetector
    try:
        kb_record = create_knowledge_base(
            kb_id=kb_id,
            kb_name=name,
            kb_description=description,
            owner_id="system",  # Special owner for official KBs
            is_official=True,
            is_public=True,  # Official KBs are always public
            vector_table_name=vector_table_name,
            chunking_mode="auto",  # FileDetector will auto-detect per file
            chunk_size=5000,  # Default, may be overridden by specific chunkers
            chunk_overlap=200,  # Default, may be overridden by specific chunkers
            max_results=max_results,
        )
    except Exception as e:
        logger.error(f"Failed to create official KB record for '{name}': {e}")
        return None

    # Create vector DB
    try:
        create_knowledge_vector(
            id=safe_kb_id,
            table_name=vector_table_name,
        )
    except Exception as e:
        logger.error(f"Failed to create vector DB for official KB '{name}': {e}")
        # Rollback DB record
        from auth.kb_metadata import delete_knowledge_base, drop_knowledge_tables
        delete_knowledge_base(kb_id)
        return None

    # Populate with initial documents if provided
    if initial_documents:
        populate_official_kb(kb_id, initial_documents)

    logger.info(f"Created official knowledge base '{name}' with ID {kb_id}")
    return kb_record


def populate_official_kb(
    kb_id: str,
    document_paths: List[str],
) -> int:
    """
    Populate an official knowledge base with documents.

    Note: FileDetector will automatically select the appropriate reader
    and chunker for each document based on its file type.

    Returns:
        Number of documents successfully processed
    """
    safe_kb_id = kb_id.replace("-", "_")
    knowledge = create_knowledge(
        id=safe_kb_id,
        name=f"Official: {kb_id}",
        description="Official knowledge base",
    )

    processed_count = 0
    for doc_path in document_paths:
        try:
            path = Path(doc_path)
            if not path.exists():
                logger.warning(f"Document not found: {doc_path}")
                continue

            # Use FileDetector to automatically select reader and chunker
            from knowledge.file_detector import get_reader_and_chunker
            reader, chunker = get_reader_and_chunker(
                doc_path,
                chunk_size=5000,
                overlap=200,
            )
            logger.info(f"Using chunker {type(chunker).__name__} for {doc_path}")

            knowledge.insert(
                path=str(path),
                reader=reader,
            )
            processed_count += 1
            logger.info(f"Added document {doc_path} to official KB {kb_id}")
        except Exception as e:
            logger.error(f"Failed to insert {doc_path} into official KB {kb_id}: {e}")

    # Update chunk count in metadata
    if processed_count > 0:
        try:
            chunk_count = _count_chunks(kb_id)
            from auth.kb_metadata import update_kb_chunk_count
            update_kb_chunk_count(kb_id, increment=chunk_count)
        except Exception as e:
            logger.error(f"Failed to update chunk count for official KB {kb_id}: {e}")

    return processed_count


def _count_chunks(kb_id: str) -> int:
    """Count chunks in a knowledge base's vector table."""
    try:
        with psycopg.connect(get_psycopg_db_url(id="official-kb-counter")) as conn:
            with conn.cursor() as cur:
                safe_kb_id = kb_id.replace("-", "_")
                cur.execute(f"SELECT COUNT(*) FROM {Config.DB_NAME}.{safe_kb_id}_knowledge_vectors")
                count = cur.fetchone()[0]
                return count
    except Exception as e:
        logger.error(f"Failed to count chunks in KB {kb_id}: {e}")
        return 0


def ensure_default_official_kbs() -> Dict[str, Optional[KnowledgeBaseRecord]]:
    """
    Ensure default official knowledge bases exist.

    This should be called on application startup to create official KBs
    if they don't exist yet.

    Returns:
        Dictionary mapping KB names to their records
    """
    # Define default official KBs
    default_kbs = [
        {
            "name": "System Documentation",
            "description": "Official system documentation and user guides",
            "documents": [],
        },
        {
            "name": "Code Architecture",
            "description": "Code architecture and design patterns",
            "documents": [],
        },
        {
            "name": "Data and Storage",
            "description": "Data configuration and storage conventions",
            "documents": [],
        },
    ]

    # Try to find documentation files
    docs_dir = Path("./docs/agent_docs")
    if docs_dir.exists():
        # Map KB names to potential document files
        doc_mapping = {
            "System Documentation": ["01_project_overview.md"],
            "Code Architecture": ["02_code_architecture.md"],
            "Data and Storage": ["05_data_config_and_storage.md"],
        }

        for kb_config in default_kbs:
            kb_name = kb_config["name"]
            if kb_name in doc_mapping:
                for doc_file in doc_mapping[kb_name]:
                    doc_path = docs_dir / doc_file
                    if doc_path.exists():
                        kb_config["documents"].append(str(doc_path))

    # Create KBs
    results = {}
    for kb_config in default_kbs:
        try:
            kb_record = create_official_knowledge_base(
                name=kb_config["name"],
                description=kb_config["description"],
                initial_documents=kb_config.get("documents", []),
            )
            results[kb_config["name"]] = kb_record
        except Exception as e:
            logger.error(f"Failed to create official KB '{kb_config['name']}': {e}")
            results[kb_config["name"]] = None

    return results


def list_official_knowledge_bases() -> List[KnowledgeBaseRecord]:
    """List all official knowledge bases."""
    return list_knowledge_bases(is_official=True, is_active=True)


def copy_official_kb_to_personal(
    source_kb_id: str,
    target_kb_id: str,
) -> Dict[str, int]:
    """
    Copy all chunks from an official KB to a personal KB.

    Args:
        source_kb_id: The official KB ID to copy from
        target_kb_id: The personal KB ID to copy to

    Returns:
        Dictionary with 'chunks_copied' and 'errors' counts
    """
    source_kb = get_knowledge_base(source_kb_id)
    if not source_kb or not source_kb.is_official:
        raise ValueError("Source must be an official knowledge base")

    target_kb = get_knowledge_base(target_kb_id)
    if not target_kb:
        raise ValueError("Target knowledge base not found")

    safe_source_id = source_kb_id.replace("-", "_")
    safe_target_id = target_kb_id.replace("-", "_")

    chunks_copied = 0
    errors = 0

    try:
        with psycopg.connect(get_psycopg_db_url(id="official-kb-copy")) as conn:
            with conn.cursor() as cur:
                # Read chunks from source
                cur.execute(f"""
                    SELECT embedding, data, meta
                    FROM {Config.DB_NAME}.{safe_source_id}_knowledge_vectors
                """)

                chunks = cur.fetchall()

                # Insert chunks into target
                for embedding, data, meta in chunks:
                    try:
                        cur.execute(f"""
                            INSERT INTO {Config.DB_NAME}.{safe_target_id}_knowledge_vectors
                            (embedding, data, meta)
                            VALUES (%s, %s, %s)
                        """, (embedding, data, meta))
                        chunks_copied += 1
                    except Exception as e:
                        logger.error(f"Failed to copy chunk: {e}")
                        errors += 1

                conn.commit()

        # Update target KB chunk count
        from auth.knowledge_db import update_kb_chunk_count
        update_kb_chunk_count(target_kb_id, increment=chunks_copied)

        logger.info(f"Copied {chunks_copied} chunks from {source_kb_id} to {target_kb_id}")

    except Exception as e:
        logger.error(f"Failed to copy KB content: {e}")
        raise

    return {
        "chunks_copied": chunks_copied,
        "errors": errors,
    }


def sync_official_kb_updates(
    source_kb_id: str,
    target_kb_ids: List[str],
) -> Dict[str, Dict[str, int]]:
    """
    Sync updates from an official KB to multiple personal KBs that were copied from it.

    Args:
        source_kb_id: The official KB ID to sync from
        target_kb_ids: List of personal KB IDs that were copied from this official KB

    Returns:
        Dictionary mapping target KB IDs to copy results
    """
    results = {}

    for target_kb_id in target_kb_ids:
        try:
            results[target_kb_id] = copy_official_kb_to_personal(source_kb_id, target_kb_id)
        except Exception as e:
            logger.error(f"Failed to sync to {target_kb_id}: {e}")
            results[target_kb_id] = {"chunks_copied": 0, "errors": 1}

    return results
