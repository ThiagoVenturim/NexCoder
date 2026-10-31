from __future__ import annotations

import tempfile
from pathlib import Path

from faccoder_ideation.models import StructuredIdea, ValueHypothesis
from faccoder_ideation.output.architecture import ArchitectureDesigner
from faccoder_ideation.output.gate import HumanGateManager
from faccoder_ideation.output.prd import PRDGenerator
from faccoder_ideation.pipeline import IdeationPipeline
from faccoder_ideation.research.squad import ResearchSquad
from faccoder_ideation.search.providers import MockSearchProvider


def _sample_idea() -> StructuredIdea:
    return StructuredIdea(
        title="Autonomous Bug Triage Engine",
        summary="Classifies, reproduces, and suggests minimal fixes for incoming error traces.",
        problem="Support engineers spend hours diagnosing root causes manually.",
        target_audience=[],
        value_hypothesis=ValueHypothesis(
            problem_statement="Triaging bugs takes up 30% of engineering bandwidth",
            proposed_solution="Automated trace analysis and reproduction sandbox",
            key_benefit="Instant root cause analysis and validated patch candidate",
        ),
        domain_tags=["ai", "qa", "developer-tools"],
    )


def test_architecture_designer() -> None:
    idea = _sample_idea()
    report = ResearchSquad(MockSearchProvider()).run(idea)
    designer = ArchitectureDesigner()
    arch = designer.design(idea, report)

    assert "AutonomousBugTriageEngine" in arch.system_name
    assert len(arch.components) >= 4
    assert len(arch.security_controls) >= 2
    assert "data_flow_description" in arch.model_dump()


def test_human_gate_manager_flow() -> None:
    gate_mgr = HumanGateManager(ttl_seconds=1800)
    gate, secret = gate_mgr.create_gate("idea-123", dry_run=False)

    assert gate.required is True
    assert gate.approved is False
    assert gate.approval_token != ""

    # Approve with wrong token
    res = gate_mgr.approve(gate, "invalid-token")
    assert res is False
    assert gate.approved is False

    # Approve with valid secret
    res = gate_mgr.approve(gate, secret, approver="alice")
    assert res is True
    assert gate.approved is True
    assert gate.approved_by == "alice"


def test_prd_and_report_generators() -> None:
    idea = _sample_idea()
    pipeline = IdeationPipeline(search_provider=MockSearchProvider(), allow_network=False)
    output, secret = pipeline.run(f"{idea.title}\n{idea.problem}", dry_run=False)

    # Check Markdown PRD
    prd = PRDGenerator.generate(
        output.structured_idea,
        output.research_report,
        output.jury_verdict,
        output.architecture,
        output.approval_gate,
    )
    assert "# PRD: " in prd
    assert "## 1. Executive Summary" in prd
    assert "## 5. Functional Requirements" in prd
    assert "<!-- faccoder-id: prd-" in prd

    # Check Markdown Report
    assert "Ideation & Diligence Executive Report" in output.markdown_report

    # Check HTML Report
    assert "<!DOCTYPE html>" in output.html_report
    assert "Autonomous Bug Triage Engine" in output.html_report or "Autonomous" in output.html_report
    assert "Jury Committee Evaluation" in output.html_report


def test_pipeline_end_to_end_and_saving() -> None:
    pipeline = IdeationPipeline(search_provider=MockSearchProvider(), allow_network=False)
    raw = "Cloud-native cost optimizer that detects idle resources and resizes databases."

    output, secret = pipeline.run(raw, dry_run=False)

    assert output.structured_idea.id != ""
    assert output.jury_verdict.total_jurors == 6
    assert output.approval_gate.approved is False

    # Approve gate
    success = pipeline.approve_gate(output, secret, approver="lead-dev")
    assert success is True
    assert output.approval_gate.approved is True

    # Test saving deliverables
    with tempfile.TemporaryDirectory() as tmpdir:
        files = pipeline.save_deliverables(output, tmpdir)
        for name, path in files.items():
            assert Path(path).exists()
            assert Path(path).stat().st_size > 0
