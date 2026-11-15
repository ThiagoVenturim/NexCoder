"""Unit tests for dataset curation, synthetic generation, filtering, and versioning."""

from __future__ import annotations

from pathlib import Path

from nexcoder_mlops.dataset.builder import (
    DataSample,
    DatasetBuilder,
    DatasetFormat,
)


def test_data_sample_formatting() -> None:
    sample = DataSample(
        instruction="Calculate 2 + 2",
        input_text="in Python",
        output="4",
        system_prompt="Math bot",
    )
    alpaca = sample.to_formatted(DatasetFormat.ALPACA)
    assert alpaca["instruction"] == "Calculate 2 + 2"
    assert alpaca["input"] == "in Python"
    assert alpaca["output"] == "4"

    chatml = sample.to_formatted(DatasetFormat.CHATML)
    assert len(chatml["messages"]) == 3
    assert chatml["messages"][0]["role"] == "system"
    assert chatml["messages"][1]["role"] == "user"
    assert chatml["messages"][2]["role"] == "assistant"
    assert chatml["messages"][2]["content"] == "4"

    sharegpt = sample.to_formatted(DatasetFormat.SHAREGPT)
    assert len(sharegpt["conversations"]) == 3
    assert sharegpt["conversations"][1]["from"] == "human"

    completion = sample.to_formatted(DatasetFormat.COMPLETION)
    assert "Assistant: " in completion["prompt"]
    assert completion["completion"] == "4"


def test_synthetic_dataset_and_filtering(tmp_path: Path) -> None:
    builder = DatasetBuilder()
    created = builder.create_synthetic_dataset(task_name="test_task", count=10)
    assert len(created) == 10

    # Add duplicate and short sample
    builder.add_sample(instruction=created[0].instruction, output=created[0].output)
    builder.add_sample(instruction="hi", output="no")  # too short

    removed = builder.filter_and_deduplicate(min_instruction_len=5, min_output_len=5)
    assert removed == 2
    assert len(builder.samples) == 10

    # Test anonymization
    builder.add_sample(
        instruction="Email me at user@example.com",
        output="My api key is sk-1234567890abcdef1234567890abcdef",
    )
    builder.anonymize_samples()
    last = builder.samples[-1]
    assert "user@example.com" not in last.instruction
    assert "sk-1234567890abcdef" not in last.output

    # Split
    train, val, test = builder.split(train_ratio=0.8, val_ratio=0.1)
    assert len(train) > 0
    assert len(val) >= 1
    assert len(test) >= 1

    manifest = builder.build_manifest(train, val, test, fmt=DatasetFormat.CHATML)
    assert len(manifest.version_hash) == 64
    assert manifest.total_samples == len(train) + len(val) + len(test)

    # Export and load
    out_file = tmp_path / "train.jsonl"
    DatasetBuilder.export_jsonl(train, out_file)
    assert out_file.exists()

    loaded = DatasetBuilder.load_jsonl(out_file)
    assert len(loaded) == len(train)
    assert loaded[0].instruction != ""
