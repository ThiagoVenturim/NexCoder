from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PersonaType(StrEnum):
    """Classification of the user's situation and starting scenario."""

    PERSONA_A = "established_product"  # Established company with existing software/codebase
    PERSONA_B = "idea_stage"  # Starting from scratch, pain or idea only


class InterviewState(StrEnum):
    """Lifecycle state of an onboarding interview."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class InterviewQuestion(BaseModel):
    """Structured question presented during branching onboarding interview."""

    id: str
    persona: PersonaType
    title: str
    prompt: str
    explanation: str
    required: bool = True
    category: str = "general"


class PersonaADetails(BaseModel):
    """Extracted scenario details for Persona A (existing company & product)."""

    tech_stack: list[str] = Field(default_factory=list)
    hosting_infra: str = ""
    pain_points: list[str] = Field(default_factory=list)
    business_goals: list[str] = Field(default_factory=list)
    constraints_compliance: list[str] = Field(default_factory=list)
    code_access_status: str = ""
    has_repo: bool = True
    has_running_product: bool = True


class PersonaBDetails(BaseModel):
    """Extracted scenario details for Persona B (idea stage / pain only)."""

    problem_statement: str = ""
    target_audience: str = ""
    value_proposition_diff: str = ""
    budget_range: str = ""
    timeline: str = ""
    risks_assumptions: list[str] = Field(default_factory=list)
    validation_hypotheses: list[str] = Field(default_factory=list)


class ScenarioProfile(BaseModel):
    """Unified scenario profile that feeds the NexCoder pipeline (research, jury, PRD, architecture, cost)."""

    profile_id: str = Field(default_factory=lambda: f"profile-{uuid.uuid4().hex[:8]}")
    persona: PersonaType
    project_name: str = "Novo Projeto"
    session_id: str = ""
    summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    answers: dict[str, str] = Field(default_factory=dict)
    raw_signals: dict[str, Any] = Field(default_factory=dict)
    persona_a_details: PersonaADetails | None = None
    persona_b_details: PersonaBDetails | None = None
    recommended_pipeline: list[str] = Field(default_factory=list)
    pipeline_readiness: dict[str, Any] = Field(default_factory=dict)
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    is_sanitized: bool = True


class InterviewSession(BaseModel):
    """Stateful interview session tracking questions, answers, and progress."""

    session_id: str = Field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:8]}")
    persona: PersonaType | None = None
    state: InterviewState = InterviewState.PENDING
    questions: list[InterviewQuestion] = Field(default_factory=list)
    current_index: int = 0
    answers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    audit_log: list[dict[str, Any]] = Field(default_factory=list)
