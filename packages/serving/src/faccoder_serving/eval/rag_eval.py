"""RAG evaluation engine and LLM judge for faithfulness, relevance, precision, and recall."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class EvaluationSample(BaseModel):
    question: str
    contexts: list[str] = Field(default_factory=list)
    answer: str
    ground_truth: str | None = None


class EvaluationResult(BaseModel):
    sample: EvaluationSample
    faithfulness: float
    answer_relevance: float
    context_precision: float
    context_recall: float
    overall_score: float
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class AggregatedEvalResult(BaseModel):
    total_samples: int
    mean_faithfulness: float
    mean_answer_relevance: float
    mean_context_precision: float
    mean_context_recall: float
    mean_overall_score: float
    pass_rate: float
    results: list[EvaluationResult] = Field(default_factory=list)


def _tokenize(text: str) -> set[str]:
    """Extract lowercased alphanumeric tokens from text."""
    words = re.findall(r"\b[a-zA-Z0-9_\u00C0-\u00FF]+\b", text.lower())
    stopwords = {
        "o", "a", "os", "as", "um", "uma", "de", "do", "da", "em", "no", "na",
        "para", "por", "com", "que", "e", "the", "an", "in", "on", "of", "to", "for", "with", "is", "are"
    }
    return {w for w in words if len(w) > 2 and w not in stopwords}


class LLMJudge:
    """Evaluates RAG components either using an LLM or offline deterministic heuristics."""

    def __init__(self, model: Any = None) -> None:
        self.model = model

    def evaluate_faithfulness(self, contexts: list[str], answer: str) -> tuple[float, str]:
        """Faithfulness: whether the answer is grounded in the retrieved contexts."""
        if not contexts:
            return 0.0, "No contexts provided."
        if not answer.strip():
            return 0.0, "Empty answer."

        full_context = " ".join(contexts).lower()
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", answer) if s.strip()]
        if not sentences:
            return 1.0, "Answer has no statements."

        supported = 0
        for sent in sentences:
            tokens = _tokenize(sent)
            if not tokens:
                supported += 1
                continue
            matched = sum(1 for t in tokens if t in full_context)
            ratio = matched / len(tokens)
            if ratio >= 0.5:
                supported += 1

        score = round(supported / len(sentences), 4)
        return score, f"{supported}/{len(sentences)} sentences grounded in context."

    def evaluate_answer_relevance(self, question: str, answer: str) -> tuple[float, str]:
        """Answer relevance: whether the answer addresses the question."""
        q_tokens = _tokenize(question)
        a_tokens = _tokenize(answer)
        if not q_tokens:
            return 1.0, "Question has no keywords."
        if not a_tokens:
            return 0.0, "Answer has no keywords."

        overlap = q_tokens.intersection(a_tokens)
        score = min(1.0, round((len(overlap) / len(q_tokens)) * 1.5, 4))
        return score, f"{len(overlap)} question tokens addressed in answer."

    def evaluate_context_precision(
        self,
        question: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> tuple[float, str]:
        """Context precision: whether higher-ranked contexts are more relevant."""
        if not contexts:
            return 0.0, "No contexts provided."

        target_text = ground_truth or question
        target_tokens = _tokenize(target_text)
        if not target_tokens:
            return 1.0, "Target has no tokens."

        precisions: list[float] = []
        relevant_count = 0
        for i, ctx in enumerate(contexts):
            ctx_tokens = _tokenize(ctx)
            overlap = target_tokens.intersection(ctx_tokens)
            is_relevant = len(overlap) / len(target_tokens) >= 0.2
            if is_relevant:
                relevant_count += 1
                precisions.append(relevant_count / (i + 1))

        if not precisions:
            return 0.0, "No retrieved contexts relevant to target."

        score = round(sum(precisions) / len(precisions), 4)
        return score, f"Mean average precision over {len(contexts)} contexts."

    def evaluate_context_recall(self, contexts: list[str], ground_truth: str | None = None) -> tuple[float, str]:
        """Context recall: whether the retrieved context contains all ground truth facts."""
        if not ground_truth:
            return 1.0, "No ground truth specified for recall."
        if not contexts:
            return 0.0, "No contexts provided."

        gt_tokens = _tokenize(ground_truth)
        if not gt_tokens:
            return 1.0, "Ground truth has no tokens."

        full_context = " ".join(contexts).lower()
        matched = sum(1 for t in gt_tokens if t in full_context)
        score = round(matched / len(gt_tokens), 4)
        return score, f"{matched}/{len(gt_tokens)} ground truth tokens recalled in contexts."


class RagEvaluator:
    """Orchestrates end-to-end evaluation of RAG responses against quality thresholds."""

    def __init__(
        self,
        judge: LLMJudge | None = None,
        faithfulness_threshold: float = 0.70,
        relevance_threshold: float = 0.70,
        precision_threshold: float = 0.60,
        recall_threshold: float = 0.60,
    ) -> None:
        self.judge = judge or LLMJudge()
        self.faithfulness_threshold = faithfulness_threshold
        self.relevance_threshold = relevance_threshold
        self.precision_threshold = precision_threshold
        self.recall_threshold = recall_threshold

    def evaluate_sample(self, sample: EvaluationSample) -> EvaluationResult:
        """Evaluate a single RAG sample across all 4 metrics."""
        faith, faith_reason = self.judge.evaluate_faithfulness(sample.contexts, sample.answer)
        relev, relev_reason = self.judge.evaluate_answer_relevance(sample.question, sample.answer)
        prec, prec_reason = self.judge.evaluate_context_precision(sample.question, sample.contexts, sample.ground_truth)
        rec, rec_reason = self.judge.evaluate_context_recall(sample.contexts, sample.ground_truth)

        overall = round((faith + relev + prec + rec) / 4.0, 4)
        passed = (
            faith >= self.faithfulness_threshold
            and relev >= self.relevance_threshold
            and prec >= self.precision_threshold
            and rec >= self.recall_threshold
        )

        return EvaluationResult(
            sample=sample,
            faithfulness=faith,
            answer_relevance=relev,
            context_precision=prec,
            context_recall=rec,
            overall_score=overall,
            passed=passed,
            details={
                "faithfulness_reason": faith_reason,
                "relevance_reason": relev_reason,
                "precision_reason": prec_reason,
                "recall_reason": rec_reason,
            },
        )

    def evaluate_dataset(self, samples: list[EvaluationSample]) -> AggregatedEvalResult:
        """Run batch evaluation and calculate aggregated statistics."""
        if not samples:
            return AggregatedEvalResult(
                total_samples=0,
                mean_faithfulness=0.0,
                mean_answer_relevance=0.0,
                mean_context_precision=0.0,
                mean_context_recall=0.0,
                mean_overall_score=0.0,
                pass_rate=0.0,
                results=[],
            )

        results = [self.evaluate_sample(s) for s in samples]
        n = len(results)
        passed_count = sum(1 for r in results if r.passed)

        return AggregatedEvalResult(
            total_samples=n,
            mean_faithfulness=round(sum(r.faithfulness for r in results) / n, 4),
            mean_answer_relevance=round(sum(r.answer_relevance for r in results) / n, 4),
            mean_context_precision=round(sum(r.context_precision for r in results) / n, 4),
            mean_context_recall=round(sum(r.context_recall for r in results) / n, 4),
            mean_overall_score=round(sum(r.overall_score for r in results) / n, 4),
            pass_rate=round(passed_count / n, 4),
            results=results,
        )
