from __future__ import annotations

import json
import logging
from typing import Any

from nexcoder_ideation.models import (
    ArchitectureProposal,
    ComponentSpec,
    ResearchSquadReport,
    StructuredIdea,
)

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        clean = text.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.debug("Failed extracting JSON from text: %s", exc)
        return None


class ArchitectureDesigner:
    """Agent designing the baseline system architecture based on structured idea and research constraints."""

    def __init__(self, model: Any = None) -> None:
        self.model = model

    def design(self, idea: StructuredIdea, report: ResearchSquadReport) -> ArchitectureProposal:
        """Synthesize technical architecture proposal."""
        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                "You are a Principal Software Architect.\n"
                f"Design a modular system architecture for: {idea.title}.\n"
                f"Problem: {idea.problem}\n"
                f"Proposed Solution: {idea.value_hypothesis.proposed_solution}\n"
                f"Tags: {idea.domain_tags}\n\n"
                "Return JSON with:\n"
                "{\n"
                f'  "system_name": "{idea.title} Engine",\n'
                '  "components": [\n'
                '    {"name": "...", "purpose": "...", "technology_choices": ["..."], '
                '"data_stores": ["..."], "dependencies": ["..."]}\n'
                "  ],\n"
                '  "data_flow_description": "...",\n'
                '  "integration_points": ["..."],\n'
                '  "security_controls": ["..."],\n'
                '  "deployment_model": "..."\n'
                "}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    return ArchitectureProposal(
                        system_name=str(data.get("system_name", f"{idea.title} Core")),
                        components=[
                            ComponentSpec(
                                name=c.get("name", "Component"),
                                purpose=c.get("purpose", ""),
                                technology_choices=list(c.get("technology_choices", [])),
                                data_stores=list(c.get("data_stores", [])),
                                dependencies=list(c.get("dependencies", [])),
                            )
                            for c in data.get("components", [])
                        ],
                        data_flow_description=str(data.get("data_flow_description", "")),
                        integration_points=list(data.get("integration_points", [])),
                        security_controls=list(data.get("security_controls", [])),
                        deployment_model=str(data.get("deployment_model", "Cloud-native / Containerized")),
                    )
            except Exception as exc:
                logger.debug("Model-based architecture design failed: %s", exc)

        # Deterministic heuristic architecture
        clean_name = idea.title.replace(" ", "")
        return ArchitectureProposal(
            system_name=f"{clean_name}Platform",
            components=[
                ComponentSpec(
                    name="API & Gateway Ingestion Service",
                    purpose="Validates incoming payloads, manages API keys, and routes requests to agent pipeline.",
                    technology_choices=["FastAPI", "Pydantic v2", "Uvicorn"],
                    data_stores=["Redis (Rate limiting & sessions)"],
                    dependencies=["Authentication Middleware"],
                ),
                ComponentSpec(
                    name="Agent Orchestration & Pipeline Runner",
                    purpose="Executes structured workflows, manages block transitions, and aggregates citations.",
                    technology_choices=["Python 3.11+", "LangChain", "nexcoder-core"],
                    data_stores=["SQLite / PostgreSQL (State store)"],
                    dependencies=["Model Registry", "Observability Circuit Breaker"],
                ),
                ComponentSpec(
                    name="Knowledge & Retrieval Subsystem",
                    purpose="Manages vector embeddings, keyword search, hybrid fusion (RRF), and citation indexing.",
                    technology_choices=["sqlite-vec / pgvector", "HashEmbedder", "BM25"],
                    data_stores=["Vector Store", "FTS5 Index"],
                    dependencies=["Search Provider"],
                ),
                ComponentSpec(
                    name="Governance & Human-in-the-Loop Gateway",
                    purpose="Enforces b90 jury quorum checks and b85 human approval tokens before plan handoff.",
                    technology_choices=["Cryptographic HMAC tokens", "JSON audit logs"],
                    data_stores=["Audit Trail Ledger"],
                    dependencies=["Security Policy Engine"],
                ),
            ],
            data_flow_description=(
                "1. User submits raw idea or intent via CLI or Gateway. "
                "2. Pipeline routes payload to Idea Analyst and Research Squad specialists. "
                "3. Squad performs cited search and compiles verified intelligence report. "
                "4. b90 Jury Committee convenes, scoring the public rubric and casting quorum votes. "
                "5. On GO verdict, Architecture and PRD documents are compiled and held at the b85 human gate."
            ),
            integration_points=[
                "GitHub / GitLab / Azure DevOps Platform Trackers",
                "Langfuse Distributed Observability & Tracing",
                "Local Open-Source LLMs (Ollama / vLLM OpenAI-compatible endpoints)",
            ],
            security_controls=[
                "Zero storage of plaintext credentials; environment variables with least privilege",
                "Strict sandbox execution for file system access",
                "Short-lived (30-minute) cryptographic tokens for destructive approvals",
                "100% offline airgapped operation with mock/local fallbacks",
            ],
            deployment_model="Modular Python package with optional Docker containerization",
        )
