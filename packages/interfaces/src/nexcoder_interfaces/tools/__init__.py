from __future__ import annotations

from nexcoder_interfaces.registry import ToolDefinition
from nexcoder_interfaces.tools.agents import approve_step, run_agent, run_pipeline
from nexcoder_interfaces.tools.base import unavailable_tool_handler
from nexcoder_interfaces.tools.code import generate_docs, impact_analysis, search_code
from nexcoder_interfaces.tools.email import send_email
from nexcoder_interfaces.tools.ideation import judge_idea, research_idea
from nexcoder_interfaces.tools.planning import (
    estimate_product_cost,
    plan_sprints,
    productivity_report,
    sync_board,
)
from nexcoder_interfaces.tools.security import security_report, security_review, security_scan
from nexcoder_interfaces.tools.testing import (
    cancel_security_test,
    export_security_test_report,
    get_security_test_canvas,
    get_security_test_status,
    trigger_security_tests,
    verify_security_test_target,
)
from nexcoder_interfaces.tools.unavailable import (
    audit_log,
    capture_page,
    check_budget,
    evaluate_rag,
    generate_tests,
    schedule_job,
    serve_model,
    trigger_improvement,
)
from nexcoder_interfaces.tools.vcs import (
    vcs_audit_records,
    vcs_list_repositories,
    vcs_manage_issue,
    vcs_manage_pull_request,
    vcs_svn_operation,
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
    "productivity_report": ToolDefinition(
        name="productivity_report",
        description="Build a developer productivity dashboard via NexDash (GitHub, Azure DevOps, Redmine).",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "project": {"type": "string", "default": "nexcoder-platform", "description": "Project identifier."},
                "team": {"type": "string", "default": "core-engineering", "description": "Team name."},
                "period": {"type": "string", "default": "2026-Q4", "description": "Reporting period."},
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Platforms to query (github, azure_devops, redmine).",
                },
                "transport": {
                    "type": "string",
                    "default": "offline",
                    "description": "NexDash transport (offline, mcp, rest).",
                },
            },
        },
        handler=productivity_report,
        is_available=True,
    ),
    "estimate_product_cost": ToolDefinition(
        name="estimate_product_cost",
        description="Estimate product lifecycle cost (build, publish, maintain mes/ano, licenca e marca).",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Product or project name."},
                "complexity": {"type": "string", "default": "medium", "description": "Scope complexity tier."},
                "feature_count": {"type": "integer", "default": 10, "description": "Number of product features."},
                "mode": {"type": "string", "default": "hybrid", "description": "Delivery execution mode."},
                "infra_target": {"type": "string", "default": "hetzner", "description": "Infra provider target."},
                "infra_tier": {"type": "string", "default": "standard", "description": "Infra sizing tier."},
                "domain_tld": {"type": "string", "default": "com_br", "description": "Domain TLD code."},
                "currency": {"type": "string", "default": "BRL", "description": "Currency (BRL or USD)."},
                "include_proposal": {"type": "boolean", "default": False, "description": "Generate proposal."},
            },
            "required": ["project_name"],
        },
        handler=estimate_product_cost,
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
                "owned_target": {
                    "type": "boolean",
                    "default": False,
                    "description": "Confirm target is owned or explicitly authorized per USAGE_POLICY.md.",
                },
                "authorized_by": {
                    "type": "string",
                    "default": "owner",
                    "description": "Identity of the owner or authorizer recorded in the audit log.",
                },
                "approval_token": {
                    "type": "string",
                    "description": "Optional single-use control plane approval token.",
                },
            },
        },
        handler=security_scan,
        is_available=True,
    ),
    "security_review": ToolDefinition(
        name="security_review",
        description=(
            "Run responsible-disclosure security review (prompt injection, SQLi, data leakage, general security)."
        ),
        module="security",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": ".", "description": "Target directory or file to review."},
                "owned_target": {
                    "type": "boolean",
                    "default": False,
                    "description": "Confirm target is owned or explicitly authorized per USAGE_POLICY.md.",
                },
                "authorized_by": {
                    "type": "string",
                    "default": "owner",
                    "description": "Identity of the owner or authorizer recorded in the audit log.",
                },
                "approval_token": {
                    "type": "string",
                    "description": "Optional single-use control plane approval token.",
                },
                "enable_runtime_monitor": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable optional runtime prompt/tool monitor.",
                },
                "oss_contribution_mode": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable OSS contribution responsible disclosure mode.",
                },
            },
        },
        handler=security_review,
        is_available=True,
    ),
    "security_report": ToolDefinition(
        name="security_report",
        description="Build a security posture and gate coverage dashboard via NexDash.",
        module="security",
        parameters={
            "type": "object",
            "properties": {
                "project": {"type": "string", "default": "nexcoder-platform", "description": "Project identifier."},
                "period": {"type": "string", "default": "2026-Q4", "description": "Reporting period."},
                "policy": {"type": "string", "default": "default", "description": "Gate policy (default or strict)."},
                "transport": {
                    "type": "string",
                    "default": "offline",
                    "description": "NexDash transport (offline, mcp, rest).",
                },
            },
        },
        handler=security_report,
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
        description="Capture page DOM and screenshot (nexcoder-capture, not yet in develop).",
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
        description="Generate integration tests from captured DOM (nexcoder-capture, not yet in develop).",
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
        description="Serve LLM inference via vLLM or Ollama (nexcoder-serving, not yet in develop).",
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
        description="Run RAG evaluation suite (nexcoder-serving, not yet in develop).",
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
        description="Check project spending and budget (nexcoder-control, not yet in develop).",
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
        description="Retrieve control plane audit logs (nexcoder-control, not yet in develop).",
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
        description="Schedule continuous scans (nexcoder-continuous-improvement, not yet in develop).",
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
        description="Trigger continuous scan (nexcoder-continuous-improvement, not yet in develop).",
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
    "send_email": ToolDefinition(
        name="send_email",
        description="Send an email report or proposal from user account with human approval and audit logging.",
        module="control",
        parameters={
            "type": "object",
            "properties": {
                "recipients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of recipient emails.",
                },
                "subject": {"type": "string", "description": "Email subject line."},
                "body_text": {"type": "string", "description": "Plain text message content."},
                "body_html": {"type": "string", "description": "HTML message content."},
                "attachments": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional file attachments.",
                },
                "template_name": {"type": "string", "description": "Name of reusable template."},
                "template_vars": {"type": "object", "description": "Template variables."},
                "provider": {"type": "string", "description": "Provider (gmail, outlook, smtp)."},
                "approval_token": {"type": "string", "description": "Human approval token secret."},
                "confirmed": {
                    "type": "boolean",
                    "default": False,
                    "description": "Explicit human confirmation flag.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Simulate send without actual network dispatch.",
                },
            },
            "required": ["recipients", "subject"],
        },
        handler=send_email,
        is_available=True,
    ),
    # Extreme Quality & Security Testing (NexHub Integration)
    "trigger_security_tests": ToolDefinition(
        name="trigger_security_tests",
        description=(
            "Dispatch multi-agent extreme testing (unit, system, process, DOM, API, security) for an authorized target."
        ),
        module="testing",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": ".", "description": "Target workspace or repo directory."},
                "test_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Suites to execute: unit, system, process, dom, api, security.",
                },
                "num_agents": {"type": "integer", "default": 4, "description": "Number of testing agents."},
                "budget_limit": {"type": "number", "default": 50.0, "description": "Maximum spending budget."},
                "budget_currency": {"type": "string", "default": "USD", "description": "Budget currency code."},
                "owned_target": {
                    "type": "boolean",
                    "default": False,
                    "description": "Confirm target is owned or authorized per USAGE_POLICY.md.",
                },
                "authorized_by": {
                    "type": "string",
                    "default": "owner",
                    "description": "Identity of authorizer for audit log.",
                },
                "approval_token": {"type": "string", "description": "Single-use approval token."},
                "offline": {"type": "boolean", "default": True, "description": "Run strictly offline with mocks."},
            },
        },
        handler=trigger_security_tests,
        is_available=True,
    ),
    "get_security_test_status": ToolDefinition(
        name="get_security_test_status",
        description="Retrieve execution status, per-agent logs, and progress for an active or completed test run.",
        module="testing",
        parameters={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Identifier of the test run."},
            },
            "required": ["run_id"],
        },
        handler=get_security_test_status,
        is_available=True,
    ),
    "get_security_test_canvas": ToolDefinition(
        name="get_security_test_canvas",
        description="Retrieve full NexHub canvas payload (cards, markdown notes, connections) for visualization.",
        module="testing",
        parameters={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Identifier of the test run."},
            },
            "required": ["run_id"],
        },
        handler=get_security_test_canvas,
        is_available=True,
    ),
    "verify_security_test_target": ToolDefinition(
        name="verify_security_test_target",
        description="Preflight target verification to check whether workspace is authorized for extreme testing.",
        module="testing",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": ".", "description": "Target workspace path."},
                "owned_target": {"type": "boolean", "default": False, "description": "Owned confirmation flag."},
                "authorized_by": {"type": "string", "default": "owner", "description": "Authorizer identity."},
                "approval_token": {"type": "string", "description": "Single-use approval token."},
            },
        },
        handler=verify_security_test_target,
        is_available=True,
    ),
    "cancel_security_test": ToolDefinition(
        name="cancel_security_test",
        description="Cancel an ongoing test run.",
        module="testing",
        parameters={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Identifier of the test run."},
            },
            "required": ["run_id"],
        },
        handler=cancel_security_test,
        is_available=True,
    ),
    "export_security_test_report": ToolDefinition(
        name="export_security_test_report",
        description="Export the consolidated test and security report as Markdown or raw JSON.",
        module="testing",
        parameters={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Identifier of the test run."},
                "format": {"type": "string", "default": "markdown", "description": "Format: markdown or json."},
            },
            "required": ["run_id"],
        },
        handler=export_security_test_report,
        is_available=True,
    ),
    # VCS and Repository Management
    "vcs_list_repositories": ToolDefinition(
        name="vcs_list_repositories",
        description="List repositories from Azure DevOps, GitLab, or Git.",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "VCS provider (azure_devops, gitlab, git)."},
                "project_or_org": {"type": "string", "description": "Organization or project identifier."},
                "project": {"type": "string", "description": "Project name for Azure DevOps."},
            },
            "required": ["provider"],
        },
        handler=vcs_list_repositories,
        is_available=True,
    ),
    "vcs_manage_issue": ToolDefinition(
        name="vcs_manage_issue",
        description="Create, read, update, or list issues on Azure DevOps or GitLab.",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "VCS provider (azure_devops, gitlab)."},
                "action": {"type": "string", "description": "Action (list, get, create, update)."},
                "project_or_org": {"type": "string", "description": "Organization or project ID."},
                "project": {"type": "string", "description": "Project name."},
                "issue_id": {"type": "string", "description": "Issue or work item ID."},
                "title": {"type": "string", "description": "Issue title."},
                "body": {"type": "string", "description": "Issue body markdown."},
            },
            "required": ["provider"],
        },
        handler=vcs_manage_issue,
        is_available=True,
    ),
    "vcs_manage_pull_request": ToolDefinition(
        name="vcs_manage_pull_request",
        description="Create, read, list, or merge pull requests or merge requests.",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "VCS provider (azure_devops, gitlab)."},
                "action": {"type": "string", "description": "Action (list, get, create, merge)."},
                "project_or_org": {"type": "string", "description": "Organization or project ID."},
                "project": {"type": "string", "description": "Project name."},
                "pr_id": {"type": "string", "description": "Pull request ID."},
                "title": {"type": "string", "description": "Pull request title."},
                "body": {"type": "string", "description": "Pull request body."},
                "source_branch": {"type": "string", "description": "Source branch."},
                "target_branch": {"type": "string", "description": "Target branch."},
            },
            "required": ["provider"],
        },
        handler=vcs_manage_pull_request,
        is_available=True,
    ),
    "vcs_svn_operation": ToolDefinition(
        name="vcs_svn_operation",
        description="Execute Subversion operations (checkout, commit, log, diff, status).",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "SVN action (checkout, commit, log, diff, status)."},
                "repo_url": {"type": "string", "description": "Repository URL for checkout."},
                "dest_path": {"type": "string", "description": "Destination working copy path."},
                "message": {"type": "string", "description": "Commit message."},
                "revision": {"type": "string", "description": "Revision number or HEAD."},
            },
            "required": ["action"],
        },
        handler=vcs_svn_operation,
        is_available=True,
    ),
    "vcs_audit_records": ToolDefinition(
        name="vcs_audit_records",
        description="Retrieve structured audit log records of recent repository actions.",
        module="planning",
        parameters={
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "Filter by provider name."},
                "limit": {"type": "integer", "description": "Maximum number of records to return."},
            },
        },
        handler=vcs_audit_records,
        is_available=True,
    ),
}

__all__ = [
    "TOOL_DEFINITIONS",
    "ToolDefinition",
    "approve_step",
    "audit_log",
    "cancel_security_test",
    "capture_page",
    "check_budget",
    "estimate_product_cost",
    "evaluate_rag",
    "export_security_test_report",
    "generate_docs",
    "generate_tests",
    "get_security_test_canvas",
    "get_security_test_status",
    "impact_analysis",
    "judge_idea",
    "plan_sprints",
    "productivity_report",
    "research_idea",
    "run_agent",
    "run_pipeline",
    "schedule_job",
    "search_code",
    "security_report",
    "security_review",
    "security_scan",
    "send_email",
    "serve_model",
    "sync_board",
    "trigger_improvement",
    "trigger_security_tests",
    "unavailable_tool_handler",
    "verify_security_test_target",
    "vcs_audit_records",
    "vcs_list_repositories",
    "vcs_manage_issue",
    "vcs_manage_pull_request",
    "vcs_svn_operation",
]
