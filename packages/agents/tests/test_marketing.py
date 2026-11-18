"""Unit and integration tests for marketing engine: ads, social posts, video, calendar, and publishing."""

from __future__ import annotations

import re
import wave
from pathlib import Path

import pytest
from nexcoder_agents.marketing import (
    AdChannel,
    AdCopyGenerator,
    ContentCalendarGenerator,
    FFmpegCompositor,
    MarketingOrchestrator,
    PiperTTSClient,
    PublicationGovernanceError,
    PublicationRequest,
    SafeSocialPublisher,
    SocialPlatform,
    SocialPostGenerator,
    SubtitleGenerator,
    TargetAudience,
    VideoScriptGenerator,
)
from nexcoder_control.approval.tokens import ApprovalTokenManager

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


def assert_no_emojis(text: str) -> None:
    hits = EMOJI_PATTERN.findall(text)
    assert not hits, f"Found emojis in output: {hits}"


class TestAdCopyGenerator:
    def test_generate_all_channels(self) -> None:
        generator = AdCopyGenerator()
        campaigns = generator.generate_all_channels(
            product_name="NexCoder",
            feature_summary="Automated marketing and video generator",
            audience=TargetAudience.DEVELOPERS,
        )
        assert len(campaigns) == 4
        channels = {c.channel for c in campaigns}
        assert channels == {
            AdChannel.GOOGLE_SEARCH,
            AdChannel.LINKEDIN,
            AdChannel.META_INSTAGRAM,
            AdChannel.TWITTER_X,
        }

    def test_google_ads_character_constraints(self) -> None:
        generator = AdCopyGenerator()
        campaign = generator.generate_campaign(
            product_name="NexCoder",
            feature_summary="Offline dev tooling and AST code intelligence",
            channel=AdChannel.GOOGLE_SEARCH,
            audience=TargetAudience.DEVELOPERS,
        )
        assert len(campaign.variations) >= 2
        for var in campaign.variations:
            assert len(var.headline) <= 30, f"Google headline too long: '{var.headline}'"
            assert len(var.body) <= 90, f"Google description too long: '{var.body}'"
            assert var.cta
            assert_no_emojis(var.headline)
            assert_no_emojis(var.body)

    def test_linkedin_ab_variations(self) -> None:
        generator = AdCopyGenerator()
        campaign = generator.generate_campaign(
            product_name="NexCoder",
            feature_summary="Offline dev tooling and AST code intelligence",
            channel=AdChannel.LINKEDIN,
            audience=TargetAudience.ENGINEERING_LEADERS,
        )
        var_ids = [v.variation_id for v in campaign.variations]
        assert "variant_a_engineering_impact" in var_ids
        assert "variant_b_privacy_governance" in var_ids
        for var in campaign.variations:
            assert_no_emojis(var.headline)
            assert_no_emojis(var.body)


class TestSocialPostGenerator:
    def test_generate_campaign(self) -> None:
        generator = SocialPostGenerator()
        campaign = generator.generate_campaign(
            product_name="NexCoder",
            feature_summary="Automated promo video generation and ad copy engine",
        )

        # LinkedIn
        li_text = campaign.linkedin.format_text()
        assert "NexCoder" in li_text
        assert len(campaign.linkedin.key_takeaways) >= 2
        assert any("SoftwareEngineering" in tag for tag in campaign.linkedin.hashtags)
        assert_no_emojis(li_text)

        # Instagram
        ig_text = campaign.instagram.format_text()
        assert "Slide 1:" in ig_text
        assert len(campaign.instagram.slides) == 5
        assert_no_emojis(ig_text)

        # TikTok
        tt_text = campaign.tiktok.format_text()
        assert "HOOK:" in tt_text
        assert "AUDIO STYLE:" in tt_text
        assert len(campaign.tiktok.dialogue_script) >= 4
        assert_no_emojis(tt_text)


class TestVideoProduction:
    def test_script_and_storyboard(self) -> None:
        script_gen = VideoScriptGenerator()
        script = script_gen.generate_script(
            product_name="NexCoder",
            feature_summary="Marketing campaign generator with Piper TTS and FFmpeg",
            target_duration=30.0,
            aspect_ratio="9:16",
        )
        assert len(script.scenes) == 5
        assert script.total_duration_seconds == 30.0
        assert script.aspect_ratio == "9:16"

        md = script_gen.render_storyboard_markdown(script)
        assert "# Storyboard:" in md
        assert "| Scene | Timing | Visual Direction |" in md
        assert_no_emojis(md)

    def test_subtitle_generation_srt_and_vtt(self) -> None:
        script_gen = VideoScriptGenerator()
        script = script_gen.generate_script(
            product_name="NexCoder",
            feature_summary="Automated marketing video",
        )
        sub_gen = SubtitleGenerator()

        srt = sub_gen.generate_srt(script.scenes)
        assert "1\n00:00:00,000 --> 00:00:05,000" in srt
        assert "2\n00:00:05,000 --> 00:00:11,000" in srt
        assert_no_emojis(srt)

        vtt = sub_gen.generate_vtt(script.scenes)
        assert vtt.startswith("WEBVTT\n")
        assert "00:00:00.000 --> 00:00:05.000" in vtt
        assert_no_emojis(vtt)

    def test_piper_tts_offline_wav(self, tmp_path: Path) -> None:
        tts = PiperTTSClient()
        wav_path = tmp_path / "test_narration.wav"
        result_path = tts.synthesize("Testing voiceover synthesis offline", wav_path, duration_seconds=1.5)

        assert result_path.exists()
        assert result_path.stat().st_size > 0

        with wave.open(str(result_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 22050
            frames = wf.getnframes()
            duration = frames / wf.getframerate()
            assert pytest.approx(duration, rel=0.1) == 1.5

    def test_ffmpeg_compositor_scripts(self, tmp_path: Path) -> None:
        script_gen = VideoScriptGenerator()
        script = script_gen.generate_script("NexCoder", "Promo feature")
        audio_path = tmp_path / "audio.wav"
        audio_path.write_bytes(b"RIFFdummywav")
        sub_path = tmp_path / "sub.srt"
        sub_path.write_text("1\n00:00:00,000 --> 00:00:05,000\nHello\n", encoding="utf-8")
        out_mp4 = tmp_path / "out.mp4"

        compositor = FFmpegCompositor()
        sh_script, ps1_script = compositor.render_assembly_scripts(script, audio_path, sub_path, out_mp4)

        assert "color=c=#0f172a" in sh_script
        assert "libx264" in sh_script
        assert "subtitles" in sh_script
        assert_no_emojis(sh_script)
        assert_no_emojis(ps1_script)

        artifact = compositor.assemble_video(script, audio_path, sub_path, out_mp4)
        assert artifact.mp4_video_path is not None
        assert out_mp4.exists()

    def test_ffmpeg_scripts_quote_untrusted_text(self, tmp_path: Path) -> None:
        import shlex

        script = VideoScriptGenerator().generate_script("Evil$(touch pwned)`id`", "Promo $(rm -rf ~) feature")
        audio_path = tmp_path / "audio.wav"
        sub_path = tmp_path / "sub.srt"
        out_mp4 = tmp_path / "out.mp4"
        compositor = FFmpegCompositor(ffmpeg_binary="ffmpeg")
        cmd = compositor.build_command(script, audio_path, sub_path, out_mp4)
        sh_script, ps1_script = compositor.render_assembly_scripts(script, audio_path, sub_path, out_mp4)

        sh_body = sh_script.split("# NexCoder Marketing Video Assembly\n", 1)[1].replace(" \\\n  ", " ")
        assert shlex.split(sh_body) == cmd
        for line in ps1_script.splitlines()[1:]:
            arg = line.strip().removeprefix("& ").removesuffix(" `")
            assert arg.startswith("'") and arg.endswith("'")


class TestContentCalendar:
    def test_generate_calendar_and_nextor_tasks(self) -> None:
        gen = ContentCalendarGenerator()
        calendar = gen.generate_calendar(
            product_name="NexCoder",
            feature_summary="Automated marketing and promo video suite",
        )
        assert len(calendar.schedule) == 5
        assert len(calendar.nextor_tasks) == 4

        md = gen.render_nextor_markdown(calendar)
        assert "<!-- nexcoder-id:" in md
        assert "## Publication Roadmap" in md
        assert "## Nextor Actionable Tasks" in md
        assert "- [ ]" in md
        assert_no_emojis(md)


class TestSafeSocialPublisher:
    def test_publish_blocked_without_human_confirmation(self) -> None:
        publisher = SafeSocialPublisher()
        req = PublicationRequest(
            platform=SocialPlatform.LINKEDIN,
            content_text="Sample post",
            approval_token="dummy",
            confirmed=False,
            dry_run=True,
        )
        with pytest.raises(PublicationGovernanceError, match="human confirmation is strictly mandatory"):
            publisher.publish(req)

    def test_publish_blocked_with_invalid_token(self) -> None:
        publisher = SafeSocialPublisher()
        req = PublicationRequest(
            platform=SocialPlatform.LINKEDIN,
            content_text="Sample post",
            approval_token="invalid-token",
            confirmed=True,
            dry_run=True,
        )
        with pytest.raises(PublicationGovernanceError, match="invalid, expired, or already consumed"):
            publisher.publish(req)

    def test_dry_run_success_with_valid_token(self) -> None:
        publisher = SafeSocialPublisher()
        token = publisher.issue_approval_token()

        req = PublicationRequest(
            platform=SocialPlatform.LINKEDIN,
            content_text="Sample post for LinkedIn",
            approval_token=token,
            confirmed=True,
            dry_run=True,
        )
        result = publisher.publish(req)
        assert result.success is True
        assert result.platform == SocialPlatform.LINKEDIN
        assert "dryrun" in str(result.post_id)
        assert result.audit_event_id

    def test_live_publish_blocked_without_official_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
        token_mgr = ApprovalTokenManager()
        publisher = SafeSocialPublisher(token_manager=token_mgr)
        token = publisher.issue_approval_token()

        req = PublicationRequest(
            platform=SocialPlatform.LINKEDIN,
            content_text="Sample post",
            approval_token=token,
            confirmed=True,
            dry_run=False,
        )
        with pytest.raises(PublicationGovernanceError, match="Missing official LinkedIn credentials"):
            publisher.publish(req)


class TestMarketingOrchestrator:
    def test_end_to_end_campaign_saved_as_drafts(self, tmp_path: Path) -> None:
        target_dir = tmp_path / "marketing_drafts"
        orchestrator = MarketingOrchestrator()

        bundle = orchestrator.generate_campaign(
            product_name="NexCoder",
            feature_summary="Automated marketing and promotional video engine",
            output_dir=target_dir,
            audience=TargetAudience.DEVELOPERS,
            video_duration_seconds=30.0,
        )

        assert bundle.draft_directory == str(target_dir)

        # Check drafts exist
        assert (target_dir / "ads" / "google_search_ads.json").exists()
        assert (target_dir / "ads" / "linkedin_ads.json").exists()
        assert (target_dir / "social" / "linkedin_post.md").exists()
        assert (target_dir / "social" / "instagram_carousel.md").exists()
        assert (target_dir / "social" / "tiktok_script.md").exists()
        assert (target_dir / "video" / "storyboard.md").exists()
        assert (target_dir / "video" / "subtitles.srt").exists()
        assert (target_dir / "video" / "subtitles.vtt").exists()
        assert (target_dir / "video" / "narration.wav").exists()
        assert (target_dir / "video" / "assemble.sh").exists()
        assert (target_dir / "video" / "assemble.ps1").exists()
        assert (target_dir / "calendar" / "posting_schedule.json").exists()
        assert (target_dir / "calendar" / "nextor_tasks.md").exists()
        assert (target_dir / "SUMMARY.md").exists()

        # Check summary content
        summary = (target_dir / "SUMMARY.md").read_text(encoding="utf-8")
        assert "No automated publication has occurred" in summary
        assert_no_emojis(summary)
