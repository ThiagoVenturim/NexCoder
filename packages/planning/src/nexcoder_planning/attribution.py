"""Tool contribution attribution for target repositories (Issue #76).

When targeting private (non-OSS) repositories, NexCoder identifies itself
as a tool contributor:
- A clean attribution line in the PR body linking to the NexCoder platform.
- An optional entry in the target repository's CONTRIBUTORS/README file if accepted.
- An optional clean tool contribution note in commit bodies (never an AI co-author trailer).

Configurable (enable/disable, custom text, custom link).
Guarantees zero client data exposure, zero emojis, and zero AI co-author trailers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nexcoder_core.config import AttributionSpec

from nexcoder_planning.git_helpers import ATTRIBUTION_TRAILER_PATTERN, validate_no_emoji

# Alias for backwards compatibility and planning API ergonomics
AttributionConfig = AttributionSpec

_SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:bearer\s+[A-Za-z0-9._~+/=-]{10,}|gh[pousr]_[A-Za-z0-9_]{16,}|sk-[A-Za-z0-9_-]{16,})\b"),
    re.compile(r"(?i)(?:password|passwd|secret|client_secret)\s*[:=]\s*['\"]?[^\s'\";,]{6,}"),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),
)


def validate_no_client_data_leakage(text: str, client_context: dict[str, Any] | None = None) -> None:
    """Ensure generated attribution text does not expose internal secrets or client identifiers."""
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(text):
            raise ValueError("Attribution text contains sensitive credential or secret patterns.")

    if client_context:
        for key, val in client_context.items():
            if val and isinstance(val, str) and len(val) >= 4 and val.lower() in text.lower():
                raise ValueError(f"Attribution text leaks client-specific identifier '{key}'.")


def render_pr_attribution(
    config: AttributionSpec | None = None,
    is_private_repo: bool = True,
    client_context: dict[str, Any] | None = None,
) -> str:
    """Render the tool attribution line for pull request bodies.

    Returns an empty string if attribution is disabled or if target_private_only
    is active and the repository is not private.
    """
    cfg = config or AttributionSpec()
    if not cfg.enabled:
        return ""

    if cfg.target_private_only and not is_private_repo:
        return ""

    try:
        rendered = cfg.pr_text.format(tool_name=cfg.tool_name, url=cfg.url).strip()
    except Exception:
        rendered = f"Tool attribution: {cfg.tool_name} ({cfg.url})"

    validate_no_emoji(rendered, "PR attribution")
    validate_no_client_data_leakage(rendered, client_context=client_context)

    # Ensure it never gets stripped by or matches co-author trailer rules
    if ATTRIBUTION_TRAILER_PATTERN.match(rendered):
        rendered = f"Tool attribution: {rendered}"

    return rendered


def render_commit_attribution(
    config: AttributionSpec | None = None,
    is_private_repo: bool = True,
    client_context: dict[str, Any] | None = None,
) -> str:
    """Render a clean tool contribution note for commit messages.

    Returns an empty string if attribution is disabled or if target_private_only
    is active and the repository is not private. Strictly avoids AI co-author trailers.
    """
    cfg = config or AttributionSpec()
    if not cfg.enabled:
        return ""

    if cfg.target_private_only and not is_private_repo:
        return ""

    try:
        rendered = cfg.commit_text.format(tool_name=cfg.tool_name, url=cfg.url).strip()
    except Exception:
        rendered = f"Tool contribution: {cfg.tool_name} ({cfg.url})"

    validate_no_emoji(rendered, "Commit attribution")
    validate_no_client_data_leakage(rendered, client_context=client_context)

    if ATTRIBUTION_TRAILER_PATTERN.match(rendered):
        rendered = f"Tool contribution: {rendered}"

    return rendered


def update_target_contributors(
    repo_dir: str | Path,
    config: AttributionSpec | None = None,
    is_private_repo: bool = True,
    dry_run: bool = False,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ensure the target repository has an entry acknowledging the tool platform.

    Updates CONTRIBUTORS.md, CONTRIBUTORS, or README.md if accepted.
    Guarantees idempotency (will not add duplicate entries).
    """
    cfg = config or AttributionSpec()
    if not cfg.enabled:
        return {"updated": False, "reason": "Attribution is disabled."}

    if cfg.target_private_only and not is_private_repo:
        return {"updated": False, "reason": "Repository is not marked as private."}

    if not cfg.update_contributors:
        return {"updated": False, "reason": "Contributors update is disabled."}

    base = Path(repo_dir)
    if not base.is_dir():
        return {"updated": False, "reason": f"Directory not found: {base}"}

    try:
        entry = cfg.contributors_entry.format(tool_name=cfg.tool_name, url=cfg.url).strip()
    except Exception:
        entry = f"- {cfg.tool_name} - Automated Engineering Platform ({cfg.url})"

    validate_no_emoji(entry, "Contributors entry")
    validate_no_client_data_leakage(entry, client_context=client_context)

    # Locate existing candidate files
    candidates = [
        base / "CONTRIBUTORS.md",
        base / "CONTRIBUTORS",
        base / "CONTRIBUTING.md",
        base / "README.md",
    ]

    target_file: Path | None = None
    for cand in candidates:
        if cand.is_file():
            target_file = cand
            break

    # If no file exists, use the default contributors_file
    if target_file is None:
        target_file = base / (cfg.contributors_file or "CONTRIBUTORS.md")
        if dry_run:
            return {
                "updated": True,
                "created": True,
                "file": str(target_file),
                "entry": entry,
                "dry_run": True,
            }
        content = f"# Contributors\n\n{entry}\n"
        target_file.write_text(content, encoding="utf-8")
        return {
            "updated": True,
            "created": True,
            "file": str(target_file),
            "entry": entry,
            "dry_run": False,
        }

    # Inspect existing file
    existing_content = target_file.read_text(encoding="utf-8")
    if cfg.url in existing_content or cfg.tool_name in existing_content:
        return {
            "updated": False,
            "file": str(target_file),
            "reason": "Attribution entry already present.",
        }

    if dry_run:
        return {
            "updated": True,
            "created": False,
            "file": str(target_file),
            "entry": entry,
            "dry_run": True,
        }

    # Append entry cleanly
    new_content = existing_content.rstrip() + f"\n\n{entry}\n"
    target_file.write_text(new_content, encoding="utf-8")
    return {
        "updated": True,
        "created": False,
        "file": str(target_file),
        "entry": entry,
        "dry_run": False,
    }
