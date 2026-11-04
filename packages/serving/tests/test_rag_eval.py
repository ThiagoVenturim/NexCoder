"""Unit tests for RAG evaluation metrics and LLM judge."""

from faccoder_serving.eval.rag_eval import (
    EvaluationSample,
    LLMJudge,
    RagEvaluator,
)


def test_faithfulness_grounded_answer() -> None:
    judge = LLMJudge()
    contexts = [
        "The faccoder core framework provides model routing and sqlite hybrid search.",
        "Langfuse observability has an offline circuit breaker mode.",
    ]
    answer = "The faccoder core framework provides model routing. Langfuse has an offline circuit breaker."
    score, reason = judge.evaluate_faithfulness(contexts, answer)

    assert score >= 0.8
    assert "grounded" in reason


def test_faithfulness_hallucinated_answer() -> None:
    judge = LLMJudge()
    contexts = [
        "The project runs on Python 3.12 and uses FastAPI.",
    ]
    answer = "The project is written entirely in Ruby on Rails and uses PostgreSQL exclusively."
    score, reason = judge.evaluate_faithfulness(contexts, answer)

    assert score < 0.5


def test_answer_relevance() -> None:
    judge = LLMJudge()
    question = "How does faccoder handle Langfuse circuit breaking?"
    answer = "Faccoder wraps Langfuse calls in a circuit breaker that no-ops when disconnected."
    score, reason = judge.evaluate_answer_relevance(question, answer)

    assert score >= 0.6
    assert "addressed" in reason


def test_context_precision() -> None:
    judge = LLMJudge()
    question = "Where are SQLite hybrid vector embeddings stored?"
    contexts = [
        "SQLite hybrid store uses sqlite-vec and FTS5 for table indexing.",
        "Docker compose runs vLLM and Ollama.",
        "Unrelated text about styling.",
    ]
    score, reason = judge.evaluate_context_precision(question, contexts)

    assert score > 0.5


def test_context_recall() -> None:
    judge = LLMJudge()
    ground_truth = "SQLite hybrid vector embeddings and FTS5 indexing."
    contexts = [
        "SQLite hybrid store uses sqlite-vec for embeddings and FTS5 indexing.",
    ]
    score, reason = judge.evaluate_context_recall(contexts, ground_truth)

    assert score >= 0.6


def test_rag_evaluator_dataset_aggregation() -> None:
    evaluator = RagEvaluator(
        faithfulness_threshold=0.5,
        relevance_threshold=0.5,
        precision_threshold=0.4,
        recall_threshold=0.4,
    )
    samples = [
        EvaluationSample(
            question="Which database is used by the system?",
            contexts=["The system database used is SQLite with sqlite-vec extension."],
            answer="The system database used is SQLite with sqlite-vec.",
            ground_truth="The system database used is SQLite with sqlite-vec.",
        ),
        EvaluationSample(
            question="Which model engine is supported for serving?",
            contexts=["The serving model engine supported is vLLM with GPU acceleration."],
            answer="The serving model engine supported is vLLM with GPU acceleration.",
            ground_truth="The serving model engine supported is vLLM with GPU acceleration.",
        ),
    ]

    report = evaluator.evaluate_dataset(samples)

    assert report.total_samples == 2
    assert report.mean_faithfulness >= 0.7
    assert report.pass_rate == 1.0
