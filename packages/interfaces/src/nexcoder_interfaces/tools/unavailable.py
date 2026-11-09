from __future__ import annotations

from typing import Any

from nexcoder_interfaces.tools.base import unavailable_tool_handler


def capture_page(url: str, output_dir: str | None = None) -> dict[str, Any]:
    """Capture web page and DOM structure (nexcoder-capture)."""
    return unavailable_tool_handler("capture", "capture_page")


def generate_tests(page_or_spec: str, framework: str = "pytest") -> dict[str, Any]:
    """Generate tests from captured DOM or API specification (nexcoder-capture)."""
    return unavailable_tool_handler("capture", "generate_tests")


def serve_model(model_id: str, backend: str = "vllm") -> dict[str, Any]:
    """Serve LLM inference via vLLM or Ollama (nexcoder-serving)."""
    return unavailable_tool_handler("serving", "serve_model")


def evaluate_rag(dataset: str, metrics: list[str] | None = None) -> dict[str, Any]:
    """Run RAG evaluation suite and RAFT assessment (nexcoder-serving)."""
    return unavailable_tool_handler("serving", "evaluate_rag")


def check_budget(project_id: str) -> dict[str, Any]:
    """Query budget allocation and spending limit (nexcoder-control)."""
    return unavailable_tool_handler("control", "check_budget")


def audit_log(limit: int = 50) -> dict[str, Any]:
    """Query control plane audit trails (nexcoder-control)."""
    return unavailable_tool_handler("control", "audit_log")


def schedule_job(job_name: str, cron: str) -> dict[str, Any]:
    """Schedule continuous improvement pipeline job (nexcoder-continuous-improvement)."""
    return unavailable_tool_handler("continuous-improvement", "schedule_job")


def trigger_improvement(target: str) -> dict[str, Any]:
    """Trigger continuous scan and automatic issue generation (nexcoder-continuous-improvement)."""
    return unavailable_tool_handler("continuous-improvement", "trigger_improvement")
