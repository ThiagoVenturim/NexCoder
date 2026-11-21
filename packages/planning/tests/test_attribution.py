"""Tests for tool contribution attribution in target repositories (Issue #76)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from nexcoder_core.config import AttributionSpec, NexcoderConfig, load_config
from nexcoder_planning.attribution import (
    render_commit_attribution,
    render_pr_attribution,
    update_target_contributors,
    validate_no_client_data_leakage,
)
from nexcoder_planning.git_helpers import (
    ATTRIBUTION_TRAILER_PATTERN,
    build_conventional_commit,
    build_pull_request_body,
    create_pull_request,
    strip_co_author_trailers,
)


def test_attribution_spec_defaults():
    spec = AttributionSpec()
    assert spec.enabled is True
    assert spec.target_private_only is True
    assert spec.tool_name == "NexCoder"
    assert spec.url == "https://github.com/ThiagoVenturim/NexCoder"
    assert "Tool attribution:" in spec.pr_text
    assert "Tool contribution:" in spec.commit_text

    cfg = NexcoderConfig()
    assert cfg.attribution.enabled is True
    assert cfg.attribution.tool_name == "NexCoder"


def test_render_commit_attribution_direct():
    note = render_commit_attribution(is_private_repo=True)
    assert "Tool contribution: NexCoder" in note
    assert not ATTRIBUTION_TRAILER_PATTERN.match(note)


def test_render_pr_attribution_when_enabled():
    line = render_pr_attribution(is_private_repo=True)
    assert "Tool attribution: NexCoder" in line
    assert "https://github.com/ThiagoVenturim/NexCoder" in line
    # Must not match AI co-author trailer
    assert not ATTRIBUTION_TRAILER_PATTERN.match(line)


def test_render_pr_attribution_when_disabled():
    spec = AttributionSpec(enabled=False)
    line = render_pr_attribution(config=spec, is_private_repo=True)
    assert line == ""


def test_render_pr_attribution_when_not_private():
    spec = AttributionSpec(enabled=True, target_private_only=True)
    line = render_pr_attribution(config=spec, is_private_repo=False)
    assert line == ""


def test_render_pr_attribution_custom_text_and_url():
    spec = AttributionSpec(
        tool_name="CustomTool",
        url="https://github.com/ThiagoVenturim/NexCoder",
        pr_text="Automated platform contribution by {tool_name} ({url})",
    )
    line = render_pr_attribution(config=spec, is_private_repo=True)
    assert line == "Automated platform contribution by CustomTool (https://github.com/ThiagoVenturim/NexCoder)"


def test_build_pull_request_body_with_attribution_on():
    body = build_pull_request_body(
        summary="Implement billing webhook verification",
        issue_number=76,
        issue_action="Closes",
        is_private_repo=True,
    )
    assert "## Summary" in body
    assert "Closes #76" in body
    assert "## Tool Attribution" in body
    assert "Tool attribution: NexCoder (https://github.com/ThiagoVenturim/NexCoder)" in body


def test_build_pull_request_body_with_attribution_off():
    # Disabled by is_private_repo=False (default behavior for public/OSS target)
    body_public = build_pull_request_body(
        summary="Implement billing webhook verification",
        issue_number=76,
        is_private_repo=False,
    )
    assert "## Tool Attribution" not in body_public
    assert "NexCoder" not in body_public

    # Explicitly disabled with attribution=False
    body_disabled = build_pull_request_body(
        summary="Implement billing webhook verification",
        issue_number=76,
        is_private_repo=True,
        attribution=False,
    )
    assert "## Tool Attribution" not in body_disabled
    assert "NexCoder" not in body_disabled


def test_build_pull_request_body_explicit_spec():
    spec = AttributionSpec(
        tool_name="NexCoder-Enterprise",
        url="https://github.com/ThiagoVenturim/NexCoder",
        pr_text="Automated changes via {tool_name}: {url}",
    )
    body = build_pull_request_body(
        summary="Refactor token rotation",
        attribution=spec,
    )
    assert "## Tool Attribution" in body
    assert "Automated changes via NexCoder-Enterprise: https://github.com/ThiagoVenturim/NexCoder" in body


def test_build_conventional_commit_attribution():
    # When attribution=True, appends clean non-trailer contribution line
    msg = build_conventional_commit(
        type_="feat",
        description="add token rotation middleware",
        scope="auth",
        attribution=True,
    )
    assert "feat(auth): add token rotation middleware" in msg
    assert "Tool contribution: NexCoder (https://github.com/ThiagoVenturim/NexCoder)" in msg

    # Verify that strip_co_author_trailers does NOT strip legitimate tool contribution
    stripped = strip_co_author_trailers(msg)
    assert "Tool contribution: NexCoder (https://github.com/ThiagoVenturim/NexCoder)" in stripped

    # When attribution=False, no contribution line is added
    msg_no_attr = build_conventional_commit(
        type_="feat",
        description="add token rotation middleware",
        scope="auth",
        attribution=False,
    )
    assert "Tool contribution:" not in msg_no_attr


def test_create_pull_request_attribution_integration():
    res = create_pull_request(
        title="feat: secure webhook verification",
        body="## Summary\nInitial implementation",
        head_branch="feat/webhook",
        is_private_repo=True,
        dry_run=True,
    )
    assert res.success is True
    assert "## Tool Attribution" in res.body
    assert "https://github.com/ThiagoVenturim/NexCoder" in res.body

    # Public repository preview omits attribution
    res_pub = create_pull_request(
        title="feat: secure webhook verification",
        body="## Summary\nInitial implementation",
        head_branch="feat/webhook",
        is_private_repo=False,
        dry_run=True,
    )
    assert "## Tool Attribution" not in res_pub.body


def test_update_target_contributors_new_file(tmp_path: Path):
    result = update_target_contributors(tmp_path, is_private_repo=True, dry_run=False)
    assert result["updated"] is True
    assert result["created"] is True
    contrib_file = tmp_path / "CONTRIBUTORS.md"
    assert contrib_file.is_file()
    content = contrib_file.read_text(encoding="utf-8")
    assert "NexCoder - Automated Engineering Platform" in content
    assert "https://github.com/ThiagoVenturim/NexCoder" in content

    # Idempotency: second run does not duplicate or modify
    second = update_target_contributors(tmp_path, is_private_repo=True, dry_run=False)
    assert second["updated"] is False
    assert "already present" in second["reason"].lower()


def test_update_target_contributors_existing_readme(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("# Project Documentation\n\nWelcome to the project.\n", encoding="utf-8")

    result = update_target_contributors(tmp_path, is_private_repo=True, dry_run=False)
    assert result["updated"] is True
    assert result["created"] is False
    new_content = readme.read_text(encoding="utf-8")
    assert "NexCoder - Automated Engineering Platform" in new_content


def test_update_target_contributors_dry_run(tmp_path: Path):
    result = update_target_contributors(tmp_path, is_private_repo=True, dry_run=True)
    assert result["updated"] is True
    assert result["dry_run"] is True
    # In dry-run, file should not actually be written
    assert not (tmp_path / "CONTRIBUTORS.md").exists()


def test_update_target_contributors_when_disabled(tmp_path: Path):
    spec = AttributionSpec(enabled=False)
    result = update_target_contributors(tmp_path, config=spec, is_private_repo=True)
    assert result["updated"] is False


def test_validate_no_client_data_leakage():
    # Clean text passes
    validate_no_client_data_leakage("Tool attribution: NexCoder (https://github.com/ThiagoVenturim/NexCoder)")

    # Credentials raise ValueError
    with pytest.raises(ValueError, match="sensitive credential"):
        validate_no_client_data_leakage("-----BEGIN RSA PRIVATE KEY-----")

    with pytest.raises(ValueError, match="sensitive credential"):
        validate_no_client_data_leakage("Bearer sk-1234567890abcdef123456")

    # Client identifier leakage raises ValueError
    client_ctx = {"client_corp": "AcmeEnterprises", "internal_host": "corp.internal"}
    with pytest.raises(ValueError, match="leaks client-specific identifier"):
        validate_no_client_data_leakage(
            "Attribution for AcmeEnterprises codebase",
            client_context=client_ctx,
        )


def test_nexcoder_config_env_overrides():
    with patch.dict(os.environ, {"NEXCODER_ATTRIBUTION_ENABLED": "false"}):
        cfg = load_config()
        assert cfg.attribution.enabled is False

    with patch.dict(os.environ, {"NEXCODER_ATTRIBUTION_ENABLED": "1"}):
        cfg = load_config()
        assert cfg.attribution.enabled is True

    with patch.dict(os.environ, {"NEXCODER_ATTRIBUTION_URL": "https://github.com/ThiagoVenturim/NexCoder"}):
        cfg = load_config()
        assert cfg.attribution.url == "https://github.com/ThiagoVenturim/NexCoder"
