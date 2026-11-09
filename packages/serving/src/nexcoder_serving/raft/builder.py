"""RAFT (Retrieval Augmented Fine Tuning) dataset builder with distractors and chain-of-thought."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Literal

from nexcoder_serving.raft.anonymizer import Anonymizer
from pydantic import BaseModel, Field


class RaftSample(BaseModel):
    instruction: str
    oracle_context: str
    distractor_contexts: list[str] = Field(default_factory=list)
    cot_reasoning: str
    answer: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def formatted_prompt(self, include_distractors: bool = True, shuffle: bool = True) -> str:
        """Compose the full input prompt including oracle and optional distractor contexts."""
        contexts = [self.oracle_context]
        if include_distractors:
            contexts.extend(self.distractor_contexts)
        if shuffle:
            # Deterministic pseudo-shuffle if needed, or normal shuffle
            shuffled = list(contexts)
            random.Random(42).shuffle(shuffled)  # noqa: S311
            contexts = shuffled

        ctx_blocks = "\n\n".join(f"[Context {i+1}]:\n{c}" for i, c in enumerate(contexts))
        return (
            f"You are a helpful and truthful AI assistant. Answer the question based ONLY on the provided context.\n\n"
            f"{ctx_blocks}\n\n"
            f"Question: {self.instruction}\n"
            f"Answer:"
        )

    def formatted_completion(self) -> str:
        """Compose the target completion with chain-of-thought and final answer."""
        return f"<thought>\n{self.cot_reasoning}\n</thought>\n{self.answer}"


class RaftDataset(BaseModel):
    samples: list[RaftSample] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def export_jsonl(self, path: str | Path, format_type: Literal["alpaca", "openai", "sharegpt"] = "alpaca") -> int:
        """Export samples to a JSONL file in the specified fine-tuning format."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        for s in self.samples:
            prompt = s.formatted_prompt()
            completion = s.formatted_completion()

            if format_type == "alpaca":
                record = {
                    "instruction": s.instruction,
                    "input": "\n\n".join([s.oracle_context, *s.distractor_contexts]),
                    "output": completion,
                }
            elif format_type == "openai":
                record = {
                    "messages": [
                        {"role": "system", "content": "You are a helpful coding assistant."},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": completion},
                    ]
                }
            else:  # sharegpt
                record = {
                    "conversations": [
                        {"from": "human", "value": prompt},
                        {"from": "gpt", "value": completion},
                    ]
                }
            lines.append(json.dumps(record, ensure_ascii=False))

        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return len(lines)


class RaftBuilder:
    """Builds RAFT datasets from raw document corpora and question-answer sets."""

    def __init__(
        self,
        distractor_count: int = 3,
        anonymize: bool = True,
        anonymizer: Anonymizer | None = None,
    ) -> None:
        self.distractor_count = distractor_count
        self.anonymize = anonymize
        self.anonymizer = anonymizer or (Anonymizer() if anonymize else None)

    def create_sample(
        self,
        instruction: str,
        oracle_context: str,
        corpus_pool: list[str],
        answer: str,
        cot_reasoning: str | None = None,
    ) -> RaftSample:
        """Create a single RAFT sample with sampled distractors and synthesized reasoning."""
        # Pick distractors distinct from oracle
        pool = [c for c in corpus_pool if c.strip() != oracle_context.strip()]
        distractors = random.sample(pool, min(self.distractor_count, len(pool))) if pool else []  # noqa: S311

        # Generate default chain of thought if not provided
        reasoning = cot_reasoning or (
            f"Reviewing the contexts: Context mentions facts relevant to '{instruction}'. "
            f"Based on the verified statements, the definitive answer is '{answer}'."
        )

        if self.anonymize and self.anonymizer:
            instruction = self.anonymizer.anonymize_text(instruction)
            oracle_context = self.anonymizer.anonymize_text(oracle_context)
            distractors = [self.anonymizer.anonymize_text(d) for d in distractors]
            reasoning = self.anonymizer.anonymize_text(reasoning)
            answer = self.anonymizer.anonymize_text(answer)

        return RaftSample(
            instruction=instruction,
            oracle_context=oracle_context,
            distractor_contexts=distractors,
            cot_reasoning=reasoning,
            answer=answer,
        )

    def build_dataset(
        self,
        qa_pairs: list[dict[str, str]],
        corpus_pool: list[str],
    ) -> RaftDataset:
        """Batch construct a RAFT dataset from a list of Q&A dictionaries."""
        samples: list[RaftSample] = []
        for pair in qa_pairs:
            sample = self.create_sample(
                instruction=pair["question"],
                oracle_context=pair["context"],
                corpus_pool=corpus_pool,
                answer=pair["answer"],
                cot_reasoning=pair.get("reasoning"),
            )
            samples.append(sample)

        return RaftDataset(
            samples=samples,
            metadata={
                "distractor_count": self.distractor_count,
                "anonymized": self.anonymize,
                "total_samples": len(samples),
            },
        )
