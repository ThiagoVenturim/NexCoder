"""Posting schedule calendar and Nextor Kanban task integration engine."""

from __future__ import annotations

import uuid

from nexcoder_agents.marketing.models import (
    ContentCalendar,
    NextorTask,
    PostingScheduleItem,
    SocialPlatform,
)


class ContentCalendarGenerator:
    """Produces optimal posting schedules and converts marketing milestones into Nextor tasks."""

    def generate_calendar(
        self,
        product_name: str,
        feature_summary: str,
    ) -> ContentCalendar:
        clean_feature = feature_summary.rstrip(".")

        schedule_items = [
            PostingScheduleItem(
                schedule_id="SCHED-01",
                platform=SocialPlatform.LINKEDIN,
                day_offset=1,
                recommended_time="Tuesday 09:00 AM",
                title=f"Architecture Announcement: {clean_feature}",
                theme="Engineering Insight",
                format_type="Long-form article and code overview",
                content_reference="drafts/social/linkedin_post.md",
            ),
            PostingScheduleItem(
                schedule_id="SCHED-02",
                platform=SocialPlatform.TIKTOK,
                day_offset=2,
                recommended_time="Wednesday 03:00 PM",
                title=f"Dev Quickstart: {clean_feature} in 30s",
                theme="Quick Tip and Demo",
                format_type="Short-form vertical video",
                content_reference="drafts/video/storyboard.md",
            ),
            PostingScheduleItem(
                schedule_id="SCHED-03",
                platform=SocialPlatform.INSTAGRAM,
                day_offset=3,
                recommended_time="Thursday 06:30 PM",
                title=f"Visual Carousel: Under the Hood of {clean_feature}",
                theme="Architecture Breakdown",
                format_type="Multi-slide carousel",
                content_reference="drafts/social/instagram_carousel.md",
            ),
            PostingScheduleItem(
                schedule_id="SCHED-04",
                platform=SocialPlatform.LINKEDIN,
                day_offset=5,
                recommended_time="Friday 10:30 AM",
                title="Community Q&A and Feedback Loop",
                theme="Open Source Engagement",
                format_type="Discussion prompt and GitHub issue link",
                content_reference="drafts/ads/linkedin_ads.json",
            ),
            PostingScheduleItem(
                schedule_id="SCHED-05",
                platform=SocialPlatform.TIKTOK,
                day_offset=7,
                recommended_time="Monday 02:00 PM",
                title="Behind the Code: Why We Chose Offline-First",
                theme="Tech Philosophy",
                format_type="Casual engineer-perspective video",
                content_reference="drafts/video/narration.wav",
            ),
        ]

        cadence_summary = (
            "Recommended Cadence: 2x/week LinkedIn (Tue/Fri morning), "
            "2x/week TikTok (Wed/Mon afternoon), 1x/week Instagram (Thu evening). "
            "Total 5 curated touchpoints over 14 days."
        )

        nextor_tasks = [
            NextorTask(
                task_id=f"MKT-TASK-{uuid.uuid4().hex[:8]}",
                title=f"Review Ad Copy Variations for {clean_feature}",
                description=(
                    f"Evaluate A/B test variations (speed vs governance) for "
                    f"{product_name} search and LinkedIn ads."
                ),
                sector="marketing-gtm",
                assignee="ad-copywriter",
                due_days_from_now=1,
                checklist=[
                    "Verify character limits for Google Search (headline <= 30, desc <= 90)",
                    "Confirm technical accuracy of value propositions",
                    "Select primary variation for initial launch run",
                ],
            ),
            NextorTask(
                task_id=f"MKT-TASK-{uuid.uuid4().hex[:8]}",
                title=f"Review Social Media Posts for {product_name}",
                description="Review drafted copy for LinkedIn, Instagram carousel, and TikTok short video script.",
                sector="marketing-gtm",
                assignee="social-media-creator",
                due_days_from_now=2,
                checklist=[
                    "Check LinkedIn post tone and bullet points",
                    "Verify Instagram carousel slides content",
                    "Review TikTok dialogue script and visual cues",
                    "Confirm all links point to official ThiagoVenturim repository",
                ],
            ),
            NextorTask(
                task_id=f"MKT-TASK-{uuid.uuid4().hex[:8]}",
                title=f"Produce Promo Video Assembly for {clean_feature}",
                description="Synthesize voiceover narration using Piper TTS and composite with FFmpeg.",
                sector="marketing-gtm",
                assignee="video-producer",
                due_days_from_now=3,
                checklist=[
                    "Generate voiceover WAV via Piper TTS",
                    "Review timed subtitles (SRT and VTT)",
                    "Run assembly script to produce preview MP4",
                    "Check video readability and audio balance",
                ],
            ),
            NextorTask(
                task_id=f"MKT-TASK-{uuid.uuid4().hex[:8]}",
                title="Human Confirmation Gate for Publication",
                description="Obtain required human approval token before scheduling any live publication.",
                sector="marketing-gtm",
                assignee="gtm-strategist",
                due_days_from_now=4,
                checklist=[
                    "Present drafts and storyboard to project owner",
                    "Obtain signed human approval token",
                    "Run dry-run verification with safe publisher",
                ],
            ),
        ]

        return ContentCalendar(
            product_name=product_name,
            schedule=schedule_items,
            cadence_summary=cadence_summary,
            nextor_tasks=nextor_tasks,
        )

    def render_nextor_markdown(self, calendar: ContentCalendar) -> str:
        lines = [
            f"# Nextor Kanban Marketing Tasks: {calendar.product_name}",
            "",
            f"<!-- nexcoder-id: {uuid.uuid4()} -->",
            "",
            f"**Cadence Summary:** {calendar.cadence_summary}",
            "",
            "## Publication Roadmap",
            "",
            "| Schedule ID | Day Offset | Platform | Recommended Slot | Content / Format |",
            "|---|---|---|---|---|",
        ]

        for s in calendar.schedule:
            row = (
                f"| {s.schedule_id} | Day +{s.day_offset} | {s.platform.value} | "
                f"{s.recommended_time} | {s.title} ({s.format_type}) |"
            )
            lines.append(row)

        lines.extend([
            "",
            "## Nextor Actionable Tasks",
            "",
        ])

        for t in calendar.nextor_tasks:
            lines.extend([
                f"### [{t.task_id}] {t.title}",
                "",
                f"- **Sector:** `{t.sector}`",
                f"- **Assignee:** `{t.assignee}`",
                f"- **Due:** In {t.due_days_from_now} day(s)",
                "",
                f"{t.description}",
                "",
                "**Checklist:**",
            ])
            for item in t.checklist:
                lines.append(f"- [ ] {item}")
            lines.append("")

        return "\n".join(lines)
