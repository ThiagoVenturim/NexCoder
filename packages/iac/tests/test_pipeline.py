"""Tests for agentic IaC delivery pipeline and end-to-end workflow."""

from nexcoder_iac.models import IaCTarget
from nexcoder_iac.pipeline import create_iac_pipeline, run_iac_workflow


def test_create_iac_pipeline_builder():
    builder = create_iac_pipeline(name="test-iac-pipeline")
    assert builder.name == "test-iac-pipeline"
    graph = builder.compile()
    assert graph is not None
    assert graph.name == "test-iac-pipeline"


def test_run_iac_workflow_local():
    result = run_iac_workflow(
        description="Quero subir uma aplicacao FastAPI com Postgres e nginx",
        target=IaCTarget.LOCAL_COMPOSE,
        confirm_apply=True,
        dry_run=True,
    )

    assert result["target"] == "local_compose"
    assert result["tool"] == "compose"
    assert "docker-compose.yml" in result["files"]
    assert result["applied"] is True
    assert result["apply_status"] == "simulated_applied"


def test_run_iac_workflow_aws_pending_confirmation():
    result = run_iac_workflow(
        description="API com postgres na AWS",
        target=IaCTarget.AWS,
        confirm_apply=False,  # Human did not confirm yet
        dry_run=True,
    )

    assert result["target"] == "aws"
    assert result["tool"] == "terraform"
    assert "main.tf" in result["files"]
    assert result["applied"] is False
    assert result["apply_status"] == "pending_confirmation"
    assert result["estimated_monthly_cost_usd"] > 0.0
