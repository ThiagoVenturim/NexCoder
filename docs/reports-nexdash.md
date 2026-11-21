# Developer Productivity and Security Reports via NexDash

`nexcoder` delegates dashboard rendering and report governance to `nexdash`. Instead of maintaining a separate charting engine inside `nexcoder`, `nexcoder-planning` and `nexcoder-security` normalize engineering and security records into semantic cubes and send them to `nexdash` over MCP or REST.

## Architecture and Data Flow

1. **Source Collection (`nexcoder-planning` and `nexcoder-security`)**:
   - `nexcoder_planning.reports` fetches pull requests, code review timestamps, lead time, and issue completion records from **GitHub** (`collect_github_productivity`), **Azure DevOps** (`collect_azure_devops_productivity`), and **Redmine** (`collect_redmine_productivity`, paired with `RedmineAdapter` for idempotent issue sync).
   - `nexcoder_security.reports` aggregates findings from `MultiScannerEngine` (`semgrep`, `bandit`, `gitleaks`, `osv-scanner`, `pip-audit`, `trivy`, `syft`), evaluates release gate coverage (`SecurityGateEvaluator`), and extracts outdated packages from `SBOMDocument`.
2. **Semantic Cube & Parameter Validation (`nexcoder_core.reports`)**:
   - Every report targets a registered semantic cube (`dev_productivity` or `security_posture`).
   - Parameters (`project`, `team`, `period`, `platforms`, `policy`) are validated against an explicit allowlist. Free-form SQL or unvalidated identifiers are rejected with `NexDashValidationError` (HTTP 422 / MCP `isError: true`).
3. **Transport Layer (`NexDashClient`)**:
   - **MCP (`transport="mcp"`)**: sends JSON-RPC 2.0 `tools/call` requests for `nexdash_list_models`, `nexdash_generate_report`, and `nexdash_publish_dashboard`.
   - **REST (`transport="rest"`)**: calls `GET /v1/models`, `POST /v1/reports/generate`, and `POST /v1/dashboards/publish` with Bearer / `X-API-Key` authentication.
   - **Offline (`transport="offline"`)**: executes `LocalNexDashEngine` in-process for deterministic CI tests and air-gapped environments.
4. **CSP-Hardened HTML Output**:
   - Returned HTML dashboards include `<meta http-equiv="Content-Security-Policy" content="... connect-src 'none' ...">` and inject `window.NEXDASH_DATA` in `<head>` with `<`, `>`, `&`, `U+2028`, and `U+2029` escaped.

## Visualization Rules

Generated dashboards follow strict visualization rules:

- **Top KPI Row**: 4 KPI cards at the top with direct comparison deltas (`vs. target`, merge rate, gate pass rate).
- **Conclusion-First Titles**: every chart title states the finding (for example, `"ana.silva liderou as entregas com 5 itens concluidos"` or `"Zero vulnerabilidades criticas ou altas ativas no ultimo scan"`), while the subtitle specifies the metric, period, and unit.
- **Zero-Baseline Bars and Line Trends**: horizontal bars start at zero and are ordered by value; multi-week trends use line charts. No pie charts, 3D effects, or dual Y axes are used.
- **Colorblind-Safe Accent**: one highlighted series uses Okabe-Ito blue (`#0072B2`) or vermilion (`#D55E00`), while secondary bars use neutral slate (`#64748B`).
- **Accessibility**: each chart includes an `aria-label` summary and an expandable `<table role="table">` with exact values.

## Reproducible Offline Usage

### Python API (MCP and REST)

```python
import httpx
from nexcoder_core.reports import (
    LocalNexDashEngine,
    NexDashClient,
    create_nexdash_mock_transport,
)
from nexcoder_planning.reports import generate_productivity_dashboard
from nexcoder_security.reports import generate_security_dashboard

engine = LocalNexDashEngine()
mock_transport = create_nexdash_mock_transport(engine=engine, api_token="local-token")

with httpx.Client(transport=mock_transport, base_url="http://nexdash.local") as http_client:
    # 1. Productivity report over MCP
    mcp_client = NexDashClient(
        transport="mcp",
        base_url="http://nexdash.local",
        api_token="local-token",
        http_client=http_client,
    )
    prod_metrics, prod_bundle = generate_productivity_dashboard(
        project="nexcoder-platform",
        team="core-engineering",
        period="2026-Q4",
        platforms=["github", "azure_devops", "redmine"],
        nexdash_client=mcp_client,
    )

    # 2. Security posture report over REST
    rest_client = NexDashClient(
        transport="rest",
        base_url="http://nexdash.local",
        api_token="local-token",
        http_client=http_client,
    )
    sec_metrics, sec_bundle = generate_security_dashboard(
        project="nexcoder-platform",
        period="2026-Q4",
        nexdash_client=rest_client,
    )
```

### Unified CLI

```bash
nexcoder report productivity --project nexcoder-platform --team core-engineering --period 2026-Q4 --transport mcp --out productivity.html
nexcoder report security --project nexcoder-platform --period 2026-Q4 --policy strict --transport offline --out security.html
```

## Cross-Repository Dependencies (`NexDash`)

This integration pairs with the following `ThiagoVenturim/NexDash` issues:

- **NexDash #9 (A1)**: Data source connectors (GitHub, Azure DevOps, Redmine, Jira, generic REST).
- **NexDash #10 (A2)**: Ready-made parameterized report models (`dev_productivity`, `security_posture`, `support_metrics`).
- **NexDash #11 (A3)**: Shared reporting engine exposed over MCP and REST.
