"""MCP tools for marketing, ad copy, social posts, video production, and safe publishing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nexcoder_agents.marketing import (
    ContentCalendarGenerator,
    MarketingOrchestrator,
    PublicationGovernanceError,
    PublicationRequest,
    SafeSocialPublisher,
    SocialPlatform,
    TargetAudience,
    VideoScriptGenerator,
)
from nexcoder_agents.marketing.video import FFmpegCompositor, PiperTTSClient, SubtitleGenerator
from nexcoder_core.sandbox import PathOutsideSandboxError, resolve_inside


def _slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name.lower().strip()) or "product"


def _resolve_output_dir(output_dir: str | None, default: str) -> Path:
    """Resolve an agent-supplied output directory, refusing anything outside the working directory."""
    return resolve_inside(Path.cwd(), output_dir or default)


def generate_marketing_campaign(
    feature_summary: str,
    product_name: str = "NexCoder",
    output_dir: str | None = None,
    audience: str = "developers",
    video_duration: float = 30.0,
) -> dict[str, Any]:
    """Generate marketing ad copy, social posts, video script/storyboard/subtitles, and calendar drafts."""
    aud_map = {
        "developers": TargetAudience.DEVELOPERS,
        "engineering_leaders": TargetAudience.ENGINEERING_LEADERS,
        "tech_founders": TargetAudience.TECH_FOUNDERS,
        "enterprise_architects": TargetAudience.ENTERPRISE_ARCHITECTS,
    }
    target_aud = aud_map.get(audience, TargetAudience.DEVELOPERS)

    try:
        target_dir = _resolve_output_dir(output_dir, f".nexcoder/marketing/drafts/{_slug(product_name)}")
    except PathOutsideSandboxError as exc:
        return {"status": "error", "message": str(exc)}

    orchestrator = MarketingOrchestrator()
    bundle = orchestrator.generate_campaign(
        product_name=product_name,
        feature_summary=feature_summary,
        output_dir=target_dir,
        audience=target_aud,
        video_duration_seconds=video_duration,
    )

    return {
        "status": "success",
        "product_name": bundle.product_name,
        "feature_summary": bundle.feature_summary,
        "draft_directory": bundle.draft_directory,
        "ads_channels": [ad.channel.value for ad in bundle.ads],
        "social_platforms": ["linkedin", "instagram", "tiktok"],
        "video": {
            "total_duration_seconds": bundle.video.script.total_duration_seconds,
            "scenes_count": len(bundle.video.script.scenes),
            "wav_path": bundle.video.wav_audio_path,
            "mp4_path": bundle.video.mp4_video_path,
        },
        "calendar": {
            "scheduled_items": len(bundle.calendar.schedule),
            "nextor_tasks": len(bundle.calendar.nextor_tasks),
            "cadence_summary": bundle.calendar.cadence_summary,
        },
    }


def assemble_marketing_video(
    feature_summary: str,
    product_name: str = "NexCoder",
    output_dir: str | None = None,
    duration: float = 30.0,
    aspect_ratio: str = "9:16",
) -> dict[str, Any]:
    """Produce promotional video script, subtitles, Piper TTS audio, and FFmpeg assembly scripts."""
    try:
        target_path = _resolve_output_dir(output_dir, f".nexcoder/marketing/drafts/{_slug(product_name)}/video")
    except PathOutsideSandboxError as exc:
        return {"status": "error", "message": str(exc)}
    target_path.mkdir(parents=True, exist_ok=True)

    script_gen = VideoScriptGenerator()
    script = script_gen.generate_script(
        product_name=product_name,
        feature_summary=feature_summary,
        target_duration=duration,
        aspect_ratio=aspect_ratio,
    )

    audio_path = target_path / "narration.wav"
    sub_srt_path = target_path / "subtitles.srt"
    sub_vtt_path = target_path / "subtitles.vtt"
    mp4_path = target_path / "promo_video.mp4"

    tts = PiperTTSClient()
    tts.synthesize_scenes(script.scenes, audio_path)

    sub_gen = SubtitleGenerator()
    srt_text = sub_gen.generate_srt(script.scenes)
    sub_srt_path.write_text(srt_text, encoding="utf-8")

    vtt_text = sub_gen.generate_vtt(script.scenes)
    sub_vtt_path.write_text(vtt_text, encoding="utf-8")

    compositor = FFmpegCompositor()
    artifact = compositor.assemble_video(
        script=script,
        audio_path=audio_path,
        subtitles_path=sub_srt_path,
        output_path=mp4_path,
    )

    (target_path / "storyboard.md").write_text(artifact.storyboard_markdown, encoding="utf-8")
    (target_path / "assemble.sh").write_text(artifact.assembly_script_sh, encoding="utf-8")
    (target_path / "assemble.ps1").write_text(artifact.assembly_script_ps1, encoding="utf-8")

    return {
        "status": "success",
        "title": script.title,
        "aspect_ratio": script.aspect_ratio,
        "total_duration_seconds": script.total_duration_seconds,
        "scenes_count": len(script.scenes),
        "storyboard_path": str(target_path / "storyboard.md"),
        "subtitles_srt_path": str(sub_srt_path),
        "subtitles_vtt_path": str(sub_vtt_path),
        "audio_path": str(audio_path),
        "video_path": str(mp4_path),
        "assembly_script_sh": str(target_path / "assemble.sh"),
        "assembly_script_ps1": str(target_path / "assemble.ps1"),
    }


def schedule_marketing_calendar(
    feature_summary: str,
    product_name: str = "NexCoder",
) -> dict[str, Any]:
    """Suggest optimal posting cadence and convert marketing milestones into Nextor Kanban tasks."""
    gen = ContentCalendarGenerator()
    calendar = gen.generate_calendar(product_name=product_name, feature_summary=feature_summary)
    nextor_md = gen.render_nextor_markdown(calendar)

    return {
        "status": "success",
        "product_name": calendar.product_name,
        "cadence_summary": calendar.cadence_summary,
        "schedule": [
            {
                "schedule_id": s.schedule_id,
                "platform": s.platform.value,
                "day_offset": s.day_offset,
                "recommended_time": s.recommended_time,
                "title": s.title,
                "format_type": s.format_type,
            }
            for s in calendar.schedule
        ],
        "nextor_tasks": [
            {
                "task_id": t.task_id,
                "title": t.title,
                "sector": t.sector,
                "assignee": t.assignee,
                "due_days_from_now": t.due_days_from_now,
                "checklist": t.checklist,
            }
            for t in calendar.nextor_tasks
        ],
        "nextor_markdown": nextor_md,
    }


_default_publisher: SafeSocialPublisher | None = None


def get_default_publisher() -> SafeSocialPublisher:
    global _default_publisher
    if _default_publisher is None:
        _default_publisher = SafeSocialPublisher()
    return _default_publisher


def publish_social_post(
    platform: str,
    content_text: str,
    approval_token: str,
    confirmed: bool = False,
    dry_run: bool = True,
    media_path: str | None = None,
    publisher: SafeSocialPublisher | None = None,
) -> dict[str, Any]:
    """Publish a post to official social media APIs with mandatory human approval token."""
    plat_map = {
        "linkedin": SocialPlatform.LINKEDIN,
        "instagram": SocialPlatform.INSTAGRAM,
        "tiktok": SocialPlatform.TIKTOK,
    }
    if platform.lower() not in plat_map:
        return {
            "success": False,
            "status_message": f"Unsupported platform '{platform}'. Choose from: linkedin, instagram, tiktok.",
        }

    pub = publisher or get_default_publisher()
    request = PublicationRequest(
        platform=plat_map[platform.lower()],
        content_text=content_text,
        media_path=media_path,
        approval_token=approval_token,
        confirmed=confirmed,
        dry_run=dry_run,
    )

    try:
        result = pub.publish(request)
        return {
            "success": result.success,
            "platform": result.platform.value,
            "post_id": result.post_id,
            "url": result.url,
            "status_message": result.status_message,
            "audit_event_id": result.audit_event_id,
        }
    except PublicationGovernanceError as exc:
        return {
            "success": False,
            "platform": platform,
            "status_message": str(exc),
        }
