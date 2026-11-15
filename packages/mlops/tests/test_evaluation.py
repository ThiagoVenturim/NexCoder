"""Unit tests for evaluation metrics, scorecard generation, and regression detection."""

from __future__ import annotations

from nexcoder_mlops.dataset.builder import DataSample
from nexcoder_mlops.evaluation.evaluator import ModelEvaluator


def test_token_f1_and_exact_match() -> None:
    samples = [
        DataSample(instruction="Q1", output="def add(a, b): return a + b"),
        DataSample(instruction="Q2", output="def subtract(a, b): return a - b"),
    ]
    predictions = [
        "def add(a, b): return a + b",
        "def subtract(x, y): return x - y",
    ]

    evaluator = ModelEvaluator()
    report = evaluator.evaluate_predictions(
        samples=samples,
        predictions=predictions,
        model_name="test-model",
        val_loss=0.5,
    )

    assert report.total_samples == 2
    assert report.exact_match_rate == 0.5
    assert 0.0 < report.avg_token_f1 <= 1.0
    assert report.perplexity is not None
    assert "Evaluation Report: test-model" in report.to_markdown()


def test_model_comparison_and_regression() -> None:
    samples = [DataSample(instruction="Q", output="hello world")]
    evaluator = ModelEvaluator()

    base_rep = evaluator.evaluate_predictions(samples, ["different answer"], model_name="base")
    ft_rep = evaluator.evaluate_predictions(samples, ["hello world"], model_name="finetuned")

    comparison = evaluator.compare_models(base_rep, ft_rep)
    assert comparison["improved"] is True
    assert comparison["has_regressed"] is False
    assert comparison["exact_match_delta"] == 1.0
