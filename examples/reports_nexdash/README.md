# Productivity and Security Dashboards via NexDash (Offline Example)

This example runs offline with deterministic synthetic datasets to generate two HTML dashboards and JSON reports through `nexdash`:

1. **Developer Productivity (`dev_productivity`)**: pulls normalized pull request, review time, lead time, and issue completion records from GitHub, Azure DevOps, and Redmine (`nexcoder-planning`) and calls `nexdash` over **MCP (JSON-RPC 2.0)**.
2. **Security Posture (`security_posture`)**: aggregates findings from `semgrep`, `bandit`, `gitleaks`, `osv-scanner`, `pip-audit`, `trivy`, and `syft` along with release gate coverage (`nexcoder-security`) and calls `nexdash` over **REST (`POST /v1/reports/generate`)**.

## Run the Example

From the repository root:

```bash
python examples/reports_nexdash/run_reports_demo.py --output-dir /tmp/nexcoder-reports
```

Generated files:

- `productivity_dashboard.html`: self-contained HTML dashboard with `Content-Security-Policy` (`connect-src 'none'`) and server-injected `window.NEXDASH_DATA`.
- `productivity_report.json`: structured metrics (PRs opened/merged, review time, lead time, closed issues, throughput per person, and weekly trend).
- `security_dashboard.html`: security posture HTML dashboard with severity distribution, multi-week remediation trend, and scanner coverage.
- `security_report.json`: structured security metrics and outdated dependency list from the SBOM.

## Run the Tests

```bash
python -m pytest examples/reports_nexdash/tests/test_reports_demo.py
```
