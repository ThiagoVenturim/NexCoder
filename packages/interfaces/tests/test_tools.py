from __future__ import annotations

from pathlib import Path

from faccoder_interfaces.tools import (
    TOOL_DEFINITIONS,
    approve_step,
    capture_page,
    generate_docs,
    generate_tests,
    impact_analysis,
    judge_idea,
    plan_sprints,
    research_idea,
    run_agent,
    run_pipeline,
    search_code,
    security_scan,
    sync_board,
)


def test_tool_definitions_registry() -> None:
    expected_tools = [
        "research_idea",
        "judge_idea",
        "plan_sprints",
        "sync_board",
        "search_code",
        "impact_analysis",
        "generate_docs",
        "security_scan",
        "run_agent",
        "run_pipeline",
        "approve_step",
        "capture_page",
        "generate_tests",
    ]
    for tool_name in expected_tools:
        assert tool_name in TOOL_DEFINITIONS
        tool = TOOL_DEFINITIONS[tool_name]
        assert tool.name == tool_name
        assert "type" in tool.parameters
        assert callable(tool.handler)


def test_research_idea_offline() -> None:
    res = research_idea("Automated Bug Reproduction Engine", dry_run=True)
    assert res["status"] == "success"
    assert "title" in res
    assert "market" in res
    assert len(res["competitors"]) >= 1


def test_judge_idea_offline() -> None:
    res = judge_idea("Autonomous Bug Reproduction Engine", dry_run=True)
    assert res["status"] == "success"
    assert res["verdict"] in ("go", "pivot", "no_go")
    assert res["total_jurors"] == 6
    assert len(res["ballots"]) == 6


def test_plan_sprints_offline() -> None:
    sample_prd = """# PRD: User Auth
# Epic: Auth Epic
## Story: JWT Token
### Task: Generate Token
- Layer: backend
- Estimate: 4.0h
- Given credentials
- When logged in
- Then return token
"""
    res = plan_sprints(prd_text=sample_prd, sprint_name="Sprint 1")
    assert res["status"] == "success"
    assert res["tasks_count"] == 1
    assert len(res["scheduled_tasks"]) == 1
    assert res["capacity_report"]["sprint_name"] == "Sprint 1"


def test_sync_board_offline() -> None:
    res = sync_board(platform="github", repo="owner/repo", dry_run=True)
    assert res["status"] == "success"
    assert res["dry_run"] is True
    assert res["platform"] == "github"


def test_search_code_offline(tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def calculate_tax(amount: float) -> float:\n    return amount * 0.2\n", encoding="utf-8")
    res = search_code(query="calculate_tax", path=str(tmp_path))
    assert res["status"] == "success"
    assert res["total_symbols_indexed"] >= 1


def test_impact_analysis_offline(tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("class Database:\n    def connect(self): pass\n", encoding="utf-8")
    res = impact_analysis(symbol_name="Database", path=str(tmp_path))
    assert res["status"] in ("success", "not_found")


def test_generate_docs_offline(tmp_path: Path) -> None:
    code_file = tmp_path / "module.py"
    code_file.write_text("def worker(task_id: int) -> None:\n    pass\n", encoding="utf-8")
    res = generate_docs(path=str(tmp_path), level="module")
    assert res["status"] == "success"
    assert res["symbols_parsed"] >= 1


def test_security_scan_offline(tmp_path: Path) -> None:
    safe_file = tmp_path / "clean.py"
    safe_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    res = security_scan(path=str(tmp_path), force_offline=True)
    assert res["status"] == "success"
    assert "passed_gate" in res


def test_run_agent_offline() -> None:
    res = run_agent(agent_name="lead-architect", task="Review microservice architecture")
    assert res["status"] == "success"
    assert res["agent"]["slug"] == "lead-architect"
    assert "rendered_prompt" in res


def test_run_pipeline_offline() -> None:
    res = run_pipeline(pipeline_name="sample_pipeline", inputs={"task": "execute test"}, dry_run=True)
    assert res["status"] == "success"
    assert res["run_status"] in ("completed", "waiting_approval")


def test_approve_step_offline() -> None:
    res = approve_step(action_name="deploy", token="valid_test_token_12345", approver="qa-lead")
    assert res["status"] == "approved"
    assert res["approved"] is True
    assert res["approver"] == "qa-lead"


def test_unavailable_tools() -> None:
    cap_res = capture_page("https://example.com")
    assert cap_res["status"] == "unavailable"
    assert cap_res["module"] == "capture"

    gen_res = generate_tests("spec_v1")
    assert gen_res["status"] == "unavailable"
    assert gen_res["module"] == "capture"
