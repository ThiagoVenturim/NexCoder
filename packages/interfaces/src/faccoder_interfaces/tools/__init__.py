from __future__ import annotations

from faccoder_interfaces.registry import ToolDefinition
from faccoder_interfaces.tools.agents import approve_step, run_agent, run_pipeline
from faccoder_interfaces.tools.base import unavailable_tool_handler
from faccoder_interfaces.tools.code import generate_docs, impact_analysis, search_code
from faccoder_interfaces.tools.ideation import judge_idea, research_idea
from faccoder_interfaces.tools.planning import plan_sprints, sync_board
from faccoder_interfaces.tools.security import security_scan
from faccoder_interfaces.tools.unavailable import (
    audit_log,
    capture_page,
    check_budget,
    evaluate_rag,
    generate_tests,
    schedule_job,
    serve_model,
    trigger_improvement,
)

TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    # Ideation
    "research_idea": ToolDefinition(
        name="research_idea",
        description="Research a software idea with specialist squad (market, competitors, differentiators, gaps).",
        module="ideation",
        parameters={
            "type": "object",
            "properties": {
                "idea": {"type": "string", "description": "Raw idea title or description."},
                "dry_run": {"type": "boolean", "default": True, "description": "Offline deterministic mode."},
                "domain_tags": {"type": "array", "items": {"type": "string"}, "description": "Optional domain tags."},
            },
            "required": ["idea"],
        },
        handler=research_idea,
        is_available=True,
    ),
    "judge_idea": ToolDefinition(
        name="judge_idea",
        description="Deliberate on an idea through the 6-member jury committee using standard rubric.",
        module="ideation",
        parameters={
            "type": "object",
            "properties": {
                "idea": {"type": "string", "description": "Idea title or problem statement."},
                "report_data": {"type": "object", "description": "Optional precomputed research report."},
                "dry_run": {"type": "boolean", "default": True, "description": "Offline deterministic mode."},
            },
            "required": ["idea"],
        },
        handler=judge_idea,
        is_available=True,
    ),
    # Planning
    "plan_sprints": ToolDefinition(
        name="plan_sprints",
        description="Convert PRD into epics, stories, and tasks, then allocate into sprint capacity.",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "prd_text": {"type": "string", "description": "Markdown PRD text."},
                "sprint_name": {"type": "string", "default": "Sprint 1", "description": "Sprint name."},
                "reserve_percentage": {"type": "number", "default": 0.20, "description": "Capacity buffer percentage."},
                "team": {"type": "array", "items": {"type": "object"}, "description": "Team member configs."},
            },
            "required": ["prd_text"],
        },
        handler=plan_sprints,
        is_available=True,
    ),
    "sync_board": ToolDefinition(
        name="sync_board",
        description="Synchronize backlog with GitHub/GitLab/Azure DevOps board and detect slippage.",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "default": "github", "description": "Target platform."},
                "repo": {"type": "string", "default": "local/repo", "description": "Target repository identifier."},
                "dry_run": {"type": "boolean", "default": True, "description": "Dry run without remote side effects."},
                "prd_text": {"type": "string", "description": "Optional PRD to build backlog."},
            },
        },
        handler=sync_board,
        is_available=True,
    ),
    # Code Intel
    "search_code": ToolDefinition(
        name="search_code",
        description="Search code across repository using lexical and symbol retrieval.",
        module="code",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "path": {"type": "string", "default": ".", "description": "Root path to search."},
                "limit": {"type": "integer", "default": 10, "description": "Max results to return."},
            },
            "required": ["query"],
        },
        handler=search_code,
        is_available=True,
    ),
    "impact_analysis": ToolDefinition(
        name="impact_analysis",
        description="Analyze blast radius and dependencies for a symbol across the code graph.",
        module="code",
        parameters={
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "Symbol name or identifier to analyze."},
                "path": {"type": "string", "default": ".", "description": "Root path containing codebase."},
                "max_depth": {"type": "integer", "default": 3, "description": "Max propagation depth."},
            },
            "required": ["symbol_name"],
        },
        handler=impact_analysis,
        is_available=True,
    ),
    "generate_docs": ToolDefinition(
        name="generate_docs",
        description="Synthesize bottom-up documentation from leaf symbols up to module level.",
        module="code",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": ".", "description": "Target path to document."},
                "level": {"type": "string", "default": "module", "description": "Hierarchy level."},
            },
        },
        handler=generate_docs,
        is_available=True,
    ),
    # Security
    "security_scan": ToolDefinition(
        name="security_scan",
        description="Run multi-scanner security analysis and evaluate release gate policy.",
        module="security",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": ".", "description": "Target directory to scan."},
                "policy": {"type": "string", "default": "default", "description": "Gate policy: default or strict."},
                "force_offline": {"type": "boolean", "default": True, "description": "Run in offline mode."},
            },
        },
        handler=security_scan,
        is_available=True,
    ),
    # Agents & Pipelines
    "run_agent": ToolDefinition(
        name="run_agent",
        description="Run a specialist agent from the catalog with a given task.",
        module="agents",
        parameters={
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent slug in catalog."},
                "task": {"type": "string", "description": "Task description to execute."},
                "inputs": {"type": "object", "description": "Optional prompt inputs."},
            },
            "required": ["agent_name", "task"],
        },
        handler=run_agent,
        is_available=True,
    ),
    "run_pipeline": ToolDefinition(
        name="run_pipeline",
        description="Execute a multi-block agentic pipeline graph.",
        module="agents",
        parameters={
            "type": "object",
            "properties": {
                "pipeline_name": {"type": "string", "description": "Name or template of the pipeline."},
                "inputs": {"type": "object", "description": "Pipeline execution inputs."},
                "dry_run": {"type": "boolean", "default": True, "description": "Offline dry-run mode."},
            },
            "required": ["pipeline_name"],
        },
        handler=run_pipeline,
        is_available=True,
    ),
    "approve_step": ToolDefinition(
        name="approve_step",
        description="Approve a paused pipeline approval gate using a secure token.",
        module="agents",
        parameters={
            "type": "object",
            "properties": {
                "action_name": {"type": "string", "description": "Action name corresponding to the gate."},
                "token": {"type": "string", "description": "Single-use approval secret token."},
                "execution_id": {"type": "string", "description": "Identifier of the paused execution."},
                "approver": {"type": "string", "default": "human", "description": "Identity of approver."},
            },
            "required": ["action_name", "token"],
        },
        handler=approve_step,
        is_available=True,
    ),
    # Unavailable tools (flagged cleanly as unavailable)
    "capture_page": ToolDefinition(
        name="capture_page",
        description="Capture page DOM and screenshot (faccoder-capture, not yet in develop).",
        module="capture",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL."},
            },
            "required": ["url"],
        },
        handler=capture_page,
        is_available=False,
    ),
    "generate_tests": ToolDefinition(
        name="generate_tests",
        description="Generate integration tests from captured DOM (faccoder-capture, not yet in develop).",
        module="capture",
        parameters={
            "type": "object",
            "properties": {
                "page_or_spec": {"type": "string", "description": "Page or spec identifier."},
            },
            "required": ["page_or_spec"],
        },
        handler=generate_tests,
        is_available=False,
    ),
    "serve_model": ToolDefinition(
        name="serve_model",
        description="Serve LLM inference via vLLM or Ollama (faccoder-serving, not yet in develop).",
        module="serving",
        parameters={
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID to serve."},
            },
            "required": ["model_id"],
        },
        handler=serve_model,
        is_available=False,
    ),
    "evaluate_rag": ToolDefinition(
        name="evaluate_rag",
        description="Run RAG evaluation suite (faccoder-serving, not yet in develop).",
        module="serving",
        parameters={
            "type": "object",
            "properties": {
                "dataset": {"type": "string", "description": "Evaluation dataset."},
            },
            "required": ["dataset"],
        },
        handler=evaluate_rag,
        is_available=False,
    ),
    "check_budget": ToolDefinition(
        name="check_budget",
        description="Check project spending and budget (faccoder-control, not yet in develop).",
        module="control",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID."},
            },
            "required": ["project_id"],
        },
        handler=check_budget,
        is_available=False,
    ),
    "audit_log": ToolDefinition(
        name="audit_log",
        description="Retrieve control plane audit logs (faccoder-control, not yet in develop).",
        module="control",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50, "description": "Max entries."},
            },
        },
        handler=audit_log,
        is_available=False,
    ),
    "schedule_job": ToolDefinition(
        name="schedule_job",
        description="Schedule continuous scans (faccoder-continuous-improvement, not yet in develop).",
        module="continuous-improvement",
        parameters={
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Job name."},
                "cron": {"type": "string", "description": "Cron expression."},
            },
            "required": ["job_name", "cron"],
        },
        handler=schedule_job,
        is_available=False,
    ),
    "trigger_improvement": ToolDefinition(
        name="trigger_improvement",
        description="Trigger continuous scan (faccoder-continuous-improvement, not yet in develop).",
        module="continuous-improvement",
        parameters={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target repository or path."},
            },
            "required": ["target"],
        },
        handler=trigger_improvement,
        is_available=False,
    ),
}

__all__ = [
    "TOOL_DEFINITIONS",
    "ToolDefinition",
    "approve_step",
    "audit_log",
    "capture_page",
    "check_budget",
    "evaluate_rag",
    "generate_docs",
    "generate_tests",
    "impact_analysis",
    "judge_idea",
    "plan_sprints",
    "research_idea",
    "run_agent",
    "run_pipeline",
    "schedule_job",
    "search_code",
    "security_scan",
    "serve_model",
    "sync_board",
    "trigger_improvement",
    "unavailable_tool_handler",
]
