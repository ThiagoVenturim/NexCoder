# Running the portfolio on Maestri

faccoder can run on a Maestri canvas. Each project gets
its own workspace, each layer of the platform gets its own floor (a git worktree
on its own branch), and each floor is staffed by one agent running the
Antigravity CLI (`agy`). A Maestro agent on the ground floor coordinates the work
and talks to the humans.

## Layout

```
OSS Portfolio (sidebar group)
|
+-- faccoder                      ground: Maestro (orchestrator), shared note "faccoder-plan"
|     +-- Ideation and Jury       layer/ideation     agent Lumen
|     +-- Planning                layer/planning     agent Quill
|     +-- Code Intelligence       layer/code-intel   agent Atlas
|     +-- Agents and Pipelines    layer/agents       agent Loom
|     +-- Capture and QA          layer/capture      agent Prism
|     +-- Security                layer/security     agent Bastion
|     +-- Docs                    layer/docs         agent Scribe
|
+-- askdash                       Semantic Layer, Dashboards
+-- Support Engine                Ingestion and RAG, Analytics
+-- Acompanhamento de NP          Extension, Claude Skills
```

## Flow of work

1. **Idea.** A human describes an idea to the Maestro, or opens an issue.
2. **Research and jury.** The Ideation floor runs `faccoder idea` and then
   `faccoder judge`. The research squad covers market, competitors,
   differentiators and gaps, with cited sources. The jury votes go, pivot or
   no-go. A pivot loops back with the changes the jury suggested.
3. **Human gate.** The Maestro posts the report and waits for approval
   (`--state blocked`).
4. **Planning.** The Planning floor turns the approved PRD into epics, stories
   and tasks. It plans sprints by capacity and dependencies and creates the
   GitHub Project, milestones and issues. Issues are marked so the step can be
   re-run without creating duplicates.
5. **Build.** Each issue is routed to the floor that owns its layer. The agent
   works on its branch and keeps its floor status current.
6. **Quality gates.** A layer is done only after:
   - Capture and QA generates and runs the tests;
   - Security runs the security gate;
   - Docs updates the guides.
7. **Review and land.** A floor in `review` waits for a human. The Maestro
   lands it only when a human says so.
8. **Continuous improvement.** A routine (`maestri routine`) re-runs the
   research and the security scans every week. Its findings become new issues
   through step 4.

## Setup

Run inside a Maestri terminal with Maestro Mode enabled:

```powershell
# once: preset, roles and the four workspaces
./ops/maestri/provision.ps1 -Bootstrap -Root C:\path\to\projects

# then, from the Maestro terminal of each workspace
./ops/maestri/provision.ps1 -Layers -Project faccoder
```

Add `-WhatIf` to print the commands without running them. The agent command
defaults to `agy`; pass `-AgentCommand "claude"` to staff the floors with Claude
Code instead.

## Rules every agent follows

Every role prompt carries these rules (see `provision.ps1`):

- No emojis anywhere.
- No AI co-author trailers. The `.githooks/commit-msg` hook removes them anyway.
- Nothing is pushed, published or made public without the Maestro relaying a
  human's approval.
