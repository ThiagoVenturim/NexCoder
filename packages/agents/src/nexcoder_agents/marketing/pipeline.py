"""End-to-end marketing campaign orchestrator generating ad copy, social posts, video, and calendar drafts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nexcoder_agents.marketing.ads import AdCopyGenerator
from nexcoder_agents.marketing.calendar import ContentCalendarGenerator
from nexcoder_agents.marketing.models import (
    AdCampaign,
    MarketingBundle,
    SocialCampaign,
    TargetAudience,
)
from nexcoder_agents.marketing.social import SocialPostGenerator
from nexcoder_agents.marketing.video import (
    FFmpegCompositor,
    PiperTTSClient,
    SubtitleGenerator,
    VideoScriptGenerator,
)


class MarketingOrchestrator:
    """Orchestrates the creation of comprehensive marketing deliverables saved as local drafts."""

    def __init__(
        self,
        ad_generator: AdCopyGenerator | None = None,
        social_generator: SocialPostGenerator | None = None,
        script_generator: VideoScriptGenerator | None = None,
        tts_client: PiperTTSClient | None = None,
        compositor: FFmpegCompositor | None = None,
        calendar_generator: ContentCalendarGenerator | None = None,
    ) -> None:
        self.ad_generator = ad_generator or AdCopyGenerator()
        self.social_generator = social_generator or SocialPostGenerator()
        self.script_generator = script_generator or VideoScriptGenerator()
        self.subtitle_generator = SubtitleGenerator()
        self.tts_client = tts_client or PiperTTSClient()
        self.compositor = compositor or FFmpegCompositor()
        self.calendar_generator = calendar_generator or ContentCalendarGenerator()

    def generate_campaign(
        self,
        product_name: str,
        feature_summary: str,
        output_dir: Path | str | None = None,
        audience: TargetAudience = TargetAudience.DEVELOPERS,
        video_duration_seconds: float = 30.0,
        aspect_ratio: str = "9:16",
    ) -> MarketingBundle:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", product_name.lower().strip())
        target_dir = Path(output_dir) if output_dir else Path(f".nexcoder/marketing/drafts/{slug}")
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Generate Ad Copies across channels with A/B variations
        ads = self.ad_generator.generate_all_channels(
            product_name=product_name,
            feature_summary=feature_summary,
            audience=audience,
        )

        # 2. Generate Social Media Posts (LinkedIn, Instagram, TikTok)
        social = self.social_generator.generate_campaign(
            product_name=product_name,
            feature_summary=feature_summary,
        )

        # 3. Generate Video Artifacts (Script, Storyboard, Subtitles, TTS audio, FFmpeg scripts)
        script = self.script_generator.generate_script(
            product_name=product_name,
            feature_summary=feature_summary,
            target_duration=video_duration_seconds,
            aspect_ratio=aspect_ratio,
        )

        video_dir = target_dir / "video"
        video_dir.mkdir(parents=True, exist_ok=True)

        audio_path = video_dir / "narration.wav"
        subtitles_srt_path = video_dir / "subtitles.srt"
        subtitles_vtt_path = video_dir / "subtitles.vtt"
        mp4_path = video_dir / "promo_video.mp4"

        # Synthesize audio with Piper TTS / offline fallback
        self.tts_client.synthesize_scenes(script.scenes, audio_path)

        # Write subtitle files
        srt_text = self.subtitle_generator.generate_srt(script.scenes)
        subtitles_srt_path.write_text(srt_text, encoding="utf-8")

        vtt_text = self.subtitle_generator.generate_vtt(script.scenes)
        subtitles_vtt_path.write_text(vtt_text, encoding="utf-8")

        # Assemble video with FFmpeg / offline simulation
        video_artifact = self.compositor.assemble_video(
            script=script,
            audio_path=audio_path,
            subtitles_path=subtitles_srt_path,
            output_path=mp4_path,
        )

        storyboard_path = video_dir / "storyboard.md"
        storyboard_path.write_text(video_artifact.storyboard_markdown, encoding="utf-8")

        sh_path = video_dir / "assemble.sh"
        sh_path.write_text(video_artifact.assembly_script_sh, encoding="utf-8")

        ps1_path = video_dir / "assemble.ps1"
        ps1_path.write_text(video_artifact.assembly_script_ps1, encoding="utf-8")

        # 4. Generate Content Calendar and Nextor tasks
        calendar = self.calendar_generator.generate_calendar(
            product_name=product_name,
            feature_summary=feature_summary,
        )

        # 5. Persist all drafts to target_dir
        self._write_drafts(target_dir, ads, social, calendar)

        return MarketingBundle(
            product_name=product_name,
            feature_summary=feature_summary,
            ads=ads,
            social=social,
            video=video_artifact,
            calendar=calendar,
            draft_directory=str(target_dir),
        )

    def _write_drafts(
        self,
        base_dir: Path,
        ads: list[AdCampaign],
        social: SocialCampaign,
        calendar: Any,
    ) -> None:
        ads_dir = base_dir / "ads"
        ads_dir.mkdir(parents=True, exist_ok=True)
        for ad in ads:
            file_name = f"{ad.channel.value}_ads.json"
            (ads_dir / file_name).write_text(ad.model_dump_json(indent=2), encoding="utf-8")

        social_dir = base_dir / "social"
        social_dir.mkdir(parents=True, exist_ok=True)
        (social_dir / "linkedin_post.md").write_text(social.linkedin.format_text(), encoding="utf-8")
        (social_dir / "instagram_carousel.md").write_text(social.instagram.format_text(), encoding="utf-8")
        (social_dir / "tiktok_script.md").write_text(social.tiktok.format_text(), encoding="utf-8")

        cal_dir = base_dir / "calendar"
        cal_dir.mkdir(parents=True, exist_ok=True)
        (cal_dir / "posting_schedule.json").write_text(calendar.model_dump_json(indent=2), encoding="utf-8")
        nextor_md = self.calendar_generator.render_nextor_markdown(calendar)
        (cal_dir / "nextor_tasks.md").write_text(nextor_md, encoding="utf-8")

        summary_md = [
            f"# Marketing Campaign Drafts: {calendar.product_name}",
            "",
            "All deliverables have been saved as offline drafts. No automated publication has occurred.",
            "",
            "## Structure of Drafts",
            "- `ads/`: Ad copies with A/B variations for Google, LinkedIn, Meta/Instagram, and Twitter/X.",
            "- `social/`: Posts formatted specifically for LinkedIn, Instagram (carousel), and TikTok (script).",
            "- `video/`: Storyboard, SRT/VTT subtitles, Piper narration WAV, and FFmpeg assembly scripts.",
            "- `calendar/`: Suggested 14-day schedule and Nextor Kanban tasks.",
            "",
            "## Publication Policy",
            "Live distribution requires explicit human confirmation (`confirmed=True`) "
            "and a signed human approval token.",
        ]
        (base_dir / "SUMMARY.md").write_text("\n".join(summary_md), encoding="utf-8")
