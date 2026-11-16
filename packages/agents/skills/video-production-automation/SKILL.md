---
name: video-production-automation
description: Automate promotional video creation using open-source tools: video scripting, storyboard generation, Piper TTS voiceovers, and FFmpeg compositing.
user-invocable: true
---

# Video Production Automation with Open-Source Tooling

Orchestrating end-to-end promotional video generation using strictly open-source, local command-line tools without proprietary cloud dependencies.

## Architecture

1. **Timed Scriptwriting & Storyboarding**
   - 5-stage narrative arc: Hook, Pain Point, Solution Demo, Key Metrics, Call to Action.
   - Outputs markdown storyboard table detailing visual direction, voiceover narration, on-screen text, and audio cues.

2. **Standard Subtitles (SRT and WebVTT)**
   - Accurate millisecond timestamps synchronized to scene durations.
   - Compatible with major video players and social platform upload requirements.

3. **Local Neural TTS with Piper**
   - Fast, local neural voice synthesis with zero cloud telemetry.
   - Zero-dependency fallback WAV synthesizer providing valid 16-bit PCM audio when Piper binary is not installed.

4. **FFmpeg Assembly Pipeline**
   - Generates executable bash and PowerShell compositing scripts.
   - Assembles solid slate background canvas (`color` filter), centered text overlays (`drawtext` filter), subtitles burn-in (`subtitles` filter), and AAC audio encoding into standard MP4.
   - Zero protected or copyrighted assets embedded.
