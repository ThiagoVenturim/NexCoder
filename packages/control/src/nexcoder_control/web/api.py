"""Lightweight FastAPI status, metrics, and governance API router with RBAC authentication."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from nexcoder_control.approval.machines import CLIMachine, MachineApprovalManager, MachineStatus
from nexcoder_control.approval.tokens import ApprovalRequiredError, ApprovalTokenManager, ApprovalTokenRecord
from nexcoder_control.auth.base import AuthPrincipal, BaseAuthProvider
from nexcoder_control.keys.models import APIKeyCreate, APIKeyCreatedResult, APIKeyRecord
from nexcoder_control.keys.store import APIKeyService
from nexcoder_control.metering.audit import AppendOnlyAuditLog, AuditEvent, AuditSeverity
from nexcoder_control.metering.budgets import BudgetAlert, BudgetManager, BudgetPolicy
from nexcoder_control.metering.cost_tracker import CostTracker, DimensionType
from nexcoder_control.metering.mcp_middleware import MCPToolMeter
from nexcoder_control.web.panel import ControlPlaneOverview, build_overview, render_html_panel


class IssueTokenRequest(BaseModel):
    action_name: str
    target_resource: str
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
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_control_router(
    key_service: APIKeyService,
    cost_tracker: CostTracker,
    tool_meter: MCPToolMeter,
    budget_mgr: BudgetManager,
    machine_mgr: MachineApprovalManager,
    audit_log: AppendOnlyAuditLog,
    token_mgr: ApprovalTokenManager | None = None,
    auth_provider: BaseAuthProvider | None = None,
) -> APIRouter:
    """Factory creating an APIRouter wired to control plane subsystems with strict authentication."""
    router = APIRouter(prefix="/control", tags=["Control Plane"])
    effective_token_mgr = token_mgr or ApprovalTokenManager()

    # ---------------------------------------------------------
    # Authentication & Authorization Dependencies
    # ---------------------------------------------------------

    def get_current_principal(request: Request) -> AuthPrincipal:
        """Authenticate request via API Key or Bearer Token."""
        auth_header = request.headers.get("authorization")
        x_api_key = request.headers.get("x-api-key")

        raw_token: str | None = None
        if auth_header:
            if auth_header.startswith("Bearer "):
                raw_token = auth_header.split("Bearer ", 1)[1].strip()
            elif auth_header.startswith("ApiKey "):
                x_api_key = auth_header.split("ApiKey ", 1)[1].strip()
            else:
                raw_token = auth_header.strip()

        # 1. API Key verification (via header or token starting with fc_key_)
        key_candidate = x_api_key or (raw_token if raw_token and raw_token.startswith("fc_key_") else None)
        if key_candidate:
            try:
                record = key_service.verify_key(key_candidate)
                is_admin = "admin" in record.scopes or "*" in record.scopes
                return AuthPrincipal(
                    id=record.owner,
                    name=record.name,
                    roles=["admin"] if is_admin else ["service"],
                    scopes=record.scopes,
                    auth_type="api_key",
                    is_active=record.is_active,
                    is_human=False,
                    metadata={"key_id": record.key_id},
                )
            except Exception as exc:
                raise HTTPException(status_code=401, detail=f"Invalid API key: {exc}") from exc

        # 2. Pluggable Auth Provider (OIDC / Local)
        if raw_token and auth_provider:
            try:
                principal = auth_provider.authenticate(raw_token)
                if principal and principal.is_active:
                    return principal
            except Exception as exc:
                raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}") from exc

        raise HTTPException(status_code=401, detail="Authentication required: missing or invalid credentials")

    def require_admin(principal: AuthPrincipal = Depends(get_current_principal)) -> AuthPrincipal:
        """Require administrator role or admin scope."""
        if not (principal.has_role("admin") or principal.has_scope("admin") or principal.has_scope("control:admin")):
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: administrator role or scope required, principal has roles={principal.roles}",
            )
        return principal

    def require_human_approver(principal: AuthPrincipal = Depends(get_current_principal)) -> AuthPrincipal:
        """Require an authenticated human approver with approver or admin role."""
        if not principal.is_human:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: human approval tokens may only be issued by authenticated human principals",
            )
        if not (
            principal.has_role("admin")
            or principal.has_role("approver")
            or principal.has_scope("admin")
            or principal.has_scope("approval:issue")
        ):
            raise HTTPException(
                status_code=403,
                detail="Forbidden: human approval role or scope required",
            )
        return principal

    # ---------------------------------------------------------
    # Status, Overview & Web Panel
    # ---------------------------------------------------------

    @router.get("/status", response_model=ControlPlaneOverview)
    def get_status(_principal: AuthPrincipal = Depends(get_current_principal)) -> ControlPlaneOverview:
        return build_overview(key_service, cost_tracker, tool_meter, budget_mgr, machine_mgr, audit_log)

    @router.get("/panel", response_class=HTMLResponse)
    def get_panel(_principal: AuthPrincipal = Depends(get_current_principal)) -> str:
        overview = build_overview(key_service, cost_tracker, tool_meter, budget_mgr, machine_mgr, audit_log)
        return render_html_panel(overview)

    # ---------------------------------------------------------
    # Metrics & Spend
    # ---------------------------------------------------------

    @router.get("/metrics/tools", response_model=list[dict[str, Any]])
    def get_tool_metrics(_principal: AuthPrincipal = Depends(get_current_principal)) -> list[dict[str, Any]]:
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
    def get_spend(
        dimension: DimensionType = "app",
        _principal: AuthPrincipal = Depends(get_current_principal),
    ) -> dict[str, Any]:
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
    # API Keys Management (Admin Only)
    # ---------------------------------------------------------

    @router.get("/keys", response_model=list[APIKeyRecord])
    def list_api_keys(_admin: AuthPrincipal = Depends(require_admin)) -> list[APIKeyRecord]:
        return key_service.list_keys()

    @router.post("/keys", response_model=APIKeyCreatedResult)
    def create_api_key(spec: APIKeyCreate, admin: AuthPrincipal = Depends(require_admin)) -> APIKeyCreatedResult:
        result = key_service.create_key(spec)
        audit_log.record_event(
            event_type="key.created",
            actor=admin.id,
            action="create_key",
            resource=result.key_id,
            severity="info",
            details={"name": spec.name, "owner": spec.owner, "scopes": spec.scopes},
        )
        return result

    @router.delete("/keys/{key_id}")
    def revoke_api_key(key_id: str, admin: AuthPrincipal = Depends(require_admin)) -> dict[str, Any]:
        success = key_service.revoke_key(key_id)
        if not success:
            raise HTTPException(status_code=404, detail="API Key not found or already revoked")
        audit_log.record_event(
            event_type="key.revoked",
            actor=admin.id,
            action="revoke_key",
            resource=key_id,
            severity="warning",
        )
        return {"key_id": key_id, "revoked": True}

    # ---------------------------------------------------------
    # Budgets Management (Admin Only)
    # ---------------------------------------------------------

    @router.get("/budgets", response_model=list[BudgetPolicy])
    def list_budgets(_admin: AuthPrincipal = Depends(require_admin)) -> list[BudgetPolicy]:
        return budget_mgr.list_policies()

    @router.post("/budgets", response_model=BudgetPolicy)
    def set_budget(policy: BudgetPolicy, admin: AuthPrincipal = Depends(require_admin)) -> BudgetPolicy:
        budget_mgr.set_policy(policy)
        audit_log.record_event(
            event_type="budget.set",
            actor=admin.id,
            action="set_budget",
            resource=policy.entity_id,
            severity="info",
            details={"dimension": policy.dimension, "limit_usd": policy.limit_usd},
        )
        return policy

    @router.get("/budgets/alerts", response_model=list[BudgetAlert])
    def list_budget_alerts(_admin: AuthPrincipal = Depends(require_admin)) -> list[BudgetAlert]:
        return budget_mgr.get_alerts()

    # ---------------------------------------------------------
    # Audit Log (Admin Only)
    # ---------------------------------------------------------

    @router.get("/audit", response_model=list[AuditEvent])
    def query_audit_log(
        event_type: str | None = None,
        actor: str | None = None,
        severity: AuditSeverity | None = None,
        limit: int = Query(default=100, le=1000),
        _admin: AuthPrincipal = Depends(require_admin),
    ) -> list[AuditEvent]:
        return audit_log.query(event_type=event_type, actor=actor, severity=severity, limit=limit)

    @router.get("/audit/verify")
    def verify_audit_integrity(_admin: AuthPrincipal = Depends(require_admin)) -> dict[str, Any]:
        is_valid, message = audit_log.verify_integrity()
        return {"valid": is_valid, "message": message}

    # ---------------------------------------------------------
    # Human Approval Tokens (Authenticated Human Approvers Only)
    # ---------------------------------------------------------

    @router.post("/approval/tokens")
    def issue_approval_token(
        req: IssueTokenRequest,
        principal: AuthPrincipal = Depends(require_human_approver),
    ) -> dict[str, Any]:
        """Issue an approval token. The approver identity is bound strictly to the authenticated human principal."""
        authenticated_approver = principal.name or principal.id
        record, raw_token = effective_token_mgr.issue_token(
            action_name=req.action_name,
            target_resource=req.target_resource,
            approver=authenticated_approver,
            ttl_minutes=req.ttl_minutes,
            metadata=req.metadata,
        )
        audit_log.record_event(
            event_type="approval.token_issued",
            actor=authenticated_approver,
            action="issue_token",
            resource=req.target_resource,
            severity="info",
            details={
                "action": req.action_name,
                "token_id": record.token_id,
                "ttl": req.ttl_minutes,
                "approver_id": principal.id,
            },
        )
        return {
            "token_id": record.token_id,
            "raw_token": raw_token,
            "expires_at": record.expires_at,
            "approver": authenticated_approver,
        }

    @router.post("/approval/tokens/verify", response_model=ApprovalTokenRecord)
    def verify_approval_token(
        req: VerifyTokenRequest,
        principal: AuthPrincipal = Depends(get_current_principal),
    ) -> ApprovalTokenRecord:
        """Verify or consume an approval token. Callable by authenticated services/machines."""
        try:
            record = effective_token_mgr.verify_and_consume(
                raw_token=req.raw_token,
                action_name=req.action_name,
                target_resource=req.target_resource,
                dry_run=req.dry_run,
            )
            audit_log.record_event(
                event_type="approval.token_verified",
                actor=principal.id,
                action="verify_token" if req.dry_run else "consume_token",
                resource=req.target_resource,
                severity="info",
                details={"action": req.action_name, "dry_run": req.dry_run, "approver": record.approver},
            )
            return record
        except ApprovalRequiredError as exc:
            audit_log.record_event(
                event_type="approval.token_failed",
                actor=principal.id,
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
    def list_machines(
        status: MachineStatus | None = None,
        _admin: AuthPrincipal = Depends(require_admin),
    ) -> list[CLIMachine]:
        return machine_mgr.list_machines(status=status)

    @router.post("/machines/register", response_model=CLIMachine)
    def register_machine(
        req: RegisterMachineRequest,
        principal: AuthPrincipal = Depends(get_current_principal),
    ) -> CLIMachine:
        registered_by = principal.id
        machine = machine_mgr.register_machine(
            machine_id=req.machine_id,
            hostname=req.hostname,
            platform=req.platform,
            client_version=req.client_version,
            registered_by=registered_by,
            metadata=req.metadata,
        )
        audit_log.record_event(
            event_type="machine.registered",
            actor=registered_by,
            action="register",
            resource=req.machine_id,
            severity="info",
            details={"hostname": req.hostname, "platform": req.platform},
        )
        return machine

    @router.post("/machines/{machine_id}/approve", response_model=CLIMachine)
    def approve_machine(
        machine_id: str,
        admin: AuthPrincipal = Depends(require_admin),
    ) -> CLIMachine:
        try:
            approver_name = admin.name or admin.id
            machine = machine_mgr.approve_machine(machine_id, approver=approver_name)
            audit_log.record_event(
                event_type="machine.approved",
                actor=approver_name,
                action="approve",
                resource=machine_id,
                severity="info",
            )
            return machine
        except KeyError:
            raise HTTPException(status_code=404, detail="Machine not found") from None

    return router
