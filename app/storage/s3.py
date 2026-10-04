"""S3-Compatible Object Storage Backend (AWS S3 & MinIO).

Provides production and local Docker MinIO storage integration for uploaded knowledge files.
All synchronous boto3 calls are dispatched to threadpool executors to ensure non-blocking
async execution within the FastAPI and worker event loops.
"""

import asyncio
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.storage.base import StorageBackend, StorageError, StorageFileNotFoundError

logger = get_logger("app.storage.s3")


class S3StorageBackend(StorageBackend):
    """S3-compatible storage implementation supporting MinIO and AWS S3."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bucket_name = self.settings.S3_BUCKET_NAME

        secret_key_val = (
            self.settings.S3_SECRET_KEY.get_secret_value() if self.settings.S3_SECRET_KEY else None
        )

        # Configure boto3 client with standard retry and connection timeout parameters
        boto_config = Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=3,
            read_timeout=10,
        )

        self._s3_client = boto3.client(
            "s3",
            endpoint_url=self.settings.S3_ENDPOINT_URL,
            aws_access_key_id=self.settings.S3_ACCESS_KEY,
            aws_secret_access_key=secret_key_val,
            region_name=self.settings.S3_REGION,
            config=boto_config,
        )

    def _ensure_bucket_sync(self) -> None:
        """Synchronously checks if bucket exists, creating it if absent."""
        try:
            self._s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                logger.info(f"Bucket '{self.bucket_name}' not found; creating it...")
                try:
                    self._s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Bucket '{self.bucket_name}' successfully created.")
                except ClientError as create_err:
                    logger.error(f"Failed to create S3 bucket '{self.bucket_name}': {create_err}")
                    raise StorageError(
                        f"Could not create storage bucket: {create_err}"
                    ) from create_err
            else:
                logger.warning(f"Error checking bucket existence: {exc}")

    async def ensure_bucket(self) -> None:
        """Asynchronously guarantees the storage bucket is provisioned."""
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def upload_file(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Uploads raw binary bytes to the S3 bucket."""
        clean_key = key.lstrip("/")

        def _upload() -> None:
            self._s3_client.put_object(
                Bucket=self.bucket_name,
                Key=clean_key,
                Body=data,
                ContentType=content_type,
            )

        try:
            await asyncio.to_thread(_upload)
            return clean_key
        except Exception as e:
            logger.error(f"Failed to upload object to S3 '{clean_key}': {e}")
            raise StorageError(f"S3 upload failed: {e}") from e

    async def download_file(self, key: str) -> bytes:
        """Downloads raw bytes for the specified key from S3."""
        clean_key = key.lstrip("/")

        def _download() -> bytes:
            try:
                response: dict[str, Any] = self._s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=clean_key,
                )
                return response["Body"].read()
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code")
                if error_code in ("NoSuchKey", "404"):
                    raise StorageFileNotFoundError(
                        f"Object '{clean_key}' not found in S3."
                    ) from exc
                raise StorageError(f"Failed downloading '{clean_key}' from S3: {exc}") from exc

        return await asyncio.to_thread(_download)

    async def delete_file(self, key: str) -> bool:
        """Deletes an object from the S3 bucket."""
        clean_key = key.lstrip("/")

        def _delete() -> None:
            try:
                self._s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=clean_key,
                )
            except Exception as exc:
                raise StorageError(f"Failed deleting '{clean_key}' from S3: {exc}") from exc

        await asyncio.to_thread(_delete)
        return True

    async def file_exists(self, key: str) -> bool:
        """Checks if an object exists in S3 via HEAD request."""
        clean_key = key.lstrip("/")

        def _exists() -> bool:
            try:
                self._s3_client.head_object(Bucket=self.bucket_name, Key=clean_key)
                return True
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code")
                if error_code in ("404", "NoSuchKey"):
                    return False
                return False

        return await asyncio.to_thread(_exists)

    async def health_check(self) -> bool:
        """Pings S3 / MinIO to verify network and credentials validity."""

        def _check() -> bool:
            try:
                self._s3_client.head_bucket(Bucket=self.bucket_name)
                return True
            except Exception:
                try:
                    self._s3_client.list_buckets()
                    return True
                except Exception:
                    return False

        return await asyncio.to_thread(_check)
