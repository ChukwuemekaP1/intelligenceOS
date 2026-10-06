import math
import uuid

from app.vectorstore.base import VectorStore, VectorStoreError
from app.vectorstore.models import SearchResult, VectorPoint


class MockVectorStore(VectorStore):
    """In-memory vector store that enforces strict workspace isolation.

    Stores points in a dictionary organized by workspace_id:
    _storage[str(workspace_id)][str(point_id)] = VectorPoint
    """

    def __init__(self) -> None:
        self._storage: dict[str, dict[str, VectorPoint]] = {}
        self._is_healthy = True

    def set_healthy(self, healthy: bool) -> None:
        """Simulates vector store outages in test suites."""
        self._is_healthy = healthy

    async def ensure_collection(self) -> None:
        """No-op for in-memory mock."""
        pass

    async def upsert_points(
        self,
        workspace_id: uuid.UUID,
        points: list[VectorPoint],
    ) -> None:
        ws_key = str(workspace_id)
        if ws_key not in self._storage:
            self._storage[ws_key] = {}

        for pt in points:
            # Enforce that every point's payload matches the targeted workspace_id
            payload_ws = pt.payload.get("workspace_id")
            if payload_ws and str(payload_ws) != ws_key:
                raise VectorStoreError(
                    f"Workspace isolation violation: Point {pt.id} payload workspace "
                    f"'{payload_ws}' does not match operation workspace '{ws_key}'"
                )
            self._storage[ws_key][str(pt.id)] = pt

    async def delete_by_document_version(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> None:
        ws_key = str(workspace_id)
        ver_str = str(document_version_id)
        if ws_key in self._storage:
            to_delete = [
                pt_id
                for pt_id, pt in self._storage[ws_key].items()
                if pt.payload.get("document_version_id") == ver_str
            ]
            for pt_id in to_delete:
                del self._storage[ws_key][pt_id]

    async def delete_by_source(
        self,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> None:
        ws_key = str(workspace_id)
        src_str = str(source_id)
        if ws_key in self._storage:
            to_delete = [
                pt_id
                for pt_id, pt in self._storage[ws_key].items()
                if pt.payload.get("source_id") == src_str
            ]
            for pt_id in to_delete:
                del self._storage[ws_key][pt_id]

    async def count_points(self, workspace_id: uuid.UUID) -> int:
        ws_key = str(workspace_id)
        return len(self._storage.get(ws_key, {}))

    async def search(
        self,
        workspace_id: uuid.UUID,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        source_ids: list[uuid.UUID] | None = None,
    ) -> list[SearchResult]:
        if not self._is_healthy:
            raise VectorStoreError("Mock vector store is simulated unhealthy.")

        ws_key = str(workspace_id)
        points_map = self._storage.get(ws_key, {})
        if not points_map:
            return []

        # Optional source_ids filter
        allowed_source_ids: set[str] | None = None
        if source_ids:
            allowed_source_ids = {str(sid) for sid in source_ids}

        scored_points: list[SearchResult] = []
        for pt in points_map.values():
            # Apply source_ids filter if specified
            if allowed_source_ids is not None:
                pt_source = pt.payload.get("source_id")
                if not pt_source or str(pt_source) not in allowed_source_ids:
                    continue

            # Calculate cosine similarity
            dot = sum(a * b for a, b in zip(query_vector, pt.vector, strict=False))
            norm_a = math.sqrt(sum(a * a for a in query_vector)) or 1.0
            norm_b = math.sqrt(sum(b * b for b in pt.vector)) or 1.0
            score = dot / (norm_a * norm_b)

            if score_threshold is not None and score < score_threshold:
                continue

            scored_points.append(
                SearchResult(
                    id=pt.id,
                    score=round(score, 6),
                    payload=pt.payload,
                    vector=pt.vector,
                )
            )

        scored_points.sort(key=lambda x: x.score, reverse=True)
        return scored_points[:limit]

    async def health_check(self) -> bool:
        return self._is_healthy

    def get_points(self, workspace_id: uuid.UUID) -> list[VectorPoint]:
        """Test helper to inspect persisted points within a specific workspace."""
        ws_key = str(workspace_id)
        return list(self._storage.get(ws_key, {}).values())
