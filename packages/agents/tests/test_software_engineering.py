"""Offline tests for software engineering review, ADRs, practices audit,
technical planning, and guided test-backed refactoring (Issue #84).
"""

from __future__ import annotations

from pathlib import Path

from nexcoder_agents.catalog.registry import AgentCatalog
from nexcoder_agents.catalog.skills import SkillCatalog
from nexcoder_agents.cli import main
from nexcoder_agents.engine.models import ApprovalStatus
from nexcoder_agents.engine.pipelines import build_pipeline, get_pipeline_template
from nexcoder_agents.software_engineering import (
    ActionPriority,
    ArchitecturePattern,
    SoftwareEngineeringAdvisor,
    classify_module_layer,
)
from nexcoder_core.llm.fake import FakeChatModel


def _sample_project_dir() -> Path:
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    return repo_root / "examples" / "quickstart" / "sample_project"


def test_software_engineering_skills_and_personas() -> None:
    skills = SkillCatalog.default()
    expected_slugs = [
        "architecture-review",
        "clean-architecture",
        "engineering-best-practices",
        "adr-and-engineering-docs",
        "guided-refactoring",
        "technical-planning",
    ]
    for slug in expected_slugs:
        skill = skills.get(slug)
        assert skill is not None, f"Expected skill '{slug}' in default catalog"
        assert skill.description
        assert skill.content

    agents = AgentCatalog.default()
    architect = agents.get_or_raise("lead-architect")
    assert "architecture-review" in architect.skills
    assert "engineering-best-practices" in architect.skills
    assert "adr-and-engineering-docs" in architect.skills
    assert "guided-refactoring" in architect.skills
    assert "technical-planning" in architect.skills


def test_classify_module_layer() -> None:
    assert classify_module_layer("models.py") == "domain"
    assert classify_module_layer("service.py") == "application"
    assert classify_module_layer("storage.py") == "infrastructure"
    assert classify_module_layer("api/routes.py") == "presentation"
    assert classify_module_layer("tests/test_tasks.py") == "tests"


def test_analyze_sample_project_and_guided_refactor(tmp_path: Path) -> None:
    sample_dir = _sample_project_dir()
    assert sample_dir.is_dir()

    workspace_copy = tmp_path / "refactored_project"
    advisor = SoftwareEngineeringAdvisor()
    report = advisor.analyze_project(
        sample_dir,
        apply_safe_refactor=True,
        refactor_workspace=workspace_copy,
    )

    # 1. Architecture review & pattern trade-offs
    assert report.project_name == "sample_project"
    assert report.architecture.detected_pattern == ArchitecturePattern.LAYERED
    assert report.architecture.recommended_pattern == ArchitecturePattern.HEXAGONAL
    assert report.architecture.modules_analyzed == 3
    assert report.architecture.symbols_analyzed >= 8
    assert report.architecture.communities_detected >= 1
    assert len(report.architecture.pattern_trade_offs) == 3
    assert any("export_tasks_csv" in f for f in report.architecture.coupling_findings)

    # 2. Engineering best practices audit
    check_map = {c.category: c for c in report.practices.checks}
    assert {"testing", "ci_cd", "semver", "commit_conventions", "branch_organization"} == set(check_map.keys())
    assert any("export_tasks_csv" in sym for sym in report.practices.untested_symbols)
    assert check_map["commit_conventions"].passed is True
    assert check_map["branch_organization"].passed is True

    # 3. ADRs, Mermaid diagram, and bottom-up docs from code-intel
    assert len(report.adrs) >= 2
    adr_md = report.adrs[0].to_markdown()
    assert "## Context" in adr_md
    assert "## Decision" in adr_md
    assert "## Consequences" in adr_md
    assert "flowchart TD" in report.architecture_diagram
    assert "service" in report.architecture_diagram
    assert "# Architecture Overview" in report.bottom_up_system_doc
    assert report.bottom_up_node_count >= 10

    # 4. Prioritized actions & technical planning via nexcoder-planning
    assert len(report.prioritized_actions) >= 3
    assert report.prioritized_actions[0].priority == ActionPriority.P0
    assert report.technical_plan.total_hours() > 0
    assert len(report.sprint_plan.scheduled_tasks) == len(report.prioritized_actions)

    # 5. Guided refactoring with blast-radius impact analysis and test verification
    assert len(report.refactor_suggestions) >= 1
    primary_ref = report.refactor_suggestions[0]
    assert primary_ref.id == "REF-01"
    assert primary_ref.safe_to_auto_apply is True
    assert primary_ref.impact_report is not None
    assert primary_ref.impact_report.risk_level in {"low", "medium", "high", "critical"}

    assert report.applied_refactor is not None
    assert report.applied_refactor.applied is True
    assert report.applied_refactor.tests_passed is True
    assert report.applied_refactor.commit_message.startswith("refactor(service):")
    assert "service.py" in report.applied_refactor.modified_files
    assert "tests/test_tasks.py" in report.applied_refactor.modified_files

    # 6. Full markdown report rendering
    markdown = report.to_markdown()
    assert "# Software Engineering & Architecture Assessment: sample_project" in markdown
    assert "## 1. Architecture Review (Parecer de Arquitetura)" in markdown
    assert "## 3. Prioritized Engineering Actions" in markdown
    assert "### Applied Refactoring Verification" in markdown


def test_layer_violation_detection_and_branch_audit(tmp_path: Path) -> None:
    proj = tmp_path / "bad_layers_app"
    proj.mkdir()
    (proj / "models.py").write_text(
        "from storage import SqlClient\n\nclass Order:\n    def save(self) -> None:\n        pass\n",
        encoding="utf-8",
    )
    (proj / "storage.py").write_text(
        "class SqlClient:\n    def connect(self) -> bool:\n        return True\n",
        encoding="utf-8",
    )

    advisor = SoftwareEngineeringAdvisor()
    report = advisor.analyze_project(
        proj,
        apply_safe_refactor=False,
        commit_messages=["bad commit message without prefix"],
        branch_names=["main", "random_unscoped_branch"],
    )

    assert len(report.architecture.layer_violations) == 1
    violation = report.architecture.layer_violations[0]
    assert violation.source_layer == "domain"
    assert violation.target_layer == "infrastructure"
    assert violation.severity == "high"

    check_map = {c.category: c for c in report.practices.checks}
    assert check_map["commit_conventions"].passed is False
    assert check_map["branch_organization"].passed is False


def test_software_engineering_pipeline_execution(tmp_path: Path) -> None:
    tmpl = get_pipeline_template("software-engineering-review")
    assert tmpl.category == "engineering"
    assert "project_name" in tmpl.required_inputs

    fake_llm = FakeChatModel(
        responses=[
            "Executive opinion: adopt hexagonal ports for TaskRepository and fix overdue predicate.",
        ]
    )
    pipeline = build_pipeline("software-engineering-review", model=fake_llm)
    res = pipeline.run(
        inputs={
            "project_name": "sample_project",
            "architecture_goal": "Audit architecture, generate ADRs, and verify guided refactorings",
            "project_path": str(_sample_project_dir()),
            "apply_safe_refactor": True,
            "refactor_workspace": str(tmp_path / "pipeline_refactor_ws"),
        },
        dry_run=True,
    )

    assert res.status == "completed"
    assert res.approval is not None
    assert res.approval.status == ApprovalStatus.DRY_RUN
    assert "architecture_assessment" in res.data
    assert "prioritized_actions" in res.data
    assert "adrs" in res.data
    assert "technical_plan" in res.data
    assert "sprint_plan" in res.data
    assert res.data["applied_refactor"]["tests_passed"] is True


def test_cli_review_project_command(tmp_path: Path, capsys) -> None:
    out_file = tmp_path / "parecer_arquitetura.md"
    code = main(
        [
            "review-project",
            str(_sample_project_dir()),
            "--output",
            str(out_file),
            "--no-refactor",
        ]
    )
    assert code == 0
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "Parecer de Arquitetura" in content
    assert "ADR-001" in content

    # Non-existent directory returns 1
    code_err = main(["review-project", str(tmp_path / "missing_dir_xyz")])
    assert code_err == 1
    _ = capsys.readouterr()
