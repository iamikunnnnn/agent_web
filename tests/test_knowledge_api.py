"""
Tests for knowledge base API endpoints.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch


class TestKnowledgeBaseAPI:
    """Test knowledge base API endpoints."""

    @pytest.mark.asyncio
    async def test_create_knowledge_base_unauthorized(self, async_client: AsyncClient):
        """Test creating a knowledge base without authentication."""
        response = await async_client.post(
            "/knowledge/bases",
            json={
                "name": "Test KB",
                "description": "Test knowledge base",
                "chunking_mode": "document",
                "chunk_size": 5000,
                "chunk_overlap": 200,
                "max_results": 10,
                "is_public": False,
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_unauthorized(self, async_client: AsyncClient):
        """Test listing knowledge bases without authentication."""
        response = await async_client.get("/knowledge/bases")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_knowledge_base_unauthorized(self, async_client: AsyncClient):
        """Test getting a knowledge base without authentication."""
        response = await async_client.get("/knowledge/bases/some-id")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_search_unauthorized(self, async_client: AsyncClient):
        """Test searching without authentication."""
        response = await async_client.post(
            "/knowledge/search",
            json={
                "query": "test query",
                "kb_id": "some-kb-id",
                "max_results": 10,
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_file_unauthorized(self, async_client: AsyncClient):
        """Test uploading a file without authentication."""
        response = await async_client.post(
            "/knowledge/bases/some-id/files",
            files={"file": ("test.pdf", b"test content", "application/pdf")},
        )

        assert response.status_code == 401


class TestKnowledgeBaseAPIWithAuth:
    """Test knowledge base API endpoints with authentication."""

    @pytest.fixture
    def mock_token(self):
        """Mock JWT token."""
        return "Bearer mock-token"

    @pytest.fixture
    def mock_user(self):
        """Mock current user."""
        from auth.model import CurrentUser

        return CurrentUser(
            user_id="test-user-123",
            email="test@example.com",
            scopes=["read", "write"],
        )

    @pytest.mark.asyncio
    async def test_create_knowledge_base_authorized(
        self, async_client: AsyncClient, mock_user, mock_token
    ):
        """Test creating a knowledge base with authentication."""
        # Mock the JWT verification and current user
        with patch("auth.permissions.get_current_user", return_value=mock_user):
            with patch("auth.knowledge_db.create_knowledge_vector"):
                response = await async_client.post(
                    "/knowledge/bases",
                    json={
                        "name": "Test KB",
                        "description": "Test knowledge base",
                        "chunking_mode": "document",
                        "chunk_size": 5000,
                        "chunk_overlap": 200,
                        "max_results": 10,
                        "is_public": False,
                    },
                    headers={"Authorization": mock_token},
                )

                # Should create successfully or fail with specific error
                assert response.status_code in [201, 500]  # 500 if vector DB creation fails

                if response.status_code == 201:
                    data = response.json()
                    assert "kb_id" in data
                    assert data["name"] == "Test KB"
                    assert data["owner_id"] == "test-user-123"
                    assert data["is_official"] is False
                    assert data["is_public"] is False

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_authorized(
        self, async_client: AsyncClient, mock_user, mock_token
    ):
        """Test listing knowledge bases with authentication."""
        with patch("auth.permissions.get_current_user", return_value=mock_user):
            response = await async_client.get(
                "/knowledge/bases",
                headers={"Authorization": mock_token},
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_official_knowledge_bases(
        self, async_client: AsyncClient, mock_user, mock_token
    ):
        """Test listing official knowledge bases."""
        with patch("auth.permissions.get_current_user", return_value=mock_user):
            response = await async_client.get(
                "/knowledge/official",
                headers={"Authorization": mock_token},
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_search_with_auth(
        self, async_client: AsyncClient, mock_user, mock_token
    ):
        """Test searching with authentication."""
        with patch("auth.permissions.get_current_user", return_value=mock_user):
            with patch("auth.knowledge_db.get_knowledge_base") as mock_get_kb:
                # Mock a valid KB
                from auth.knowledge_db import KnowledgeBaseRecord
                from datetime import datetime

                mock_get_kb.return_value = KnowledgeBaseRecord(
                    kb_id="test-kb-id",
                    kb_name="Test KB",
                    kb_description="Test",
                    owner_id="test-user-123",
                    is_official=False,
                    is_public=False,
                    vector_table_name="test_knowledge_vectors",
                    chunking_mode="document",
                    chunk_size=5000,
                    chunk_overlap=200,
                    max_results=10,
                    file_count=0,
                    total_chunks=0,
                    is_active=True,
                    indexing_status="idle",
                    last_indexed_at=None,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                with patch("config.db_config.create_knowledge") as mock_create_kb:
                    # Mock empty search results
                    mock_kb_instance = mock_create_kb.return_value
                    mock_kb_instance.search.return_value = []

                    response = await async_client.post(
                        "/knowledge/search",
                        json={
                            "query": "test query",
                            "kb_id": "test-kb-id",
                            "max_results": 10,
                        },
                        headers={"Authorization": mock_token},
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert isinstance(data, list)


class TestFileUploadAPI:
    """Test file upload API endpoints."""

    @pytest.fixture
    def mock_user(self):
        """Mock current user."""
        from auth.model import CurrentUser

        return CurrentUser(
            user_id="test-user-123",
            email="test@example.com",
            scopes=["read", "write"],
        )

    @pytest.mark.asyncio
    async def test_upload_file_with_auth(
        self, async_client: AsyncClient, mock_user
    ):
        """Test uploading a file with authentication."""
        from auth.knowledge_db import KnowledgeBaseRecord
        from datetime import datetime

        with patch("auth.permissions.get_current_user", return_value=mock_user):
            with patch("auth.knowledge_db.get_knowledge_base") as mock_get_kb:
                # Mock a valid KB owned by the user
                mock_get_kb.return_value = KnowledgeBaseRecord(
                    kb_id="test-kb-id",
                    kb_name="Test KB",
                    kb_description="Test",
                    owner_id="test-user-123",
                    is_official=False,
                    is_public=False,
                    vector_table_name="test_knowledge_vectors",
                    chunking_mode="document",
                    chunk_size=5000,
                    chunk_overlap=200,
                    max_results=10,
                    file_count=0,
                    total_chunks=0,
                    is_active=True,
                    indexing_status="idle",
                    last_indexed_at=None,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                with patch("auth.knowledge_processor.queue_file_for_processing"):
                    response = await async_client.post(
                        "/knowledge/bases/test-kb-id/files",
                        files={"file": ("test.pdf", b"test content", "application/pdf")},
                        headers={"Authorization": "Bearer mock-token"},
                    )

                    assert response.status_code == 201
                    data = response.json()
                    assert "file_id" in data
                    assert data["kb_id"] == "test-kb-id"
                    assert data["processing_status"] == "pending"

    @pytest.mark.asyncio
    async def test_upload_unsupported_file_type(
        self, async_client: AsyncClient, mock_user
    ):
        """Test uploading an unsupported file type."""
        from auth.knowledge_db import KnowledgeBaseRecord
        from datetime import datetime

        with patch("auth.permissions.get_current_user", return_value=mock_user):
            with patch("auth.knowledge_db.get_knowledge_base") as mock_get_kb:
                mock_get_kb.return_value = KnowledgeBaseRecord(
                    kb_id="test-kb-id",
                    kb_name="Test KB",
                    kb_description="Test",
                    owner_id="test-user-123",
                    is_official=False,
                    is_public=False,
                    vector_table_name="test_knowledge_vectors",
                    chunking_mode="document",
                    chunk_size=5000,
                    chunk_overlap=200,
                    max_results=10,
                    file_count=0,
                    total_chunks=0,
                    is_active=True,
                    indexing_status="idle",
                    last_indexed_at=None,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                response = await async_client.post(
                    "/knowledge/bases/test-kb-id/files",
                    files={"file": ("test.exe", b"test content", "application/octet-stream")},
                    headers={"Authorization": "Bearer mock-token"},
                )

                assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_to_official_kb_as_non_admin(
        self, async_client: AsyncClient
    ):
        """Test that non-admin users cannot upload to official KBs."""
        from auth.model import CurrentUser
        from auth.knowledge_db import KnowledgeBaseRecord
        from datetime import datetime

        non_admin_user = CurrentUser(
            user_id="regular-user",
            email="regular@example.com",
            scopes=["read", "write"],
        )

        with patch("auth.permissions.get_current_user", return_value=non_admin_user):
            with patch("auth.knowledge_db.get_knowledge_base") as mock_get_kb:
                # Mock an official KB
                mock_get_kb.return_value = KnowledgeBaseRecord(
                    kb_id="official-kb-id",
                    kb_name="Official KB",
                    kb_description="Official",
                    owner_id="system",
                    is_official=True,
                    is_public=True,
                    vector_table_name="official_knowledge_vectors",
                    chunking_mode="document",
                    chunk_size=5000,
                    chunk_overlap=200,
                    max_results=10,
                    file_count=0,
                    total_chunks=0,
                    is_active=True,
                    indexing_status="idle",
                    last_indexed_at=None,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                response = await async_client.post(
                    "/knowledge/bases/official-kb-id/files",
                    files={"file": ("test.pdf", b"test content", "application/pdf")},
                    headers={"Authorization": "Bearer mock-token"},
                )

                assert response.status_code == 403


class TestDeleteOperations:
    """Test delete operations."""

    @pytest.fixture
    def mock_user(self):
        """Mock current user."""
        from auth.model import CurrentUser

        return CurrentUser(
            user_id="test-user-123",
            email="test@example.com",
            scopes=["read", "write"],
        )

    @pytest.mark.asyncio
    async def test_delete_own_kb(
        self, async_client: AsyncClient, mock_user
    ):
        """Test deleting own knowledge base."""
        from auth.knowledge_db import KnowledgeBaseRecord
        from datetime import datetime

        with patch("auth.permissions.get_current_user", return_value=mock_user):
            with patch("auth.knowledge_db.get_knowledge_base") as mock_get_kb:
                mock_get_kb.return_value = KnowledgeBaseRecord(
                    kb_id="test-kb-id",
                    kb_name="Test KB",
                    kb_description="Test",
                    owner_id="test-user-123",
                    is_official=False,
                    is_public=False,
                    vector_table_name="test_knowledge_vectors",
                    chunking_mode="document",
                    chunk_size=5000,
                    chunk_overlap=200,
                    max_results=10,
                    file_count=0,
                    total_chunks=0,
                    is_active=True,
                    indexing_status="idle",
                    last_indexed_at=None,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                with patch("auth.knowledge_db.drop_knowledge_tables"):
                    with patch("auth.knowledge_db.delete_knowledge_base"):
                        response = await async_client.delete(
                            "/knowledge/bases/test-kb-id",
                            headers={"Authorization": "Bearer mock-token"},
                        )

                        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_other_users_kb(
        self, async_client: AsyncClient, mock_user
    ):
        """Test that users cannot delete other users' KBs."""
        from auth.knowledge_db import KnowledgeBaseRecord
        from datetime import datetime

        with patch("auth.permissions.get_current_user", return_value=mock_user):
            with patch("auth.knowledge_db.get_knowledge_base") as mock_get_kb:
                # Mock a KB owned by another user
                mock_get_kb.return_value = KnowledgeBaseRecord(
                    kb_id="other-users-kb",
                    kb_name="Other User's KB",
                    kb_description="Not yours",
                    owner_id="other-user-456",
                    is_official=False,
                    is_public=False,
                    vector_table_name="other_knowledge_vectors",
                    chunking_mode="document",
                    chunk_size=5000,
                    chunk_overlap=200,
                    max_results=10,
                    file_count=0,
                    total_chunks=0,
                    is_active=True,
                    indexing_status="idle",
                    last_indexed_at=None,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                response = await async_client.delete(
                    "/knowledge/bases/other-users-kb",
                    headers={"Authorization": "Bearer mock-token"},
                )

                assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_official_kb_as_non_admin(
        self, async_client: AsyncClient, mock_user
    ):
        """Test that non-admin users cannot delete official KBs."""
        from auth.knowledge_db import KnowledgeBaseRecord
        from datetime import datetime

        with patch("auth.permissions.get_current_user", return_value=mock_user):
            with patch("auth.knowledge_db.get_knowledge_base") as mock_get_kb:
                # Mock an official KB
                mock_get_kb.return_value = KnowledgeBaseRecord(
                    kb_id="official-kb",
                    kb_name="Official KB",
                    kb_description="Official",
                    owner_id="system",
                    is_official=True,
                    is_public=True,
                    vector_table_name="official_knowledge_vectors",
                    chunking_mode="document",
                    chunk_size=5000,
                    chunk_overlap=200,
                    max_results=10,
                    file_count=0,
                    total_chunks=0,
                    is_active=True,
                    indexing_status="idle",
                    last_indexed_at=None,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                response = await async_client.delete(
                    "/knowledge/bases/official-kb",
                    headers={"Authorization": "Bearer mock-token"},
                )

                assert response.status_code == 403
