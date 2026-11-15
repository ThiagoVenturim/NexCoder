"""Dataset preparation, synthetic generation, quality filtering, and versioning for fine-tuning."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from nexcoder_serving.raft.anonymizer import Anonymizer
from pydantic import BaseModel, Field


class DatasetFormat(StrEnum):
    CHATML = "chatml"
    ALPACA = "alpaca"
    SHAREGPT = "sharegpt"
    COMPLETION = "completion"


class DataSample(BaseModel):
    """A single supervised fine-tuning / instruction sample."""

    instruction: str
    input_text: str = ""
    output: str
    system_prompt: str = "You are a helpful and precise assistant."
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_formatted(self, fmt: DatasetFormat) -> dict[str, Any]:
        """Convert sample into target training format."""
        if fmt == DatasetFormat.ALPACA:
            return {
                "instruction": self.instruction,
                "input": self.input_text,
                "output": self.output,
            }
        if fmt == DatasetFormat.CHATML:
            messages = []
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            user_content = f"{self.instruction}\n{self.input_text}".strip() if self.input_text else self.instruction
            messages.append({"role": "user", "content": user_content})
            messages.append({"role": "assistant", "content": self.output})
            return {"messages": messages}
        if fmt == DatasetFormat.SHAREGPT:
            conversations = []
            if self.system_prompt:
                conversations.append({"from": "system", "value": self.system_prompt})
            user_val = f"{self.instruction}\n{self.input_text}".strip() if self.input_text else self.instruction
            conversations.append({"from": "human", "value": user_val})
            conversations.append({"from": "gpt", "value": self.output})
            return {"conversations": conversations}
        # COMPLETION format
        prompt = (
            f"{self.system_prompt}\n\nUser: {self.instruction}\nInput: {self.input_text}\nAssistant: "
            if self.input_text
            else f"{self.system_prompt}\n\nUser: {self.instruction}\nAssistant: "
        )
        return {"prompt": prompt, "completion": self.output}

    def content_hash(self) -> str:
        """Deterministic hash of the sample payload for deduplication."""
        raw = f"{self.instruction.strip()}|{self.input_text.strip()}|{self.output.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DatasetManifest(BaseModel):
    """Immutable metadata and cryptographic checksum of a curated dataset split."""

    version_hash: str
    total_samples: int
    train_count: int
    val_count: int
    test_count: int
    format: DatasetFormat
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetBuilder:
    """Pipelines for building, filtering, anonymizing, splitting, and versioning fine-tuning datasets."""

    def __init__(self, anonymizer: Anonymizer | None = None) -> None:
        self.samples: list[DataSample] = []
        self.anonymizer = anonymizer or Anonymizer()

    def add_sample(
        self,
        instruction: str,
        output: str,
        input_text: str = "",
        system_prompt: str = "You are a helpful and precise assistant.",
        metadata: dict[str, Any] | None = None,
    ) -> DataSample:
        sample = DataSample(
            instruction=instruction,
            input_text=input_text,
            output=output,
            system_prompt=system_prompt,
            metadata=metadata or {},
        )
        self.samples.append(sample)
        return sample

    def create_synthetic_dataset(self, task_name: str = "code_qa", count: int = 10) -> list[DataSample]:
        """Generate a deterministic synthetic dataset for testing or bootstrap fine-tuning."""
        templates = [
            (
                "Write a Python function to compute the Fibonacci sequence up to n terms.",
                "",
                (
                    "def fibonacci(n: int) -> list[int]:\n"
                    "    if n <= 0:\n"
                    "        return []\n"
                    "    if n == 1:\n"
                    "        return [0]\n"
                    "    seq = [0, 1]\n"
                    "    while len(seq) < n:\n"
                    "        seq.append(seq[-1] + seq[-2])\n"
                    "    return seq"
                ),
            ),
            (
                "Explain the difference between mutable and immutable types in Python.",
                "",
                (
                    "Mutable types (like lists, dictionaries, sets) can be altered in place after creation. "
                    "Immutable types (like ints, strings, tuples) cannot be modified once instantiated; "
                    "any modification creates a new object."
                ),
            ),
            (
                "Write a function that reverses words in a string.",
                "",
                "def reverse_words(sentence: str) -> str:\n    return ' '.join(reversed(sentence.split()))",
            ),
            (
                "What is LoRA in the context of parameter-efficient fine-tuning?",
                "",
                (
                    "LoRA (Low-Rank Adaptation) freezes the pre-trained model weights and injects trainable rank "
                    "decomposition matrices into each layer, substantially reducing the number of trainable "
                    "parameters."
                ),
            ),
            (
                "Implement a safe division function in Python that handles ZeroDivisionError.",
                "",
                (
                    "def safe_divide(numerator: float, denominator: float) -> float | None:\n"
                    "    if denominator == 0:\n"
                    "        return None\n"
                    "    return numerator / denominator"
                ),
            ),
        ]
        created = []
        for i in range(count):
            tmpl = templates[i % len(templates)]
            s = self.add_sample(
                instruction=f"{tmpl[0]} (variant {i + 1})",
                input_text=tmpl[1],
                output=f"{tmpl[2]} # variant {i + 1}",
                metadata={"synthetic": True, "task": task_name, "index": i + 1},
            )
            created.append(s)
        return created

    def filter_and_deduplicate(
        self,
        min_instruction_len: int = 5,
        min_output_len: int = 5,
    ) -> int:
        """Deduplicate samples by hash and filter out short or empty rows. Returns count removed."""
        seen_hashes = set()
        cleaned: list[DataSample] = []
        removed = 0

        for s in self.samples:
            if len(s.instruction.strip()) < min_instruction_len or len(s.output.strip()) < min_output_len:
                removed += 1
                continue
            h = s.content_hash()
            if h in seen_hashes:
                removed += 1
                continue
            seen_hashes.add(h)
            cleaned.append(s)

        self.samples = cleaned
        return removed

    def anonymize_samples(self) -> None:
        """Mask PII (emails, IPs, keys) across instructions and outputs."""
        for s in self.samples:
            s.instruction = self.anonymizer.anonymize_text(s.instruction)
            if s.input_text:
                s.input_text = self.anonymizer.anonymize_text(s.input_text)
            s.output = self.anonymizer.anonymize_text(s.output)

    def split(
        self,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
    ) -> tuple[list[DataSample], list[DataSample], list[DataSample]]:
        """Deterministically partition samples into train, validation, and test subsets."""
        n = len(self.samples)
        if n == 0:
            return [], [], []
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)

        train_set = self.samples[:train_end]
        val_set = self.samples[train_end:val_end]
        test_set = self.samples[val_end:]
        return train_set, val_set, test_set

    def build_manifest(
        self,
        train: list[DataSample],
        val: list[DataSample],
        test: list[DataSample],
        fmt: DatasetFormat = DatasetFormat.CHATML,
    ) -> DatasetManifest:
        """Calculate deterministic SHA-256 version hash for the dataset."""
        concatenated = "".join(s.content_hash() for s in train + val + test)
        version_hash = hashlib.sha256(concatenated.encode("utf-8")).hexdigest()
        return DatasetManifest(
            version_hash=version_hash,
            total_samples=len(train) + len(val) + len(test),
            train_count=len(train),
            val_count=len(val),
            test_count=len(test),
            format=fmt,
        )

    @staticmethod
    def export_jsonl(samples: list[DataSample], path: str | Path, fmt: DatasetFormat = DatasetFormat.CHATML) -> Path:
        """Export samples formatted as JSONL."""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for s in samples:
                payload = s.to_formatted(fmt)
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return out_path

    @staticmethod
    def load_jsonl(path: str | Path) -> list[DataSample]:
        """Load DataSample objects from a JSONL file."""
        in_path = Path(path)
        samples = []
        with in_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                if "messages" in data:
                    msgs = data["messages"]
                    sys_prompt = ""
                    user_prompt = ""
                    asst_output = ""
                    for m in msgs:
                        role = m.get("role")
                        content = m.get("content", "")
                        if role == "system":
                            sys_prompt = content
                        elif role == "user":
                            user_prompt = content
                        elif role == "assistant":
                            asst_output = content
                    samples.append(
                        DataSample(
                            instruction=user_prompt,
                            output=asst_output,
                            system_prompt=sys_prompt or "You are a helpful and precise assistant.",
                        )
                    )
                elif "conversations" in data:
                    convs = data["conversations"]
                    sys_prompt = ""
                    user_prompt = ""
                    asst_output = ""
                    for c in convs:
                        sender = c.get("from")
                        val = c.get("value", "")
                        if sender == "system":
                            sys_prompt = val
                        elif sender == "human":
                            user_prompt = val
                        elif sender == "gpt":
                            asst_output = val
                    samples.append(
                        DataSample(
                            instruction=user_prompt,
                            output=asst_output,
                            system_prompt=sys_prompt or "You are a helpful and precise assistant.",
                        )
                    )
                elif "instruction" in data:
                    samples.append(
                        DataSample(
                            instruction=data.get("instruction", ""),
                            input_text=data.get("input", ""),
                            output=data.get("output", ""),
                        )
                    )
                elif "prompt" in data and "completion" in data:
                    samples.append(
                        DataSample(
                            instruction=data["prompt"],
                            output=data["completion"],
                        )
                    )
        return samples
