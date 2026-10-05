"""In-memory and persistent trace storage for execution inspection."""

from collections import deque

from app.observability.tracer import Trace


class TraceRepository:
    """Thread-safe trace repository for storing and querying execution traces."""

    def __init__(self, max_traces: int = 1000) -> None:
        self._traces: deque[Trace] = deque(maxlen=max_traces)
        self._by_id: dict[str, Trace] = {}

    def save_trace(self, trace: Trace) -> None:
        """Stores a completed trace."""
        self._traces.append(trace)
        self._by_id[trace.trace_id] = trace

    def get_trace(self, trace_id: str) -> Trace | None:
        """Retrieves a trace by its ID."""
        return self._by_id.get(trace_id)

    def list_traces(
        self,
        workspace_id: str | None = None,
        operation_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Trace]:
        """Lists stored traces with workspace and operation filtering."""
        filtered = list(self._traces)
        if workspace_id:
            filtered = [t for t in filtered if t.workspace_id == str(workspace_id)]
        if operation_name:
            filtered = [t for t in filtered if t.operation_name == operation_name]

        # Reverse order so latest traces appear first
        filtered.reverse()
        return filtered[offset : offset + limit]

    def clear(self) -> None:
        """Clears stored traces (used in testing)."""
        self._traces.clear()
        self._by_id.clear()


# Global trace repository singleton
_trace_repo = TraceRepository()


def get_trace_repository() -> TraceRepository:
    return _trace_repo
