"""Social media post generation for LinkedIn, Instagram, and TikTok with channel-specific tones."""

from __future__ import annotations

from nexcoder_agents.marketing.models import (
    InstagramCarouselSlide,
    InstagramPost,
    LinkedInPost,
    SocialCampaign,
    TikTokPost,
    TikTokScene,
)


class SocialPostGenerator:
    """Generates tailored social media posts respecting the conventions and tone of each network."""

    def generate_campaign(
        self,
        product_name: str,
        feature_summary: str,
        target_audience: str = "developers and engineering leaders",
        repo_url: str = "https://github.com/ThiagoVenturim/NexCoder",
        key_takeaways: list[str] | None = None,
    ) -> SocialCampaign:
        takeaways = key_takeaways or [
            "Deterministic offline verification eliminates flakiness.",
            "Zero co-author trailers or synthetic noise in git history.",
            "Human approval gates keep sensitive operations safe.",
        ]

        linkedin_post = self.generate_linkedin(
            product_name=product_name,
            feature_summary=feature_summary,
            key_takeaways=takeaways,
            repo_url=repo_url,
        )

        instagram_post = self.generate_instagram(
            product_name=product_name,
            feature_summary=feature_summary,
            repo_url=repo_url,
        )

        tiktok_post = self.generate_tiktok(
            product_name=product_name,
            feature_summary=feature_summary,
        )

        return SocialCampaign(
            product_name=product_name,
            feature_summary=feature_summary,
            linkedin=linkedin_post,
            instagram=instagram_post,
            tiktok=tiktok_post,
        )

    def generate_linkedin(
        self,
        product_name: str,
        feature_summary: str,
        key_takeaways: list[str],
        repo_url: str = "https://github.com/ThiagoVenturim/NexCoder",
    ) -> LinkedInPost:
        clean_feature = feature_summary.rstrip(".")
        headline = f"Engineering Update: How we built {clean_feature} for {product_name}"
        body = (
            f"Shipping high-velocity software requires more than prompt templates and boilerplate. "
            f"In our latest update to {product_name}, we addressed a fundamental workflow need: "
            f"{clean_feature}.\n\n"
            f"Rather than relying on brittle cloud integrations or unchecked automation, "
            f"every step is designed to run offline, adhere to strict architectural boundaries, "
            f"and remain fully under human supervision."
        )
        cta = (
            f"Read the technical design doc and clone the open-source repository at {repo_url}."
        )
        hashtags = [
            "SoftwareEngineering",
            "OpenSource",
            "Architecture",
            "DevOps",
            "EngineeringLeadership",
        ]
        return LinkedInPost(
            headline=headline,
            body=body,
            key_takeaways=key_takeaways,
            call_to_action=cta,
            hashtags=hashtags,
        )

    def generate_instagram(
        self,
        product_name: str,
        feature_summary: str,
        repo_url: str = "https://github.com/ThiagoVenturim/NexCoder",
    ) -> InstagramPost:
        clean_feature = feature_summary.rstrip(".")
        hook = f"How {product_name} solves {clean_feature}"
        caption = (
            f"Swipe through to see how we designed {clean_feature} inside {product_name}.\n\n"
            f"We believe open-source tools should be deterministic, fast, and respectful "
            f"of developer control. No emojis, no secret leaking, just clean code.\n\n"
            f"Check out the link in bio or visit {repo_url} to try the offline quickstart."
        )

        slides = [
            InstagramCarouselSlide(
                slide_number=1,
                title="The Challenge",
                description=(
                    f"Modern development teams struggle with {clean_feature.lower()} "
                    "without introducing security risks or vendor lock-in."
                ),
            ),
            InstagramCarouselSlide(
                slide_number=2,
                title="The Approach",
                description=(
                    f"{product_name} introduces a modular architecture where every artifact "
                    "is generated as a draft and validated offline."
                ),
            ),
            InstagramCarouselSlide(
                slide_number=3,
                title="Under The Hood",
                description=(
                    "Built with Python 3.11, strict Pydantic models, AST intelligence, "
                    "and human-in-the-loop confirmation gates."
                ),
            ),
            InstagramCarouselSlide(
                slide_number=4,
                title="The Outcome",
                description="Instant local feedback, zero flaky dependencies during tests, and reproducible builds.",
            ),
            InstagramCarouselSlide(
                slide_number=5,
                title="Get Started",
                description=f"Clone the repository, run the CLI quickstart, and contribute to {product_name}.",
            ),
        ]

        hashtags = [
            "coding",
            "developer",
            "softwaredeveloper",
            "opensource",
            "techcommunity",
            "programming",
        ]

        return InstagramPost(
            hook=hook,
            caption=caption,
            slides=slides,
            hashtags=hashtags,
        )

    def generate_tiktok(
        self,
        product_name: str,
        feature_summary: str,
    ) -> TikTokPost:
        clean_feature = feature_summary.rstrip(".")
        hook = f"Stop doing this manually in your dev projects: {clean_feature}"
        scenes = [
            TikTokScene(
                timecode="00:00 - 00:03",
                dialogue=(
                    f"If you're building software and still struggling with "
                    f"{clean_feature.lower()}, stop right now."
                ),
                visual_cue="Close-up on terminal with frantic typing, then zooming in on error or backlog.",
            ),
            TikTokScene(
                timecode="00:03 - 00:10",
                dialogue=f"We built {product_name} to handle this completely offline with zero vendor lock-in.",
                visual_cue="Screen recording showing nexcoder CLI running seamlessly in terminal.",
            ),
            TikTokScene(
                timecode="00:10 - 00:18",
                dialogue=(
                    "Notice how it generates drafts, verifies everything locally, "
                    "and requires human approval before publishing anything."
                ),
                visual_cue="Highlighting the generated drafts folder and human confirmation token prompt.",
            ),
            TikTokScene(
                timecode="00:18 - 00:25",
                dialogue="No random bots, no leaked keys. Just clean code and tested architecture.",
                visual_cue="Green pytest test results passing across the screen.",
            ),
            TikTokScene(
                timecode="00:25 - 00:30",
                dialogue=f"It's open source on GitHub under ThiagoVenturim/{product_name}. Check it out!",
                visual_cue="Final shot showing GitHub repository page and star button.",
            ),
        ]

        caption = f"Building offline-first dev tooling with {product_name}! #coding #developer #tech #opensource"
        hashtags = ["coding", "developer", "tech", "opensource", "softwareengineer", "buildinpublic"]

        return TikTokPost(
            hook_first_3s=hook,
            dialogue_script=scenes,
            music_audio_recommendation="Upbeat lo-fi synthwave beat with rhythmic clicks",
            caption=caption,
            hashtags=hashtags,
        )
