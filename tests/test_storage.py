"""Tests for Object Storage Backends (Mock, Local, Supabase, Path Traversal Protection)."""

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.storage.base import StorageError, StorageFileNotFoundError
from app.storage.local import LocalStorageBackend
from app.storage.mock import MockStorageBackend
from app.storage.supabase import SupabaseStorageBackend


@pytest.mark.asyncio
async def test_mock_storage_operations() -> None:
    """Verifies that MockStorageBackend supports upload, download, exists, and delete."""
    storage = MockStorageBackend()

    # Upload
    key = "test/path/document.pdf"
    content = b"%PDF-1.4 mock content"
    uploaded_key = await storage.upload_file(key, content, "application/pdf")
    assert uploaded_key == key

    # Exists
    assert await storage.file_exists(key) is True
    assert await storage.file_exists("nonexistent.pdf") is False

    # Download
    downloaded = await storage.download_file(key)
    assert downloaded == content

    # Health check
    assert await storage.health_check() is True
    storage.set_healthy(False)
    assert await storage.health_check() is False

    # Delete
    assert await storage.delete_file(key) is True
    assert await storage.file_exists(key) is False

    # Download after delete raises FileNotFoundError
    with pytest.raises(StorageFileNotFoundError):
        await storage.download_file(key)


@pytest.mark.asyncio
async def test_local_storage_operations(tmp_path: pytest.TempPathFactory) -> None:
    """Verifies that LocalStorageBackend writes and reads securely from disk."""
    base_dir = str(tmp_path)
    storage = LocalStorageBackend(base_dir=base_dir)

    key = "workspaces/ws-1/sources/src-1/test.txt"
    content = b"Local storage test content."

    # Upload
    await storage.upload_file(key, content, "text/plain")
    assert await storage.file_exists(key) is True

    # Download
    data = await storage.download_file(key)
    assert data == content

    # Health check
    assert await storage.health_check() is True

    # Delete
    await storage.delete_file(key)
    assert await storage.file_exists(key) is False


@pytest.mark.asyncio
async def test_local_storage_path_traversal_protection(tmp_path: pytest.TempPathFactory) -> None:
    """Verifies that LocalStorageBackend detects and blocks directory traversal attempts."""
    storage = LocalStorageBackend(base_dir=str(tmp_path))

    traversal_key = "../../../etc/passwd"
    with pytest.raises(StorageError, match="Directory traversal detected"):
        await storage.upload_file(traversal_key, b"malicious", "text/plain")


@pytest.mark.asyncio
async def test_supabase_storage_operations() -> None:
    """Verifies that SupabaseStorageBackend communicates via asynchronous REST calls."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and "object/test-bucket/test.pdf" in url:
            return httpx.Response(200, json={"Key": "test.pdf"})
        if request.method == "GET" and "object/authenticated/test-bucket/test.pdf" in url:
            return httpx.Response(200, content=b"supabase content")
        if request.method == "GET" and "object/info/authenticated/test-bucket/test.pdf" in url:
            return httpx.Response(200, json={"size": 16})
        if request.method == "DELETE" and "object/test-bucket" in url:
            return httpx.Response(200, json=[{"name": "test.pdf"}])
        if request.method == "GET" and "bucket/test-bucket" in url:
            return httpx.Response(200, json={"id": "test-bucket"})
        return httpx.Response(404, text="Not Found")

    transport = httpx.MockTransport(handler)
    settings = Settings(
        SUPABASE_URL="https://mockproject.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY=SecretStr("mock-service-role-key-test-long-secret"),
        SUPABASE_STORAGE_BUCKET="test-bucket",
    )
    backend = SupabaseStorageBackend(settings=settings)
    backend._get_client = lambda timeout=15.0: httpx.AsyncClient(transport=transport)

    # Upload
    key = await backend.upload_file("test.pdf", b"supabase content", "application/pdf")
    assert key == "test.pdf"

    # Exists
    assert await backend.file_exists("test.pdf") is True
    assert await backend.file_exists("absent.pdf") is False

    # Download
    data = await backend.download_file("test.pdf")
    assert data == b"supabase content"

    # Health check
    assert await backend.health_check() is True

    # Delete
    assert await backend.delete_file("test.pdf") is True

    # Directory traversal check
    with pytest.raises(StorageError, match="Directory traversal detected"):
        await backend.upload_file("../secret.txt", b"hack", "text/plain")
