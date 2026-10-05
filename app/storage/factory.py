"""Factory for creating and resolving the configured object storage backend."""

from app.core.config import Settings, get_settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend
from app.storage.mock import MockStorageBackend
from app.storage.supabase import SupabaseStorageBackend

_storage_instance: StorageBackend | None = None


def get_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """Returns the singleton instance of the configured StorageBackend.

    Selects between:
      - 'supabase': SupabaseStorageBackend (Supabase Storage buckets)
      - 'local': LocalStorageBackend (Local filesystem)
      - 'mock': MockStorageBackend (In-memory test store)
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    if settings is None:
        settings = get_settings()

    if settings.STORAGE_BACKEND == "mock":
        _storage_instance = MockStorageBackend()
    elif settings.STORAGE_BACKEND == "local":
        _storage_instance = LocalStorageBackend(base_dir=settings.LOCAL_STORAGE_DIR)
    else:
        _storage_instance = SupabaseStorageBackend(settings=settings)

    return _storage_instance


def reset_storage_backend() -> None:
    """Resets the singleton storage instance (used in test isolation)."""
    global _storage_instance
    _storage_instance = None
