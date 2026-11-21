# nexcoder-testing

Multi-agent extreme application testing (`unit`, `system`, `dom`, `api`, and defensive `security`) for owned or explicitly authorized targets.

## Overview

`nexcoder-testing` provides an orchestrator (`ExtremeTestOrchestrator`) that divides application testing work across a configurable number of parallel worker agents (`num_agents = 1..N`) and consolidates findings, severity ratings, remediation guidance, and generated test suites into a unified report (`ExtremeTestReport`).

It reuses:
- **`nexcoder-control`**: `TargetAuthorizationGate`, `ApprovalTokenManager`, and `AppendOnlyAuditLog` to enforce that tests run **only** against targets marked as owned (`owned_target=True`, pre-registered in the gate, or backed by a single-use approval token), with full secret redaction in audit events.
- **`nexcoder-capture`**: `WebCaptureEngine`, `audit_accessibility_tree`, `generate_playwright_test`, and `generate_page_object` to scrape DOM screens, check expected selectors/texts and accessibility, and generate Playwright UI tests and Page Objects.
- **`nexcoder-security`**: `MultiScannerEngine` and `SecurityGateEvaluator` combined with defensive application probes (HTTP security headers, authentication enforcement, malformed input error handling, and secret leakage detection in logs and responses).
- **`nexcoder-agents`**: `PipelineBuilder`, `BaseBlock`, `ValidatorBlock`, `PromptBlock`, `CommitteeBlock`, and `HumanApprovalBlock` via `ExtremeTestingBlock` and `create_extreme_testing_pipeline`.

## Installation

```bash
pip install -e packages/testing
```

## Usage limits

- Only targets you own or are explicitly authorized to test. An unmarked target raises
  `TargetNotAuthorizedError` and the denial is written to the audit log (see `USAGE_POLICY.md`).
- `base_url` must point to a host in `allowed_hosts` (loopback by default). Third-party hosts are refused.
- Offline mode is the default (`offline=True`, `NexcoderConfig(preset="offline")`). In offline mode only
  loopback hosts are reachable, even if `allowed_hosts` lists other hosts.
- Every runner sends HTTP through `nexcoder_testing.gate.gated_http_request`, which checks the host again on
  each request, so runners used on their own follow the same rules.

## Quick Example (Offline with Synthetic Target)

```python
from pathlib import Path
from nexcoder_testing import (
    ExtremeTestConfig,
    ExtremeTestOrchestrator,
    create_synthetic_target_app,
)

synth = create_synthetic_target_app(Path("./tmp_synthetic_app"), include_flaws=True)
orchestrator = ExtremeTestOrchestrator()

config = ExtremeTestConfig(
    target_path=synth.root_dir,
    num_agents=3,
    owned_target=True,
    authorized_by="app-owner",
    offline=True,
    endpoints=synth.endpoints,
    screens=synth.screens,
    system_flows=synth.system_flows,
)

report = orchestrator.run(config, requester=synth.dispatch_request)
print(report.to_markdown())
```

## CLI Usage

```bash
# Run with 4 parallel agents on an owned target directory
nexcoder-testing run ./my-app --owned-target --authorized-by dev-team --num-agents 4

# Run the offline synthetic target demo
nexcoder-testing demo-synthetic ./tmp/synth-demo --num-agents 5
```
