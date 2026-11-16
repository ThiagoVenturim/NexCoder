"""Offline unit tests for campaign models, budgets, and reporting formats (Issue #71)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from nexcoder_security.campaign.models import (
    AgentExecutionResult,
    CampaignBudget,
    CampaignConfig,
    CampaignReport,
    CampaignStatus,
    TestFinding,
    TestType,
)
from nexcoder_security.models import Severity


class TestCampaignModels:
    def test_test_type_parsing(self) -> None:
        assert TestType.from_str("unit") == TestType.UNIT
        assert TestType.from_str("unitario") == TestType.UNIT
        assert TestType.from_str("system") == TestType.SYSTEM
        assert TestType.from_str("sistema") == TestType.SYSTEM
        assert TestType.from_str("process") == TestType.PROCESS
        assert TestType.from_str("processo") == TestType.PROCESS
        assert TestType.from_str("dom") == TestType.DOM
        assert TestType.from_str("ui") == TestType.DOM
        assert TestType.from_str("api") == TestType.API
        assert TestType.from_str("security") == TestType.SECURITY
        assert TestType.from_str("seguranca") == TestType.SECURITY

        with pytest.raises(ValueError, match="Unknown test type"):
            TestType.from_str("unknown_type")

    def test_campaign_budget_defaults_and_validation(self) -> None:
        budget = CampaignBudget()
        assert budget.max_cost_usd == 5.0
        assert budget.max_duration_seconds == 120.0
        assert budget.max_requests == 1000
        assert budget.currency == "USD"

        custom = CampaignBudget(max_cost_usd=15.5, max_duration_seconds=300.0, max_requests=5000)
        assert custom.max_cost_usd == 15.5
        assert custom.max_duration_seconds == 300.0

    def test_campaign_config_defaults(self) -> None:
        config = CampaignConfig(target="/local/repo")
        assert config.target == "/local/repo"
        assert config.agent_count == 3
        assert len(config.test_types) == 3
        assert config.dry_run is True
        assert config.owned_target is False

    def test_test_finding_reproduction_guide(self) -> None:
        finding = TestFinding(
            campaign_id="camp_123",
            test_type=TestType.API,
            agent_id="agent-api-1",
            title="Unauthenticated admin endpoint",
            severity=Severity.HIGH,
            category="auth",
            target_ref="/api/admin/reset:1",
            description="Endpoint does not verify bearer token.",
            steps_to_reproduce=[
                "Send POST request to /api/admin/reset without Authorization header.",
                "Observe HTTP 200 response with administrative reset executed.",
            ],
            reproduction_snippet="curl -X POST http://localhost:8000/api/admin/reset",
            remediation_suggestion="Add Security(get_current_admin) dependency to route.",
        )

        guide = finding.format_reproduction_guide()
        assert "1. Send POST request" in guide
        assert "2. Observe HTTP 200" in guide
        assert "curl -X POST" in guide

    def test_campaign_report_export_json_markdown_html(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        finding = TestFinding(
            campaign_id="camp_abc",
            test_type=TestType.SECURITY,
            agent_id="agent-security-1",
            title="Hardcoded test secret",
            severity=Severity.CRITICAL,
            category="secrets",
            target_ref="config.py:42",
            description="Detected API secret string in source code.",
            steps_to_reproduce=["Inspect config.py line 42."],
            remediation_suggestion="Load secret from environment variable.",
        )
        agent_res = AgentExecutionResult(
            agent_id="agent-security-1",
            test_type=TestType.SECURITY,
            tests_run=10,
            tests_passed=9,
            tests_failed=1,
            duration_seconds=1.25,
            cost_usd=0.005,
            findings=[finding],
            status="success",
        )
        report = CampaignReport(
            campaign_id="camp_abc",
            target="/local/app",
            status=CampaignStatus.COMPLETED,
            authorized_by="Lead Engineer",
            authorized_at=now,
            ownership="owned",
            scope=["*"],
            agent_count=2,
            test_types=[TestType.SECURITY, TestType.API],
            budget_limit_usd=10.0,
            actual_cost_usd=0.005,
            duration_seconds=1.25,
            total_tests_run=10,
            total_passed=9,
            total_failed=1,
            severity_counts={"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0},
            findings=[finding],
            agent_results=[agent_res],
        )

        # JSON
        json_str = report.to_json()
        assert '"camp_abc"' in json_str
        assert '"Lead Engineer"' in json_str

        # Markdown
        md_str = report.to_markdown()
        assert "# Security and Quality Test Campaign Report: camp_abc" in md_str
        assert "Hardcoded test secret" in md_str
        assert "Remediation Suggestion" in md_str
        assert "Steps to Reproduce" in md_str

        # HTML
        html_str = report.to_html()
        assert "<!DOCTYPE html>" in html_str
        assert "camp_abc" in html_str
        assert "badge-critical" in html_str

        # Disk export
        json_file = tmp_path / "report.json"
        md_file = tmp_path / "report.md"
        html_file = tmp_path / "report.html"

        report.export(json_file, format="json")
        report.export(md_file, format="markdown")
        report.export(html_file, format="html")

        assert json_file.exists() and len(json_file.read_text(encoding="utf-8")) > 50
        assert md_file.exists() and len(md_file.read_text(encoding="utf-8")) > 50
        assert html_file.exists() and len(html_file.read_text(encoding="utf-8")) > 50
