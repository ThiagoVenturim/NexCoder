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
