"""Answer evaluators isolating model-based judges behind an explicit abstraction."""

import json
import re
from abc import ABC, abstractmethod

from app.providers.llm.base import LLMProvider
from app.schemas.llm import CompletionRequest


class AnswerEvaluationResult:
    def __init__(
        self,
        answer_relevance: float,
        groundedness: float,
        citation_correctness: float,
        reasoning: str = "",
        is_model_based: bool = False,
    ) -> None:
        self.answer_relevance = answer_relevance
        self.groundedness = groundedness
        self.citation_correctness = citation_correctness
        self.reasoning = reasoning
        self.is_model_based = is_model_based


class BaseAnswerEvaluator(ABC):
    """Abstract interface for answer quality and groundedness evaluators."""

    @abstractmethod
    async def evaluate_answer(
        self,
        query: str,
        answer: str,
        context_texts: list[str],
        expected_answer: str | None = None,
        citations: list[str] | None = None,
    ) -> AnswerEvaluationResult:
        pass


class DeterministicAnswerEvaluator(BaseAnswerEvaluator):
    """Deterministic, rule-based evaluator computing lexical overlap and keyword coverage.

    Does NOT treat LLM output as ground truth; provides zero-shot reproducible baseline.
    """

    async def evaluate_answer(
        self,
        query: str,
        answer: str,
        context_texts: list[str],
        expected_answer: str | None = None,
        citations: list[str] | None = None,
    ) -> AnswerEvaluationResult:
        if not answer.strip():
            return AnswerEvaluationResult(
                0.0, 0.0, 0.0, reasoning="Empty answer", is_model_based=False
            )

        clean_ans = answer.lower()
        clean_ctx = " ".join(c.lower() for c in context_texts)

        # 1. Answer Groundedness: fraction of significant answer words supported by context
        ans_words = set(re.findall(r"\b\w{4,}\b", clean_ans))
        if not ans_words:
            groundedness = 1.0
        else:
            supported = sum(1 for w in ans_words if w in clean_ctx)
            groundedness = round(supported / len(ans_words), 4)

        # 2. Answer Relevance: overlap with query keywords or expected answer
        if expected_answer:
            exp_words = set(re.findall(r"\b\w{4,}\b", expected_answer.lower()))
            if exp_words:
                matched_exp = sum(1 for w in exp_words if w in clean_ans)
                relevance = round(matched_exp / len(exp_words), 4)
            else:
                relevance = 1.0
        else:
            q_words = set(re.findall(r"\b\w{4,}\b", query.lower()))
            if q_words:
                matched_q = sum(1 for w in q_words if w in clean_ans)
                relevance = round(matched_q / len(q_words), 4)
            else:
                relevance = 0.5

        # 3. Citation correctness
        cit_score = 1.0 if (citations and len(citations) > 0) else 0.5

        return AnswerEvaluationResult(
            answer_relevance=relevance,
            groundedness=groundedness,
            citation_correctness=cit_score,
            reasoning="Computed via deterministic lexical overlap against context and references.",
            is_model_based=False,
        )


class LLMAssistedAnswerEvaluator(BaseAnswerEvaluator):
    """Model-assisted judge evaluating groundedness and relevance.

    Note: Isolated behind abstraction; LLM judge score is treated as an auxiliary heuristic,
    never as authoritative ground truth.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    async def evaluate_answer(
        self,
        query: str,
        answer: str,
        context_texts: list[str],
        expected_answer: str | None = None,
        citations: list[str] | None = None,
    ) -> AnswerEvaluationResult:
        prompt = (
            "You are an automated evaluation judge. Evaluate the generated answer "
            "based ONLY on the provided context.\n\n"
            f"Context:\n{' '.join(context_texts)[:4000]}\n\n"
            f"User Query:\n{query}\n\n"
            f"Generated Answer:\n{answer}\n\n"
            f"Reference Answer:\n{expected_answer or 'N/A'}\n\n"
            "Respond strictly with a JSON object:\n"
            "{\n"
            '  "answer_relevance": <float between 0.0 and 1.0>,\n'
            '  "groundedness": <float between 0.0 and 1.0>,\n'
            '  "citation_correctness": <float between 0.0 and 1.0>,\n'
            '  "reasoning": "<concise explanation>"\n'
            "}\n"
        )
        req = CompletionRequest(
            prompt=prompt,
            temperature=0.0,
            max_tokens=300,
        )
        try:
            resp = await self.llm_provider.generate_text(req)
            clean_text = resp.text.strip()
            # Extract JSON block if markdown fenced
            match = re.search(r"\{.*?\}", clean_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return AnswerEvaluationResult(
                    answer_relevance=float(data.get("answer_relevance", 0.5)),
                    groundedness=float(data.get("groundedness", 0.5)),
                    citation_correctness=float(data.get("citation_correctness", 0.5)),
                    reasoning=str(data.get("reasoning", "")),
                    is_model_based=True,
                )
        except Exception:
            pass

        # Fallback to deterministic on judge failure
        fallback = DeterministicAnswerEvaluator()
        return await fallback.evaluate_answer(
            query, answer, context_texts, expected_answer, citations
        )
