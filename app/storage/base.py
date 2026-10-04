"""Abstract Base Class for Object Storage.

Defines the contract for storing, retrieving, and managing raw uploaded files
(e.g., PDFs, CSVs, Images) across various backends (S3/MinIO, Local Filesystem, Mock).
"""

from abc import ABC, abstractmethod


class StorageError(Exception):
    """Base exception for all storage backend operations."""

    pass


class StorageFileNotFoundError(StorageError):
    """Raised when an object key is not found in the storage backend."""

    pass


class StorageBackend(ABC):
    """Interface abstraction for object storage providers.

    Decouples application business logic from specific cloud storage vendors.
    PostgreSQL stores object keys and metadata; actual binary payloads are stored here.
    """

    @abstractmethod
    async def upload_file(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Uploads binary data to the storage backend.

        Args:
            key: The unique storage path/key (e.g. 'workspaces/{ws_id}/{filename}').
            data: Raw binary content to store.
            content_type: MIME type of the file.

        Returns:
            The storage key referencing the persisted object.

        Raises:
            StorageError: If the upload operation fails.
        """
        pass

    @abstractmethod
    async def download_file(self, key: str) -> bytes:
        """Downloads raw binary data from the storage backend.

        Args:
            key: The storage key identifying the object.

        Returns:
            Bytes representing the file contents.

        Raises:
            StorageFileNotFoundError: If the object key does not exist.
            StorageError: If download fails.
        """
        pass

    @abstractmethod
    async def delete_file(self, key: str) -> bool:
        """Deletes an object from the storage backend.

        Args:
            key: The storage key to delete.

        Returns:
            True if the object was deleted or already absent.

        Raises:
            StorageError: If deletion encounters an unexpected failure.
        """
        pass

    @abstractmethod
    async def file_exists(self, key: str) -> bool:
        """Checks whether an object exists at the specified key.

        Args:
            key: The storage key to verify.

        Returns:
            True if the object exists, False otherwise.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Checks whether the storage backend is reachable and healthy.

        Returns:
            True if connected and operational, False otherwise.
        """
        pass
