"""Offline tests for multi-agent extreme application testing (nexcoder-testing)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nexcoder_agents.engine.pipelines import build_pipeline, get_pipeline_template
from nexcoder_control.approval import (
    ApprovalTokenManager,
    TargetAuthorizationGate,
    TargetNotAuthorizedError,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_security.models import Severity
from nexcoder_testing import (
    DOMScreenSpec,
    ExtremeTestConfig,
    ExtremeTestOrchestrator,
    TestScope,
    create_extreme_testing_pipeline,
    create_synthetic_target_app,
)
from nexcoder_testing.cli import main as cli_main


def test_unmarked_target_is_refused_and_audited(tmp_path: Path) -> None:
    """Running extreme testing without owned_target or authorization must fail and log denial."""
    synth = create_synthetic_target_app(tmp_path / "unmarked_app")
    audit_log = AppendOnlyAuditLog()
    gate = TargetAuthorizationGate(audit_log=audit_log)
    orchestrator = ExtremeTestOrchestrator(target_gate=gate, audit_log=audit_log)

    cfg = ExtremeTestConfig(
        target_path=synth.root_dir,
        num_agents=2,
        owned_target=False,
        authorized_by="tester",
    )

    with pytest.raises(TargetNotAuthorizedError):
        orchestrator.run(cfg, requester=synth.dispatch_request)

    denied_events = audit_log.query(event_type="target.authorization.denied")
    assert len(denied_events) == 1
    assert denied_events[0].details["status"] == "denied"
    valid, _ = audit_log.verify_integrity()
    assert valid is True


def test_third_party_external_url_is_refused(tmp_path: Path) -> None:
    """Attempting to target a third-party external hostname must be refused even if owned_target=True."""
    synth = create_synthetic_target_app(tmp_path / "app")
    audit_log = AppendOnlyAuditLog()
    orchestrator = ExtremeTestOrchestrator(audit_log=audit_log)

    cfg = ExtremeTestConfig(
        target_path=synth.root_dir,
        base_url="https://third-party-unowned.example.org",
        num_agents=2,
        owned_target=True,
        authorized_by="owner",
    )

    with pytest.raises(TargetNotAuthorizedError, match="outside allowed local/owned hosts"):
        orchestrator.run(cfg)

    denied = audit_log.query(event_type="target.authorization.denied")
    assert len(denied) == 1
    assert denied[0].resource == "https://third-party-unowned.example.org"


def test_authorization_via_pre_registered_gate_and_approval_token(tmp_path: Path) -> None:
    """Targets authorized via mark_owned_target or single-use ApprovalTokenManager succeed."""
    synth = create_synthetic_target_app(tmp_path / "token_app", include_flaws=False)
    audit_log = AppendOnlyAuditLog()
    token_mgr = ApprovalTokenManager()
    gate = TargetAuthorizationGate(audit_log=audit_log, token_manager=token_mgr)
    orchestrator = ExtremeTestOrchestrator(target_gate=gate, audit_log=audit_log)

    # 1. Single-use approval token
    _, raw_token = token_mgr.issue_token(
        action_name="extreme_testing",
        target_resource=str(synth.root_dir.resolve()),
        approver="security-lead",
    )
    cfg_token = ExtremeTestConfig(
        target_path=synth.root_dir,
        num_agents=2,
        scopes=[TestScope.UNIT],
        owned_target=False,
        approval_token=raw_token,
    )
    rep1 = orchestrator.run(cfg_token, requester=synth.dispatch_request)
    assert rep1.ownership == "authorized"
    assert rep1.total_tests > 0

    # 2. Pre-registered owned target in gate
    orchestrator.authorize_target(synth.root_dir, authorized_by="repo-owner")
    cfg_reg = ExtremeTestConfig(
        target_path=synth.root_dir,
        num_agents=1,
        scopes=[TestScope.UNIT],
        owned_target=False,
    )
    rep2 = orchestrator.run(cfg_reg, requester=synth.dispatch_request)
    assert rep2.ownership == "owned"
    assert rep2.authorized_by == "repo-owner"


@pytest.mark.parametrize("num_agents", [1, 2, 3, 5, 8])
def test_configurable_n_agents_partition_and_merge(tmp_path: Path, num_agents: int) -> None:
    """Orchestrator partitions work across N=1..8 agents and produces a consistent merged report."""
    synth = create_synthetic_target_app(tmp_path / f"app_n{num_agents}", include_flaws=True)
    audit_log = AppendOnlyAuditLog()
    orchestrator = ExtremeTestOrchestrator(audit_log=audit_log)

    cfg = ExtremeTestConfig(
        target_path=synth.root_dir,
        num_agents=num_agents,
        scopes=TestScope.all_scopes(),
        owned_target=True,
        authorized_by="qa-lead",
        endpoints=synth.endpoints,
        screens=synth.screens,
        system_flows=synth.system_flows,
    )

    slices = orchestrator.partition_work(cfg)
    assert len(slices) == num_agents

    report = orchestrator.run(cfg, requester=synth.dispatch_request)
    assert report.num_agents == num_agents
    assert len(report.agent_reports) == num_agents
    assert report.total_tests >= 15

    # Verify all 5 scopes are present in scope_summaries
    for scope in TestScope.all_scopes():
        assert scope.value in report.scope_summaries
        assert report.scope_summaries[scope.value].total_tests >= 1

    # Verify planted flaws across unit, dom, api, and security are caught and deduplicated
    rule_ids = {f.rule_id for f in report.findings}
    assert "UNIT-CONTRACT-001" in rule_ids  # ZeroDivisionError in compute_page_count
    assert "API-AUTH-001" in rule_ids  # Missing auth on /api/admin/debug
    assert "SEC-LOG-LEAK-001" in rule_ids  # Secret leaked in app.log
    assert "SEC-RESP-LEAK-001" in rule_ids  # Secret leaked in /api/admin/debug response
    assert "SEC-HEADER-001" in rule_ids  # Missing security headers on /api/admin/debug
    assert "SEC-ERR-LEAK-001" in rule_ids  # 500 stack trace on malformed POST

    # Verify secrets are redacted in finding descriptions and audit log
    full_md = report.to_markdown()
    assert "sk-syntheticlogsecret123456789" not in full_md
    assert "sk-syntheticdebug9876543210abcdef" not in full_md
    assert "[REDACTED]" in full_md

    # Verify generated test artifacts (unit, system, api, Playwright UI test, Page Object)
    artifact_scopes = {a.scope for a in report.artifacts}
    assert TestScope.UNIT in artifact_scopes
    assert TestScope.SYSTEM in artifact_scopes
    assert TestScope.DOM in artifact_scopes
    assert TestScope.API in artifact_scopes

    # Verify security gate blocks flawed target
    assert report.security_gate_verdict is not None
    assert report.security_gate_verdict.passed is False
    assert report.has_critical_or_high() is True

    # Verify audit trail events
    assert len(report.audit_event_ids) == num_agents + 2
    valid, _ = audit_log.verify_integrity()
    assert valid is True


def test_clean_synthetic_target_passes_all_tests_and_security_gate(tmp_path: Path) -> None:
    """When the synthetic target has no flaws, all unit, system, DOM, API, and security checks pass."""
    synth = create_synthetic_target_app(tmp_path / "clean_app", include_flaws=False)
    orchestrator = ExtremeTestOrchestrator()

    cfg = ExtremeTestConfig(
        target_path=synth.root_dir,
        num_agents=4,
        scopes=TestScope.all_scopes(),
        owned_target=True,
        authorized_by="owner",
        endpoints=synth.endpoints,
        screens=synth.screens,
        system_flows=synth.system_flows,
    )

    report = orchestrator.run(cfg, requester=synth.dispatch_request)
    assert report.failed_tests == 0
    assert report.passed_tests == report.total_tests
    assert len(report.findings_by_severity(Severity.CRITICAL)) == 0
    assert len(report.findings_by_severity(Severity.HIGH)) == 0
    assert report.security_gate_verdict is not None
    assert report.security_gate_verdict.passed is True


def test_ephemeral_localhost_http_server_e2e(tmp_path: Path) -> None:
    """System, API, and Security runners work against a real local ephemeral HTTP server."""
    synth = create_synthetic_target_app(tmp_path / "live_ephemeral", include_flaws=False)
    orchestrator = ExtremeTestOrchestrator()

    with synth.start_ephemeral_server() as base_url:
        cfg = ExtremeTestConfig(
            target_path=synth.root_dir,
            base_url=base_url,
            num_agents=3,
            scopes=[TestScope.SYSTEM, TestScope.API, TestScope.SECURITY],
            owned_target=True,
            authorized_by="owner",
            endpoints=synth.endpoints,
            system_flows=synth.system_flows,
        )
        report = orchestrator.run(cfg)

    assert report.total_tests >= 10
    assert report.failed_tests == 0
    assert report.security_gate_verdict is not None
    assert report.security_gate_verdict.passed is True


def test_offline_is_default_and_uses_offline_preset() -> None:
    """Config and orchestrator default to offline mode and the offline nexcoder preset."""
    cfg = ExtremeTestConfig()
    assert cfg.offline is True
    assert cfg.owned_target is False
    orchestrator = ExtremeTestOrchestrator()
    assert orchestrator.nexcoder_config.preset == "offline"


def test_offline_mode_refuses_widened_remote_host(tmp_path: Path) -> None:
    """In offline mode a remote host is refused even when the user adds it to allowed_hosts."""
    synth = create_synthetic_target_app(tmp_path / "offline_app")
    audit_log = AppendOnlyAuditLog()
    orchestrator = ExtremeTestOrchestrator(audit_log=audit_log)

    cfg = ExtremeTestConfig(
        target_path=synth.root_dir,
        base_url="https://staging.example.org",
        allowed_hosts=["localhost", "127.0.0.1", "staging.example.org"],
        owned_target=True,
    )
    with pytest.raises(TargetNotAuthorizedError, match="offline mode"):
        orchestrator.run(cfg)
    assert len(audit_log.query(event_type="target.authorization.denied")) == 1


def test_full_run_opens_no_external_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A full N-agent run against a local ephemeral target only ever connects to loopback addresses."""
    import ipaddress
    import socket

    synth = create_synthetic_target_app(tmp_path / "netguard_app", include_flaws=True)
    original_connect = socket.socket.connect
    attempted: list[str] = []

    def guarded_connect(self: socket.socket, address: object) -> None:
        host = address[0] if isinstance(address, tuple) else str(address)
        attempted.append(str(host))
        if not ipaddress.ip_address(str(host)).is_loopback:
            raise AssertionError(f"external network access attempted: {host}")
        return original_connect(self, address)

    with synth.start_ephemeral_server() as base_url:
        monkeypatch.setattr(socket.socket, "connect", guarded_connect)
        cfg = ExtremeTestConfig(
            target_path=synth.root_dir,
            base_url=base_url,
            num_agents=3,
            scopes=TestScope.all_scopes(),
            owned_target=True,
            endpoints=synth.endpoints,
            screens=synth.screens,
            system_flows=synth.system_flows,
        )
        report = ExtremeTestOrchestrator().run(cfg)
        monkeypatch.undo()

    assert report.offline is True
    assert report.total_tests >= 15
    assert attempted, "expected requests to the local target"
    assert all(ipaddress.ip_address(h).is_loopback for h in attempted)


def test_runner_transport_refuses_remote_hosts_on_its_own() -> None:
    """Runners used without the orchestrator still cannot reach third-party or non-local hosts."""
    from nexcoder_testing.gate import TargetHostNotAllowedError, check_target_host
    from nexcoder_testing.models import APIEndpointSpec
    from nexcoder_testing.runners import APIRequestRunner

    with pytest.raises(TargetHostNotAllowedError, match="outside the allowed"):
        APIRequestRunner().run([APIEndpointSpec(path="/health")], base_url="https://third-party.example.org")
    with pytest.raises(TargetHostNotAllowedError, match="offline mode"):
        check_target_host("http://10.0.0.5:8080", offline=True, allowed_hosts=["10.0.0.5"])
    with pytest.raises(TargetHostNotAllowedError, match="scheme"):
        check_target_host("ftp://localhost/x")
    assert check_target_host("http://127.0.0.1:9000") == "127.0.0.1"
    assert check_target_host("http://[::1]:9000") == "::1"
    assert check_target_host("http://10.0.0.5:8080", offline=False, allowed_hosts=["10.0.0.5"]) == "10.0.0.5"


def test_dom_scraping_detects_missing_expected_elements(tmp_path: Path) -> None:
    """DOMScrapingRunner flags missing expected selectors and texts on a screen."""
    synth = create_synthetic_target_app(tmp_path / "dom_missing", include_flaws=False)
    orchestrator = ExtremeTestOrchestrator()

    custom_screen = DOMScreenSpec(
        name="broken_checkout",
        url_or_path=str(synth.root_dir / "templates" / "dashboard.html"),
        expected_selectors=["[data-testid='nonexistent-pay-btn']"],
        expected_texts=["Nonexistent Checkout Banner"],
    )
    cfg = ExtremeTestConfig(
        target_path=synth.root_dir,
        num_agents=1,
        scopes=[TestScope.DOM],
        owned_target=True,
        screens=[custom_screen],
    )

    report = orchestrator.run(cfg)
    assert report.failed_tests >= 1
    assert any(f.rule_id == "DOM-CONTRACT-001" for f in report.findings)


def test_langgraph_pipeline_integration(tmp_path: Path) -> None:
    """ExtremeTestingBlock and 'extreme-testing' template integrate with nexcoder-agents."""
    synth = create_synthetic_target_app(tmp_path / "pipeline_app", include_flaws=True)

    tmpl = get_pipeline_template("extreme-testing")
    assert tmpl.name == "extreme-testing"
    assert tmpl.category == "qa"

    pipeline = build_pipeline("extreme-testing")
    res = pipeline.run(
        inputs={
            "target_path": str(synth.root_dir),
            "num_agents": 3,
            "owned_target": True,
            "authorized_by": "pipeline-operator",
            "endpoints": synth.endpoints,
            "screens": synth.screens,
            "system_flows": synth.system_flows,
            "requester": synth.dispatch_request,
        },
        dry_run=True,
    )

    assert res.status == "completed"
    assert res.data["total_tests"] >= 15
    assert res.data["total_findings"] >= 5
    assert "Extreme Application Test Report" in res.data["extreme_test_markdown"]

    # Also verify pipeline fails closed when owned_target is False
    unauth_pipeline = create_extreme_testing_pipeline().compile()
    unauth_res = unauth_pipeline.run(
        inputs={
            "target_path": str(synth.root_dir),
            "owned_target": False,
        },
        dry_run=True,
    )
    assert unauth_res.status == "failed"


def test_cli_commands_and_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI refuses unmarked target and succeeds with --owned-target or demo-synthetic."""
    synth = create_synthetic_target_app(tmp_path / "cli_app", include_flaws=True)

    # 1. Refused without --owned-target
    code_refused = cli_main(["run", str(synth.root_dir), "--num-agents", "2"])
    assert code_refused == 1
    captured_err = capsys.readouterr()
    assert "Refused:" in captured_err.err

    # 2. Succeeds with --owned-target and writes Markdown output file
    out_md = tmp_path / "report.md"
    code_ok = cli_main(
        [
            "run",
            str(synth.root_dir),
            "--owned-target",
            "--authorized-by",
            "cli-tester",
            "--num-agents",
            "2",
            "--output",
            str(out_md),
        ]
    )
    assert code_ok == 0
    assert out_md.exists()
    assert "Extreme Application Test Report" in out_md.read_text(encoding="utf-8")
    _ = capsys.readouterr()

    # 3. demo-synthetic with --json
    demo_dir = tmp_path / "demo_synth"
    code_demo = cli_main(["demo-synthetic", str(demo_dir), "--num-agents", "3", "--json"])
    assert code_demo == 0
    demo_out = capsys.readouterr().out
    parsed = json.loads(demo_out)
    assert parsed["num_agents"] == 3
    assert len(parsed["findings"]) >= 5
