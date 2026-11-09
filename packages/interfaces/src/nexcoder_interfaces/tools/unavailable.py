from __future__ import annotations

from typing import Any

from faccoder_interfaces.tools.base import unavailable_tool_handler


def capture_page(url: str, output_dir: str | None = None) -> dict[str, Any]:
    """Capture web page and DOM structure (faccoder-capture)."""
    return unavailable_tool_handler("capture", "capture_page")


def generate_tests(page_or_spec: str, framework: str = "pytest") -> dict[str, Any]:
    """Generate tests from captured DOM or API specification (faccoder-capture)."""
    return unavailable_tool_handler("capture", "generate_tests")


def serve_model(model_id: str, backend: str = "vllm") -> dict[str, Any]:
    """Serve LLM inference via vLLM or Ollama (faccoder-serving)."""
    return unavailable_tool_handler("serving", "serve_model")


def evaluate_rag(dataset: str, metrics: list[str] | None = None) -> dict[str, Any]:
    """Run RAG evaluation suite and RAFT assessment (faccoder-serving)."""
    return unavailable_tool_handler("serving", "evaluate_rag")


def check_budget(project_id: str) -> dict[str, Any]:
    """Query budget allocation and spending limit (faccoder-control)."""
    return unavailable_tool_handler("control", "check_budget")


def audit_log(limit: int = 50) -> dict[str, Any]:
    """Query control plane audit trails (faccoder-control)."""
    return unavailable_tool_handler("control", "audit_log")


def schedule_job(job_name: str, cron: str) -> dict[str, Any]:
    """Schedule continuous improvement pipeline job (faccoder-continuous-improvement)."""
    return unavailable_tool_handler("continuous-improvement", "schedule_job")


def trigger_improvement(target: str) -> dict[str, Any]:
    """Trigger continuous scan and automatic issue generation (faccoder-continuous-improvement)."""
    return unavailable_tool_handler("continuous-improvement", "trigger_improvement")
