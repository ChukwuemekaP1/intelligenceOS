"""Factory for instantiating the configured candidate reranker."""

from app.core.config import Settings, get_settings
from app.rag.reranking.base import BaseReranker
from app.rag.reranking.external import ExternalReranker
from app.rag.reranking.local import LocalReranker
from app.rag.reranking.passthrough import PassThroughReranker


def get_reranker(
    settings: Settings | None = None,
    enabled: bool | None = None,
) -> BaseReranker:
    """Returns the configured BaseReranker instance.

    Args:
        settings: Application settings instance.
        enabled: Optional runtime override to enable/disable reranking.
    """
    cfg = settings or get_settings()

    is_enabled = cfg.RAG_ENABLE_RERANKING if enabled is None else enabled
    if not is_enabled or cfg.RERANKER_TYPE == "none":
        return PassThroughReranker()

    if cfg.RERANKER_TYPE == "external":
        api_key = cfg.RERANKER_API_KEY.get_secret_value() if cfg.RERANKER_API_KEY else None
        return ExternalReranker(
            api_key=api_key,
            endpoint=cfg.RERANKER_ENDPOINT,
            model=cfg.RERANKER_MODEL,
        )

    return LocalReranker()
