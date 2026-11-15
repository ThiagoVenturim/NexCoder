"""End-to-end offline tests for productivity and security dashboards via NexDash."""

from __future__ import annotations

from pathlib import Path

from nexcoder_core.reports import NEXDASH_CSP

from examples.reports_nexdash.run_reports_demo import run_reports_demo


def test_reports_demo_generates_productivity_and_security_dashboards(tmp_path: Path) -> None:
    result = run_reports_demo(output_dir=tmp_path)
    assert result["status"] == "success"

    artifacts = result["artifacts"]
    prod_html = artifacts["productivity_html"].read_text(encoding="utf-8")
    sec_html = artifacts["security_html"].read_text(encoding="utf-8")

    # Productivity dashboard checks (via MCP)
    assert result["productivity_bundle"].transport == "mcp"
    assert result["productivity_published"]["status"] == "published"
    assert NEXDASH_CSP in prod_html
    assert "window.NEXDASH_DATA=" in prod_html
    assert "throughput_by_author" in prod_html
    assert "lead_time_by_week" in prod_html
    assert "review_time_by_platform" in prod_html

    # Security dashboard checks (via REST)
    assert result["security_bundle"].transport == "rest"
    assert result["security_published"]["status"] == "published"
    assert NEXDASH_CSP in sec_html
    assert "window.NEXDASH_DATA=" in sec_html
    assert "vulnerabilities_by_severity" in sec_html
    assert "security_trend" in sec_html
    assert "findings_by_scanner" in sec_html
