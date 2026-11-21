"""Reproducible offline demo: developer productivity and security posture dashboards via NexDash.

Demonstrates:
1. Collecting and normalizing developer productivity records from GitHub, Azure DevOps,
   and Redmine (nexcoder-planning).
2. Generating and publishing a developer productivity dashboard via NexDash MCP
   (JSON-RPC 2.0 over in-memory transport).
3. Extracting multi-scanner security findings, SBOM dependency lag, and release gate
   coverage (nexcoder-security).
4. Generating and publishing a security posture dashboard via NexDash REST
   (httpx MockTransport with Bearer token authentication).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import httpx
from nexcoder_core.reports import (
    LocalNexDashEngine,
    NexDashClient,
    create_nexdash_mock_transport,
)
from nexcoder_planning.reports import generate_productivity_dashboard
from nexcoder_security.reports import generate_security_dashboard


def run_reports_demo(output_dir: Path | str | None = None) -> dict[str, Any]:
    """Run the offline productivity and security reporting flow and write artifacts."""
    base_dir = Path(__file__).parent.resolve()
    out_dir = Path(output_dir).resolve() if output_dir else (base_dir / ".reports_artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = LocalNexDashEngine()
    mock_transport = create_nexdash_mock_transport(engine=engine, api_token="demo-offline-token")

    artifacts: dict[str, Path] = {}

    # 1. Developer Productivity Dashboard via MCP transport
    with httpx.Client(transport=mock_transport, base_url="http://nexdash.local") as http_client:
        mcp_client = NexDashClient(
            transport="mcp",
            base_url="http://nexdash.local",
            api_token="demo-offline-token",
            http_client=http_client,
            engine=engine,
        )
        prod_metrics, prod_bundle = generate_productivity_dashboard(
            project="nexcoder-platform",
            team="core-engineering",
            period="2026-Q4",
            platforms=["github", "azure_devops", "redmine"],
            nexdash_client=mcp_client,
        )
        prod_published = mcp_client.publish_dashboard(prod_bundle, cadence="daily")

        # 2. Security Posture Dashboard via REST transport
        rest_client = NexDashClient(
            transport="rest",
            base_url="http://nexdash.local",
            api_token="demo-offline-token",
            http_client=http_client,
            engine=engine,
        )
        sec_metrics, sec_bundle = generate_security_dashboard(
            project="nexcoder-platform",
            period="2026-Q4",
            nexdash_client=rest_client,
        )
        sec_published = rest_client.publish_dashboard(sec_bundle, cadence="daily")

    prod_html_file = out_dir / "productivity_dashboard.html"
    prod_html_file.write_text(prod_bundle.html, encoding="utf-8")
    artifacts["productivity_html"] = prod_html_file

    prod_json_file = out_dir / "productivity_report.json"
    prod_json_file.write_text(prod_metrics.model_dump_json(indent=2), encoding="utf-8")
    artifacts["productivity_json"] = prod_json_file

    sec_html_file = out_dir / "security_dashboard.html"
    sec_html_file.write_text(sec_bundle.html, encoding="utf-8")
    artifacts["security_html"] = sec_html_file

    sec_json_file = out_dir / "security_report.json"
    sec_json_file.write_text(sec_metrics.model_dump_json(indent=2), encoding="utf-8")
    artifacts["security_json"] = sec_json_file

    return {
        "status": "success",
        "artifacts_dir": out_dir,
        "artifacts": artifacts,
        "productivity_metrics": prod_metrics,
        "productivity_bundle": prod_bundle,
        "productivity_published": prod_published,
        "security_metrics": sec_metrics,
        "security_bundle": sec_bundle,
        "security_published": sec_published,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate offline productivity and security dashboards via NexDash."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Target directory for generated HTML and JSON report artifacts.",
    )
    args = parser.parse_args()
    res = run_reports_demo(output_dir=args.output_dir)
    print(f"Generated NexDash reports in: {res['artifacts_dir']}")
    for name, path in res["artifacts"].items():
        print(f"  - {name}: {path}")


if __name__ == "__main__":
    main()
