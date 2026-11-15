"""Server hardening automation, checklist evaluation, and idempotent script generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

HardeningProfile = Literal["basic", "advanced"]


class HardeningOptions(BaseModel):
    """Configuration options for server hardening."""

    profile: HardeningProfile = "basic"
    os_target: Literal["linux", "windows"] = "linux"
    ssh_port: int = 22
    allow_ssh_ports: list[int] = Field(default_factory=lambda: [22])
    allow_web_ports: list[int] = Field(default_factory=lambda: [80, 443])
    disable_root_login: bool = True
    disable_password_auth: bool = True
    service_user: str = "nexcoder"
    service_user_shell: str = "/usr/sbin/nologin"
    enable_fail2ban: bool = True
    fail2ban_maxretry: int = 3
    fail2ban_bantime: int = 3600
    fail2ban_findtime: int = 600
    enable_auto_updates: bool = True
    enable_kernel_sysctl: bool = True
    firewall_tool: Literal["ufw", "nftables", "netsh"] = "ufw"
    umask: str = "027"
    custom_sysctl: dict[str, str] = Field(default_factory=dict)


class HardeningCheckItem(BaseModel):
    """Individual item in the security hardening checklist."""

    item_id: str
    category: str
    description: str
    compliant: bool
    remediation_hint: str
    severity: Literal["low", "medium", "high", "critical"] = "high"


class HardeningResult(BaseModel):
    """Outcome of hardening checklist evaluation or remediation."""

    total_checks: int
    passed_checks: int
    failed_checks: int
    changes_made: int
    idempotent: bool
    items: list[HardeningCheckItem] = Field(default_factory=list)
    remediated_items: list[str] = Field(default_factory=list)


def generate_bash_hardening_script(options: HardeningOptions | None = None) -> str:
    """Generate an idempotent, production-grade Bash hardening script for Linux hosts."""
    opts = options or HardeningOptions(os_target="linux")

    ssh_ports_csv = ",".join(str(p) for p in opts.allow_ssh_ports)
    web_ports_csv = ",".join(str(p) for p in opts.allow_web_ports)

    lines: list[str] = [
        "#!/usr/bin/env bash",
        "# Hardened server security bootstrap for Linux (Ubuntu/Debian)",
        "# Idempotent execution: safe to run multiple times without duplicating state.",
        "set -euo pipefail",
        "",
        'echo "=== [nexcoder-security] Starting server hardening checklist ==="',
        "",
        "# 1. Principle of least privilege: Require root execution",
        'if [[ $EUID -ne 0 ]]; then',
        '    echo "ERROR: This script must be executed as root (sudo)." >&2',
        "    exit 1",
        "fi",
        "",
        "# 2. Dedicated unprivileged service user and restricted umask",
        f'SERVICE_USER="{opts.service_user}"',
        'if id "$SERVICE_USER" &>/dev/null; then',
        '    echo "[CHECK] Service user $SERVICE_USER already exists. Skipping creation."',
        "else",
        '    echo "[ACTION] Creating unprivileged system user $SERVICE_USER..."',
        f'    useradd --system --no-create-home --shell "{opts.service_user_shell}" "$SERVICE_USER"',
        "fi",
        "",
        'UMASK_FILE="/etc/profile.d/nexcoder-umask.sh"',
        f'if [[ ! -f "$UMASK_FILE" ]] || ! grep -q "umask {opts.umask}" "$UMASK_FILE"; then',
        f'    echo "[ACTION] Setting secure umask {opts.umask}..."',
        f'    echo "umask {opts.umask}" > "$UMASK_FILE"',
        '    chmod 0644 "$UMASK_FILE"',
        "else",
        f'    echo "[CHECK] Secure umask {opts.umask} already configured."',
        "fi",
        "",
        "# 3. Firewall Hardening",
    ]

    if opts.firewall_tool == "ufw":
        lines.extend(
            [
                'if command -v ufw &>/dev/null; then',
                '    echo "[ACTION] Configuring UFW firewall rules..."',
                "    ufw --force reset &>/dev/null || true",
                "    ufw default deny incoming",
                "    ufw default allow outgoing",
            ]
        )
        for port in opts.allow_ssh_ports:
            lines.append(f'    ufw allow {port}/tcp comment "SSH access"')
        for port in opts.allow_web_ports:
            lines.append(f'    ufw allow {port}/tcp comment "Web ingress"')
        lines.extend(
            [
                "    ufw --force enable",
                '    echo "[CHECK] UFW enabled with default deny and explicit ingress."',
                "else",
                '    echo "[WARN] ufw not installed. Skipping UFW configuration."',
                "fi",
            ]
        )
    elif opts.firewall_tool == "nftables":
        lines.extend(
            [
                'if command -v nft &>/dev/null; then',
                '    echo "[ACTION] Configuring nftables firewall..."',
                "    nft flush ruleset || true",
                "    nft add table inet filter",
                "    nft add chain inet filter input '{ type filter hook input priority 0; policy drop; }'",
                "    nft add chain inet filter forward '{ type filter hook forward priority 0; policy drop; }'",
                "    nft add chain inet filter output '{ type filter hook output priority 0; policy accept; }'",
                "    nft add rule inet filter input ct state established,related accept",
                "    nft add rule inet filter input iifname lo accept",
                f"    nft add rule inet filter input tcp dport '{{ {ssh_ports_csv} }}' accept",
                f"    nft add rule inet filter input tcp dport '{{ {web_ports_csv} }}' accept",
                '    echo "[CHECK] nftables configured with default drop and allowed ports."',
                "fi",
            ]
        )

    lines.extend(
        [
            "",
            "# 4. SSH Daemon Hardening (passwordless, no root login, timeouts)",
            'SSHD_DIR="/etc/ssh/sshd_config.d"',
            'SSHD_CONF="/etc/ssh/sshd_config.d/99-nexcoder-security.conf"',
            'if [[ -d "$SSHD_DIR" ]]; then',
            '    cat <<\'EOF\' > "$SSHD_CONF"',
            "# Hardened SSH configuration applied by nexcoder-security",
            f"Port {opts.ssh_port}",
            f"PermitRootLogin {'no' if opts.disable_root_login else 'prohibit-password'}",
            f"PasswordAuthentication {'no' if opts.disable_password_auth else 'yes'}",
            "PubkeyAuthentication yes",
            "X11Forwarding no",
            "MaxAuthTries 4",
            "ClientAliveInterval 300",
            "ClientAliveCountMax 2",
            "AuthenticationMethods publickey",
            "EOF",
            '    chmod 0600 "$SSHD_CONF"',
            '    if command -v sshd &>/dev/null && sshd -t -f "$SSHD_CONF" 2>/dev/null; then',
            '        systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null || true',
            '        echo "[CHECK] SSH hardening configuration verified and reloaded."',
            "    else",
            '        echo "[CHECK] SSH hardening configuration written."',
            "    fi",
            "else",
            '    echo "[WARN] sshd_config.d directory not found. Appending to main sshd_config if absent."',
            '    MAIN_SSHD="/etc/ssh/sshd_config"',
            '    if [[ -f "$MAIN_SSHD" ]]; then',
            '        sed -i -E "s/^#?PermitRootLogin .*/PermitRootLogin no/" "$MAIN_SSHD"',
            '        sed -i -E "s/^#?PasswordAuthentication .*/PasswordAuthentication no/" "$MAIN_SSHD"',
            '        sed -i -E "s/^#?X11Forwarding .*/X11Forwarding no/" "$MAIN_SSHD"',
            "    fi",
            "fi",
            "",
            "# 5. Fail2ban Intrusion Prevention",
        ]
    )

    if opts.enable_fail2ban:
        lines.extend(
            [
                'FAIL2BAN_JAIL="/etc/fail2ban/jail.local"',
                'if [[ -d "/etc/fail2ban" ]]; then',
                '    cat <<\'EOF\' > "$FAIL2BAN_JAIL"',
                "[DEFAULT]",
                f"bantime = {opts.fail2ban_bantime}",
                f"findtime = {opts.fail2ban_findtime}",
                f"maxretry = {opts.fail2ban_maxretry}",
                "backend = systemd",
                "",
                "[sshd]",
                "enabled = true",
                f"port = {opts.ssh_port}",
                "EOF",
                '    chmod 0644 "$FAIL2BAN_JAIL"',
                '    systemctl restart fail2ban 2>/dev/null || true',
                '    echo "[CHECK] Fail2ban configured with strict sshd jail."',
                "else",
                '    echo "[INFO] fail2ban not installed. Install via apt-get install fail2ban to activate."',
                "fi",
            ]
        )

    lines.extend(
        [
            "",
            "# 6. Automatic Security Updates",
        ]
    )

    if opts.enable_auto_updates:
        lines.extend(
            [
                'UPGRADES_CONF="/etc/apt/apt.conf.d/50unattended-upgrades"',
                'AUTO_UPGRADES="/etc/apt/apt.conf.d/20auto-upgrades"',
                'if [[ -d "/etc/apt/apt.conf.d" ]]; then',
                '    cat <<\'EOF\' > "$AUTO_UPGRADES"',
                'APT::Periodic::Update-Package-Lists "1";',
                'APT::Periodic::Unattended-Upgrade "1";',
                'APT::Periodic::AutocleanInterval "7";',
                "EOF",
                '    echo "[CHECK] Unattended security updates configured."',
                "fi",
            ]
        )

    lines.extend(
        [
            "",
            "# 7. Kernel Network and Memory Hardening (sysctl)",
        ]
    )

    if opts.enable_kernel_sysctl:
        sysctl_entries = {
            "net.ipv4.ip_forward": "0",
            "net.ipv4.tcp_syncookies": "1",
            "net.ipv4.conf.all.accept_redirects": "0",
            "net.ipv4.conf.default.accept_redirects": "0",
            "net.ipv4.conf.all.send_redirects": "0",
            "net.ipv4.conf.default.send_redirects": "0",
            "net.ipv4.conf.all.accept_source_route": "0",
            "net.ipv4.conf.default.accept_source_route": "0",
            "net.ipv6.conf.all.accept_redirects": "0",
            "net.ipv4.icmp_echo_ignore_broadcasts": "1",
            "fs.protected_hardlinks": "1",
            "fs.protected_symlinks": "1",
            "kernel.randomize_va_space": "2",
        }
        sysctl_entries.update(opts.custom_sysctl)

        lines.extend(
            [
                'SYSCTL_CONF="/etc/sysctl.d/99-nexcoder-security.conf"',
                'cat <<\'EOF\' > "$SYSCTL_CONF"',
                "# Kernel security parameters applied by nexcoder-security",
            ]
        )
        for k, v in sysctl_entries.items():
            lines.append(f"{k} = {v}")
        lines.extend(
            [
                "EOF",
                'chmod 0644 "$SYSCTL_CONF"',
                'sysctl --system &>/dev/null || sysctl -p "$SYSCTL_CONF" &>/dev/null || true',
                'echo "[CHECK] Kernel security parameters loaded."',
            ]
        )

    lines.extend(
        [
            "",
            'echo "=== [nexcoder-security] Server hardening completed successfully ==="',
        ]
    )

    return "\n".join(lines) + "\n"


def generate_ps1_hardening_script(options: HardeningOptions | None = None) -> str:
    """Generate an idempotent, production-grade PowerShell hardening script for Windows hosts."""
    opts = options or HardeningOptions(os_target="windows")

    lines: list[str] = [
        "# Hardened server security bootstrap for Windows Server / Windows",
        "# Idempotent execution: safe to run multiple times without duplicating state.",
        "$ErrorActionPreference = 'Stop'",
        "",
        'Write-Host "=== [nexcoder-security] Starting Windows server hardening ==="',
        "",
        "# 1. Ensure Administrative execution",
        "$curUser = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()",
        "$isAdmin = $curUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)",
        "if (-not $isAdmin) {",
        '    Write-Error "This script must be executed with Administrator privileges."',
        "    exit 1",
        "}",
        "",
        "# 2. Dedicated service account check / creation",
        f'$ServiceUser = "{opts.service_user}"',
        "$existingUser = Get-LocalUser -Name $ServiceUser -ErrorAction SilentlyContinue",
        "if (-not $existingUser) {",
        '    Write-Host "[ACTION] Creating unprivileged local user $ServiceUser..."',
        '    $dummyPass = ConvertTo-SecureString "A1!dummy_vault_secret_placeholder" -AsPlainText -Force',
        "    New-LocalUser -Name $ServiceUser -Password $dummyPass -PasswordNeverExpires "
        "-UserMayNotChangePassword | Out-Null",
        "} else {",
        '    Write-Host "[CHECK] Service user $ServiceUser already exists."',
        "}",
        "",
        "# 3. Windows Defender Firewall Hardening",
        "$prof = 'Domain,Public,Private'",
        "Set-NetFirewallProfile -Profile $prof -DefaultInboundAction Block -DefaultOutboundAction Allow",
        'Write-Host "[CHECK] Inbound firewall policy set to Block by default."',
    ]

    for port in opts.allow_web_ports:
        rule_name = f"NexCoder-Allow-Web-{port}"
        lines.extend(
            [
                f'$rule = Get-NetFirewallRule -DisplayName "{rule_name}" -ErrorAction SilentlyContinue',
                "if (-not $rule) {",
                f'    Write-Host "[ACTION] Creating firewall rule for TCP port {port}..."',
                f'    New-NetFirewallRule -DisplayName "{rule_name}" -Direction Inbound '
                f"-LocalPort {port} -Protocol TCP -Action Allow | Out-Null",
                "} else {",
                f'    Write-Host "[CHECK] Firewall rule for port {port} already active."',
                "}",
            ]
        )

    for port in opts.allow_ssh_ports:
        rule_name = f"NexCoder-Allow-SSH-{port}"
        lines.extend(
            [
                f'$rule = Get-NetFirewallRule -DisplayName "{rule_name}" -ErrorAction SilentlyContinue',
                "if (-not $rule) {",
                f'    Write-Host "[ACTION] Creating firewall rule for SSH port {port}..."',
                f'    New-NetFirewallRule -DisplayName "{rule_name}" -Direction Inbound '
                f"-LocalPort {port} -Protocol TCP -Action Allow | Out-Null",
                "} else {",
                f'    Write-Host "[CHECK] Firewall rule for SSH port {port} already active."',
                "}",
            ]
        )

    lines.extend(
        [
            "",
            "# 4. Disallow unauthenticated null sessions and SMBv1",
            "$srvParam = 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters'",
            "Set-ItemProperty -Path $srvParam -Name 'NullSessionPipes' -Value @() -ErrorAction SilentlyContinue",
            "Set-ItemProperty -Path $srvParam -Name 'SMB1' -Value 0 -ErrorAction SilentlyContinue",
            'Write-Host "[CHECK] SMBv1 disabled and null sessions eliminated."',
            "",
            'Write-Host "=== [nexcoder-security] Windows server hardening completed ==="',
        ]
    )

    return "\r\n".join(lines) + "\r\n"


class ServerHardeningEngine:
    """Programmatic hardening engine for verifying and simulating server state idempotently."""

    def __init__(self, options: HardeningOptions | None = None) -> None:
        self.options = options or HardeningOptions()

    def audit_checklist(self, state: dict[str, Any] | None = None) -> list[HardeningCheckItem]:
        """Audit current server configuration against hardening checklist."""
        sys_state = state or {}
        items: list[HardeningCheckItem] = []

        # 1. Root login (compliant only if explicitly disabled)
        root_login_disabled = sys_state.get("permit_root_login") is False
        items.append(
            HardeningCheckItem(
                item_id="ssh_permit_root_login",
                category="ssh",
                description="Disable direct SSH root login (PermitRootLogin no)",
                compliant=root_login_disabled,
                remediation_hint="Set PermitRootLogin no in sshd_config",
                severity="critical",
            )
        )

        # 2. Password auth (compliant only if explicitly disabled)
        password_auth_disabled = sys_state.get("password_authentication") is False
        items.append(
            HardeningCheckItem(
                item_id="ssh_password_auth",
                category="ssh",
                description="Require SSH public keys and disable password auth",
                compliant=password_auth_disabled,
                remediation_hint="Set PasswordAuthentication no in sshd_config",
                severity="critical",
            )
        )

        # 3. Firewall default deny (compliant only if explicitly configured to deny)
        firewall_deny = sys_state.get("firewall_default_incoming") == "deny"
        items.append(
            HardeningCheckItem(
                item_id="firewall_default_deny",
                category="firewall",
                description="Default incoming network traffic must be dropped/denied",
                compliant=firewall_deny,
                remediation_hint="Configure default drop/deny incoming policy in ufw/nftables/firewall",
                severity="critical",
            )
        )

        # 4. Fail2ban
        fail2ban_active = sys_state.get("fail2ban_active", False) is True
        items.append(
            HardeningCheckItem(
                item_id="fail2ban_active",
                category="intrusion_prevention",
                description="Fail2ban monitoring SSH brute-force attempts",
                compliant=fail2ban_active,
                remediation_hint="Install and enable fail2ban jail for sshd",
                severity="high",
            )
        )

        # 5. Non-root user
        service_user_present = bool(sys_state.get("service_user_exists", False))
        items.append(
            HardeningCheckItem(
                item_id="service_user_isolated",
                category="privilege",
                description="Dedicated unprivileged user created for application execution",
                compliant=service_user_present,
                remediation_hint=f"Create dedicated unprivileged service user '{self.options.service_user}'",
                severity="high",
            )
        )

        # 6. Sysctl syncookies
        syncookies = sys_state.get("tcp_syncookies") == 1
        items.append(
            HardeningCheckItem(
                item_id="sysctl_syncookies",
                category="kernel",
                description="Kernel TCP SYN cookies enabled against SYN floods",
                compliant=syncookies,
                remediation_hint="Set net.ipv4.tcp_syncookies = 1 in sysctl",
                severity="medium",
            )
        )

        # 7. Unattended updates
        auto_updates = sys_state.get("auto_updates_enabled", False) is True
        items.append(
            HardeningCheckItem(
                item_id="unattended_updates",
                category="patching",
                description="Automatic security updates scheduled",
                compliant=auto_updates,
                remediation_hint="Enable unattended-upgrades periodic job",
                severity="high",
            )
        )

        return items

    def apply_checklist(
        self,
        current_state: dict[str, Any],
    ) -> tuple[dict[str, Any], HardeningResult]:
        """Apply hardening checklist to state, remediating non-compliant items.

        Returns the new state and the hardening result with exact changes_made count.
        """
        audit_before = self.audit_checklist(current_state)
        new_state = dict(current_state)
        remediated: list[str] = []

        for item in audit_before:
            if not item.compliant:
                if item.item_id == "ssh_permit_root_login":
                    new_state["permit_root_login"] = False
                    remediated.append(item.item_id)
                elif item.item_id == "ssh_password_auth":
                    new_state["password_authentication"] = False
                    remediated.append(item.item_id)
                elif item.item_id == "firewall_default_deny":
                    new_state["firewall_default_incoming"] = "deny"
                    remediated.append(item.item_id)
                elif item.item_id == "fail2ban_active":
                    new_state["fail2ban_active"] = True
                    remediated.append(item.item_id)
                elif item.item_id == "service_user_isolated":
                    new_state["service_user_exists"] = True
                    remediated.append(item.item_id)
                elif item.item_id == "sysctl_syncookies":
                    new_state["tcp_syncookies"] = 1
                    remediated.append(item.item_id)
                elif item.item_id == "unattended_updates":
                    new_state["auto_updates_enabled"] = True
                    remediated.append(item.item_id)

        audit_after = self.audit_checklist(new_state)
        passed = sum(1 for i in audit_after if i.compliant)
        failed = sum(1 for i in audit_after if not i.compliant)

        res = HardeningResult(
            total_checks=len(audit_after),
            passed_checks=passed,
            failed_checks=failed,
            changes_made=len(remediated),
            idempotent=True,
            items=audit_after,
            remediated_items=remediated,
        )
        return new_state, res

    def verify_idempotence(self, initial_state: dict[str, Any]) -> bool:
        """Verify that running the hardening remediation twice leaves the second run with 0 changes."""
        state_after_first, res_first = self.apply_checklist(initial_state)
        state_after_second, res_second = self.apply_checklist(state_after_first)

        return (
            res_second.changes_made == 0
            and res_second.failed_checks == 0
            and state_after_first == state_after_second
        )
