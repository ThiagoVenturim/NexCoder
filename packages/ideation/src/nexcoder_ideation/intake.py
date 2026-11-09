from __future__ import annotations

import json
import logging
from typing import Any

from nexcoder_ideation.models import (
    AudienceSegment,
    RawIdea,
    StructuredIdea,
    ValueHypothesis,
)

logger = logging.getLogger(__name__)


class IdeaAnalyst:
    """Agent responsible for taking raw free-text ideas and structuring them into formal specifications."""

    def __init__(self, model: Any = None) -> None:
        self.model = model

    def analyze(self, raw_input: str | RawIdea) -> StructuredIdea:
        """Process raw idea text into a StructuredIdea model."""
        if isinstance(raw_input, str):
            raw_idea = RawIdea(raw_text=raw_input)
        else:
            raw_idea = raw_input

        text = raw_idea.raw_text.strip()

        # If LLM model provided, invoke structured extraction
        if self.model is not None and hasattr(self.model, "invoke"):
            structured = self._analyze_with_model(text, raw_idea.context)
            if structured:
                return structured

        # Deterministic heuristic fallback
        return self._heuristic_analyze(text, raw_idea.context)

    def _analyze_with_model(self, text: str, context: dict[str, Any]) -> StructuredIdea | None:
        prompt = (
            "You are an expert product strategist and idea analyst.\n"
            "Analyze the following software product idea and return a JSON object with this schema:\n"
            "{\n"
            '  "title": "Short title",\n'
            '  "summary": "1-2 sentence executive summary",\n'
            '  "problem": "Detailed problem statement",\n'
            '  "target_audience": [\n'
            '    {"name": "...", "description": "...", "pain_points": ["..."], "willingness_to_pay": "medium"}\n'
            "  ],\n"
            '  "value_hypothesis": {\n'
            '    "problem_statement": "...",\n'
            '    "proposed_solution": "...",\n'
            '    "key_benefit": "...",\n'
            '    "differentiation_summary": "...",\n'
            '    "primary_metric": "..."\n'
            "  },\n"
            '  "domain_tags": ["tag1", "tag2"],\n'
            '  "initial_assumptions": ["assumption1", "assumption2"]\n'
            "}\n\n"
            f"Idea description:\n{text}\n\n"
            f"Additional context: {json.dumps(context)}"
        )
        try:
            res = self.model.invoke(prompt)
            content = getattr(res, "content", str(res))
            # Extract JSON block if wrapped in markdown fences
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            return StructuredIdea(
                title=str(data.get("title", "Structured Product Idea")),
                summary=str(data.get("summary", text[:120])),
                problem=str(data.get("problem", text)),
                target_audience=[
                    AudienceSegment(
                        name=seg.get("name", "Target User"),
                        description=seg.get("description", ""),
                        pain_points=list(seg.get("pain_points", [])),
                        willingness_to_pay=str(seg.get("willingness_to_pay", "medium")),
                    )
                    for seg in data.get("target_audience", [])
                ],
                value_hypothesis=ValueHypothesis(
                    problem_statement=str(data.get("value_hypothesis", {}).get("problem_statement", text)),
                    proposed_solution=str(data.get("value_hypothesis", {}).get("proposed_solution", "")),
                    key_benefit=str(data.get("value_hypothesis", {}).get("key_benefit", "")),
                    differentiation_summary=str(data.get("value_hypothesis", {}).get("differentiation_summary", "")),
                    primary_metric=str(data.get("value_hypothesis", {}).get("primary_metric", "")),
                ),
                domain_tags=list(data.get("domain_tags", [])),
                initial_assumptions=list(data.get("initial_assumptions", [])),
            )
        except Exception as exc:
            logger.debug("Failed model-based idea analysis, reverting to heuristic: %s", exc)
            return None

    def _heuristic_analyze(self, text: str, context: dict[str, Any]) -> StructuredIdea:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = lines[0][:80] if lines else "New Product Idea"
        if len(title) > 60:
            title = title[:57] + "..."

        # Detect domain keywords
        domain_tags: list[str] = []
        lowered = text.lower()
        keyword_map = {
            "ai": "artificial-intelligence",
            "llm": "genai",
            "dev": "developer-tools",
            "api": "api-platform",
            "cloud": "cloud-infrastructure",
            "security": "cybersecurity",
            "mobile": "mobile",
            "data": "data-platform",
            "analytics": "business-intelligence",
            "commerce": "ecommerce",
            "fintech": "fintech",
            "health": "healthtech",
        }
        for kw, tag in keyword_map.items():
            if kw in lowered and tag not in domain_tags:
                domain_tags.append(tag)
        if not domain_tags:
            domain_tags = ["software", "productivity"]

        # Synthesize audience segments
        segments = [
            AudienceSegment(
                name="Primary Adopters",
                description="Core professionals and teams encountering the problem directly.",
                pain_points=[
                    "Manual overhead and inefficient current workflows",
                    "Lack of unified specialized tooling",
                ],
                willingness_to_pay="medium",
            ),
            AudienceSegment(
                name="Engineering & Product Leaders",
                description="Decision makers evaluating efficiency gains, integration overhead, and ROI.",
                pain_points=["Fragmented tooling landscape", "Governance and security blind spots"],
                willingness_to_pay="high",
            ),
        ]

        value_hypo = ValueHypothesis(
            problem_statement=text[:300],
            proposed_solution=f"An automated, end-to-end platform addressing: {text[:150]}",
            key_benefit=(
                "Radical productivity acceleration and reduced cognitive friction through autonomous workflows."
            ),
            differentiation_summary=(
                "Deep agentic orchestration, verifiable citations, and deterministic quality gates."
            ),
            primary_metric="Time-to-delivery reduction by >= 60%",
        )

        assumptions = [
            "Target users experience significant daily friction in this problem space.",
            "Willingness to adopt agent-assisted automation if citations and safety gates are present.",
            "Integration with existing developer and operational toolchains is essential.",
        ]

        return StructuredIdea(
            title=title,
            summary=lines[0] if lines else text[:120],
            problem=text,
            target_audience=segments,
            value_hypothesis=value_hypo,
            domain_tags=domain_tags,
            initial_assumptions=assumptions,
        )
