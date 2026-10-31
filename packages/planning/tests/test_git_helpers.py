import httpx
import pytest
from faccoder_planning.git_helpers import (
    build_conventional_commit,
    build_pull_request_body,
    create_branch,
    create_pull_request,
    execute_commit,
    strip_co_author_trailers,
    validate_no_emoji,
)


def test_build_conventional_commit_valid():
    msg = build_conventional_commit(
        type_="feat",
        scope="planning",
        description="add sprint sync loop",
        issue_number=4,
        body="Implements the board synchronizer.",
    )
    assert msg.startswith("feat(planning): add sprint sync loop (#4)\n\nImplements the board synchronizer.")


def test_build_conventional_commit_without_scope_or_issue():
    msg = build_conventional_commit(
        type_="fix",
        description="resolve off by one calculation",
    )
    assert msg == "fix: resolve off by one calculation"


def test_build_conventional_commit_invalid_type():
    with pytest.raises(ValueError, match="Invalid commit type"):
        build_conventional_commit(
            type_="unknown",
            description="some change",
        )


def test_validate_no_emoji_rejection():
    # Attempting to use an emoji should raise ValueError
    emoji_rocket = chr(0x1F680)
    emoji_sparkle = chr(0x2728)
    with pytest.raises(ValueError, match="contains emoji"):
        validate_no_emoji(f"Add feature {emoji_rocket}", "Commit")

    with pytest.raises(ValueError, match="contains emoji"):
        build_conventional_commit(
            type_="feat",
            description=f"cool feature {emoji_sparkle}",
        )


def test_strip_co_author_trailers():
    raw_message = (
        "feat(core): initial scaffold\n\n"
        "Some details.\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>\n"
        "Co-Authored-By: Assistant <bot@ai.org>"
    )
    cleaned = strip_co_author_trailers(raw_message)
    assert "Co-Authored-By" not in cleaned
    assert "Some details." in cleaned


def test_create_branch_dry_run():
    res = create_branch(
        name="layer/planning-slice-2",
        base_branch="develop",
        checkout=True,
        dry_run=True,
    )
    assert res.success is True
    assert res.dry_run is True
    assert "checkout" in res.command
    assert "-b" in res.command
    assert "layer/planning-slice-2" in res.command


def test_execute_commit_dry_run():
    res = execute_commit(
        message="feat(planning): implement kanban loop (#4)",
        stage_all=False,
        dry_run=True,
    )
    assert res.success is True
    assert res.dry_run is True
    assert "commit" in res.command


def test_build_pull_request_body():
    body = build_pull_request_body(
        summary="Implement board synchronizer and Projects v2 integration.",
        issue_number=4,
        milestone="v0.1.0 (layer:planning)",
        verification_steps=[
            "All unit tests pass",
            "Ruff linter clean",
        ],
    )
    assert "## Summary" in body
    assert "Closes #4" in body
    assert "v0.1.0 (layer:planning)" in body
    assert "- [x] All unit tests pass" in body


def test_create_pull_request_mock_client():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/pulls" in str(request.url)
        return httpx.Response(
            201,
            json={
                "number": 14,
                "html_url": "https://github.com/org/repo/pull/14",
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    res = create_pull_request(
        title="feat(planning): sprint sync and projects v2 (#4)",
        body="Pull request body",
        head_branch="layer/planning",
        base_branch="develop",
        repo="org/repo",
        client=mock_client,
        dry_run=False,
    )
    assert res.success is True
    assert res.pr_number == 14
    assert res.url == "https://github.com/org/repo/pull/14"
