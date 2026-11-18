from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from nexcoder_interfaces.api.sse import format_sse_event, pipeline_event_generator
from nexcoder_interfaces.mcp.server import MCPServer
from nexcoder_interfaces.registry import get_module_statuses
from nexcoder_interfaces.tools import TOOL_DEFINITIONS

router = APIRouter()
mcp_server = MCPServer()


class ToolInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class IdeationResearchRequest(BaseModel):
    idea: str
    dry_run: bool = True
    domain_tags: list[str] | None = None


class IdeationJudgeRequest(BaseModel):
    idea: str
    report_data: dict[str, Any] | None = None
    dry_run: bool = True


class PlanningSprintsRequest(BaseModel):
    prd_text: str
    sprint_name: str = "Sprint 1"
    reserve_percentage: float = 0.20
    team: list[dict[str, Any]] | None = None


class PlanningSyncRequest(BaseModel):
    platform: str = "github"
    repo: str = "local/repo"
    dry_run: bool = True
    prd_text: str | None = None


class PlanningCostRequest(BaseModel):
    project_name: str
    complexity: str = "medium"
    feature_count: int = 10
    estimated_screens: int = 5
    estimated_endpoints: int = 12
    mode: str = "hybrid"
    infra_target: str = "hetzner"
    infra_tier: str = "standard"
    domain_tld: str = "com_br"
    trademark_jurisdiction: str = "inpi_br"
    currency: str = "BRL"
    exchange_rate: float = 5.50
    include_proposal: bool = False
    client_name: str = "Cliente"


class CodeSearchRequest(BaseModel):
    query: str
    path: str = "."
    limit: int = 10


class CodeImpactRequest(BaseModel):
    symbol_name: str
    path: str = "."
    max_depth: int = 3


class CodeDocsRequest(BaseModel):
    path: str = "."
    level: str = "module"


class SecurityScanRequest(BaseModel):
    path: str = "."
    policy: str = "default"
    force_offline: bool = True
    owned_target: bool = False
    authorized_by: str = "owner"
    approval_token: str | None = None


class ProductivityReportRequest(BaseModel):
    project: str = "nexcoder-platform"
    team: str = "core-engineering"
    period: str = "2026-Q4"
    platforms: list[str] | None = None
    transport: str = "offline"


class SecurityReportRequest(BaseModel):
    project: str = "nexcoder-platform"
    period: str = "2026-Q4"
    policy: str = "default"
    transport: str = "offline"


class SecurityCampaignRunRequest(BaseModel):
    target: str = "."
    test_types: list[str] | None = None
    agent_count: int = 3
    allowed_scope: list[str] | None = None
    max_cost_usd: float = 5.0
    max_duration_seconds: float = 120.0
    owned_target: bool = False
    authorized_by: str = "owner"
    authorization_document: Any | None = None
    require_signed_document: bool = False
    dry_run: bool = True


class AgentRunRequest(BaseModel):
    agent_name: str
    task: str
    inputs: dict[str, Any] | None = None


class PipelineRunRequest(BaseModel):
    pipeline_name: str
    inputs: dict[str, Any] | None = None
    dry_run: bool = True


class PipelineApproveRequest(BaseModel):
    action_name: str
    token: str
    execution_id: str | None = None
    target_resource: str = "pipeline"


class SecurityTestPreflightRequest(BaseModel):
    path: str = "."
    owned_target: bool = False
    authorized_by: str = "owner"
    approval_token: str | None = None


class SecurityTestRunRequest(BaseModel):
    path: str = "."
    test_types: list[str] | None = None
    num_agents: int = 4
    budget_limit: float = 50.0
    budget_currency: str = "USD"
    owned_target: bool = False
    authorized_by: str = "owner"
    approval_token: str | None = None
    offline: bool = True


class SecurityTestCancelRequest(BaseModel):
    run_id: str


@router.get("/health")
@router.get("/v1/health")
def get_health() -> dict[str, Any]:
    """Health check endpoint indicating service availability and loaded modules."""
    statuses = get_module_statuses()
    available_count = sum(1 for s in statuses.values() if s["available"])
    return {
        "status": "ok",
        "service": "nexcoder-interfaces",
        "version": "0.1.0",
        "available_modules": available_count,
        "total_modules": len(statuses),
        "modules": statuses,
    }


@router.get("/v1/capabilities")
def get_capabilities() -> dict[str, Any]:
    """List all registered capabilities, tools, and module statuses."""
    tools_list = []
    for _name, tool in TOOL_DEFINITIONS.items():
        tools_list.append(
            {
                "name": tool.name,
                "description": tool.description,
                "module": tool.module,
                "is_available": tool.is_available,
                "parameters": tool.parameters,
            }
        )

    return {
        "modules": get_module_statuses(),
        "tools": tools_list,
        "mcp_enabled": True,
        "sse_enabled": True,
    }


@router.post("/v1/tools/{tool_name}")
def invoke_tool(tool_name: str, payload: ToolInvokeRequest) -> dict[str, Any]:
    """Invoke any registered tool by name with arguments."""
    if tool_name not in TOOL_DEFINITIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' is not recognized.",
        )

    tool = TOOL_DEFINITIONS[tool_name]
    try:
        result = tool.handler(**payload.arguments)
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error executing tool '{tool_name}': {exc}",
        ) from exc


# Specialized /v1 endpoints
@router.post("/v1/ideation/research")
def endpoint_ideation_research(req: IdeationResearchRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["research_idea"].handler(
        idea=req.idea,
        dry_run=req.dry_run,
        domain_tags=req.domain_tags,
    )


@router.post("/v1/ideation/judge")
def endpoint_ideation_judge(req: IdeationJudgeRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["judge_idea"].handler(
        idea=req.idea,
        report_data=req.report_data,
        dry_run=req.dry_run,
    )


@router.post("/v1/planning/sprints")
def endpoint_planning_sprints(req: PlanningSprintsRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["plan_sprints"].handler(
        prd_text=req.prd_text,
        sprint_name=req.sprint_name,
        reserve_percentage=req.reserve_percentage,
        team=req.team,
    )


@router.post("/v1/planning/sync")
def endpoint_planning_sync(req: PlanningSyncRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["sync_board"].handler(
        platform=req.platform,
        repo=req.repo,
        dry_run=req.dry_run,
        prd_text=req.prd_text,
    )


@router.post("/v1/planning/cost")
def endpoint_planning_cost(req: PlanningCostRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["estimate_product_cost"].handler(
        project_name=req.project_name,
        complexity=req.complexity,
        feature_count=req.feature_count,
        estimated_screens=req.estimated_screens,
        estimated_endpoints=req.estimated_endpoints,
        mode=req.mode,
        infra_target=req.infra_target,
        infra_tier=req.infra_tier,
        domain_tld=req.domain_tld,
        trademark_jurisdiction=req.trademark_jurisdiction,
        currency=req.currency,
        exchange_rate=req.exchange_rate,
        include_proposal=req.include_proposal,
        client_name=req.client_name,
    )


@router.post("/v1/code/search")
def endpoint_code_search(req: CodeSearchRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["search_code"].handler(
        query=req.query,
        path=req.path,
        limit=req.limit,
    )


@router.post("/v1/code/impact")
def endpoint_code_impact(req: CodeImpactRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["impact_analysis"].handler(
        symbol_name=req.symbol_name,
        path=req.path,
        max_depth=req.max_depth,
    )


@router.post("/v1/code/docs")
def endpoint_code_docs(req: CodeDocsRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["generate_docs"].handler(
        path=req.path,
        level=req.level,
    )


@router.post("/v1/security/scan")
def endpoint_security_scan(req: SecurityScanRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["security_scan"].handler(
        path=req.path,
        policy=req.policy,
        force_offline=req.force_offline,
        owned_target=req.owned_target,
        authorized_by=req.authorized_by,
        approval_token=req.approval_token,
    )


@router.post("/v1/reports/productivity")
def endpoint_reports_productivity(req: ProductivityReportRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["productivity_report"].handler(
        project=req.project,
        team=req.team,
        period=req.period,
        platforms=req.platforms,
        transport=req.transport,
    )


@router.post("/v1/reports/security")
def endpoint_reports_security(req: SecurityReportRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["security_report"].handler(
        project=req.project,
        period=req.period,
        policy=req.policy,
        transport=req.transport,
    )


@router.post("/v1/security/campaigns/run")
def endpoint_security_campaigns_run(req: SecurityCampaignRunRequest) -> dict[str, Any]:
    """Trigger an orchestrated security and quality test campaign."""
    res = TOOL_DEFINITIONS["run_security_test_campaign"].handler(
        target=req.target,
        test_types=req.test_types,
        agent_count=req.agent_count,
        allowed_scope=req.allowed_scope,
        max_cost_usd=req.max_cost_usd,
        max_duration_seconds=req.max_duration_seconds,
        owned_target=req.owned_target,
        authorized_by=req.authorized_by,
        authorization_document=req.authorization_document,
        require_signed_document=req.require_signed_document,
        dry_run=req.dry_run,
    )
    if res.get("status") == "rejected":
        raise HTTPException(status_code=403, detail=res.get("reason", "Target authorization denied"))
    return res


@router.get("/v1/security/campaigns")
def endpoint_security_campaigns_list(limit: int = 50) -> dict[str, Any]:
    """List historical and active testing campaigns."""
    from nexcoder_security.campaign import get_global_registry

    registry = get_global_registry()
    return {"campaigns": registry.list_campaigns(limit=limit)}


@router.get("/v1/security/campaigns/{campaign_id}")
def endpoint_security_campaigns_get(campaign_id: str) -> dict[str, Any]:
    """Retrieve detailed campaign status and findings."""
    res = TOOL_DEFINITIONS["get_security_test_campaign"].handler(campaign_id=campaign_id)
    if res.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found")
    return res


@router.get("/v1/security/campaigns/{campaign_id}/report")
def endpoint_security_campaigns_report(
    campaign_id: str,
    format: str = Query(default="json"),
) -> Any:
    """Retrieve exported campaign report (json, markdown, html)."""
    res = TOOL_DEFINITIONS["export_security_campaign_report"].handler(campaign_id=campaign_id, format=format)
    if res.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found")
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Export error"))

    content = res.get("content", "")
    if format.lower() in ("html", "htm"):
        from fastapi.responses import HTMLResponse

        return HTMLResponse(content=content)
    if format.lower() in ("markdown", "md"):
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(content=content, media_type="text/markdown")
    return res


@router.post("/v1/agents/run")
def endpoint_agents_run(req: AgentRunRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["run_agent"].handler(
        agent_name=req.agent_name,
        task=req.task,
        inputs=req.inputs,
    )


@router.post("/v1/pipelines/run")
def endpoint_pipelines_run(req: PipelineRunRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["run_pipeline"].handler(
        pipeline_name=req.pipeline_name,
        inputs=req.inputs,
        dry_run=req.dry_run,
    )


@router.post("/v1/pipelines/approve")
def endpoint_pipelines_approve(
    req: PipelineApproveRequest,
    request: Request,
) -> dict[str, Any]:
    # 1. An agent/machine API key cannot approve pipeline gates
    is_human = getattr(request.state, "is_human", False)
    if not is_human:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Pipeline actions require approval by a human approver, not an agent API key.",
        )

    # 2. Approver is strictly taken from authenticated human principal, never request body
    approver_name = getattr(request.state, "principal_name", "authenticated_human")
    if hasattr(request.state, "principal") and getattr(request.state.principal, "name", None):
        approver_name = request.state.principal.name

    from nexcoder_interfaces.tools.agents import GLOBAL_EXECUTION_REGISTRY

    token_manager = getattr(request.app.state, "approval_token_manager", None)
    has_pending_execution = bool(
        (req.execution_id and GLOBAL_EXECUTION_REGISTRY.get(req.execution_id))
        or GLOBAL_EXECUTION_REGISTRY.find_by_action(req.action_name)
    )

    if has_pending_execution or token_manager is None:
        res = TOOL_DEFINITIONS["approve_step"].handler(
            action_name=req.action_name,
            token=req.token,
            execution_id=req.execution_id,
            approver=approver_name,
        )
        if not res.get("approved"):
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: {res.get('reason', 'Approval rejected')}",
            )
        return res

    # Otherwise verify control plane approval token
    try:
        record = token_manager.verify_and_consume(
            raw_token=req.token,
            action_name=req.action_name,
            target_resource=req.target_resource,
            dry_run=False,
        )
        return {
            "status": "approved",
            "action_name": req.action_name,
            "approved": True,
            "approver": record.approver or approver_name,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: Invalid or expired human approval token: {exc}",
        ) from exc


@router.get("/v1/pipelines/stream")
@router.post("/v1/pipelines/stream")
async def endpoint_pipelines_stream(
    pipeline_name: str = Query(default="release_pipeline"),
    task: str = Query(default="build and scan"),
) -> StreamingResponse:
    """Stream pipeline events over SSE."""
    inputs = {"task": task}
    gen = pipeline_event_generator(pipeline_name=pipeline_name, inputs=inputs)
    return StreamingResponse(gen, media_type="text/event-stream")


# Extreme Testing / NexHub Canvas Endpoints
@router.post("/v1/security-tests/preflight")
def endpoint_security_tests_preflight(req: SecurityTestPreflightRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["verify_security_test_target"].handler(
        path=req.path,
        owned_target=req.owned_target,
        authorized_by=req.authorized_by,
        approval_token=req.approval_token,
    )


@router.post("/v1/security-tests/run")
def endpoint_security_tests_run(req: SecurityTestRunRequest) -> dict[str, Any]:
    return TOOL_DEFINITIONS["trigger_security_tests"].handler(
        path=req.path,
        test_types=req.test_types,
        num_agents=req.num_agents,
        budget_limit=req.budget_limit,
        budget_currency=req.budget_currency,
        owned_target=req.owned_target,
        authorized_by=req.authorized_by,
        approval_token=req.approval_token,
        offline=req.offline,
    )


@router.get("/v1/security-tests/runs/{run_id}")
def endpoint_security_tests_status(run_id: str) -> dict[str, Any]:
    return TOOL_DEFINITIONS["get_security_test_status"].handler(run_id=run_id)


@router.get("/v1/security-tests/runs/{run_id}/canvas")
def endpoint_security_tests_canvas(run_id: str) -> dict[str, Any]:
    return TOOL_DEFINITIONS["get_security_test_canvas"].handler(run_id=run_id)


@router.get("/v1/security-tests/runs/{run_id}/report")
def endpoint_security_tests_report(
    run_id: str,
    format: str = Query(default="markdown"),
) -> dict[str, Any]:
    return TOOL_DEFINITIONS["export_security_test_report"].handler(run_id=run_id, format=format)


@router.post("/v1/security-tests/runs/{run_id}/cancel")
def endpoint_security_tests_cancel(run_id: str) -> dict[str, Any]:
    return TOOL_DEFINITIONS["cancel_security_test"].handler(run_id=run_id)


@router.get("/v1/security-tests/runs/{run_id}/stream")
async def endpoint_security_tests_stream(run_id: str) -> StreamingResponse:
    """Stream live test run progress and findings events over SSE."""
    from nexcoder_interfaces.testing.service import GLOBAL_SECURITY_TEST_SERVICE

    async def event_generator():
        async for evt in GLOBAL_SECURITY_TEST_SERVICE.stream_run_events(run_id):
            yield format_sse_event(evt, event=evt.get("event", "message"))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# MCP SSE Endpoints
@router.get("/sse")
async def endpoint_mcp_sse(request: Request) -> StreamingResponse:
    """Establish MCP SSE transport session."""
    session_id, queue = mcp_server.create_sse_session()

    async def event_stream():
        # First event: endpoint URI with session_id
        yield format_sse_event(f"/messages?session_id={session_id}", event="endpoint")
        try:
            while True:
                # Poll or wait for enqueued responses
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield format_sse_event(data, event="message")
                except TimeoutError:
                    # Keep-alive ping
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            mcp_server.close_sse_session(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/messages")
async def endpoint_mcp_messages(
    request: Request,
    session_id: str | None = Query(default=None),
) -> JSONResponse:
    """Receive MCP JSON-RPC message."""
    raw_body = (await request.body()).decode("utf-8")
    if session_id:
        resp = await mcp_server.post_sse_message(session_id, raw_body)
    else:
        resp = mcp_server.handle_message_json(raw_body)

    if resp:
        return JSONResponse(content=resp if isinstance(resp, (dict, list)) else {"raw_response": resp})
    return JSONResponse(content={"status": "accepted"})
