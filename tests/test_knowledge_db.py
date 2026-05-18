"""
Tests for knowledge base database operations.
"""

import pytest
import uuid
from datetime import datetime, timezone

from auth.knowledge_db import (
    create_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    update_knowledge_base,
    delete_knowledge_base,
    create_file_record,
    get_file_record,
    list_files_by_kb,
    update_file_status,
    delete_file as db_delete_file,
    update_kb_file_count,
    update_kb_chunk_count,
    record_knowledge_copy,
    get_kb_copies,
)


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "test-user-123"


@pytest.fixture
def test_kb_id(test_user_id):
    """Create and return a test knowledge base ID."""
    kb_id = str(uuid.uuid4())
    safe_kb_id = kb_id.replace("-", "_")

    try:
        kb = create_knowledge_base(
            kb_id=kb_id,
            kb_name="Test KB",
            kb_description="Test knowledge base",
            owner_id=test_user_id,
            is_official=False,
            is_public=False,
            vector_table_name=f"{safe_kb_id}_knowledge_vectors",
            chunking_mode="document",
            chunk_size=5000,
            chunk_overlap=200,
            max_results=10,
        )
        yield kb_id
    finally:
        # Cleanup
        try:
            delete_knowledge_base(kb_id)
        except Exception:
            pass


class TestKnowledgeBaseCRUD:
    """Test knowledge base CRUD operations."""

    def test_create_knowledge_base(self, test_user_id):
        """Test creating a knowledge base."""
        kb_id = str(uuid.uuid4())
        safe_kb_id = kb_id.replace("-", "_")

        kb = create_knowledge_base(
            kb_id=kb_id,
            kb_name="Test KB",
            kb_description="Test knowledge base",
            owner_id=test_user_id,
            is_official=False,
            is_public=False,
            vector_table_name=f"{safe_kb_id}_knowledge_vectors",
            chunking_mode="document",
            chunk_size=5000,
            chunk_overlap=200,
            max_results=10,
        )

        assert kb.kb_id == kb_id
        assert kb.kb_name == "Test KB"
        assert kb.owner_id == test_user_id
        assert kb.is_official is False
        assert kb.is_public is False
        assert kb.chunking_mode == "document"
        assert kb.chunk_size == 5000
        assert kb.chunk_overlap == 200
        assert kb.max_results == 10
        assert kb.file_count == 0
        assert kb.total_chunks == 0
        assert kb.is_active is True
        assert kb.indexing_status == "idle"

        # Cleanup
        delete_knowledge_base(kb_id)

    def test_create_knowledge_base_with_auto_chunking_mode(self, test_user_id):
        """Test creating a knowledge base with persisted auto chunking mode."""
        kb_id = str(uuid.uuid4())
        safe_kb_id = kb_id.replace("-", "_")

        kb = create_knowledge_base(
            kb_id=kb_id,
            kb_name="Auto Chunk KB",
            kb_description="Test auto chunking mode",
            owner_id=test_user_id,
            is_official=False,
            is_public=False,
            vector_table_name=f"{safe_kb_id}_knowledge_vectors",
            chunking_mode="auto",
            chunk_size=5000,
            chunk_overlap=200,
            max_results=10,
        )

        assert kb.kb_id == kb_id
        assert kb.chunking_mode == "auto"

        delete_knowledge_base(kb_id)

    def test_get_knowledge_base(self, test_kb_id):
        """Test getting a knowledge base by ID."""
        kb = get_knowledge_base(test_kb_id)

        assert kb is not None
        assert kb.kb_id == test_kb_id
        assert kb.kb_name == "Test KB"

    def test_get_nonexistent_knowledge_base(self):
        """Test getting a non-existent knowledge base."""
        kb = get_knowledge_base("nonexistent-id")
        assert kb is None

    def test_list_knowledge_bases(self, test_kb_id, test_user_id):
        """Test listing knowledge bases."""
        kbs = list_knowledge_bases(owner_id=test_user_id)

        assert len(kbs) >= 1
        assert any(kb.kb_id == test_kb_id for kb in kbs)

    def test_update_knowledge_base(self, test_kb_id):
        """Test updating a knowledge base."""
        updated_kb = update_knowledge_base(
            test_kb_id,
            kb_name="Updated Test KB",
            kb_description="Updated description",
            is_public=True,
        )

        assert updated_kb is not None
        assert updated_kb.kb_name == "Updated Test KB"
        assert updated_kb.kb_description == "Updated description"
        assert updated_kb.is_public is True

    def test_delete_knowledge_base(self, test_user_id):
        """Test deleting a knowledge base."""
        kb_id = str(uuid.uuid4())
        safe_kb_id = kb_id.replace("-", "_")

        # Create
        create_knowledge_base(
            kb_id=kb_id,
            kb_name="KB to Delete",
            kb_description="Will be deleted",
            owner_id=test_user_id,
            is_official=False,
            is_public=False,
            vector_table_name=f"{safe_kb_id}_knowledge_vectors",
            chunking_mode="document",
            chunk_size=5000,
            chunk_overlap=200,
            max_results=10,
        )

        # Verify exists
        assert get_knowledge_base(kb_id) is not None

        # Delete
        result = delete_knowledge_base(kb_id)
        assert result is True

        # Verify deleted
        assert get_knowledge_base(kb_id) is None

    def test_update_kb_counts(self, test_kb_id):
        """Test updating knowledge base counts."""
        # Update file count
        update_kb_file_count(test_kb_id, increment=5)
        kb = get_knowledge_base(test_kb_id)
        assert kb.file_count == 5

        # Update chunk count
        update_kb_chunk_count(test_kb_id, increment=100)
        kb = get_knowledge_base(test_kb_id)
        assert kb.total_chunks == 100


class TestFileOperations:
    """Test file record operations."""

    def test_create_file_record(self, test_kb_id):
        """Test creating a file record."""
        file_id = str(uuid.uuid4())

        file = create_file_record(
            file_id=file_id,
            kb_id=test_kb_id,
            file_name="test.pdf",
            file_path="/test/path/test.pdf",
            file_size=1024,
            file_type="pdf",
            mime_type="application/pdf",
        )

        assert file.file_id == file_id
        assert file.kb_id == test_kb_id
        assert file.file_name == "test.pdf"
        assert file.file_size == 1024
        assert file.file_type == "pdf"
        assert file.processing_status == "pending"

    def test_get_file_record(self, test_kb_id):
        """Test getting a file record."""
        file_id = str(uuid.uuid4())

        create_file_record(
            file_id=file_id,
            kb_id=test_kb_id,
            file_name="test.pdf",
            file_path="/test/path/test.pdf",
            file_size=1024,
            file_type="pdf",
        )

        file = get_file_record(file_id)
        assert file is not None
        assert file.file_id == file_id
        assert file.file_name == "test.pdf"

    def test_list_files_by_kb(self, test_kb_id):
        """Test listing files in a knowledge base."""
        # Create multiple files
        for i in range(3):
            file_id = str(uuid.uuid4())
            create_file_record(
                file_id=file_id,
                kb_id=test_kb_id,
                file_name=f"test{i}.pdf",
                file_path=f"/test/path/test{i}.pdf",
                file_size=1024,
                file_type="pdf",
            )

        files = list_files_by_kb(test_kb_id)
        assert len(files) >= 3
        assert any(f.file_name == "test0.pdf" for f in files)

    def test_update_file_status(self, test_kb_id):
        """Test updating file processing status."""
        file_id = str(uuid.uuid4())

        create_file_record(
            file_id=file_id,
            kb_id=test_kb_id,
            file_name="test.pdf",
            file_path="/test/path/test.pdf",
            file_size=1024,
            file_type="pdf",
        )

        # Update to processing
        updated = update_file_status(file_id, "processing")
        assert updated.processing_status == "processing"

        # Update to completed with chunk count
        updated = update_file_status(file_id, "completed", chunk_count=50)
        assert updated.processing_status == "completed"
        assert updated.chunk_count == 50
        assert updated.processed_at is not None

        # Update to failed with error
        updated = update_file_status(file_id, "failed", error_message="Test error")
        assert updated.processing_status == "failed"
        assert updated.error_message == "Test error"

    def test_delete_file(self, test_kb_id):
        """Test deleting a file record."""
        file_id = str(uuid.uuid4())

        create_file_record(
            file_id=file_id,
            kb_id=test_kb_id,
            file_name="test.pdf",
            file_path="/test/path/test.pdf",
            file_size=1024,
            file_type="pdf",
        )

        # Verify exists
        assert get_file_record(file_id) is not None

        # Delete
        result = db_delete_file(file_id)
        assert result is True

        # Verify deleted
        assert get_file_record(file_id) is None


class TestCopyOperations:
    """Test knowledge base copy operations."""

    def test_record_knowledge_copy(self, test_kb_id, test_user_id):
        """Test recording a knowledge base copy operation."""
        source_kb_id = str(uuid.uuid4())
        safe_source_id = source_kb_id.replace("-", "_")

        # Create source KB
        create_knowledge_base(
            kb_id=source_kb_id,
            kb_name="Source KB",
            kb_description="Source for copy",
            owner_id=test_user_id,
            is_official=True,
            is_public=True,
            vector_table_name=f"{safe_source_id}_knowledge_vectors",
            chunking_mode="document",
            chunk_size=5000,
            chunk_overlap=200,
            max_results=10,
        )

        try:
            # Record copy
            copy = record_knowledge_copy(source_kb_id, test_kb_id)

            assert copy.source_kb_id == source_kb_id
            assert copy.target_kb_id == test_kb_id
            assert copy.copied_at is not None

            # Get copies
            copies = get_kb_copies(test_kb_id)
            assert len(copies) >= 1
            assert any(c.source_kb_id == source_kb_id for c in copies)
        finally:
            # Cleanup
            delete_knowledge_base(source_kb_id)


class TestMultiUserIsolation:
    """Test multi-user isolation."""

    @pytest.fixture
    def user_a(self):
        return "user-a-123"

    @pytest.fixture
    def user_b(self):
        return "user-b-456"

    @pytest.fixture
    def kb_a(self, user_a):
        """Create KB for user A."""
        kb_id = str(uuid.uuid4())
        safe_kb_id = kb_id.replace("-", "_")

        kb = create_knowledge_base(
            kb_id=kb_id,
            kb_name="User A's KB",
            kb_description="Private KB for user A",
            owner_id=user_a,
            is_official=False,
            is_public=False,
            vector_table_name=f"{safe_kb_id}_knowledge_vectors",
            chunking_mode="document",
            chunk_size=5000,
            chunk_overlap=200,
            max_results=10,
        )

        try:
            yield kb_id
        finally:
            try:
                delete_knowledge_base(kb_id)
            except Exception:
                pass

    def test_user_cannot_access_other_users_private_kb(self, kb_a, user_b):
        """Test that user B cannot access user A's private KB."""
        kbs = list_knowledge_bases(owner_id=user_b)

        # User B should not see user A's KB
        assert not any(kb.kb_id == kb_a for kb in kbs)

    def test_list_accessible_includes_public_kbs(self, user_a, user_b):
        """Test that public KBs are accessible to all users."""
        # Create a public KB for user A
        kb_id = str(uuid.uuid4())
        safe_kb_id = kb_id.replace("-", "_")

        try:
            create_knowledge_base(
                kb_id=kb_id,
                kb_name="Public KB",
                kb_description="Publicly accessible KB",
                owner_id=user_a,
                is_official=False,
                is_public=True,
                vector_table_name=f"{safe_kb_id}_knowledge_vectors",
                chunking_mode="document",
                chunk_size=5000,
                chunk_overlap=200,
                max_results=10,
            )

            # User B should be able to access public KBs (would need to test list_accessible_knowledge_bases)
            # For now, just test listing with is_public filter
            public_kbs = list_knowledge_bases(is_public=True)
            assert any(kb.kb_id == kb_id for kb in public_kbs)

        finally:
            try:
                delete_knowledge_base(kb_id)
            except Exception:
                pass
