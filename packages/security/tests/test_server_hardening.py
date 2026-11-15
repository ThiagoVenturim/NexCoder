"""Unit tests for server hardening script generation and idempotence."""

from nexcoder_security.server.hardening import (
    HardeningOptions,
    ServerHardeningEngine,
    generate_bash_hardening_script,
    generate_ps1_hardening_script,
)


def test_generate_bash_hardening_script():
    opts = HardeningOptions(
        profile="advanced",
        os_target="linux",
        ssh_port=2222,
        allow_ssh_ports=[2222],
        allow_web_ports=[80, 443],
        firewall_tool="ufw",
        service_user="appservice",
    )
    script = generate_bash_hardening_script(opts)

    assert "#!/usr/bin/env bash" in script
    assert "set -euo pipefail" in script
    assert 'SERVICE_USER="appservice"' in script
    assert "ufw default deny incoming" in script
    assert "ufw allow 2222/tcp" in script
    assert "ufw allow 80/tcp" in script
    assert "ufw allow 443/tcp" in script
    assert "PermitRootLogin no" in script
    assert "PasswordAuthentication no" in script
    assert "fail2ban" in script
    assert "unattended-upgrades" in script
    assert "net.ipv4.tcp_syncookies = 1" in script


def test_generate_ps1_hardening_script():
    opts = HardeningOptions(
        profile="basic",
        os_target="windows",
        allow_web_ports=[80, 443],
        service_user="winapp",
    )
    script = generate_ps1_hardening_script(opts)

    assert "$ErrorActionPreference = 'Stop'" in script
    assert "Set-NetFirewallProfile" in script
    assert "NexCoder-Allow-Web-80" in script
    assert "NexCoder-Allow-Web-443" in script
    assert "$ServiceUser = \"winapp\"" in script
    assert "New-LocalUser" in script
    assert "SMB1" in script


def test_hardening_engine_audit_checklist():
    engine = ServerHardeningEngine()
    empty_state = {}
    items = engine.audit_checklist(empty_state)

    assert len(items) == 7
    # Since state was empty, default insecure settings are flagged
    non_compliant = [i for i in items if not i.compliant]
    assert len(non_compliant) >= 4
    assert any(i.item_id == "ssh_permit_root_login" for i in non_compliant)
    assert any(i.item_id == "ssh_password_auth" for i in non_compliant)


def test_hardening_engine_idempotence():
    engine = ServerHardeningEngine()

    insecure_state = {
        "permit_root_login": True,
        "password_authentication": True,
        "firewall_default_incoming": "allow",
        "fail2ban_active": False,
        "service_user_exists": False,
        "tcp_syncookies": 0,
        "auto_updates_enabled": False,
    }

    # First pass: remediates non-compliant items
    state_after_first, res_first = engine.apply_checklist(insecure_state)
    assert res_first.changes_made == 7
    assert res_first.failed_checks == 0
    assert res_first.passed_checks == 7

    # Second pass: zero changes made, identical state
    state_after_second, res_second = engine.apply_checklist(state_after_first)
    assert res_second.changes_made == 0
    assert res_second.failed_checks == 0
    assert res_second.passed_checks == 7
    assert state_after_first == state_after_second

    # Helper method explicitly validates idempotence
    assert engine.verify_idempotence(insecure_state) is True
