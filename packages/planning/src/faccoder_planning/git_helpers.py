"""Git automation helpers: branches, conventional commits, and pull requests.

Enforces zero emojis, strict rejection of AI co-author trailers and generated-by notes,
and dry-run safety across all write operations.
"""

from __future__ import annotations

import logging
import re
import subprocess

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Emoji detection pattern covering pictographs, symbols, flags, and variants
EMOJI_PATTERN = re.compile(
    "["
    "\U0001f000-\U0001faff"
    "\U00002600-\U000027bf"
    "\U00002b00-\U00002bff"
    "\U0001f1e6-\U0001f1ff"
    "\U0000fe0f"
    "\U0000200d"
    "\U000020e3"
    "]"
)

# Strips any co-author trailers and 'Generated with' lines from commit messages and PR bodies
ATTRIBUTION_STRIP_PATTERN = re.compile(
    r"(?im)^\s*(?:co-authored-by|generated[- ](?:with|by)|authored-by)[:\s].*$",
    re.MULTILINE,
)

ALLOWED_COMMIT_TYPES = {
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "chore",
    "ci",
    "build",
}


class GitResult(BaseModel):
    """Result of a local git automation command."""

    success: bool
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    message: str = ""
    dry_run: bool = True


class PRResult(BaseModel):
    """Result of opening or previewing a pull request."""

    success: bool
    title: str
    body: str
    head_branch: str
    base_branch: str
    pr_number: int | None = None
    url: str | None = None
    message: str = ""
    dry_run: bool = True


def validate_no_emoji(text: str, context: str = "Text") -> None:
    """Raise ValueError if text contains any emoji or pictographic symbol."""
    if EMOJI_PATTERN.search(text):
        raise ValueError(f"{context} contains emoji characters, which are strictly prohibited.")


def strip_co_author_trailers(text: str) -> str:
    """Remove any Co-Authored-By and Generated-with lines to honor open-source attribution policy."""
    cleaned = ATTRIBUTION_STRIP_PATTERN.sub("", text)
    # Remove consecutive blank lines left by trailer stripping
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def validate_branch_name(name: str) -> None:
    """Validate branch name according to git ref format and ban emojis."""
    validate_no_emoji(name, "Branch name")
    if not name or name.strip() != name:
        raise ValueError(f"Branch name cannot be empty or have leading/trailing whitespace: '{name}'")
    invalid_chars = [" ", "~", "^", ":", "\\", "?", "*", "[", "@{"]
    if any(c in name for c in invalid_chars) or ".." in name or "//" in name or name.endswith("/"):
        raise ValueError(f"Invalid git branch name: '{name}'")

    try:
        res = subprocess.run(  # noqa: S603
            ["git", "check-ref-format", "--branch", name],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            err = res.stderr.strip() or "failed git check-ref-format"
            raise ValueError(f"Invalid git branch name '{name}': {err}")
    except FileNotFoundError:
        pass


def build_conventional_commit(
    type_: str,
    description: str,
    scope: str | None = None,
    issue_number: int | None = None,
    issue_numbers: list[int] | None = None,
    issue_action: str = "Refs",
    body: str | None = None,
) -> str:
    """Construct a clean conventional commit message with zero emojis and no co-author trailers."""
    type_normalized = type_.strip().lower()
    if type_normalized not in ALLOWED_COMMIT_TYPES:
        raise ValueError(f"Invalid commit type '{type_}'. Must be one of: {sorted(ALLOWED_COMMIT_TYPES)}")

    clean_desc = description.strip()
    validate_no_emoji(clean_desc, "Commit description")

    scope_part = f"({scope.strip().lower()})" if scope and scope.strip() else ""

    # Collect issue numbers
    all_issues: list[int] = []
    if issue_number:
        all_issues.append(issue_number)
    if issue_numbers:
        for num in issue_numbers:
            if num not in all_issues:
                all_issues.append(num)

    if all_issues:
        refs_formatted = ", ".join(f"{issue_action} #{num}" for num in all_issues)
        header = f"{type_normalized}{scope_part}: {clean_desc} ({refs_formatted})"
    else:
        header = f"{type_normalized}{scope_part}: {clean_desc}"

    validate_no_emoji(header, "Commit header")

    if not body or not body.strip():
        return header

    clean_body = strip_co_author_trailers(body.strip())
    validate_no_emoji(clean_body, "Commit body")

    return f"{header}\n\n{clean_body}"


def run_git_command(
    args: list[str],
    cwd: str | None = None,
    dry_run: bool = True,
    dry_run_message: str = "",
) -> GitResult:
    """Execute a git command via subprocess or simulate when dry_run=True."""
    full_cmd = ["git"] + args
    if dry_run:
        msg = dry_run_message or f"[DRY-RUN] Would execute: {' '.join(full_cmd)}"
        return GitResult(
            success=True,
            command=full_cmd,
            stdout="",
            stderr="",
            message=msg,
            dry_run=True,
        )

    try:
        proc = subprocess.run(  # noqa: S603
            full_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        success = proc.returncode == 0
        return GitResult(
            success=success,
            command=full_cmd,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
            message="Git command executed successfully." if success else proc.stderr.strip(),
            dry_run=False,
        )
    except Exception as exc:
        return GitResult(
            success=False,
            command=full_cmd,
            stdout="",
            stderr=str(exc),
            message=f"Git execution error: {exc}",
            dry_run=False,
        )


def create_branch(
    name: str,
    base_branch: str = "develop",
    checkout: bool = True,
    cwd: str | None = None,
    dry_run: bool = True,
) -> GitResult:
    """Create a new working branch from base_branch safely after format validation."""
    validate_branch_name(name)
    validate_branch_name(base_branch)

    if checkout:
        cmd = ["checkout", "-b", name, base_branch]
    else:
        cmd = ["branch", name, base_branch]

    return run_git_command(
        cmd,
        cwd=cwd,
        dry_run=dry_run,
        dry_run_message=f"[DRY-RUN] Would create branch '{name}' from '{base_branch}'",
    )


def execute_commit(
    message: str,
    stage_all: bool = False,
    cwd: str | None = None,
    dry_run: bool = True,
) -> GitResult:
    """Commit staged changes using the sanitized conventional commit message."""
    validate_no_emoji(message, "Commit message")
    sanitized_message = strip_co_author_trailers(message)

    if stage_all:
        stage_res = run_git_command(["add", "."], cwd=cwd, dry_run=dry_run)
        if not stage_res.success:
            return stage_res

    cmd = ["commit", "-m", sanitized_message]
    return run_git_command(
        cmd,
        cwd=cwd,
        dry_run=dry_run,
        dry_run_message=f"[DRY-RUN] Would commit with message: {sanitized_message.splitlines()[0]}",
    )


def build_pull_request_body(
    summary: str,
    issue_number: int | None = None,
    issue_numbers: list[int] | None = None,
    issue_action: str = "Refs",
    milestone: str | None = None,
    verification_steps: list[str] | None = None,
) -> str:
    """Build a standard, clean pull request body without emojis, supporting Refs or Closes."""
    validate_no_emoji(summary, "PR summary")
    sections: list[str] = []

    sections.append(f"## Summary\n{summary.strip()}")

    all_issues: list[int] = []
    if issue_number:
        all_issues.append(issue_number)
    if issue_numbers:
        for num in issue_numbers:
            if num not in all_issues:
                all_issues.append(num)

    if all_issues:
        lines = [f"{issue_action} #{num}" for num in all_issues]
        sections.append("## Related Issues\n" + "\n".join(lines))

    if milestone:
        sections.append(f"## Milestone\n{milestone.strip()}")

    if verification_steps:
        steps_text = "\n".join(f"- [x] {step.strip()}" for step in verification_steps if step.strip())
        sections.append(f"## Verification\n{steps_text}")

    body = "\n\n".join(sections)
    validate_no_emoji(body, "Pull request body")
    return strip_co_author_trailers(body)


def create_pull_request(
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "develop",
    repo: str | None = None,
    token: str | None = None,
    api_url: str = "https://api.github.com",
    client: httpx.Client | None = None,
    dry_run: bool = True,
) -> PRResult:
    """Create a pull request on GitHub or return a dry-run preview."""
    validate_no_emoji(title, "PR title")
    validate_no_emoji(body, "PR body")
    sanitized_body = strip_co_author_trailers(body)

    if dry_run:
        return PRResult(
            success=True,
            title=title,
            body=sanitized_body,
            head_branch=head_branch,
            base_branch=base_branch,
            pr_number=999,
            url=f"https://github.com/{repo or 'org/repo'}/pull/999",
            message=f"[DRY-RUN] Would open PR from '{head_branch}' into '{base_branch}': {title}",
            dry_run=True,
        )

    if not repo:
        raise ValueError("Repository in 'owner/repo' format is required when dry_run=False")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "faccoder-planning",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    http_client = client or httpx.Client(headers=headers, timeout=30.0)
    url = f"{api_url.rstrip('/')}/repos/{repo}/pulls"
    payload = {
        "title": title,
        "body": sanitized_body,
        "head": head_branch,
        "base": base_branch,
    }

    try:
        res = http_client.post(url, json=payload)
        res.raise_for_status()
        data = res.json()
        return PRResult(
            success=True,
            title=title,
            body=sanitized_body,
            head_branch=head_branch,
            base_branch=base_branch,
            pr_number=data.get("number"),
            url=data.get("html_url"),
            message=f"Created PR #{data.get('number')} '{title}'",
            dry_run=False,
        )
    except Exception as exc:
        return PRResult(
            success=False,
            title=title,
            body=sanitized_body,
            head_branch=head_branch,
            base_branch=base_branch,
            message=f"Failed to open pull request: {exc}",
            dry_run=False,
        )
