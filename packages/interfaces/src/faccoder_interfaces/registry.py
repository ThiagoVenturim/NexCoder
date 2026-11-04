from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModuleInfo:
    name: str
    package_name: str
    description: str
    available_in_develop: bool
    tools: list[str] = field(default_factory=list)


KNOWN_MODULES: dict[str, ModuleInfo] = {
    "ideation": ModuleInfo(
        name="ideation",
        package_name="faccoder_ideation",
        description="Market and competitor research squad, jury committee, and PRD generation.",
        available_in_develop=True,
        tools=["research_idea", "judge_idea"],
    ),
    "planning": ModuleInfo(
        name="planning",
        package_name="faccoder_planning",
        description="Agentic sprint planning, backlog breakdown, and board synchronization.",
        available_in_develop=True,
        tools=["plan_sprints", "sync_board"],
    ),
    "code": ModuleInfo(
        name="code",
        package_name="faccoder_code_intel",
        description="Code search, AST symbol parsing, impact graph, and bottom-up docgen.",
        available_in_develop=True,
        tools=["search_code", "impact_analysis", "generate_docs"],
    ),
    "security": ModuleInfo(
        name="security",
        package_name="faccoder_security",
        description="Security scanning engine, specialist security agents, and release gate.",
        available_in_develop=True,
        tools=["security_scan"],
    ),
    "agents": ModuleInfo(
        name="agents",
        package_name="faccoder_agents",
        description="Multi-agent pipelines, block engine, agent catalog, and human approval gates.",
        available_in_develop=True,
        tools=["run_agent", "run_pipeline", "approve_step"],
    ),
    "capture": ModuleInfo(
        name="capture",
        package_name="faccoder_capture",
        description="Web page and screen capture with automated test generation.",
        available_in_develop=True,
        tools=["capture_page", "generate_tests"],
    ),
    "serving": ModuleInfo(
        name="serving",
        package_name="faccoder_serving",
        description="vLLM, Ollama serving, RAG evaluation, and RAFT fine-tuning.",
        available_in_develop=True,
        tools=["serve_model", "evaluate_rag"],
    ),
    "control": ModuleInfo(
        name="control",
        package_name="faccoder_control",
        description="Control plane: keys, cost, budgets, policy enforcement, and audit.",
        available_in_develop=False,
        tools=["check_budget", "audit_log"],
    ),
    "continuous-improvement": ModuleInfo(
        name="continuous-improvement",
        package_name="faccoder_continuous_improvement",
        description="Scheduled research, continuous scans, and automatic issue creation.",
        available_in_develop=True,
        tools=["schedule_job", "trigger_improvement"],
    ),
}


def is_module_installed(package_name: str) -> bool:
    """Check if a module package is present in Python environment."""
    return importlib.util.find_spec(package_name) is not None


def get_module_statuses() -> dict[str, dict[str, Any]]:
    """Return status summary for all known modules."""
    result: dict[str, dict[str, Any]] = {}
    for mod_id, info in KNOWN_MODULES.items():
        installed = is_module_installed(info.package_name)
        result[mod_id] = {
            "name": info.name,
            "package": info.package_name,
            "description": info.description,
            "available": installed,
            "expected_in_develop": info.available_in_develop,
            "tools": info.tools,
            "status": "available" if installed else "unavailable",
            "message": (
                "Module is ready and available."
                if installed
                else f"Module '{info.name}' is not yet available in this release."
            ),
        }
    return result


@dataclass
class ToolDefinition:
    name: str
    description: str
    module: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    is_available: bool = True
