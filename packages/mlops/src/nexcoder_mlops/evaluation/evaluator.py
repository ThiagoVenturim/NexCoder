"""Evaluation pipeline for fine-tuned models: metrics, regression testing, and LLM judge integration."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from nexcoder_serving.eval.rag_eval import LLMJudge
from pydantic import BaseModel, Field

from nexcoder_mlops.dataset.builder import DataSample


class SampleEvaluation(BaseModel):
    """Detailed score for an individual test sample."""

    instruction: str
    ground_truth: str
    prediction: str
    exact_match: bool
    token_overlap_f1: float
    judge_score: float | None = None
    judge_reasoning: str = ""


class EvaluationReport(BaseModel):
    """Aggregated evaluation metrics and scorecard for a trained model."""

    model_name_or_path: str
    dataset_version: str = ""
    total_samples: int
    exact_match_rate: float
    avg_token_f1: float
    perplexity: float | None = None
    judge_avg_score: float | None = None
    samples_evaluated: list[SampleEvaluation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_markdown(self) -> str:
        """Render evaluation scorecard as markdown table."""
        judge_line = f"- **LLM Judge Score**: {self.judge_avg_score:.2f} / 5.0\n" if self.judge_avg_score else ""
        ppl_line = f"- **Perplexity**: {self.perplexity:.2f}\n" if self.perplexity else ""
        return (
            f"## Evaluation Report: {self.model_name_or_path}\n\n"
            f"- **Dataset Version**: `{self.dataset_version or 'N/A'}`\n"
            f"- **Evaluated Samples**: {self.total_samples}\n"
            f"- **Exact Match Rate**: {self.exact_match_rate * 100:.1f}%\n"
            f"- **Token Overlap F1**: {self.avg_token_f1:.3f}\n"
            f"{ppl_line}"
            f"{judge_line}\n"
            f"### Sample Details (First 5)\n"
            "| Instruction | Ground Truth | Prediction | Match | F1 |\n"
            "| :--- | :--- | :--- | :--- | :--- |\n"
            + "\n".join(
                f"| {s.instruction[:20]}... | {s.ground_truth[:20]}... | "
                f"{s.prediction[:20]}... | {'Yes' if s.exact_match else 'No'} | {s.token_overlap_f1:.2f} |"
                for s in self.samples_evaluated[:5]
            )
            + "\n"
        )


class ModelEvaluator:
    """Evaluates fine-tuned outputs against test benchmarks and optional LLM judge."""

    def __init__(self, judge: LLMJudge | None = None) -> None:
        self.judge = judge

    @staticmethod
    def _compute_token_f1(prediction: str, ground_truth: str) -> float:
        """Compute token-level precision, recall, and F1 overlap."""
        pred_tokens = set(prediction.lower().split())
        gt_tokens = set(ground_truth.lower().split())
        if not pred_tokens or not gt_tokens:
            return 1.0 if pred_tokens == gt_tokens else 0.0

        common = pred_tokens.intersection(gt_tokens)
        if not common:
            return 0.0

        precision = len(common) / len(pred_tokens)
        recall = len(common) / len(gt_tokens)
        return 2.0 * (precision * recall) / (precision + recall)

    def evaluate_predictions(
        self,
        samples: list[DataSample],
        predictions: list[str],
        model_name: str = "fine-tuned-model",
        dataset_version: str = "",
        val_loss: float | None = None,
    ) -> EvaluationReport:
        """Compute offline metrics and optional judge ratings across sample pairs."""
        if len(samples) != len(predictions):
            raise ValueError(f"Mismatch between samples ({len(samples)}) and predictions ({len(predictions)})")

        evaluated: list[SampleEvaluation] = []
        matches = 0
        total_f1 = 0.0
        judge_scores: list[float] = []

        for sample, pred in zip(samples, predictions, strict=False):
            is_match = sample.output.strip() == pred.strip()
            if is_match:
                matches += 1

            f1 = self._compute_token_f1(pred, sample.output)
            total_f1 += f1

            judge_score = None
            judge_reason = ""
            if self.judge:
                # Reusing LLMJudge from nexcoder-serving
                sample_res = self.judge.evaluate_faithfulness(
                    question=sample.instruction,
                    context=sample.input_text or sample.instruction,
                    answer=pred,
                )
                judge_score = sample_res.score
                judge_reason = sample_res.reasoning
                judge_scores.append(judge_score)

            evaluated.append(
                SampleEvaluation(
                    instruction=sample.instruction,
                    ground_truth=sample.output,
                    prediction=pred,
                    exact_match=is_match,
                    token_overlap_f1=round(f1, 4),
                    judge_score=judge_score,
                    judge_reasoning=judge_reason,
                )
            )

        n = len(samples) if samples else 1
        em_rate = matches / n
        avg_f1 = total_f1 / n
        avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else None

        # Perplexity estimation from validation cross-entropy loss if provided
        perplexity = math.exp(val_loss) if val_loss is not None and val_loss < 20 else None

        return EvaluationReport(
            model_name_or_path=model_name,
            dataset_version=dataset_version,
            total_samples=len(samples),
            exact_match_rate=round(em_rate, 4),
            avg_token_f1=round(avg_f1, 4),
            perplexity=round(perplexity, 4) if perplexity is not None else None,
            judge_avg_score=round(avg_judge, 2) if avg_judge is not None else None,
            samples_evaluated=evaluated,
        )

    def compare_models(
        self,
        baseline_report: EvaluationReport,
        finetuned_report: EvaluationReport,
    ) -> dict[str, Any]:
        """Perform comparison and check for regressions."""
        f1_delta = finetuned_report.avg_token_f1 - baseline_report.avg_token_f1
        em_delta = finetuned_report.exact_match_rate - baseline_report.exact_match_rate
        has_regressed = f1_delta < -0.05 or em_delta < -0.05

        return {
            "baseline_model": baseline_report.model_name_or_path,
            "finetuned_model": finetuned_report.model_name_or_path,
            "f1_delta": round(f1_delta, 4),
            "exact_match_delta": round(em_delta, 4),
            "improved": f1_delta > 0 or em_delta > 0,
            "has_regressed": has_regressed,
        }
