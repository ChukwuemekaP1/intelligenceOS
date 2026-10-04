"""Local in-process reranker combining lexical density, exact phrase matching, and initial score."""

import re

from app.rag.reranking.base import BaseReranker
from app.rag.retrieval.lexical import STOPWORDS
from app.schemas.rag import RetrievedChunk


class LocalReranker(BaseReranker):
    """Refines candidate ranking using cross-feature lexical density and query term coverage."""

    def __init__(self, initial_score_weight: float = 0.35) -> None:
        self.initial_score_weight = initial_score_weight
        self.rerank_score_weight = 1.0 - initial_score_weight

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        clean_query = query.strip().lower()
        query_words = re.findall(r"\b[A-Za-z0-9_-]{2,}\b", clean_query)
        keywords = [w for w in query_words if w not in STOPWORDS]
        if not keywords:
            keywords = query_words

        scored: list[tuple[float, RetrievedChunk]] = []

        for candidate in candidates:
            content_lower = candidate.content.lower()
            source_lower = candidate.source_name.lower()
            words_in_chunk = max(len(content_lower.split()), 1)

            # 1. Exact query phrase match bonus
            exact_phrase_bonus = 0.0
            if len(clean_query) > 3 and clean_query in content_lower:
                exact_phrase_bonus = 0.4

            # 2. Term coverage ratio (fraction of keywords present)
            present_terms = sum(1 for kw in keywords if kw in content_lower)
            term_coverage = (present_terms / len(keywords)) if keywords else 0.0

            # 3. Term frequency density
            tf_count = sum(content_lower.count(kw) for kw in keywords)
            tf_density = min(tf_count / (words_in_chunk + 10.0) * 10.0, 1.0)

            # 4. Source name relevance bonus
            source_bonus = 0.0
            if any(kw in source_lower for kw in keywords):
                source_bonus = 0.15

            # Combine signals into normalized rerank score [0.0, 1.0]
            lexical_score = min(
                (term_coverage * 0.4)
                + (tf_density * 0.2)
                + exact_phrase_bonus
                + source_bonus,
                1.0,
            )

            # Blend with initial score
            blended_score = (
                (candidate.score * self.initial_score_weight)
                + (lexical_score * self.rerank_score_weight)
            )

            updated = candidate.model_copy(update={"score": round(blended_score, 4)})
            scored.append((blended_score, updated))

        # Sort descending by blended score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]
