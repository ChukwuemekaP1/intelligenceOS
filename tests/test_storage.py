"""Tests for Object Storage Backends (Mock, Local, Path Traversal Protection)."""

import pytest

from app.storage.base import StorageError, StorageFileNotFoundError
from app.storage.local import LocalStorageBackend
from app.storage.mock import MockStorageBackend


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
