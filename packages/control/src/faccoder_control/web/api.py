"""Lightweight FastAPI status, metrics, and governance API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from faccoder_control.approval.machines import CLIMachine, MachineApprovalManager, MachineStatus
from faccoder_control.approval.tokens import ApprovalRequiredError, ApprovalTokenManager, ApprovalTokenRecord
from faccoder_control.keys.models import APIKeyCreate, APIKeyCreatedResult, APIKeyRecord
from faccoder_control.keys.store import APIKeyService
from faccoder_control.metering.audit import AppendOnlyAuditLog, AuditEvent, AuditSeverity
from faccoder_control.metering.budgets import BudgetAlert, BudgetManager, BudgetPolicy
from faccoder_control.metering.cost_tracker import CostTracker, DimensionType
from faccoder_control.metering.mcp_middleware import MCPToolMeter
from faccoder_control.web.panel import ControlPlaneOverview, build_overview, render_html_panel


class IssueTokenRequest(BaseModel):
    action_name: str
    target_resource: str
    approver: str
    ttl_minutes: int = 15
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerifyTokenRequest(BaseModel):
    raw_token: str
    action_name: str
    target_resource: str
    dry_run: bool = False


class RegisterMachineRequest(BaseModel):
    machine_id: str
    hostname: str
    platform: str = "unknown"
    client_version: str = "0.1.0"
    registered_by: str = "anonymous"
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_control_router(
    key_service: APIKeyService,
    cost_tracker: CostTracker,
    tool_meter: MCPToolMeter,
    budget_mgr: BudgetManager,
    machine_mgr: MachineApprovalManager,
    audit_log: AppendOnlyAuditLog,
) -> APIRouter:
    """Factory creating an APIRouter wired to control plane subsystems."""
    router = APIRouter(prefix="/control", tags=["Control Plane"])

    # ---------------------------------------------------------
    # Status, Overview & Web Panel
    # ---------------------------------------------------------

    @router.get("/status", response_model=ControlPlaneOverview)
    def get_status() -> ControlPlaneOverview:
        return build_overview(key_service, cost_tracker, tool_meter, budget_mgr, machine_mgr, audit_log)

    @router.get("/panel", response_class=HTMLResponse)
    def get_panel() -> str:
        overview = build_overview(key_service, cost_tracker, tool_meter, budget_mgr, machine_mgr, audit_log)
        return render_html_panel(overview)

    # ---------------------------------------------------------
    # Metrics & Spend
    # ---------------------------------------------------------

    @router.get("/metrics/tools", response_model=list[dict[str, Any]])
    def get_tool_metrics() -> list[dict[str, Any]]:
        metrics = tool_meter.get_tool_metrics()
        return [
            {
                "tool_name": m.tool_name,
                "invocations": m.invocations,
                "errors": m.errors,
                "error_rate": round(m.error_rate, 4),
                "avg_duration_ms": round(m.avg_duration_ms, 2),
                "p95_duration_ms": round(m.p95_duration_ms, 2),
                "total_input_tokens": m.total_input_tokens,
                "total_output_tokens": m.total_output_tokens,
                "total_cost_usd": round(m.total_cost_usd, 4),
            }
            for m in metrics
        ]

    @router.get("/metrics/spend")
    def get_spend(dimension: DimensionType = "app") -> dict[str, Any]:
        summaries = cost_tracker.aggregate_by(dimension)
        return {
            "dimension": dimension,
            "total_spend_usd": round(cost_tracker.total_spend(), 4),
            "breakdown": {
                k: {
                    "cost_usd": round(v.total_cost_usd, 4),
                    "calls": v.calls_count,
                    "tokens": v.total_input_tokens + v.total_output_tokens,
                }
                for k, v in summaries.items()
            },
        }

    # ---------------------------------------------------------
    # API Keys Management
    # ---------------------------------------------------------

    @router.get("/keys", response_model=list[APIKeyRecord])
    def list_api_keys() -> list[APIKeyRecord]:
        return key_service.list_keys()

    @router.post("/keys", response_model=APIKeyCreatedResult)
    def create_api_key(spec: APIKeyCreate) -> APIKeyCreatedResult:
        result = key_service.create_key(spec)
        audit_log.record_event(
            event_type="key.created",
            actor=spec.owner,
            action="create",
            resource=result.key_id,
            severity="info",
            details={"name": spec.name, "scopes": spec.scopes, "usd_cap": spec.usd_cap},
        )
        return result

    @router.delete("/keys/{key_id}")
    def revoke_api_key(key_id: str, actor: str = "admin") -> dict[str, bool]:
        success = key_service.revoke_key(key_id)
        if not success:
            raise HTTPException(status_code=404, detail="Key not found")
        audit_log.record_event(
            event_type="key.revoked",
            actor=actor,
            action="revoke",
            resource=key_id,
            severity="warning",
        )
        return {"revoked": True}

    # ---------------------------------------------------------
    # Budgets & Policies
    # ---------------------------------------------------------

    @router.get("/budgets", response_model=list[BudgetPolicy])
    def list_budgets() -> list[BudgetPolicy]:
        return budget_mgr.list_policies()

    @router.post("/budgets", response_model=BudgetPolicy)
    def create_budget(policy: BudgetPolicy) -> BudgetPolicy:
        budget_mgr.add_policy(policy)
        audit_log.record_event(
            event_type="budget.created",
            actor="admin",
            action="create",
            resource=policy.policy_id,
            severity="info",
            details={"dimension": policy.dimension, "entity_id": policy.entity_id, "limit": policy.limit_usd},
        )
        return policy

    @router.get("/budgets/alerts", response_model=list[BudgetAlert])
    def list_budget_alerts() -> list[BudgetAlert]:
        return budget_mgr.get_alerts()

    # ---------------------------------------------------------
    # Audit Log
    # ---------------------------------------------------------

    @router.get("/audit", response_model=list[AuditEvent])
    def query_audit_log(
        event_type: str | None = None,
        actor: str | None = None,
        severity: AuditSeverity | None = None,
        limit: int = Query(default=100, le=1000),
    ) -> list[AuditEvent]:
        return audit_log.query(event_type=event_type, actor=actor, severity=severity, limit=limit)

    @router.get("/audit/verify")
    def verify_audit_integrity() -> dict[str, Any]:
        is_valid, message = audit_log.verify_integrity()
        return {"valid": is_valid, "message": message}

    # ---------------------------------------------------------
    # Human Approval Tokens
    # ---------------------------------------------------------

    @router.post("/approval/tokens")
    def issue_approval_token(req: IssueTokenRequest) -> dict[str, Any]:
        record, raw_token = token_mgr.issue_token(
            action_name=req.action_name,
            target_resource=req.target_resource,
            approver=req.approver,
            ttl_minutes=req.ttl_minutes,
            metadata=req.metadata,
        )
        audit_log.record_event(
            event_type="approval.token_issued",
            actor=req.approver,
            action="issue_token",
            resource=req.target_resource,
            severity="info",
            details={"action": req.action_name, "token_id": record.token_id, "ttl": req.ttl_minutes},
        )
        return {"token_id": record.token_id, "raw_token": raw_token, "expires_at": record.expires_at}

    @router.post("/approval/tokens/verify", response_model=ApprovalTokenRecord)
    def verify_approval_token(req: VerifyTokenRequest) -> ApprovalTokenRecord:
        try:
            record = token_mgr.verify_and_consume(
                raw_token=req.raw_token,
                action_name=req.action_name,
                target_resource=req.target_resource,
                dry_run=req.dry_run,
            )
            audit_log.record_event(
                event_type="approval.token_verified",
                actor=record.approver,
                action="verify_token" if req.dry_run else "consume_token",
                resource=req.target_resource,
                severity="info",
                details={"action": req.action_name, "dry_run": req.dry_run},
            )
            return record
        except ApprovalRequiredError as exc:
            audit_log.record_event(
                event_type="approval.token_failed",
                actor="unknown",
                action="verify_token",
                resource=req.target_resource,
                severity="error",
                details={"error": str(exc)},
            )
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    # ---------------------------------------------------------
    # CLI Machines Governance
    # ---------------------------------------------------------

    @router.get("/machines", response_model=list[CLIMachine])
    def list_machines(status: MachineStatus | None = None) -> list[CLIMachine]:
        return machine_mgr.list_machines(status=status)

    @router.post("/machines/register", response_model=CLIMachine)
    def register_machine(req: RegisterMachineRequest) -> CLIMachine:
        machine = machine_mgr.register_machine(
            machine_id=req.machine_id,
            hostname=req.hostname,
            platform=req.platform,
            client_version=req.client_version,
            registered_by=req.registered_by,
            metadata=req.metadata,
        )
        audit_log.record_event(
            event_type="machine.registered",
            actor=req.registered_by,
            action="register",
            resource=req.machine_id,
            severity="info",
            details={"hostname": req.hostname, "platform": req.platform},
        )
        return machine

    @router.post("/machines/{machine_id}/approve", response_model=CLIMachine)
    def approve_machine(machine_id: str, approver: str = "admin") -> CLIMachine:
        try:
            machine = machine_mgr.approve_machine(machine_id, approver=approver)
            audit_log.record_event(
                event_type="machine.approved",
                actor=approver,
                action="approve",
                resource=machine_id,
                severity="info",
            )
            return machine
        except KeyError:
            raise HTTPException(status_code=404, detail="Machine not found") from None

    return router


# Internal default token manager instance for convenience
token_mgr = ApprovalTokenManager()
