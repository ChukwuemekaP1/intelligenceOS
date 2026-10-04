"""Object storage abstraction package for IntelligenceOS."""

from app.storage.base import StorageBackend, StorageError, StorageFileNotFoundError
from app.storage.factory import get_storage_backend, reset_storage_backend
from app.storage.local import LocalStorageBackend
from app.storage.mock import MockStorageBackend
from app.storage.s3 import S3StorageBackend

__all__ = [
    "StorageBackend",
    "StorageError",
    "StorageFileNotFoundError",
    "S3StorageBackend",
    "LocalStorageBackend",
    "MockStorageBackend",
    "get_storage_backend",
    "reset_storage_backend",
]
