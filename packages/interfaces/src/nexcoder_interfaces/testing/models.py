from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TestType = Literal["unit", "system", "process", "dom", "api", "security"]
TestRunStatus = Literal["queued", "running", "completed", "failed", "rejected", "cancelled"]
AgentState = Literal["idle", "running", "completed", "failed", "cancelled"]

ALL_TEST_TYPES: list[TestType] = ["unit", "system", "process", "dom", "api", "security"]


class CanvasPosition(BaseModel):
    x: int = 0
    y: int = 0


class TestFinding(BaseModel):
    id: str
    test_type: TestType
    title: str
    severity: Literal["critical", "high", "medium", "low", "info"] = "medium"
    location: str | None = None
    description: str = ""
    reproducer: str | None = None
    remediation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentCard(BaseModel):
    id: str
    title: str
    role: str = "Quality Engineer"
    agent_type: str = "tester"
    assigned_types: list[TestType] = Field(default_factory=list)
    state: AgentState = "idle"
    position: CanvasPosition = Field(default_factory=CanvasPosition)
    width: int = 460
    height: int = 300
    logs: list[str] = Field(default_factory=list)
    findings_count: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)

    def add_log(self, message: str) -> None:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {message}")
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]


class CanvasNote(BaseModel):
    id: str
    title: str
    body: str
    category: str = "report"
    position: CanvasPosition = Field(default_factory=CanvasPosition)
    width: int = 540
    height: int = 380


class CanvasConnection(BaseModel):
    from_id: str
    to_id: str
    label: str = ""


class NexHubCanvasPayload(BaseModel):
    cards: list[AgentCard] = Field(default_factory=list)
    notes: list[CanvasNote] = Field(default_factory=list)
    connections: list[CanvasConnection] = Field(default_factory=list)


class SecurityTestRunConfig(BaseModel):
    target_path: str = "."
    test_types: list[TestType] = Field(default_factory=lambda: list(ALL_TEST_TYPES))
    num_agents: int = 4
    budget_limit: float = 50.0
    budget_currency: str = "USD"
    owned_target: bool = False
    authorized_by: str = "owner"
    approval_token: str | None = None
    offline: bool = True
    synthetic_target: bool = False


class SecurityTestRunRecord(BaseModel):
    run_id: str
    status: TestRunStatus = "queued"
    target_path: str
    config: SecurityTestRunConfig
    authorized: bool = False
    authorized_by: str = ""
    rejection_reason: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    progress_percent: float = 0.0
    budget_spent: float = 0.0
    total_findings: int = 0
    passed_gate: bool = True
    summary: str = ""
    agents: list[AgentCard] = Field(default_factory=list)
    findings: list[TestFinding] = Field(default_factory=list)
    canvas: NexHubCanvasPayload = Field(default_factory=NexHubCanvasPayload)
