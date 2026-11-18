"""Pydantic models and schemas for marketing, advertising, social posts, video, and publishing."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class AdChannel(StrEnum):
    GOOGLE_SEARCH = "google_search"
    LINKEDIN = "linkedin"
    META_INSTAGRAM = "meta_instagram"
    TWITTER_X = "twitter_x"


class TargetAudience(StrEnum):
    DEVELOPERS = "developers"
    ENGINEERING_LEADERS = "engineering_leaders"
    TECH_FOUNDERS = "tech_founders"
    ENTERPRISE_ARCHITECTS = "enterprise_architects"


class AdVariation(BaseModel):
    variation_id: str = Field(description="Identifier such as 'variant_a' or 'variant_b'.")
    headline: str = Field(description="Ad headline within channel character limits.")
    body: str = Field(description="Persuasive value proposition body copy.")
    cta: str = Field(description="Action-oriented call to action.")
    display_path: str = Field(default="", description="Display URL or path token.")


class AdCampaign(BaseModel):
    product_name: str
    feature_summary: str
    channel: AdChannel
    audience: TargetAudience
    variations: list[AdVariation] = Field(min_length=2, description="A/B test variations.")
    keywords: list[str] = Field(default_factory=list, description="Target search and ad keywords.")
    key_benefits: list[str] = Field(default_factory=list, description="Core benefits highlighted.")


class SocialPlatform(StrEnum):
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


class LinkedInPost(BaseModel):
    headline: str = Field(description="Professional opening hook.")
    body: str = Field(description="Structured body text with context and technical value.")
    key_takeaways: list[str] = Field(default_factory=list, description="Bullet points summarizing impact.")
    call_to_action: str = Field(description="Call to action directing to docs, demo, or repo.")
    hashtags: list[str] = Field(default_factory=list, description="Professional domain hashtags.")

    def format_text(self) -> str:
        bullets = "\n".join(f"- {item}" for item in self.key_takeaways)
        tags = " ".join(f"#{tag.lstrip('#')}" for tag in self.hashtags)
        parts = [self.headline, self.body]
        if bullets:
            parts.append(bullets)
        parts.extend([self.call_to_action, tags])
        return "\n\n".join(part for part in parts if part.strip())


class InstagramCarouselSlide(BaseModel):
    slide_number: int
    title: str
    description: str


class InstagramPost(BaseModel):
    hook: str = Field(description="Punchy visual hook line.")
    caption: str = Field(description="Engaging caption accompanying the visual/carousel.")
    slides: list[InstagramCarouselSlide] = Field(
        default_factory=list, description="Multi-slide carousel layout."
    )
    hashtags: list[str] = Field(default_factory=list, description="Engaging community hashtags.")

    def format_text(self) -> str:
        tags = " ".join(f"#{tag.lstrip('#')}" for tag in self.hashtags)
        slides_text = "\n".join(
            f"Slide {s.slide_number}: {s.title}\n{s.description}" for s in self.slides
        )
        parts = [self.hook, self.caption]
        if slides_text:
            parts.append(slides_text)
        if tags:
            parts.append(tags)
        return "\n\n".join(parts)


class TikTokScene(BaseModel):
    timecode: str = Field(description="Timestamp interval, e.g. '00:00 - 00:03'.")
    dialogue: str = Field(description="Spoken narration or dialogue.")
    visual_cue: str = Field(description="Screen action, camera framing, or UI interaction.")


class TikTokPost(BaseModel):
    hook_first_3s: str = Field(description="Aggressive hook for the first 3 seconds.")
    dialogue_script: list[TikTokScene] = Field(default_factory=list)
    music_audio_recommendation: str = Field(
        default="Fast-paced electronic or lo-fi beat",
        description="Suggested audio mood or style.",
    )
    caption: str = Field(description="Short video caption.")
    hashtags: list[str] = Field(default_factory=list, description="Trending and niche hashtags.")

    def format_text(self) -> str:
        tags = " ".join(f"#{tag.lstrip('#')}" for tag in self.hashtags)
        scenes = "\n".join(
            f"[{s.timecode}] Visual: {s.visual_cue} | Audio: {s.dialogue}"
            for s in self.dialogue_script
        )
        parts = [
            f"HOOK: {self.hook_first_3s}",
            f"AUDIO STYLE: {self.music_audio_recommendation}",
            "SCRIPT:",
            scenes,
            f"CAPTION: {self.caption}",
            tags,
        ]
        return "\n\n".join(part for part in parts if part.strip())


class SocialCampaign(BaseModel):
    product_name: str
    feature_summary: str
    linkedin: LinkedInPost
    instagram: InstagramPost
    tiktok: TikTokPost


class SubtitleFormat(StrEnum):
    SRT = "srt"
    VTT = "vtt"


class VideoScene(BaseModel):
    scene_id: int
    title: str
    duration_seconds: float = Field(ge=1.0)
    visual_description: str
    narration_text: str
    on_screen_text: str
    audio_cue: str = ""


class VideoScript(BaseModel):
    title: str
    target_duration_seconds: float = 30.0
    aspect_ratio: Literal["9:16", "16:9"] = "9:16"
    scenes: list[VideoScene] = Field(min_length=1)

    @property
    def total_duration_seconds(self) -> float:
        return sum(scene.duration_seconds for scene in self.scenes)


class GeneratedVideoArtifact(BaseModel):
    script: VideoScript
    srt_subtitles: str
    vtt_subtitles: str
    wav_audio_path: str | None = None
    mp4_video_path: str | None = None
    assembly_script_sh: str = ""
    assembly_script_ps1: str = ""
    storyboard_markdown: str = ""


class PostingScheduleItem(BaseModel):
    schedule_id: str
    platform: SocialPlatform
    day_offset: int
    recommended_time: str
    title: str
    theme: str
    format_type: str
    content_reference: str


class NextorTask(BaseModel):
    task_id: str
    title: str
    description: str
    sector: str = "marketing-gtm"
    assignee: str
    due_days_from_now: int
    checklist: list[str] = Field(default_factory=list)


class ContentCalendar(BaseModel):
    product_name: str
    schedule: list[PostingScheduleItem] = Field(default_factory=list)
    cadence_summary: str
    nextor_tasks: list[NextorTask] = Field(default_factory=list)


class PublicationRequest(BaseModel):
    platform: SocialPlatform
    content_text: str
    media_path: str | None = None
    approval_token: str
    confirmed: bool = False
    dry_run: bool = True


class PublicationResult(BaseModel):
    success: bool
    platform: SocialPlatform
    post_id: str | None = None
    url: str | None = None
    status_message: str = ""
    audit_event_id: str = ""


class MarketingBundle(BaseModel):
    product_name: str
    feature_summary: str
    ads: list[AdCampaign]
    social: SocialCampaign
    video: GeneratedVideoArtifact
    calendar: ContentCalendar
    draft_directory: str | None = None
