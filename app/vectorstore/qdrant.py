"""Qdrant Vector Database implementation.

Integrates with Qdrant for storing and retrieving high-dimensional vector embeddings.
Enforces multi-tenant workspace isolation at the query and mutation boundary.
"""

import uuid

from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.vectorstore.base import VectorStore, VectorStoreError
from app.vectorstore.models import SearchResult, VectorPoint

logger = get_logger("app.vectorstore.qdrant")


class QdrantVectorStore(VectorStore):
    """Asynchronous vector storage adapter for Qdrant."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.collection_name = self.settings.QDRANT_COLLECTION

        api_key_val = (
            self.settings.QDRANT_API_KEY.get_secret_value()
            if self.settings.QDRANT_API_KEY
            else None
        )

        timeout_val = getattr(self.settings, "QDRANT_TIMEOUT", 15.0)

        if self.settings.QDRANT_URL:
            self._client = AsyncQdrantClient(
                url=self.settings.QDRANT_URL,
                api_key=api_key_val,
                timeout=timeout_val,
            )
        else:
            self._client = AsyncQdrantClient(
                host=self.settings.QDRANT_HOST,
                port=self.settings.QDRANT_PORT,
                api_key=api_key_val,
                timeout=timeout_val,
            )

    async def ensure_collection(self) -> None:
        """Provisions the collection and payload indexes if not already present."""
        try:
            exists = await self._client.collection_exists(self.collection_name)
            if not exists:
                logger.info(f"Creating Qdrant collection '{self.collection_name}'...")
                await self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.settings.EMBEDDING_DIMENSION,
                        distance=models.Distance.COSINE,
                    ),
                )

                # Provision keyword indexes for fast tenant and source filtering
                for field in ("workspace_id", "source_id", "document_version_id"):
                    try:
                        await self._client.create_payload_index(
                            collection_name=self.collection_name,
                            field_name=field,
                            field_schema=models.PayloadSchemaType.KEYWORD,
                        )
                    except Exception as idx_err:
                        logger.warning(f"Payload index creation for '{field}': {idx_err}")

                logger.info(f"Qdrant collection '{self.collection_name}' provisioned successfully.")
        except Exception as exc:
            logger.error(f"Failed to ensure Qdrant collection '{self.collection_name}': {exc}")
            raise VectorStoreError(f"Could not initialize Qdrant collection: {exc}") from exc

    async def upsert_points(
        self,
        workspace_id: uuid.UUID,
        points: list[VectorPoint],
    ) -> None:
        if not points:
            return

        ws_str = str(workspace_id)
        point_structs: list[models.PointStruct] = []

        for pt in points:
            # Enforce that every point strictly carries the operation workspace_id
            pt_ws = pt.payload.get("workspace_id")
            if pt_ws and str(pt_ws) != ws_str:
                raise VectorStoreError(
                    f"Cross-workspace vector violation: Point {pt.id} belongs to "
                    f"'{pt_ws}', but upsert requested for '{ws_str}'"
                )

            # Ensure workspace_id is explicitly set in payload
            payload = dict(pt.payload)
            payload["workspace_id"] = ws_str

            point_structs.append(
                models.PointStruct(
                    id=str(pt.id),
                    vector=pt.vector,
                    payload=payload,
                )
            )

        try:
            await self._client.upsert(
                collection_name=self.collection_name,
                points=point_structs,
            )
        except Exception as exc:
            logger.error(f"Failed upserting {len(points)} points to Qdrant: {exc}")
            raise VectorStoreError(f"Qdrant upsert failed: {exc}") from exc

    async def delete_by_document_version(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> None:
        # Enforce both workspace_id and document_version_id filters
        version_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=str(workspace_id)),
                ),
                models.FieldCondition(
                    key="document_version_id",
                    match=models.MatchValue(value=str(document_version_id)),
                ),
            ]
        )

        try:
            await self._client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=version_filter),
            )
        except Exception as exc:
            logger.error(
                f"Failed to delete points by document version {document_version_id}: {exc}"
            )
            raise VectorStoreError(f"Qdrant version deletion failed: {exc}") from exc

    async def delete_by_source(
        self,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> None:
        # Enforce both workspace_id and source_id filters
        source_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=str(workspace_id)),
                ),
                models.FieldCondition(
                    key="source_id",
                    match=models.MatchValue(value=str(source_id)),
                ),
            ]
        )

        try:
            await self._client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=source_filter),
            )
        except Exception as exc:
            logger.error(f"Failed to delete points by source {source_id}: {exc}")
            raise VectorStoreError(f"Qdrant source deletion failed: {exc}") from exc

    async def count_points(self, workspace_id: uuid.UUID) -> int:
        tenant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=str(workspace_id)),
                ),
            ]
        )
        try:
            result = await self._client.count(
                collection_name=self.collection_name,
                count_filter=tenant_filter,
                exact=True,
            )
            return result.count
        except Exception as exc:
            logger.error(f"Failed counting points for workspace {workspace_id}: {exc}")
            raise VectorStoreError(f"Qdrant count failed: {exc}") from exc

    async def search(
        self,
        workspace_id: uuid.UUID,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        ws_str = str(workspace_id)
        tenant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=ws_str),
                ),
            ]
        )
        try:
            response = await self._client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=tenant_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )

            results: list[SearchResult] = []
            for pt in response.points:
                try:
                    pt_id = uuid.UUID(str(pt.id))
                except ValueError:
                    continue

                results.append(
                    SearchResult(
                        id=pt_id,
                        score=float(pt.score),
                        payload=pt.payload or {},
                    )
                )
            return results
        except Exception as exc:
            logger.error(f"Failed searching Qdrant for workspace {workspace_id}: {exc}")
            raise VectorStoreError(f"Qdrant vector search failed: {exc}") from exc

    async def health_check(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            return False
