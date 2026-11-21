"""User credential isolation, safety auditing, and environment template generation."""

from __future__ import annotations

import os
import re

from nexcoder_iac.models import ArchitectureSpec, IaCTarget

# Required user-provided environment variables per cloud provider / target
TARGET_ENV_VARS: dict[IaCTarget, list[str]] = {
    IaCTarget.LOCAL_COMPOSE: [],
    IaCTarget.VM: [
        "SERVER_HOST",
        "SSH_USER",
        "SSH_PRIVATE_KEY_PATH",
    ],
    IaCTarget.AWS: [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
    ],
    IaCTarget.GCP: [
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GCP_PROJECT_ID",
        "GCP_REGION",
    ],
    IaCTarget.AZURE: [
        "ARM_SUBSCRIPTION_ID",
        "ARM_CLIENT_ID",
        "ARM_CLIENT_SECRET",
        "ARM_TENANT_ID",
    ],
    IaCTarget.DIGITALOCEAN: [
        "DIGITALOCEAN_TOKEN",
    ],
    IaCTarget.HETZNER: [
        "HCLOUD_TOKEN",
    ],
}

# Regex patterns for detecting inadvertently embedded secrets
SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"ghp_[A-Za-z0-9_]{36}", "GitHub Personal Access Token"),
    (r"gho_[A-Za-z0-9_]{36}", "GitHub OAuth Access Token"),
    (r"-----BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY-----", "Private Key"),
    (r"xox[baprs]-[0-9a-zA-Z]{10,48}", "Slack Token"),
    (r"(?i)(?:password|secret|api_key|token)\s*=\s*['\"][a-zA-Z0-9_\-\.\$]{12,}['\"]", "Hardcoded plain secret"),
]


def get_required_env_vars(target: IaCTarget) -> list[str]:
    """Get the list of mandatory environment variables for a deployment target."""
    return TARGET_ENV_VARS.get(target, []).copy()


def verify_user_credentials(
    target: IaCTarget,
    env: dict[str, str] | None = None,
) -> tuple[bool, list[str]]:
    """Verify that all credentials for the target exist in the environment without exposing values."""
    required = get_required_env_vars(target)
    if not required:
        return True, []

    source = os.environ if env is None else env
    missing = [var for var in required if not source.get(var)]
    return len(missing) == 0, missing


def scan_for_secrets(content: str) -> list[str]:
    """Inspect generated text for accidental hardcoded credentials or private keys.

    Returns a list of violation descriptions. Empty list means clean.
    """
    findings: list[str] = []

    for pattern, description in SECRET_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            findings.append(f"Potential secret detected ({description}): {len(matches)} occurrence(s)")

    return findings


def generate_env_example(target: IaCTarget, spec: ArchitectureSpec) -> str:
    """Generate a clean .env.example file containing only safe placeholder variables."""
    lines: list[str] = [
        f"# Environment variables for {spec.name} ({target.value})",
        "# Copy this file to .env and insert your real credentials.",
        "# NEVER commit the real .env file into version control.",
        "",
        "# Application Configuration",
        f"APP_ENV={spec.tier.value}",
        f"APP_NAME={spec.name}",
    ]

    # Target specific credentials
    req_vars = get_required_env_vars(target)
    if req_vars:
        lines.append("")
        lines.append(f"# {target.value.upper()} Provider Credentials (Required for Terraform/Cloud)")
        for var in req_vars:
            lines.append(f"{var}=your_{var.lower()}_here")

    # Database credentials if database present
    if spec.database:
        lines.append("")
        lines.append("# Database Credentials (User Managed)")
        lines.append(f"DB_NAME={spec.database.database_name}")
        lines.append("DB_USER=appuser")
        lines.append("DB_PASSWORD=your_secure_db_password_here")
        if target == IaCTarget.LOCAL_COMPOSE:
            lines.append("DB_HOST=db")
        else:
            lines.append("DB_HOST=your_database_endpoint_here")

    # Cache / Redis
    if spec.cache:
        lines.append("")
        lines.append("# Cache / Queue Credentials")
        lines.append("REDIS_PASSWORD=your_secure_redis_password_here")

    # AI Serving
    if spec.ai_serving and spec.ai_serving.enabled:
        lines.append("")
        lines.append("# AI Serving Profile Configuration")
        lines.append("HUGGING_FACE_HUB_TOKEN=your_huggingface_token_here")
        lines.append(f"MODEL_NAME={spec.ai_serving.model_name}")

    lines.append("")
    return "\n".join(lines)
