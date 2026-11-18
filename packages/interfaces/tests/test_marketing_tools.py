"""Tests for marketing MCP tools and interfaces integration."""

from __future__ import annotations

from pathlib import Path

from nexcoder_agents.marketing import SafeSocialPublisher
from nexcoder_interfaces.cli.main import app
from nexcoder_interfaces.tools.marketing import (
    assemble_marketing_video,
    generate_marketing_campaign,
    publish_social_post,
    schedule_marketing_calendar,
)
from typer.testing import CliRunner

runner = CliRunner()


def test_generate_marketing_campaign_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    draft_dir = tmp_path / "drafts"
    res = generate_marketing_campaign(
        feature_summary="Automated marketing and video generator",
        product_name="NexCoder",
        output_dir="drafts",
    )
    assert res["status"] == "success"
    assert "google_search" in res["ads_channels"]
    assert "linkedin" in res["social_platforms"]
    assert res["video"]["scenes_count"] == 5
    assert res["calendar"]["scheduled_items"] == 5
    assert (draft_dir / "SUMMARY.md").exists()


def test_marketing_tools_refuse_output_dir_outside_workdir(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    outside = tmp_path / "outside"

    res = generate_marketing_campaign(feature_summary="x", output_dir=str(outside))
    assert res["status"] == "error"
    res_video = assemble_marketing_video(feature_summary="x", output_dir="../outside")
    assert res_video["status"] == "error"
    res_name = assemble_marketing_video(feature_summary="x", product_name="../../escape")
    assert res_name["status"] == "success"
    assert not outside.exists()
    assert not (tmp_path / "escape").exists()


def test_assemble_marketing_video_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    res = assemble_marketing_video(
        feature_summary="Offline video production with Piper and FFmpeg",
        product_name="NexCoder",
        output_dir="video",
    )
    assert res["status"] == "success"
    assert Path(res["storyboard_path"]).exists()
    assert Path(res["subtitles_srt_path"]).exists()
    assert Path(res["audio_path"]).exists()
    assert Path(res["assembly_script_sh"]).exists()


def test_schedule_marketing_calendar_tool() -> None:
    res = schedule_marketing_calendar(
        feature_summary="Nextor tasks for marketing release",
        product_name="NexCoder",
    )
    assert res["status"] == "success"
    assert len(res["schedule"]) == 5
    assert len(res["nextor_tasks"]) == 4
    assert "<!-- nexcoder-id:" in res["nextor_markdown"]


def test_publish_social_post_tool_governance() -> None:
    # 1. Blocked without confirmation
    res_unconfirmed = publish_social_post(
        platform="linkedin",
        content_text="Hello world",
        approval_token="fake_token",
        confirmed=False,
    )
    assert res_unconfirmed["success"] is False
    assert "human confirmation is strictly mandatory" in res_unconfirmed["status_message"]

    # 2. Blocked with invalid token
    res_bad_token = publish_social_post(
        platform="linkedin",
        content_text="Hello world",
        approval_token="invalid_token",
        confirmed=True,
    )
    assert res_bad_token["success"] is False
    assert "invalid, expired, or already consumed" in res_bad_token["status_message"]

    # 3. Valid token dry-run succeeds
    publisher = SafeSocialPublisher()
    valid_token = publisher.issue_approval_token()
    res_dryrun = publish_social_post(
        platform="linkedin",
        content_text="Hello world",
        approval_token=valid_token,
        confirmed=True,
        dry_run=True,
        publisher=publisher,
    )
    assert res_dryrun["success"] is True
    assert "dryrun" in res_dryrun["post_id"]


def test_cli_marketing_campaign(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "cli_drafts"
    result = runner.invoke(
        app,
        [
            "marketing",
            "campaign",
            "--feature",
            "Continuous automated marketing generator",
            "--product",
            "NexCoder",
            "--output-dir",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0
    assert "status" in result.output
    assert (out_dir / "SUMMARY.md").exists()


def test_cli_marketing_calendar() -> None:
    result = runner.invoke(
        app,
        [
            "marketing",
            "calendar",
            "--feature",
            "Multi-channel launch plan",
        ],
    )
    assert result.exit_code == 0
    assert "cadence_summary" in result.output
