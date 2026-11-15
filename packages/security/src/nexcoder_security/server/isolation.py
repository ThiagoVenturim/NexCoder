"""Privatization and server isolation engine ensuring internal services never expose raw ports."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

DEFAULT_INTERNAL_PORTS: dict[int, str] = {
    5432: "PostgreSQL Database",
    3306: "MySQL Database",
    6379: "Redis Cache",
    27017: "MongoDB Database",
    9200: "Elasticsearch",
    8000: "App Server Upstream",
    8080: "Alternative App Server",
    9090: "Prometheus Metrics",
}


class IsolationViolation(BaseModel):
    """Detected breach of server isolation or network privatization."""

    rule: str
    target: str
    severity: Literal["low", "medium", "high", "critical"] = "high"
    message: str
    remediation: str


class IsolationReport(BaseModel):
    """Summary of isolation audit."""

    passed: bool
    total_violations: int
    violations: list[IsolationViolation] = Field(default_factory=list)


class ServerIsolationAuditor:
    """Audits network port bindings, Docker Compose mappings, and secret permissions."""

    def __init__(
        self,
        internal_ports: dict[int, str] | None = None,
        allowed_public_ports: set[int] | None = None,
    ) -> None:
        self.internal_ports = internal_ports or DEFAULT_INTERNAL_PORTS
        self.allowed_public_ports = allowed_public_ports or {80, 443, 22}

    def audit_port_bindings(
        self,
        bindings: list[dict[str, Any]],
    ) -> IsolationReport:
        """Audit active port bindings for exposed internal services.

        Each binding is expected to be a dict with keys:
        'port' (int), 'host' (str: e.g. '0.0.0.0', '127.0.0.1', '::'), 'service' (optional str)
        """
        violations: list[IsolationViolation] = []

        for b in bindings:
            port = int(b.get("port", 0))
            host = str(b.get("host", "0.0.0.0")).strip()  # noqa: S104
            service = b.get("service") or self.internal_ports.get(port, f"Port {port}")

            # Check if internal service is bound globally
            is_global = host in {"0.0.0.0", "::", "*", ""}  # noqa: S104
            if is_global and port not in self.allowed_public_ports:
                violations.append(
                    IsolationViolation(
                        rule="internal_service_exposed_globally",
                        target=f"{host}:{port} ({service})",
                        severity="critical" if port in self.internal_ports else "high",
                        message=(
                            f"Internal service '{service}' is listening on public interface ({host}:{port}). "
                            "It must only be accessible via localhost (127.0.0.1) or an isolated private network."
                        ),
                        remediation=(
                            f"Bind '{service}' strictly to 127.0.0.1:{port} or communicate "
                            "exclusively through reverse proxy / private network bridge."
                        ),
                    )
                )

        return IsolationReport(
            passed=len(violations) == 0,
            total_violations=len(violations),
            violations=violations,
        )

    def audit_compose_text(self, compose_content: str) -> IsolationReport:
        """Audit docker-compose.yml content for unshielded host port mappings."""
        violations: list[IsolationViolation] = []
        lines = compose_content.splitlines()

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Match standard yaml port mappings like - "5432:5432" or - 6379:6379
            m = re.search(r'-\s*["\']?(?:([0-9.]+):)?(\d+):(\d+)["\']?', stripped)
            if m:
                bind_ip = m.group(1)
                host_port = int(m.group(2))

                if (not bind_ip or bind_ip in {"0.0.0.0", "::"}) and host_port not in self.allowed_public_ports:  # noqa: S104
                    service_desc = self.internal_ports.get(host_port, f"Port {host_port}")
                    violations.append(
                        IsolationViolation(
                            rule="compose_port_exposed_without_localhost",
                            target=f"Line {idx}: {stripped}",
                            severity="critical" if host_port in self.internal_ports else "high",
                            message=(
                                f"Docker compose maps {host_port} to 0.0.0.0 ({service_desc}). "
                                "Raw database, cache or backend ports must not be exposed to the public internet."
                            ),
                            remediation=(
                                f"Change port mapping to '127.0.0.1:{host_port}:{m.group(3)}' or use "
                                "internal Docker network without host port publishing."
                            ),
                        )
                    )

        return IsolationReport(
            passed=len(violations) == 0,
            total_violations=len(violations),
            violations=violations,
        )

    def remediate_compose_text(self, compose_content: str) -> str:
        """Convert public port mappings for internal services to 127.0.0.1 bindings."""
        remediated_lines: list[str] = []

        for line in compose_content.splitlines():
            # Check for unshielded port mapping e.g. - "5432:5432" or - 5432:5432
            def _repl(m: re.Match[str]) -> str:
                prefix = m.group(1)
                quote_open = m.group(2) or ""
                bind_ip = m.group(3)
                host_port = int(m.group(4))
                container_port = m.group(5)
                quote_close = m.group(6) or quote_open

                if (not bind_ip or bind_ip in {"0.0.0.0", "::"}) and host_port not in self.allowed_public_ports:  # noqa: S104
                    q = quote_open or ('"' if quote_close == '"' else "'")
                    return f"{prefix}{q}127.0.0.1:{host_port}:{container_port}{q}"
                return m.group(0)

            patched = re.sub(
                r'(\s*-\s*)(["\']?)(?:([0-9.]+):)?(\d+):(\d+)(["\']?)',
                _repl,
                line,
            )
            remediated_lines.append(patched)

        return "\n".join(remediated_lines)

    def audit_secret_file_permissions(self, file_path: str | Path) -> IsolationReport:
        """Audit file permissions of sensitive secret/env files on disk."""
        target = Path(file_path)
        violations: list[IsolationViolation] = []

        if not target.exists():
            return IsolationReport(passed=True, total_violations=0, violations=[])

        try:
            stat_res = target.stat()
            # On POSIX check file mode
            if hasattr(os, "stat") and os.name != "nt":
                mode = stat_res.st_mode & 0o777
                # Group or others should have no access (chmod 600 or 400)
                if mode & 0o077 != 0:
                    violations.append(
                        IsolationViolation(
                            rule="insecure_secret_file_permissions",
                            target=str(target),
                            severity="high",
                            message=(
                                f"Secret file has overly permissive mode: {oct(mode)}. "
                                "Must be restricted to 0600 or 0400."
                            ),
                            remediation=f"Run chmod 0600 {target}",
                        )
                    )
        except Exception as exc:
            violations.append(
                IsolationViolation(
                    rule="stat_check_error",
                    target=str(target),
                    severity="low",
                    message=f"Could not inspect file permissions: {exc}",
                    remediation="Verify file access permissions manually",
                )
            )

        return IsolationReport(
            passed=len(violations) == 0,
            total_violations=len(violations),
            violations=violations,
        )
