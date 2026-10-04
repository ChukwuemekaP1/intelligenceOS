"""In-memory Mock Object Storage Backend.

Provides a fast, zero-dependency storage provider for isolated tests and local offline development.
"""

from app.storage.base import StorageBackend, StorageFileNotFoundError


class MockStorageBackend(StorageBackend):
    """Stores files in an in-memory dictionary.

    Keys map to tuples of (data: bytes, content_type: str).
    Thread-safe within asyncio single-threaded event loop.
    """

    def __init__(self) -> None:
        self._storage: dict[str, tuple[bytes, str]] = {}
        self._is_healthy: bool = True

    def set_healthy(self, healthy: bool) -> None:
        """Helper for test suites to simulate downstream storage failures."""
        self._is_healthy = healthy

    async def upload_file(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Saves bytes to in-memory store."""
        self._storage[key] = (data, content_type)
        return key

    async def download_file(self, key: str) -> bytes:
        """Retrieves bytes from in-memory store."""
        if key not in self._storage:
            raise StorageFileNotFoundError(f"Object '{key}' not found in mock storage.")
        return self._storage[key][0]

    async def delete_file(self, key: str) -> bool:
        """Removes object from in-memory store."""
        self._storage.pop(key, None)
        return True

    async def file_exists(self, key: str) -> bool:
        """Checks presence in in-memory store."""
        return key in self._storage

    async def health_check(self) -> bool:
        """Returns the simulated health status."""
        return self._is_healthy
