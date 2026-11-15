from __future__ import annotations

import httpx
import pytest
from nexcoder_core.reports import (
    NEXDASH_CSP,
    LocalNexDashEngine,
    NexDashAuthError,
    NexDashClient,
    NexDashComputedChart,
    NexDashComputedKPI,
    NexDashCubeSpec,
    NexDashDimensionSpec,
    NexDashMetricSpec,
    NexDashValidationError,
    create_nexdash_mock_transport,
    safe_json_for_script,
)


def _sample_dataset() -> dict:
    cube = NexDashCubeSpec(
        name="dev_productivity",
        table="fact_dev_productivity",
        dimensions=[
            NexDashDimensionSpec(name="author", type="string"),
            NexDashDimensionSpec(name="platform", type="string"),
        ],
        metrics=[
            NexDashMetricSpec(name="prs_merged", aggregation="sum", column="prs_merged"),
        ],
    )
    kpis = [
        NexDashComputedKPI(
            id="prs_merged",
            label="PRs Mesclados",
            value=24,
            formatted_value="24",
            delta="+18%",
            comparison_label="vs. sprint anterior",
            status="good",
        )
    ]
    charts = [
        NexDashComputedChart(
            id="throughput_by_author",
            type="bar",
            title="Ana liderou entregas com 9 PRs mesclados no periodo",
            subtitle="PRs mesclados por pessoa, ultimos 30 dias (unidades)",
            x="Pessoa",
            y="PRs mesclados",
            unit="PRs",
            labels=["ana", "bruno"],
            values=[9.0, 6.0],
            highlight_label="ana",
            annotation="Pico de entregas na semana 3 apos automacao de CI.",
            alt_text="Grafico de barras horizontais mostrando ana com 9 PRs e bruno com 6 PRs.",
        )
    ]
    return {
        "title": "Throughput subiu 18% na Sprint 4",
        "subtitle": "Produtividade de engenharia consolidada (GitHub, Azure DevOps, Redmine)",
        "cube": cube.model_dump(),
        "kpis": [k.model_dump() for k in kpis],
        "charts": [c.model_dump() for c in charts],
        "rows": [{"author": "ana", "prs_merged": 9}, {"author": "bruno", "prs_merged": 6}],
        "source_summary": "GitHub + Azure DevOps + Redmine (sintetico offline)",
    }


def test_safe_json_for_script_escapes_script_breakout() -> None:
    malicious = {"payload": "</script><script>alert(1)</script><!-- & \u2028 \u2029"}
    encoded = safe_json_for_script(malicious)
    assert "</script>" not in encoded
    assert "<!--" not in encoded
    assert "\\u003c/script\\u003e" in encoded
    assert "\\u0026" in encoded
    assert "\\u2028" in encoded
    assert "\\u2029" in encoded


def test_nexdash_client_offline_and_mcp_and_rest() -> None:
    engine = LocalNexDashEngine()
    dataset = _sample_dataset()
    params = {"project": "nexcoder", "team": "core-platform", "period": "2026-Q4"}

    # 1. Offline transport
    offline_client = NexDashClient(transport="offline", engine=engine)
    models = offline_client.list_models()
    assert len(models) >= 2
    bundle_offline = offline_client.generate_dashboard("dev_productivity", params, dataset)
    assert bundle_offline.status == "success"
    assert bundle_offline.transport == "offline"
    assert NEXDASH_CSP in bundle_offline.html
    assert "window.NEXDASH_DATA=" in bundle_offline.html

    # 2. MCP transport
    mcp_client = NexDashClient(transport="mcp", engine=engine)
    bundle_mcp = mcp_client.generate_dashboard("dev_productivity", params, dataset)
    assert bundle_mcp.status == "success"
    assert bundle_mcp.transport == "mcp"
    pub_mcp = mcp_client.publish_dashboard(bundle_mcp, cadence="daily")
    assert pub_mcp["status"] == "published"

    # 3. REST transport with MockTransport and constant-time token verification
    mock_transport = create_nexdash_mock_transport(engine=engine, api_token="secret-token-123")
    with httpx.Client(transport=mock_transport, base_url="http://nexdash.local") as http_client:
        rest_client = NexDashClient(
            transport="rest",
            base_url="http://nexdash.local",
            api_token="secret-token-123",
            http_client=http_client,
        )
        assert "***" in repr(rest_client)
        assert "secret-token-123" not in repr(rest_client)

        rest_models = rest_client.list_models()
        assert any(m.model_id == "dev_productivity" for m in rest_models)

        bundle_rest = rest_client.generate_dashboard("dev_productivity", params, dataset)
        assert bundle_rest.status == "success"
        assert bundle_rest.transport == "rest"

        # Invalid token raises NexDashAuthError
        bad_client = NexDashClient(
            transport="rest",
            base_url="http://nexdash.local",
            api_token="wrong-token",
            http_client=http_client,
        )
        with pytest.raises(NexDashAuthError):
            bad_client.list_models()


def test_nexdash_rejects_invalid_parameters_and_sql_injection() -> None:
    engine = LocalNexDashEngine()
    dataset = _sample_dataset()
    mock_transport = create_nexdash_mock_transport(engine=engine)

    with httpx.Client(transport=mock_transport, base_url="http://nexdash.local") as http_client:
        rest_client = NexDashClient(
            transport="rest",
            base_url="http://nexdash.local",
            http_client=http_client,
        )
        mcp_client = NexDashClient(
            transport="mcp",
            base_url="http://nexdash.local",
            http_client=http_client,
        )

        # Missing required parameter 'period'
        with pytest.raises(NexDashValidationError, match="Missing required parameter 'period'"):
            rest_client.generate_dashboard("dev_productivity", {"project": "nexcoder"}, dataset)

        # Disallowed parameter name
        with pytest.raises(NexDashValidationError, match="not allowed"):
            mcp_client.generate_dashboard(
                "dev_productivity",
                {"project": "nexcoder", "period": "30d", "raw_sql": "SELECT 1"},
                dataset,
            )

        # SQL injection attempt in parameter value
        with pytest.raises(NexDashValidationError, match="forbidden SQL"):
            rest_client.generate_dashboard(
                "dev_productivity",
                {"project": "nexcoder'; DROP TABLE users; --", "period": "30d"},
                dataset,
            )

        # Unknown model_id
        with pytest.raises(NexDashValidationError, match="Unknown report model"):
            mcp_client.generate_dashboard("unknown_model", {"project": "nexcoder", "period": "30d"}, dataset)
