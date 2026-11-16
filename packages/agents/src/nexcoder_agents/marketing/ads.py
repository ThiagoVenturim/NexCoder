"""Ad copy generation engine with channel constraints, audience targeting, and A/B variations."""

from __future__ import annotations

from nexcoder_agents.marketing.models import (
    AdCampaign,
    AdChannel,
    AdVariation,
    TargetAudience,
)


class AdCopyGenerator:
    """Generates structured, platform-compliant advertising copy with A/B variations."""

    def __init__(self) -> None:
        pass

    def generate_campaign(
        self,
        product_name: str,
        feature_summary: str,
        channel: AdChannel = AdChannel.LINKEDIN,
        audience: TargetAudience = TargetAudience.DEVELOPERS,
        key_benefits: list[str] | None = None,
    ) -> AdCampaign:
        benefits = key_benefits or [
            "Deterministic offline testing and local execution",
            "Zero vendor lock-in with open-source foundation",
            "Automated developer workflows with human approval",
        ]

        if channel == AdChannel.GOOGLE_SEARCH:
            variations = self._generate_google_variations(product_name, feature_summary, audience)
            keywords = [
                f"{product_name.lower()} open source",
                f"{product_name.lower()} developer tool",
                "local dev workflow automation",
                "ai code intelligence",
            ]
        elif channel == AdChannel.LINKEDIN:
            variations = self._generate_linkedin_variations(product_name, feature_summary, audience)
            keywords = ["B2B Tech", "Engineering Leadership", "DevOps", "AI Engineering"]
        elif channel == AdChannel.META_INSTAGRAM:
            variations = self._generate_meta_variations(product_name, feature_summary, audience)
            keywords = ["#devlife", "#techstartup", "#softwareengineering", "#coding"]
        else:  # TWITTER_X
            variations = self._generate_twitter_variations(product_name, feature_summary, audience)
            keywords = ["#buildinpublic", "#opensource", "#devtools", "#tech"]

        return AdCampaign(
            product_name=product_name,
            feature_summary=feature_summary,
            channel=channel,
            audience=audience,
            variations=variations,
            keywords=keywords,
            key_benefits=benefits,
        )

    def generate_all_channels(
        self,
        product_name: str,
        feature_summary: str,
        audience: TargetAudience = TargetAudience.DEVELOPERS,
        key_benefits: list[str] | None = None,
    ) -> list[AdCampaign]:
        """Generate ad campaigns across all supported channels."""
        channels = [
            AdChannel.GOOGLE_SEARCH,
            AdChannel.LINKEDIN,
            AdChannel.META_INSTAGRAM,
            AdChannel.TWITTER_X,
        ]
        return [
            self.generate_campaign(
                product_name=product_name,
                feature_summary=feature_summary,
                channel=ch,
                audience=audience,
                key_benefits=key_benefits,
            )
            for ch in channels
        ]

    def _generate_google_variations(
        self, product: str, feature: str, audience: TargetAudience
    ) -> list[AdVariation]:
        # Google headline max 30 chars, description max 90 chars
        if audience in (TargetAudience.ENGINEERING_LEADERS, TargetAudience.ENTERPRISE_ARCHITECTS):
            var_a_head = f"{product}: Secure Dev Platform"[:30]
            var_a_body = f"Streamline engineering without lock-in. {feature}."[:90]
            var_b_head = f"{product} for Enterprise"[:30]
            var_b_body = "Audit-ready architecture, human-governed execution, 100% offline tests."[:90]
        else:
            var_a_head = f"{product} - Fast Dev Tools"[:30]
            var_a_body = f"Stop boilerplate grind. {feature}. Try offline quickstart today."[:90]
            var_b_head = f"Build Fast with {product}"[:30]
            var_b_body = "Open-source dev tools with AST intelligence and clean commits. Free."[:90]

        return [
            AdVariation(
                variation_id="variant_a_speed_pain",
                headline=var_a_head,
                body=var_a_body,
                cta="Explore Open Source Docs",
                display_path="devtools/quickstart",
            ),
            AdVariation(
                variation_id="variant_b_control_arch",
                headline=var_b_head,
                body=var_b_body,
                cta="View on GitHub",
                display_path="github/repo",
            ),
        ]

    def _generate_linkedin_variations(
        self, product: str, feature: str, audience: TargetAudience
    ) -> list[AdVariation]:
        clean_feature = feature.rstrip(".")
        var_a = AdVariation(
            variation_id="variant_a_engineering_impact",
            headline=f"Accelerate Engineering Velocity with {product}",
            body=(
                f"Tired of brittle tools and disconnected silos? {clean_feature}. "
                f"Designed for modern engineering teams who demand precision, deterministic "
                f"reproducibility, and strict governance."
            ),
            cta="Read Technical Architecture",
            display_path="linkedin/engineering",
        )
        var_b = AdVariation(
            variation_id="variant_b_privacy_governance",
            headline=f"Zero-Leakage Developer Intelligence: {product}",
            body=(
                f"Deploy autonomous workflows without leaking intellectual property. "
                f"{product} features human approval gates, audit logging, and 100% offline verification. "
                f"See how {clean_feature} transforms your delivery."
            ),
            cta="Schedule Deep Dive Demo",
            display_path="linkedin/governance",
        )
        return [var_a, var_b]

    def _generate_meta_variations(
        self, product: str, feature: str, audience: TargetAudience
    ) -> list[AdVariation]:
        clean_feature = feature.rstrip(".")
        var_a = AdVariation(
            variation_id="variant_a_visual_hook",
            headline=f"The Developer Workflow Upgrade: {product}",
            body=(
                f"Ship code with confidence. {clean_feature}. "
                f"Zero emojis, pure engineering rigor, and instant local test loops. "
                f"Swipe up to see the interactive quickstart."
            ),
            cta="Try Free Quickstart",
            display_path="instagram/quickstart",
        )
        var_b = AdVariation(
            variation_id="variant_b_creator_story",
            headline=f"Build Smarter, Not Harder with {product}",
            body=(
                f"From raw feature concept to tested pull request in minutes. "
                f"{clean_feature}. Built by developers, for developers."
            ),
            cta="Get the Code on GitHub",
            display_path="instagram/github",
        )
        return [var_a, var_b]

    def _generate_twitter_variations(
        self, product: str, feature: str, audience: TargetAudience
    ) -> list[AdVariation]:
        clean_feature = feature.rstrip(".")
        var_a = AdVariation(
            variation_id="variant_a_dev_thread",
            headline=f"Meet {product}",
            body=(
                f"Developer workflows shouldn't be fragile.\n\n"
                f"{clean_feature}.\n\n"
                f"100% offline tests. Strict governance. Open source."
            ),
            cta="Clone and Run Locally",
            display_path="twitter/quickstart",
        )
        var_b = AdVariation(
            variation_id="variant_b_punchy_metrics",
            headline=f"{product} Launch",
            body=(
                f"What if your tools verified their own work before asking for review?\n\n"
                f"{clean_feature}.\n\n"
                f"Check out the release on GitHub."
            ),
            cta="Star the Repo",
            display_path="twitter/release",
        )
        return [var_a, var_b]
