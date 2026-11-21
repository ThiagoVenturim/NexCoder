# Marketing and Product Promotion Engine

The `nexcoder` marketing engine assists engineering teams and product creators in announcing, promoting, and distributing software releases and features. It generates multi-channel advertising copy, tailored social media posts, promotional video scripts and open-source video assemblies, and structured content calendars that integrate with the Nextor Kanban board.

All artifacts are generated and persisted strictly as local offline drafts. Live publication is impossible without explicit human confirmation and a valid, cryptographically signed approval token.

---

## Architectural Principles and Ethical Governance

1. **Strict Draft-First Generation**:
   - Every execution writes artifacts to a designated local directory (default `.nexcoder/marketing/drafts/<product>/`).
   - Automated distribution to social networks or ad platforms is prohibited by design.

2. **Human Governance Gate for Publication**:
   - Publishing to external platforms requires `confirmed=True` and a valid single-use human approval token issued via `ApprovalTokenManager`.
   - Attempting to publish without explicit confirmation raises `PublicationGovernanceError` and records a blocked audit event in `AppendOnlyAuditLog`.

3. **Official Platform APIs Only**:
   - All network dispatch routes exclusively through official platform developer APIs (LinkedIn Community Management API v2, Instagram Graph API, TikTok Content Posting API).
   - Scraping, automated browser sessions, session hijacking, or terms-of-service circumvention are strictly forbidden.

4. **Zero Copyrighted Assets**:
   - Promo video synthesis relies exclusively on open-source, local generative primitives: solid color canvas backdrops (`color` filter), centered text overlays (`drawtext` filter), subtitles burn-in (`subtitles` filter), and local voiceover synthesis (Piper TTS).
   - No proprietary music tracks, stock footage, or copyrighted assets are bundled.

5. **Clean Code and Communications**:
   - Zero emojis in copy, scripts, video subtitles, UI strings, or commit messages.
   - All repository links reference official project URLs under `ThiagoVenturim/NexCoder`.

---

## Capabilities

### 1. Multi-Channel Advertising Copy and A/B Testing

Generates platform-compliant advertising copy tailored by audience:
- **Google Search Ads**: Enforces strict character limits (Headlines <= 30 chars, Descriptions <= 90 chars, Display paths <= 15 chars).
- **LinkedIn Ads**: Professional B2B copy with technical value proposition and architecture focus.
- **Meta / Instagram Ads**: Visual hook and educational transformation narrative.
- **Twitter / X Ads**: Concise 280-character post format with clear CTA.

Every campaign automatically produces contrasting A/B variations:
- **Variant A (Speed & Pain Point)**: Focuses on developer velocity, removing boilerplate grind, and fast feedback loops.
- **Variant B (Governance & Privacy)**: Focuses on architectural rigor, offline testability, tamper-evident audit trails, and zero data leakage.

### 2. Social Media Content with Platform Tone Adaptation

- **LinkedIn**: Structured narrative with problem statement, engineering architecture breakdown, bulleted key takeaways, and relevant domain hashtags (`#SoftwareEngineering`, `#Architecture`, `#OpenSource`).
- **Instagram Carousel**: 5-slide pedagogical visual carousel layout (The Challenge, The Approach, Under The Hood, The Outcome, Get Started) plus caption and community hashtags.
- **TikTok Short Video Script**: 3-second attention hook, fast-paced dialogue lines with timestamp intervals (`00:00 - 00:03`), screen visual cues, audio style recommendations, caption, and trending hashtags.

### 3. Open-Source Video Production

Transforms feature descriptions into short promotional videos (15s to 60s):
- **Structured Storyboard**: 5-stage narrative arc (Hook, Pain Point, Solution Demo, Key Advantage, Call to Action) rendered into a markdown table.
- **Synchronized Subtitles**: Outputs standard SubRip (`.srt`) and WebVTT (`.vtt`) files with accurate millisecond timecodes.
- **Piper TTS Narration**: Local neural voice synthesis with deterministic fallback generation (synthesizing valid 16-bit PCM WAV audio).
- **FFmpeg Assembly Automation**: Builds production-ready command lines and exports executable shell scripts (`assemble.sh` and `assemble.ps1`) to composite video, text overlays, subtitles, and audio into an MP4 container.

### 4. Content Calendar and Nextor Kanban Integration

- Generates an optimal 14-day posting schedule roadmap recommending peak engagement time slots per network (e.g. LinkedIn Tuesday mornings, TikTok Wednesday afternoons, Instagram Thursday evenings).
- Converts marketing milestones into trackable Nextor tasks with unique identifiers (`MKT-TASK-...`), assignees (`gtm-strategist`, `social-media-creator`, `video-producer`, `ad-copywriter`), due dates, checklists, and idempotent tracking markers (`<!-- nexcoder-id: <uuid> -->`).

---

## Directory Structure of Generated Drafts

When running the campaign generator, artifacts are structured as follows:

```
.nexcoder/marketing/drafts/<slug>/
├── SUMMARY.md
├── ads/
│   ├── google_search_ads.json
│   ├── linkedin_ads.json
│   ├── meta_instagram_ads.json
│   └── twitter_x_ads.json
├── social/
│   ├── linkedin_post.md
│   ├── instagram_carousel.md
│   └── tiktok_script.md
├── video/
│   ├── storyboard.md
│   ├── subtitles.srt
│   ├── subtitles.vtt
│   ├── narration.wav
│   ├── promo_video.mp4
│   ├── assemble.sh
│   └── assemble.ps1
└── calendar/
    ├── posting_schedule.json
    └── nextor_tasks.md
```

---

## CLI Usage

### Generate Full Marketing Campaign
```bash
nexcoder marketing campaign \
  --feature "Automated marketing and video production suite" \
  --product "NexCoder" \
  --audience developers \
  --duration 30.0 \
  --output-dir ".nexcoder/marketing/drafts/campaign-01"
```

### Produce Promo Video Artifacts
```bash
nexcoder marketing video \
  --feature "AST code intelligence and impact analysis" \
  --product "NexCoder" \
  --duration 30.0 \
  --aspect-ratio "9:16"
```

### Generate Calendar and Nextor Tasks
```bash
nexcoder marketing calendar \
  --feature "Security scanning and authorization gates" \
  --product "NexCoder"
```

### Publish Social Post (Requires Confirmation)
```bash
nexcoder marketing publish \
  --platform linkedin \
  --content "We just shipped offline-first marketing pipelines in NexCoder." \
  --token "<APPROVAL_TOKEN>" \
  --confirmed \
  --dry-run
```

---

## MCP Tools Integration

| Tool Name | Module | Description | Gated / Safe |
|---|---|---|---|
| `generate_marketing_campaign` | `marketing` | Creates ads with A/B variations, social posts, video, and calendar drafts. | Offline Safe |
| `assemble_marketing_video` | `marketing` | Builds video storyboard, subtitles, Piper WAV audio, and FFmpeg scripts. | Offline Safe |
| `schedule_marketing_calendar` | `marketing` | Generates posting schedule and Nextor Kanban markdown tasks. | Offline Safe |
| `publish_social_post` | `marketing` | Dispatches post to official social APIs with human approval token. | Human-Gated |
