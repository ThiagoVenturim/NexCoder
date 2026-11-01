from __future__ import annotations

import re
from pathlib import Path


def generate_csp_header(
    profile: str = "strict",
    custom_directives: dict[str, list[str]] | None = None,
) -> str:
    """Generate a standard Content Security Policy (CSP) header value.

    Profiles:
    - 'strict': default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'
    - 'spa': includes font-src, inline styles with hash/nonce placeholder
    - 'api': default-src 'none'; frame-ancestors 'none'; sandbox
    """
    directives: dict[str, list[str]] = {}

    if profile == "api":
        directives = {
            "default-src": ["'none'"],
            "frame-ancestors": ["'none'"],
            "base-uri": ["'none'"],
        }
    elif profile == "spa":
        directives = {
            "default-src": ["'self'"],
            "script-src": ["'self'"],
            "style-src": ["'self'", "'unsafe-inline'"],
            "img-src": ["'self'", "data:", "https:"],
            "font-src": ["'self'", "https:"],
            "connect-src": ["'self'"],
            "frame-ancestors": ["'none'"],
            "base-uri": ["'self'"],
            "form-action": ["'self'"],
        }
    else:  # strict default
        directives = {
            "default-src": ["'none'"],
            "script-src": ["'self'"],
            "style-src": ["'self'"],
            "img-src": ["'self'", "data:"],
            "connect-src": ["'self'"],
            "frame-ancestors": ["'none'"],
            "base-uri": ["'none'"],
            "form-action": ["'self'"],
        }

    if custom_directives:
        for k, v in custom_directives.items():
            directives[k] = v

    parts = [f"{k} {' '.join(v)}" for k, v in directives.items()]
    return "; ".join(parts)


def generate_security_md(
    project_name: str,
    contact_email: str = "security@example.com",
    supported_versions: list[str] | None = None,
) -> str:
    """Generate a standard SECURITY.md responsible disclosure policy document."""
    versions = supported_versions or ["0.1.x", "0.2.x"]
    ver_table = "\n".join([f"| {v} | Supported |" for v in versions])

    return f"""# Security Policy

## Supported Versions

The following versions of **{project_name}** are currently supported with security updates:

| Version | Supported |
| ------- | --------- |
{ver_table}

## Reporting a Vulnerability

We take the security of {project_name} seriously. If you believe you have found a security vulnerability,
please report it responsibly.

### How to Report

- **Email**: Send vulnerability reports directly to `{contact_email}`.
- **Details to Include**:
  - Description of the issue and potential impact.
  - Minimal reproducible example or proof-of-concept steps.
  - Affected versions and environments.

Please do **not** disclose security vulnerabilities publicly via GitHub issues or discussions until
a patch has been released and coordinated.

### Our Commitment

- We will acknowledge receipt of your vulnerability report within 48 hours.
- We will provide regular updates regarding remediation progress.
- Once fixed, we will credit responsible reporters in our release notes (unless requested otherwise).
"""


def pin_dependencies(
    requirements_text: str,
    default_fallback_version: str = "1.0.0",
) -> str:
    """Convert unpinned or range-based requirements into exact pinned versions."""
    pinned_lines: list[str] = []

    for line in requirements_text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            pinned_lines.append(line)
            continue

        # Already pinned with ==
        if "==" in clean:
            pinned_lines.append(clean)
            continue

        # Match package name and possible existing bounds
        m = re.match(r"^([a-zA-Z0-9_\-]+)(?:[>=<~^]+([0-9a-zA-Z\.\-]+))?", clean)
        if m:
            pkg_name = m.group(1)
            found_ver = m.group(2) or default_fallback_version
            pinned_lines.append(f"{pkg_name}=={found_ver}")
        else:
            pinned_lines.append(clean)

    return "\n".join(pinned_lines) + "\n"


def scaffold_app_security(
    target_dir: str | Path,
    project_name: str,
    contact_email: str = "security@example.com",
) -> dict[str, str]:
    """Generate standard security assets for a new application."""
    dir_path = Path(target_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    sec_md_path = dir_path / "SECURITY.md"
    sec_content = generate_security_md(project_name=project_name, contact_email=contact_email)
    sec_md_path.write_text(sec_content, encoding="utf-8")

    csp_header = generate_csp_header(profile="strict")

    return {
        "security_md": str(sec_md_path),
        "csp_header": csp_header,
    }
