"""End-to-end test for offline quickstart pipeline."""

from __future__ import annotations

import time
from pathlib import Path

from examples.quickstart.run_quickstart import run_quickstart


def test_quickstart_end_to_end(tmp_path: Path) -> None:
    start_time = time.perf_counter()
    result = run_quickstart(output_dir=tmp_path)
    duration = time.perf_counter() - start_time

    # Must complete comfortably under 60 seconds
    assert duration < 60.0

    assert result["status"] == "success"
    artifacts = result["artifacts"]

    # Verify Stage 1 artifact
    jury_file = artifacts["jury_verdict"]
    assert jury_file.exists()
    assert jury_file.stat().st_size > 0
    assert result["jury_verdict"].total_jurors == 6

    # Verify Stage 2 artifact
    prd_file = artifacts["prd"]
    assert prd_file.exists()
    assert "# PRD:" in prd_file.read_text(encoding="utf-8")

    # Verify Stage 3 artifacts & git repository
    sprint_file = artifacts["sprint_plan"]
    assert sprint_file.exists()
    backlog_file = artifacts["backlog"]
    assert backlog_file.exists()
    planning_repo = tmp_path / "planning_repo"
    assert (planning_repo / ".git").exists()

    # Verify Stage 4 artifacts
    db_file = artifacts["code_intel_db"]
    assert db_file.exists()
    rag_file = artifacts["rag_summary"]
    assert rag_file.exists()
    assert "Question:" in rag_file.read_text(encoding="utf-8")

    # Verify Stage 5 artifact
    pipeline_file = artifacts["pipeline_result"]
    assert pipeline_file.exists()
    assert '"status": "completed"' in pipeline_file.read_text(encoding="utf-8")

    # Verify Stage 6 artifact
    security_file = artifacts["security_verdict"]
    assert security_file.exists()
    assert result["gate_verdict"].passed is True
