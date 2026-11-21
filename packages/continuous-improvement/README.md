# nexcoder-continuous-improvement

Continuous improvement engine for nexcoder projects: scheduled research diffs, Langfuse observability monitors, security watchers, and autonomous repository auto-improvement.

## Capabilities

- **Scheduler**: Configurable cron scheduler for periodic analysis routines.
- **Competitor & Gap Diff**: Re-runs market/competitor research and detects diffs against prior runs.
- **Observability Monitor**: Ingests Langfuse traces, token usage, costs, errors, and user feedback.
- **Security Watcher**: Periodic vulnerability analysis and dependency diffing against baseline.
- **Planning Bridge**: Automatically synthesizes improvement findings into prioritized issues (Given/When/Then).
- **Fix Gate**: Safe automated fix proposals requiring jury verdict and human approval code.
- **Continuous Auto-Improvement (Issue #78)**: Autonomous closed-loop improvement engine:
  - **Repo Scanner**: Scans repository for failing tests, coverage deficits, TODO technical debt, outdated dependencies, security risks, and lint issues.
  - **Automated Issue Sync**: Opens and deduplicates issues on platform trackers with label `auto`, layer and type metadata, and structured Given/When/Then criteria.
  - **NexLink Agent Bridge**: Dispatches developer agents on isolated branches branched strictly from `develop`.
  - **Verification Gates**: Runs tests offline, ruff lint, no-emoji check, and internal reference leak scanner.
  - **Safe Automated Merge**: Merges validated changes directly into `develop` while strictly enforcing safety guardrails (never `main`, no force push, no repo creation).
  - **Control Plane Quota & Budgets**: Enforces daily ceiling of automated merges and integrates with control plane budget policies.
  - **Tamper-Evident Audit**: Cryptographically logs every action in an append-only hash chain.
  - **Reporting & Dashboard**: Generates comprehensive summaries of issues, changes, quota usage, and audit head hashes.

## Quickstart

```python
from nexcoder_continuous_improvement import AutoImproveLoop, DailyQuotaTracker

# Initialize loop with a daily ceiling of 5 automated merges
loop = AutoImproveLoop(repo_path=".", max_daily_merges=5)

# Execute one complete improvement cycle
report = loop.run_cycle(dry_run=False)
print(report.summary)
```

## CLI Usage

```bash
# Scan repository for actionable continuous improvement findings
nexcoder-ci scan --repo-path .

# Run auto-improvement cycle
nexcoder-ci auto-improve --repo-path . --max-daily 5
```
