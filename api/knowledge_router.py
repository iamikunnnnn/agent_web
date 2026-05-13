"""
Knowledge Base Management API Router

Provides endpoints for managing user knowledge bases with multi-tenant isolation.
"""
from agno.utils.log import logger
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import uuid
import aiofiles

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse as FastAPIFileResponse

from auth.permissions import get_current_user
from auth.model import CurrentUser
from auth.knowledge_db import (
    create_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    list_accessible_knowledge_bases,
    update_knowledge_base,
    delete_knowledge_base,
    drop_knowledge_tables,
    create_file_record,
    get_file_record,
    list_files_by_kb,
    update_file_status,
    delete_file as db_delete_file,
    update_kb_file_count,
    update_kb_chunk_count,
    update_kb_indexing_status,
    record_knowledge_copy,
    get_kb_copies,
)
from config.db_config import Config, create_knowledge_vector, create_knowledge

from models.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    FileUploadResponse,
    FileResponse,
    SearchRequest,
    SearchResult,
    CopyKnowledgeRequest,
    CopyKnowledgeResponse,
)

knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Storage
from storage import get_qiniu_storage

# Temporary directory for processing files
TEMP_PROCESSING_DIR = Path("./user_cache/knowledge_temp")
TEMP_PROCESSING_DIR.mkdir(parents=True, exist_ok=True)


# ============ Knowledge Base CRUD ============

@knowledge_router.post("/bases", response_model=KnowledgeBaseResponse, status_code=201)
async def create_user_knowledge_base(
    request: Request,
    payload: KnowledgeBaseCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Create a new personal knowledge base for the current user.

    - Users cannot create official knowledge bases (admin only)
    - Public flag allows read access to all authenticated users
    """
    # Generate unique KB ID
    kb_id = str(uuid.uuid4())

    # Derive table name from kb_id (replace hyphens with underscores)
    safe_kb_id = kb_id.replace("-", "_")
    vector_table_name = f"{safe_kb_id}_knowledge_vectors"
    content_table_name = f"{safe_kb_id}_knowledge_contents"

    # Create database record
    # Note: chunking_mode, chunk_size, and chunk_overlap are set to defaults
    # The actual chunking strategy is automatically selected per file by FileDetector
    kb_record = create_knowledge_base(
        kb_id=kb_id,
        kb_name=payload.name,
        kb_description=payload.description,
        owner_id=current_user.user_id,
        is_official=False,
        is_public=payload.is_public,
        vector_table_name=vector_table_name,
        chunking_mode="auto",  # FileDetector will auto-detect per file
        chunk_size=5000,  # Default, may be overridden by specific chunkers
        chunk_overlap=200,  # Default, may be overridden by specific chunkers
        max_results=payload.max_results,
    )

    # Create actual vector DB instance (PgVector)
    try:
        create_knowledge_vector(
            id=safe_kb_id,
            table_name=vector_table_name,
        )
    except Exception as e:
        # Rollback DB record if vector DB creation fails
        delete_knowledge_base(kb_id)
        raise HTTPException(status_code=500, detail=f"Failed to create vector DB: {str(e)}")

    return KnowledgeBaseResponse(
        kb_id=kb_record.kb_id,
        name=kb_record.kb_name,
        description=kb_record.kb_description,
        owner_id=kb_record.owner_id,
        is_official=kb_record.is_official,
        is_public=kb_record.is_public,
        max_results=kb_record.max_results,
        file_count=kb_record.file_count,
        total_chunks=kb_record.total_chunks,
        is_active=kb_record.is_active,
        indexing_status=kb_record.indexing_status,
        last_indexed_at=kb_record.last_indexed_at,
        created_at=kb_record.created_at,
        updated_at=kb_record.updated_at,
    )


@knowledge_router.get("/bases", response_model=List[KnowledgeBaseResponse])
async def list_user_knowledge_bases(
    current_user: CurrentUser = Depends(get_current_user),
    include_official: bool = Query(True, description="Include official knowledge bases"),
    include_public: bool = Query(True, description="Include public knowledge bases"),
    active_only: bool = Query(True, description="Only return active knowledge bases"),
):
    """
    List knowledge bases accessible to the current user.

    - Returns user's own knowledge bases
    - Optionally includes official knowledge bases
    - Optionally includes public knowledge bases from other users
    """
    kbs = list_accessible_knowledge_bases(
        user_id=current_user.user_id,
        include_official=include_official,
        include_public=include_public,
        active_only=active_only,
    )

    return [
        KnowledgeBaseResponse(
            kb_id=kb.kb_id,
            name=kb.kb_name,
            description=kb.kb_description,
            owner_id=kb.owner_id,
            is_official=kb.is_official,
            is_public=kb.is_public,
            max_results=kb.max_results,
            file_count=kb.file_count,
            total_chunks=kb.total_chunks,
            is_active=kb.is_active,
            indexing_status=kb.indexing_status,
            last_indexed_at=kb.last_indexed_at,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
        for kb in kbs
    ]


@knowledge_router.get("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base_detail(
    kb_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get a knowledge base by ID.

    - Users can access their own KBs, official KBs, and public KBs
    """
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check access permission
    if (kb.owner_id != current_user.user_id and
        not kb.is_official and
        not kb.is_public):
        raise HTTPException(status_code=403, detail="Not authorized to access this knowledge base")

    return KnowledgeBaseResponse(
        kb_id=kb.kb_id,
        name=kb.kb_name,
        description=kb.kb_description,
        owner_id=kb.owner_id,
        is_official=kb.is_official,
        is_public=kb.is_public,
        max_results=kb.max_results,
        file_count=kb.file_count,
        total_chunks=kb.total_chunks,
        is_active=kb.is_active,
        indexing_status=kb.indexing_status,
        last_indexed_at=kb.last_indexed_at,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@knowledge_router.put("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_user_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Update an existing knowledge base.

    - Users can only update their own knowledge bases
    - Official knowledge bases can only be updated by admins
    """
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check permissions
    if kb.is_official:
        if "admin" not in current_user.scopes:
            raise HTTPException(status_code=403, detail="Cannot modify official knowledge base")
    else:
        if kb.owner_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this knowledge base")

    # Build update dict (only non-None fields)
    update_data = {}
    if payload.name is not None:
        update_data["kb_name"] = payload.name
    if payload.description is not None:
        update_data["kb_description"] = payload.description
    if payload.is_public is not None:
        update_data["is_public"] = payload.is_public
    if payload.max_results is not None:
        update_data["max_results"] = payload.max_results
    if payload.is_active is not None:
        update_data["is_active"] = payload.is_active

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update in database
    updated_kb = update_knowledge_base(kb_id, **update_data)
    if not updated_kb:
        raise HTTPException(status_code=500, detail="Failed to update knowledge base")

    return KnowledgeBaseResponse(
        kb_id=updated_kb.kb_id,
        name=updated_kb.kb_name,
        description=updated_kb.kb_description,
        owner_id=updated_kb.owner_id,
        is_official=updated_kb.is_official,
        is_public=updated_kb.is_public,
        max_results=updated_kb.max_results,
        file_count=updated_kb.file_count,
        total_chunks=updated_kb.total_chunks,
        is_active=updated_kb.is_active,
        indexing_status=updated_kb.indexing_status,
        last_indexed_at=updated_kb.last_indexed_at,
        created_at=updated_kb.created_at,
        updated_at=updated_kb.updated_at,
    )


@knowledge_router.delete("/bases/{kb_id}", status_code=204)
async def delete_user_knowledge_base(
    kb_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Delete a knowledge base and all its data.

    - Users can only delete their own knowledge bases
    - Official knowledge bases can only be deleted by admins
    - This will cascade delete all files and vector embeddings
    """
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check permissions
    if kb.is_official:
        if "admin" not in current_user.scopes:
            raise HTTPException(status_code=403, detail="Cannot delete official knowledge base")
    else:
        if kb.owner_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this knowledge base")

    # Delete vector DB tables
    try:
        drop_knowledge_tables(kb.vector_table_name, f"{kb.vector_table_name.replace('_vectors', '_contents')}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete vector DB: {str(e)}")

    # Delete database record (cascades to files)
    delete_knowledge_base(kb_id)

    return None


# ============ File Operations ============

@knowledge_router.post("/bases/{kb_id}/files", response_model=FileUploadResponse, status_code=201)
async def upload_file_to_knowledge_base(
    kb_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Upload a file to a knowledge base for indexing.

    - Users can only upload to their own knowledge bases
    - File will be processed asynchronously
    - Supported formats: PDF, DOCX, TXT, MD, HTML
    """
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check write permission
    if kb.is_official and "admin" not in current_user.scopes:
        raise HTTPException(status_code=403, detail="Cannot modify official knowledge base")
    if not kb.is_official and kb.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this knowledge base")

    # Validate file type
    allowed_extensions = {'.pdf', '.docx', '.txt', '.md', '.html', '.htm', '.csv'}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

    # Generate file ID
    file_id = str(uuid.uuid4())

    # Read file content
    file_size = 0
    content = b""
    while chunk := await file.read(8192):
        content += chunk
        file_size += len(chunk)

    # Upload to Qiniu
    try:
        storage = get_qiniu_storage()
        file_url = storage.upload_content(
            module="knowledge",
            user_id=current_user.user_id,
            content=content,
            filename=f"{file_id}{file_ext}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file to storage: {str(e)}")

    # Create file record in database
    file_record = create_file_record(
        file_id=file_id,
        kb_id=kb_id,
        file_name=file.filename,
        file_path=file_url,  # Store URL instead of local path
        file_size=file_size,
        file_type=file_ext[1:],  # Remove the dot
    )

    # Update KB file count
    update_kb_file_count(kb_id, increment=1)

    # Queue file for processing
    from auth.knowledge_processor import queue_file_for_processing
    await queue_file_for_processing(file_id, kb_id)

    return FileUploadResponse(
        file_id=file_record.file_id,
        file_name=file_record.file_name,
        kb_id=file_record.kb_id,
        processing_status=file_record.processing_status,
        uploaded_at=file_record.uploaded_at,
    )


@knowledge_router.get("/bases/{kb_id}/files", response_model=List[FileResponse])
async def list_knowledge_base_files(
    kb_id: str,
    status: Optional[str] = Query(None, description="Filter by processing status"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    List files in a knowledge base.

    - Users can only list files from their own knowledge bases or public/official KBs
    """
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check access permission
    if (kb.owner_id != current_user.user_id and
        not kb.is_official and
        not kb.is_public):
        raise HTTPException(status_code=403, detail="Not authorized to access this knowledge base")

    files = list_files_by_kb(kb_id, status=status)

    return [
        FileResponse(
            file_id=f.file_id,
            kb_id=f.kb_id,
            file_name=f.file_name,
            file_size=f.file_size,
            file_type=f.file_type,
            processing_status=f.processing_status,
            chunk_count=f.chunk_count,
            error_message=f.error_message,
            uploaded_at=f.uploaded_at,
            processed_at=f.processed_at,
        )
        for f in files
    ]


@knowledge_router.get("/files/{file_id}/status", response_model=FileResponse)
async def get_file_status(
    file_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get the processing status of a file.

    - Users can only check status of files in their accessible KBs
    """
    file_record = get_file_record(file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Check access to the KB
    kb = get_knowledge_base(file_record.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if (kb.owner_id != current_user.user_id and
        not kb.is_official and
        not kb.is_public):
        raise HTTPException(status_code=403, detail="Not authorized to access this file")

    return FileResponse(
        file_id=file_record.file_id,
        kb_id=file_record.kb_id,
        file_name=file_record.file_name,
        file_size=file_record.file_size,
        file_type=file_record.file_type,
        processing_status=file_record.processing_status,
        chunk_count=file_record.chunk_count,
        error_message=file_record.error_message,
        uploaded_at=file_record.uploaded_at,
        processed_at=file_record.processed_at,
    )


@knowledge_router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Delete a file from a knowledge base.

    - Users can only delete files from their own knowledge bases
    - Admins can delete files from official knowledge bases
    """
    file_record = get_file_record(file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Check access to the KB
    kb = get_knowledge_base(file_record.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check permissions
    if kb.is_official:
        if "admin" not in current_user.scopes:
            raise HTTPException(status_code=403, detail="Cannot modify official knowledge base")
    else:
        if kb.owner_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this file")

    # Delete file from storage
    try:
        storage = get_qiniu_storage()
        storage.delete_file(file_record.file_path)
    except Exception as e:
        # Log error but continue
        pass

    # Delete from database
    db_delete_file(file_id)

    # Update KB file count
    update_kb_file_count(kb.kb_id, increment=-1)

    return None


# ============ Search ============

@knowledge_router.post("/search", response_model=List[SearchResult])
async def search_knowledge_base(
    payload: SearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Search within a knowledge base.

    - Users can search their own KBs, official KBs, and public KBs
    - Returns ranked results with similarity scores
    """
    kb = get_knowledge_base(payload.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check access permission
    if (kb.owner_id != current_user.user_id and
        not kb.is_official and
        not kb.is_public):
        raise HTTPException(status_code=403, detail="Not authorized to access this knowledge base")

    # Create knowledge instance for search
    try:
        safe_kb_id = kb.kb_id.replace("-", "_")
        knowledge = create_knowledge(
            id=safe_kb_id,
            name=kb.kb_name,
            description=kb.kb_description,
        )

        # Search
        results = knowledge.search(
            query=payload.query,
            max_results=payload.max_results,
        )

        return [
            SearchResult(
                content=result.data.get("content", ""),
                metadata=result.meta or {},
                score=result.score or 0.0,
                source_file=result.data.get("source", ""),
            )
            for result in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ============ Copy Operations ============

@knowledge_router.post("/bases/{kb_id}/copy", response_model=CopyKnowledgeResponse)
async def copy_to_knowledge_base(
    kb_id: str,
    payload: CopyKnowledgeRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Copy content from an official knowledge base to a personal knowledge base.

    - Only official KBs can be used as source
    - Only KB owners can copy to their personal KBs
    - Copies all chunks from source to target
    """
    # Verify target KB
    target_kb = get_knowledge_base(kb_id)
    if not target_kb:
        raise HTTPException(status_code=404, detail="Target knowledge base not found")

    if target_kb.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this knowledge base")

    # Verify source KB
    source_kb = get_knowledge_base(payload.source_kb_id)
    if not source_kb:
        raise HTTPException(status_code=404, detail="Source knowledge base not found")

    if not source_kb.is_official:
        raise HTTPException(status_code=400, detail="Source must be an official knowledge base")

    # Record the copy operation
    copy_record = record_knowledge_copy(source_kb.kb_id, target_kb.kb_id)

    # Perform actual vector data copying
    from auth.official_knowledge import copy_official_kb_to_personal
    try:
        copy_result = copy_official_kb_to_personal(source_kb.kb_id, target_kb.kb_id)
        chunks_copied = copy_result.get("chunks_copied", 0)
    except Exception as e:
        logger.error(f"Failed to copy KB content: {e}")
        chunks_copied = 0

    return CopyKnowledgeResponse(
        copy_id=copy_record.copy_id,
        source_kb_id=copy_record.source_kb_id,
        target_kb_id=copy_record.target_kb_id,
        chunks_copied=0,  # Will be updated by background process
        copied_at=copy_record.copied_at,
    )


@knowledge_router.get("/bases/{kb_id}/copies")
async def get_knowledge_base_copies(
    kb_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get copy operations for a knowledge base.

    - Returns records of what this KB was copied from or to
    """
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check access permission
    if (kb.owner_id != current_user.user_id and
        not kb.is_official and
        not kb.is_public):
        raise HTTPException(status_code=403, detail="Not authorized to access this knowledge base")

    copies = get_kb_copies(kb_id)

    return [
        {
            "copy_id": c.copy_id,
            "source_kb_id": c.source_kb_id,
            "target_kb_id": c.target_kb_id,
            "copied_at": c.copied_at,
        }
        for c in copies
    ]


# ============ Official Knowledge Bases ============

@knowledge_router.get("/official", response_model=List[KnowledgeBaseResponse])
async def list_official_knowledge_bases(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    List all official knowledge bases.

    - Available to all authenticated users
    """
    kbs = list_knowledge_bases(is_official=True, is_active=True)

    return [
        KnowledgeBaseResponse(
            kb_id=kb.kb_id,
            name=kb.kb_name,
            description=kb.kb_description,
            owner_id=kb.owner_id,
            is_official=kb.is_official,
            is_public=kb.is_public,
            max_results=kb.max_results,
            file_count=kb.file_count,
            total_chunks=kb.total_chunks,
            is_active=kb.is_active,
            indexing_status=kb.indexing_status,
            last_indexed_at=kb.last_indexed_at,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
        for kb in kbs
    ]
