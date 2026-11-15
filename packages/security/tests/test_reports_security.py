from __future__ import annotations

import httpx
from nexcoder_core.reports import (
    LocalNexDashEngine,
    NexDashClient,
    create_nexdash_mock_transport,
)
from nexcoder_security.reports import (
    build_synthetic_security_scans,
    compute_security_metrics,
    generate_security_dashboard,
)


def test_synthetic_security_scans_and_metrics() -> None:
    history = build_synthetic_security_scans(project="nexcoder-platform")
    assert len(history) == 4

    # First week had critical & high -> gate blocked
    assert history[0][2].passed is False
    # Latest week has 0 critical and 0 high -> gate passed
    assert history[-1][2].passed is True

    metrics = compute_security_metrics(
        history[-1][1],
        history=history,
        project="nexcoder-platform",
        period="2026-Q4",
    )
    assert metrics.gate_passed is True
    assert metrics.severity_counts["critical"] == 0
    assert metrics.severity_counts["high"] == 0
    assert metrics.severity_counts["medium"] == 2
    assert metrics.severity_counts["low"] == 1
    assert metrics.suppressed_findings == 1
    assert metrics.sbom_present is True
    assert metrics.sbom_components_count == 6
    assert metrics.outdated_dependencies_count == 1
    assert metrics.outdated_dependencies[0].package_name == "jinja2"
    assert metrics.outdated_dependencies[0].recommended_version == "3.1.4"
    assert metrics.gate_coverage_pct == 100.0
    assert len(metrics.trend) == 4
    assert metrics.trend[0].total_active == 9
    assert metrics.trend[-1].total_active == 3


def test_generate_security_dashboard_offline_mcp_and_rest() -> None:
    # 1. Offline
    metrics_off, bundle_off = generate_security_dashboard(
        project="nexcoder-platform",
        period="2026-Q4",
        transport="offline",
    )
    assert metrics_off.gate_passed is True
    assert bundle_off.status == "success"
    assert bundle_off.model_id == "security_posture"
    assert len(bundle_off.kpis) == 4
    assert len(bundle_off.charts) == 3
    assert "vulnerabilities_by_severity" in [c.id for c in bundle_off.charts]
    assert "security_trend" in [c.id for c in bundle_off.charts]
    assert "findings_by_scanner" in [c.id for c in bundle_off.charts]
    assert "window.NEXDASH_DATA=" in bundle_off.html

    # 2. MCP
    engine = LocalNexDashEngine()
    mcp_client = NexDashClient(transport="mcp", engine=engine)
    _m_mcp, bundle_mcp = generate_security_dashboard(
        project="nexcoder-platform",
        period="2026-Q4",
        nexdash_client=mcp_client,
    )
    assert bundle_mcp.transport == "mcp"
    assert bundle_mcp.total_rows == 4

    # 3. REST
    mock_transport = create_nexdash_mock_transport(engine=engine, api_token="sec-tok")
    with httpx.Client(transport=mock_transport, base_url="http://nexdash.local") as http_client:
        rest_client = NexDashClient(
            transport="rest",
            base_url="http://nexdash.local",
            api_token="sec-tok",
            http_client=http_client,
        )
        _m_rest, bundle_rest = generate_security_dashboard(
            project="nexcoder-platform",
            period="2026-Q4",
            nexdash_client=rest_client,
        )
        assert bundle_rest.transport == "rest"
        assert bundle_rest.status == "success"
