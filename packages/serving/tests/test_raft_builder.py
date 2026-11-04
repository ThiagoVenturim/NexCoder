"""Unit tests for RAFT dataset builder."""

import json
from pathlib import Path

from faccoder_serving.raft.builder import RaftBuilder, RaftSample


def test_raft_sample_formatting() -> None:
    sample = RaftSample(
        instruction="What is the default port for vLLM?",
        oracle_context="vLLM binds by default to port 8000.",
        distractor_contexts=[
            "Ollama uses port 11434.",
            "PostgreSQL runs on port 5432.",
        ],
        cot_reasoning="Looking at context, vLLM specifies port 8000.",
        answer="8000",
    )

    prompt = sample.formatted_prompt(include_distractors=True)
    completion = sample.formatted_completion()

    assert "What is the default port for vLLM?" in prompt
    assert "port 8000" in prompt
    assert "port 11434" in prompt
    assert "<thought>" in completion
    assert "8000" in completion


def test_raft_builder_anonymized_dataset(tmp_path: Path) -> None:
    builder = RaftBuilder(distractor_count=2, anonymize=True)
    corpus = [
        "Chunk 1: Contact support at support@example.com for access.",
        "Chunk 2: The database password should be stored in secrets.",
        "Chunk 3: Developer phone number is (11) 98765-1234.",
    ]
    qa_pairs = [
        {
            "question": "Who to contact at support@example.com?",
            "context": "Contact support at support@example.com for access.",
            "answer": "Contact support team at support@example.com.",
        }
    ]

    dataset = builder.build_dataset(qa_pairs, corpus_pool=corpus)
    assert len(dataset.samples) == 1
    sample = dataset.samples[0]

    # Email must be anonymized in both prompt and completion
    assert "support@example.com" not in sample.instruction
    assert "[EMAIL_" in sample.instruction

    out_file = tmp_path / "raft_train.jsonl"
    count = dataset.export_jsonl(out_file, format_type="openai")
    assert count == 1
    assert out_file.exists()

    record = json.loads(out_file.read_text(encoding="utf-8").strip())
    assert "messages" in record
    assert len(record["messages"]) == 3
