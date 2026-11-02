from __future__ import annotations

import tempfile
import time
from pathlib import Path

from faccoder_ideation.models import GateStatus, StructuredIdea, ValueHypothesis
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


def test_human_gate_security_lifecycle() -> None:
    """Security verification for b85 gate: rejection of dry-run-token, raw hash, expired, and consumed tokens."""
    gate_mgr = HumanGateManager(ttl_seconds=1800)
    gate, secret = gate_mgr.create_gate("idea-123", dry_run=False)

    assert gate.required is True
    assert gate.approved is False
    assert gate.status == GateStatus.PENDING
    assert gate.consumed is False
    assert len(gate.token_hash) == 64  # Full SHA-256

    # 1. Rejection of static placeholder 'dry-run-token'
    res_placeholder = gate_mgr.approve(gate, "dry-run-token")
    assert res_placeholder is False
    assert gate.approved is False
    assert gate.status == GateStatus.PENDING

    # 2. Rejection of the stored raw hash itself (must provide the pre-image raw secret)
    res_hash = gate_mgr.approve(gate, gate.token_hash)
    assert res_hash is False
    assert gate.approved is False
    assert gate.status == GateStatus.PENDING

    # 3. Rejection of expired token
    expired_time = gate.expires_at + 10.0
    res_expired = gate_mgr.approve(gate, secret, current_time=expired_time)
    assert res_expired is False
    assert gate.status == GateStatus.EXPIRED
    assert gate.consumed is True

    # 4. Rejection of non-pending / consumed gate
    gate2, secret2 = gate_mgr.create_gate("idea-456", dry_run=False)
    # First approval succeeds
    res_valid = gate_mgr.approve(gate2, secret2, approver="alice", current_time=time.time())
    assert res_valid is True
    assert gate2.approved is True
    assert gate2.status == GateStatus.APPROVED
    assert gate2.consumed is True
    assert gate2.approved_by == "alice"

    # Attempting to re-use token strictly rejected (single-use)
    res_reuse = gate_mgr.approve(gate2, secret2, approver="bob")
    assert res_reuse is False
    assert gate2.approved_by == "alice"


def test_prd_and_report_no_token_leak() -> None:
    """Verify that neither the raw secret nor token hash is ever rendered in PRD or reports."""
    idea = _sample_idea()
    pipeline = IdeationPipeline(search_provider=MockSearchProvider(), allow_network=False)
    output, secret = pipeline.run(f"{idea.title}\n{idea.problem}", dry_run=False)

    prd = PRDGenerator.generate(
        output.structured_idea,
        output.research_report,
        output.jury_verdict,
        output.architecture,
        output.approval_gate,
    )

    # Assert raw secret and token hash are NEVER present in PRD text
    assert secret not in prd
    assert output.approval_gate.token_hash not in prd
    assert "Approval Token" not in prd

    # Assert raw secret and token hash are NEVER present in reports
    assert secret not in output.markdown_report
    assert output.approval_gate.token_hash not in output.markdown_report
    assert secret not in output.html_report
    assert output.approval_gate.token_hash not in output.html_report

    # Structural PRD validation
    assert "# PRD: " in prd
    assert "## 1. Executive Summary" in prd
    assert "## 5. Functional Requirements" in prd
    assert "<!-- faccoder-id: prd-" in prd


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
    assert output.approval_gate.status == GateStatus.APPROVED

    # Test saving deliverables
    with tempfile.TemporaryDirectory() as tmpdir:
        files = pipeline.save_deliverables(output, tmpdir)
        for name, path in files.items():
            assert Path(path).exists()
            assert Path(path).stat().st_size > 0
            content = Path(path).read_text(encoding="utf-8")
            assert secret not in content
            assert output.approval_gate.token_hash not in content
