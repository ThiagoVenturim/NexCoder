"""Unit tests for nexcoder-security server CLI subcommands and audit logging."""

from pathlib import Path

from nexcoder_control.approval import TargetAuthorizationGate
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_security.cli import main


def test_cli_server_nginx_basic(tmp_path: Path):
    audit_log = AppendOnlyAuditLog()
    gate = TargetAuthorizationGate(audit_log=audit_log)
    out_file = tmp_path / "nginx.conf"

    code = main(
        [
            "server",
            "nginx",
            "--domain",
            "test.app",
            "--upstream",
            "127.0.0.1:8000",
            "--output",
            str(out_file),
            "--owned-target",
        ],
        audit_log=audit_log,
        target_gate=gate,
    )
    assert code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "server_name test.app;" in content
    assert "proxy_pass http://app_backend;" in content

    # Check audit log recorded the action
    events = audit_log.query(event_type="server_generate_nginx_config")
    assert len(events) == 1
    assert events[0].resource == "test.app"


def test_cli_server_hardening(tmp_path: Path):
    audit_log = AppendOnlyAuditLog()
    gate = TargetAuthorizationGate(audit_log=audit_log)
    bash_out = tmp_path / "hardening.sh"
    ps1_out = tmp_path / "hardening.ps1"

    code = main(
        [
            "server",
            "hardening",
            "--profile",
            "basic",
            "--os",
            "linux",
            "--output-bash",
            str(bash_out),
            "--output-ps1",
            str(ps1_out),
            "--owned-target",
        ],
        audit_log=audit_log,
        target_gate=gate,
    )
    assert code == 0
    assert bash_out.exists()
    assert ps1_out.exists()
    assert "ufw default deny incoming" in bash_out.read_text(encoding="utf-8")
    assert "Set-NetFirewallProfile" in ps1_out.read_text(encoding="utf-8")

    events = audit_log.query(event_type="server_generate_hardening_scripts")
    assert len(events) == 1


def test_cli_server_isolate(tmp_path: Path):
    audit_log = AppendOnlyAuditLog()
    gate = TargetAuthorizationGate(audit_log=audit_log)

    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        "services:\n  db:\n    image: postgres\n    ports:\n      - '5432:5432'\n",
        encoding="utf-8",
    )

    code = main(
        [
            "server",
            "isolate",
            str(compose_file),
            "--remediate",
            "--owned-target",
        ],
        audit_log=audit_log,
        target_gate=gate,
    )
    assert code == 0
    remediated = compose_file.read_text(encoding="utf-8")
    assert "127.0.0.1:5432:5432" in remediated

    events = audit_log.query(event_type="server_audit_isolation")
    assert len(events) == 1


def test_cli_server_mask(tmp_path: Path):
    audit_log = AppendOnlyAuditLog()
    gate = TargetAuthorizationGate(audit_log=audit_log)

    input_file = tmp_path / "sample.log"
    input_file.write_text(
        "User dev@example.com logged in with token sk-testsecret12345",
        encoding="utf-8",
    )
    output_file = tmp_path / "masked.log"

    code = main(
        [
            "server",
            "mask",
            str(input_file),
            "--format",
            "log",
            "--strategy",
            "placeholder",
            "--output",
            str(output_file),
            "--owned-target",
        ],
        audit_log=audit_log,
        target_gate=gate,
    )
    assert code == 0
    assert output_file.exists()
    masked = output_file.read_text(encoding="utf-8")
    assert "dev@example.com" not in masked
    assert "sk-testsecret12345" not in masked
    assert "[EMAIL_1]" in masked
    assert "[SECRET_1]" in masked

    events = audit_log.query(event_type="server_mask_data")
    assert len(events) == 1
