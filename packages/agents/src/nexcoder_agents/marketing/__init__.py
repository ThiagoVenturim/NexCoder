"""Marketing, advertising, social media post generation, video production, and safe publishing."""

from __future__ import annotations

from nexcoder_agents.marketing.ads import AdCopyGenerator
from nexcoder_agents.marketing.calendar import ContentCalendarGenerator
from nexcoder_agents.marketing.models import (
    AdCampaign,
    AdChannel,
    AdVariation,
    ContentCalendar,
    GeneratedVideoArtifact,
    InstagramCarouselSlide,
    InstagramPost,
    LinkedInPost,
    MarketingBundle,
    NextorTask,
    PostingScheduleItem,
    PublicationRequest,
    PublicationResult,
    SocialCampaign,
    SocialPlatform,
    SubtitleFormat,
    TargetAudience,
    TikTokPost,
    TikTokScene,
    VideoScene,
    VideoScript,
)
from nexcoder_agents.marketing.pipeline import MarketingOrchestrator
from nexcoder_agents.marketing.publisher import (
    PublicationGovernanceError,
    SafeSocialPublisher,
)
from nexcoder_agents.marketing.social import SocialPostGenerator
from nexcoder_agents.marketing.video import (
    FFmpegCompositor,
    PiperTTSClient,
    SubtitleGenerator,
    VideoScriptGenerator,
)

__all__ = [
    "AdCampaign",
    "AdChannel",
    "AdCopyGenerator",
    "AdVariation",
    "ContentCalendar",
    "ContentCalendarGenerator",
    "FFmpegCompositor",
    "GeneratedVideoArtifact",
    "InstagramCarouselSlide",
    "InstagramPost",
    "LinkedInPost",
    "MarketingBundle",
    "MarketingOrchestrator",
    "NextorTask",
    "PiperTTSClient",
    "PostingScheduleItem",
    "PublicationGovernanceError",
    "PublicationRequest",
    "PublicationResult",
    "SafeSocialPublisher",
    "SocialCampaign",
    "SocialPlatform",
    "SocialPostGenerator",
    "SubtitleFormat",
    "SubtitleGenerator",
    "TargetAudience",
    "TikTokPost",
    "TikTokScene",
    "VideoScene",
    "VideoScript",
    "VideoScriptGenerator",
]
