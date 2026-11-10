from __future__ import annotations

from pathlib import Path

from nexcoder_interfaces.tools import (
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
    res = security_scan(path=str(tmp_path), force_offline=True, owned_target=True, authorized_by="dev-owner")
    assert res["status"] == "success"
    assert res["authorized"] is True
    assert "passed_gate" in res


def test_security_scan_refuses_unmarked_target(tmp_path: Path) -> None:
    from nexcoder_control.metering.audit import AppendOnlyAuditLog

    safe_file = tmp_path / "clean.py"
    safe_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    audit = AppendOnlyAuditLog()
    res = security_scan(path=str(tmp_path), force_offline=True, owned_target=False, audit_log=audit)
    assert res["status"] == "rejected"
    assert res["authorized"] is False
    assert "USAGE_POLICY.md" in res["reason"]
    events = audit.query(event_type="target.authorization.denied")
    assert len(events) == 1
    assert events[0].resource == str(tmp_path.resolve())


def test_run_agent_offline() -> None:
    res = run_agent(agent_name="lead-architect", task="Review microservice architecture")
    assert res["status"] == "success"
    assert res["agent"]["slug"] == "lead-architect"
    assert "rendered_prompt" in res


def test_run_pipeline_offline() -> None:
    res = run_pipeline(pipeline_name="sample_pipeline", inputs={"task": "execute test"}, dry_run=True)
    assert res["status"] == "success"
    assert res["run_status"] in ("completed", "waiting_approval")


def test_approve_step_sem_solicitacao_pendente_rejeita() -> None:
    res = approve_step(action_name="nonexistent_action_xyz", token="valid_looking_token_123")
    assert res["status"] == "rejected"
    assert res["approved"] is False
    assert "No pending approval request found" in res["reason"]


def test_approve_step_token_aleatorio_8_caracteres_rejeita() -> None:
    pipe_res = run_pipeline(pipeline_name="approval_deploy", inputs={"task": "deploy"}, dry_run=False)
    assert pipe_res["run_status"] == "waiting_approval"
    action_name = pipe_res["approval"]["action_name"]
    exec_id = pipe_res["execution_id"]

    # Random token with 8+ characters must be rejected
    res = approve_step(action_name=action_name, token="random_8_chars_token", execution_id=exec_id)
    assert res["status"] == "rejected"
    assert res["approved"] is False
    assert "secret token mismatch" in res["reason"]


def test_approve_step_token_certo_de_outra_execucao_rejeita() -> None:
    p1 = run_pipeline(pipeline_name="approval_gate_1", inputs={"task": "task 1"}, dry_run=False)
    p2 = run_pipeline(pipeline_name="approval_gate_2", inputs={"task": "task 2"}, dry_run=False)

    token_2 = p2["approval"]["token"]

    # Trying to approve execution 1 with token from execution 2 must be rejected
    res = approve_step(
        action_name=p1["approval"]["action_name"],
        token=token_2,
        execution_id=p1["execution_id"],
    )
    assert res["status"] == "rejected"
    assert res["approved"] is False


def test_approve_step_token_certo_aprova_uma_vez_e_segunda_falha() -> None:
    p = run_pipeline(pipeline_name="approval_release", inputs={"task": "release v1"}, dry_run=False)
    assert p["run_status"] == "waiting_approval"
    action_name = p["approval"]["action_name"]
    exec_id = p["execution_id"]
    valid_token = p["approval"]["token"]

    # First attempt with valid token succeeds and resumes pipeline
    res1 = approve_step(action_name=action_name, token=valid_token, execution_id=exec_id, approver="alice")
    assert res1["status"] == "approved"
    assert res1["approved"] is True
    assert res1["approver"] == "alice"
    assert res1["pipeline_status"] == "completed"

    # Second attempt with same token fails (single-use token already consumed)
    res2 = approve_step(action_name=action_name, token=valid_token, execution_id=exec_id, approver="alice")
    assert res2["status"] == "rejected"
    assert res2["approved"] is False


def test_unavailable_tools() -> None:
    cap_res = capture_page("https://example.com")
    assert cap_res["status"] == "unavailable"
    assert cap_res["module"] == "capture"

    gen_res = generate_tests("spec_v1")
    assert gen_res["status"] == "unavailable"
    assert gen_res["module"] == "capture"
