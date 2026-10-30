<#
.SYNOPSIS
  Provisions Maestri workspaces, floors and Antigravity (agy) agents for the faccoder portfolio.

.DESCRIPTION
  Must run inside a Maestri terminal with Maestro Mode enabled (MAESTRI_PIPE set).

  Two steps:
    1. -Bootstrap   (run once, from any Maestro terminal)
       Creates the "Antigravity" preset, the global roles, and one workspace per project
       under the "OSS Portfolio" group.
    2. -Layers      (run from the Maestro terminal of each project workspace)
       Creates one git-isolated floor per layer and recruits an agy agent on each.

  Floors can only be created in the workspace the Maestro lives in, which is why the
  second step runs once per workspace.

.EXAMPLE
  ./ops/maestri/provision.ps1 -Bootstrap -Root C:\Users\me\projetos-oss
  ./ops/maestri/provision.ps1 -Layers -Project faccoder
#>
param(
  [switch]$Bootstrap,
  [switch]$Layers,
  [ValidateSet("faccoder", "askdash", "support-engine", "acompanhamento-np")]
  [string]$Project = "faccoder",
  [string]$Root = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
  [string]$AgentCommand = "agy",
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

if (-not $env:MAESTRI_PIPE) {
  throw "Run this inside a Maestri terminal with Maestro Mode enabled (MAESTRI_PIPE is not set)."
}
$maestri = if ($env:MAESTRI_CLI) { $env:MAESTRI_CLI } else { "maestri" }

function Invoke-Maestri([string[]]$Arguments) {
  Write-Host "maestri $($Arguments -join ' ')"
  if (-not $WhatIf) { & $maestri @Arguments; if ($LASTEXITCODE) { Write-Warning "exit $LASTEXITCODE" } }
}

$Workspaces = [ordered]@{
  "faccoder"          = @{ Name = "faccoder";             Dir = "fabrica-code" }
  "askdash"           = @{ Name = "askdash";              Dir = "askdash" }
  "support-engine"    = @{ Name = "Support Engine";       Dir = "Support_Intelligence_Engine" }
  # Dir may be absolute when a project lives outside -Root.
  "acompanhamento-np" = @{ Name = "Acompanhamento de NP"; Dir = (Join-Path $HOME "acompanhamento_de_np") }
}

# Layer = floor. Each floor is a git worktree on its own branch, staffed by one agy agent.
$LayerPlan = @{
  "faccoder" = @(
    @{ Floor = "Ideation and Jury";  Branch = "layer/ideation";  Agent = "Lumen";  Role = "faccoder Ideation" }
    @{ Floor = "Planning";           Branch = "layer/planning";  Agent = "Quill";  Role = "faccoder Planner" }
    @{ Floor = "Code Intelligence";  Branch = "layer/code-intel"; Agent = "Atlas"; Role = "faccoder Code Intel" }
    @{ Floor = "Agents and Pipelines"; Branch = "layer/agents";  Agent = "Loom";   Role = "faccoder Agents" }
    @{ Floor = "Capture and QA";     Branch = "layer/capture";   Agent = "Prism";  Role = "faccoder Capture QA" }
    @{ Floor = "Security";           Branch = "layer/security";  Agent = "Bastion"; Role = "faccoder Security" }
    @{ Floor = "Docs";               Branch = "layer/docs";      Agent = "Scribe"; Role = "faccoder Docs" }
  )
  "askdash" = @(
    @{ Floor = "Semantic Layer";     Branch = "layer/semantic";  Agent = "Cubist"; Role = "askdash Builder" }
    @{ Floor = "Dashboards";         Branch = "layer/dashboards"; Agent = "Canvas"; Role = "askdash Builder" }
  )
  "support-engine" = @(
    @{ Floor = "Ingestion and RAG";  Branch = "layer/rag";       Agent = "Harbor"; Role = "Support Engine Builder" }
    @{ Floor = "Analytics";          Branch = "layer/analytics"; Agent = "Tide";   Role = "Support Engine Builder" }
  )
  "acompanhamento-np" = @(
    @{ Floor = "Extension";          Branch = "layer/extension"; Agent = "Ledger"; Role = "Legal Tools Builder" }
    @{ Floor = "Claude Skills";      Branch = "layer/skills";    Agent = "Clerk";  Role = "Legal Tools Builder" }
  )
}

$CommonRules = @"
Rules for every agent in this portfolio:
- No emojis anywhere: code, docs, UI strings, commit messages.
- Never add AI co-author trailers to commits. The repository hook strips them; do not work around it.
- Never push, open pull requests, or change repository visibility without the Maestro's go-ahead.
- Keep 'maestri floor status' current: post when you start, at milestones, '--state blocked' when you need a human, '--state review' when ready.
- Run 'maestri list' to see your teammates and shared notes before asking anyone anything.
- Read PLAN.md in the portfolio root before starting (it cites internal source paths: never copy those paths or any company names into public files). Report back with: maestri ask "Maestro" "<result>".
"@

$Roles = @{
  "faccoder Ideation"     = "You own packages/ideation: idea intake, research squad (market, competitors, differentiators, gaps) and the jury that votes go, pivot or no-go with cited sources."
  "faccoder Planner"      = "You own packages/planning: PRD to epics, stories and tasks, sprint planning by capacity and dependencies, idempotent GitHub/GitLab/Azure DevOps adapters."
  "faccoder Code Intel"   = "You own packages/code-intel: parsers for every language (tree-sitter plus Delphi, COBOL, OutSystems), hybrid RAG, GraphRAG and bottom-up documentation generation."
  "faccoder Agents"       = "You own packages/agents: the agent and skill catalog, Claude Code export, and the LangGraph pipeline engine with human approval and committee blocks."
  "faccoder Capture QA"   = "You own packages/capture: Playwright DOM and accessibility capture, desktop UI Automation, test generation and visual regression. Never bypass captchas or site terms."
  "faccoder Security"     = "You own packages/security: Semgrep, gitleaks, OSV-Scanner, Trivy and Syft wrappers, the security agents and the release security gate."
  "faccoder Docs"         = "You own docs/: guides for RAG, GraphRAG, reranking, embeddings, models open vs paid, Langfuse, pipelines and the case study. English, with a pt-BR README."
  "askdash Builder"       = "You build askdash: semantic layer, safe parameterized SQL, live dashboards with SSRF and SQL guards, and the MCP server."
  "Support Engine Builder" = "You build the Support Intelligence Engine: connectors, ingestion quality, curated hybrid RAG, sentiment, trends and the support copilot. Synthetic data only."
  "Legal Tools Builder"   = "You build acompanhamento_de_np: the MV3 extension, deadline engine, DataJud integration, MCP server and Claude skills for lawyers. LGPD first; no captcha bypass."
}

if ($Bootstrap) {
  if (-not ((& $maestri preset list) -match '"Antigravity"')) {
    Invoke-Maestri @("preset", "create", "Antigravity", "--command", $AgentCommand, "--quick-start", "on")
  }
  $existingRoles = (& $maestri role list) -join "`n"
  foreach ($role in $Roles.GetEnumerator()) {
    if ($existingRoles -match [regex]::Escape($role.Key)) { continue }
    Invoke-Maestri @("role", "create", $role.Key, "$($role.Value)`n`n$CommonRules", "--scope", "global")
  }
  $existingWorkspaces = (& $maestri workspace list) -join "`n"
  foreach ($ws in $Workspaces.Values) {
    if ($existingWorkspaces -match ('"' + [regex]::Escape($ws.Name) + '"')) { continue }
    $dir = if ([IO.Path]::IsPathRooted($ws.Dir)) { $ws.Dir } else { Join-Path $Root $ws.Dir }
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null; git -C $dir init -q }
    Invoke-Maestri @("workspace", "create", $ws.Name, "--dir", $dir, "--group", "OSS Portfolio")
  }
  Write-Host "Bootstrap done. Open each workspace, enable Maestro on its terminal and run -Layers -Project <name>."
}

if ($Layers) {
  foreach ($layer in $LayerPlan[$Project]) {
    Invoke-Maestri @("floor", "create", $layer.Floor, "--branch", $layer.Branch)
    Invoke-Maestri @("recruit", $layer.Agent, "--preset", "Antigravity", "--role", $layer.Role, "--floor", $layer.Floor)
  }
  Invoke-Maestri @("floor", "status", "Layers provisioned for $Project", "--floor", "Ground")
}

if (-not $Bootstrap -and -not $Layers) { Get-Help $MyInvocation.MyCommand.Path -Detailed }
