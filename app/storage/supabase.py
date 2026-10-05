"""Supabase Storage Backend implementation.

Provides production object storage for uploaded knowledge files using Supabase Storage buckets.
Communicates directly with the Supabase Storage REST API using asynchronous HTTP requests (httpx).
"""

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.storage.base import StorageBackend, StorageError, StorageFileNotFoundError

logger = get_logger("app.storage.supabase")


class SupabaseStorageBackend(StorageBackend):
    """Supabase Storage implementation using native asynchronous HTTP client."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bucket_name = self.settings.SUPABASE_STORAGE_BUCKET

        if not self.settings.SUPABASE_URL:
            raise StorageError("SUPABASE_URL must be configured for SupabaseStorageBackend")

        self.base_url = self.settings.SUPABASE_URL.rstrip("/")
        self.service_role_key = (
            self.settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()
            if self.settings.SUPABASE_SERVICE_ROLE_KEY
            else ""
        )

        if not self.service_role_key:
            raise StorageError(
                "SUPABASE_SERVICE_ROLE_KEY must be configured for SupabaseStorageBackend"
            )

        self._headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
        }

    def _get_client(self, timeout: float = 15.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout)

    def _sanitize_key(self, key: str) -> str:
        clean = key.strip().lstrip("/")
        if ".." in clean.split("/"):
            raise StorageError(f"Directory traversal detected in storage key: '{key}'")
        return clean

    async def upload_file(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Uploads raw binary bytes to the Supabase Storage bucket."""
        clean_key = self._sanitize_key(key)
        url = f"{self.base_url}/storage/v1/object/{self.bucket_name}/{clean_key}"

        upload_headers = {
            **self._headers,
            "Content-Type": content_type,
            "x-upsert": "true",
        }

        try:
            async with self._get_client(timeout=30.0) as client:
                response = await client.post(url, content=data, headers=upload_headers)

            if response.status_code in (200, 201):
                logger.info(
                    f"Successfully uploaded '{clean_key}' ({len(data)} bytes) "
                    f"to bucket '{self.bucket_name}'"
                )
                return clean_key

            logger.error(
                f"Failed to upload '{clean_key}' to Supabase Storage: "
                f"HTTP {response.status_code} - {response.text}"
            )
            raise StorageError(
                f"Supabase upload failed: HTTP {response.status_code} - {response.text}"
            )
        except StorageError:
            raise
        except Exception as exc:
            logger.error(f"Unexpected error uploading '{clean_key}' to Supabase Storage: {exc}")
            raise StorageError(f"Supabase Storage upload error: {exc}") from exc

    async def download_file(self, key: str) -> bytes:
        """Downloads raw bytes for the specified key from the Supabase bucket."""
        clean_key = self._sanitize_key(key)
        url = f"{self.base_url}/storage/v1/object/authenticated/{self.bucket_name}/{clean_key}"

        try:
            async with self._get_client(timeout=30.0) as client:
                response = await client.get(url, headers=self._headers)

            if response.status_code == 200:
                return response.content

            if response.status_code in (404, 400):
                # Supabase returns 400 or 404 when object is not found
                err_text = response.text.lower()
                is_missing = (
                    "not found" in err_text
                    or "not_found" in err_text
                    or response.status_code == 404
                )
                if is_missing:
                    raise StorageFileNotFoundError(
                        f"Object '{clean_key}' not found in Supabase bucket '{self.bucket_name}'."
                    )

            logger.error(
                f"Failed to download '{clean_key}' from Supabase Storage: "
                f"HTTP {response.status_code} - {response.text}"
            )
            raise StorageError(
                f"Supabase download failed: HTTP {response.status_code} - {response.text}"
            )
        except (StorageFileNotFoundError, StorageError):
            raise
        except Exception as exc:
            logger.error(f"Unexpected error downloading '{clean_key}' from Supabase Storage: {exc}")
            raise StorageError(f"Supabase Storage download error: {exc}") from exc

    async def delete_file(self, key: str) -> bool:
        """Deletes an object from the Supabase Storage bucket."""
        clean_key = self._sanitize_key(key)
        url = f"{self.base_url}/storage/v1/object/{self.bucket_name}"

        try:
            async with self._get_client(timeout=15.0) as client:
                response = await client.request(
                    "DELETE",
                    url,
                    json={"prefixes": [clean_key]},
                    headers=self._headers,
                )

            if response.status_code in (200, 204):
                logger.info(f"Successfully deleted '{clean_key}' from bucket '{self.bucket_name}'")
                return True

            logger.warning(
                f"Delete response for '{clean_key}' from Supabase Storage: "
                f"HTTP {response.status_code} - {response.text}"
            )
            return True
        except Exception as exc:
            logger.error(f"Failed deleting '{clean_key}' from Supabase Storage: {exc}")
            raise StorageError(f"Supabase delete error: {exc}") from exc

    async def file_exists(self, key: str) -> bool:
        """Checks if an object exists in the Supabase Storage bucket."""
        clean_key = self._sanitize_key(key)
        url = f"{self.base_url}/storage/v1/object/info/authenticated/{self.bucket_name}/{clean_key}"

        try:
            async with self._get_client(timeout=10.0) as client:
                response = await client.get(url, headers=self._headers)
            return response.status_code == 200
        except Exception as exc:
            logger.warning(f"Error checking file existence for '{clean_key}': {exc}")
            return False

    async def health_check(self) -> bool:
        """Pings Supabase Storage API to verify bucket reachability and credentials."""
        url = f"{self.base_url}/storage/v1/bucket/{self.bucket_name}"
        try:
            async with self._get_client(timeout=5.0) as client:
                response = await client.get(url, headers=self._headers)
            return response.status_code == 200
        except Exception as exc:
            logger.warning(f"Supabase Storage health check failed: {exc}")
            return False

    async def create_signed_url(self, key: str, expires_in: int = 3600) -> str:
        """Generates a secure temporary signed URL for client download."""
        clean_key = self._sanitize_key(key)
        url = f"{self.base_url}/storage/v1/object/sign/{self.bucket_name}/{clean_key}"

        try:
            async with self._get_client(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json={"expiresIn": expires_in},
                    headers=self._headers,
                )

            if response.status_code == 200:
                data = response.json()
                signed_path = data.get("signedURL") or data.get("signedUrl")
                if signed_path:
                    if signed_path.startswith("http"):
                        return signed_path
                    return f"{self.base_url}/storage/v1{signed_path}"

            raise StorageError(f"Failed creating signed URL: {response.text}")
        except Exception as exc:
            logger.error(f"Failed generating signed URL for '{clean_key}': {exc}")
            raise StorageError(f"Supabase signed URL error: {exc}") from exc
