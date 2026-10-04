"""Local Filesystem Object Storage Backend.

Stores uploaded files in a designated local directory on the server disk.
Implements directory containment checks to protect against path traversal attacks.
"""

import asyncio
from pathlib import Path

from app.storage.base import StorageBackend, StorageError, StorageFileNotFoundError


class LocalStorageBackend(StorageBackend):
    """Filesystem-backed storage provider.

    Enforces that all object keys reside strictly under the configured root directory.
    """

    def __init__(self, base_dir: str = "./storage_data") -> None:
        self.base_path = Path(base_dir).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, key: str) -> Path:
        """Resolves a key relative to base_dir and verifies no directory traversal occurs.

        Raises:
            StorageError: If resolved path attempts to escape base directory.
        """
        # Normalize slashes
        clean_key = key.lstrip("/\\")
        target = (self.base_path / clean_key).resolve()
        if not target.is_relative_to(self.base_path):
            raise StorageError(f"Directory traversal detected for storage key: {key}")
        return target

    async def upload_file(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Writes binary data to local file path in a thread pool."""
        target_path = self._resolve_safe_path(key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        def _write() -> None:
            target_path.write_bytes(data)

        await asyncio.to_thread(_write)
        return key

    async def download_file(self, key: str) -> bytes:
        """Reads binary data from local file path."""
        target_path = self._resolve_safe_path(key)
        if not target_path.exists() or not target_path.is_file():
            raise StorageFileNotFoundError(f"Object '{key}' not found on local disk.")

        def _read() -> bytes:
            return target_path.read_bytes()

        return await asyncio.to_thread(_read)

    async def delete_file(self, key: str) -> bool:
        """Deletes file from local disk."""
        target_path = self._resolve_safe_path(key)

        def _delete() -> None:
            if target_path.exists():
                target_path.unlink()

        await asyncio.to_thread(_delete)
        return True

    async def file_exists(self, key: str) -> bool:
        """Checks if file exists on disk."""
        target_path = self._resolve_safe_path(key)
        return await asyncio.to_thread(lambda: target_path.exists() and target_path.is_file())

    async def health_check(self) -> bool:
        """Verifies local directory is writable."""
        try:
            test_file = self.base_path / ".health_check"
            await asyncio.to_thread(lambda: test_file.write_text("ok"))
            await asyncio.to_thread(lambda: test_file.unlink(missing_ok=True))
            return True
        except Exception:
            return False
