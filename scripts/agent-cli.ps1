<#
.SYNOPSIS
Build and run the NexCoder agent CLI container (issue #115).

.DESCRIPTION
  scripts/agent-cli.ps1 build            build the image
  scripts/agent-cli.ps1 login            log in with your own account (stored in a named volume)
  scripts/agent-cli.ps1 check            check that the CLI inside the image works
  scripts/agent-cli.ps1 up | down        start or stop the long-running container (exec mode)
  scripts/agent-cli.ps1 dispatch "task"  send one task through ContainerCLIBackend

Environment: NEXCODER_CONTAINER_RUNTIME (docker or podman), NEXCODER_AGENT_IMAGE,
NEXCODER_AGENT_VOLUME, NEXCODER_AGENT_CLI (claude or generic).
Use only with your own login and within the CLI provider's terms of use.
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("build", "login", "check", "up", "down", "dispatch", "help")]
    [string]$Action = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @()
)

$ErrorActionPreference = "Stop"

function Get-Setting([string]$Name, [string]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Get-Setting "NEXCODER_CONTAINER_RUNTIME" "docker"
$Image = Get-Setting "NEXCODER_AGENT_IMAGE" "nexcoder/agent-cli:local"
$Volume = Get-Setting "NEXCODER_AGENT_VOLUME" "nexcoder-agent-cli-home"
$Cli = Get-Setting "NEXCODER_AGENT_CLI" "claude"
$Context = Join-Path $Root "docker/agent-cli"
$Compose = Join-Path $Context "compose.yml"
$Python = Get-Setting "PYTHON" "python"

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Action) {
    "build" {
        Invoke-Checked $Runtime @("build", "-t", $Image, $Context)
    }
    "login" {
        Invoke-Checked $Runtime @("volume", "create", $Volume) | Out-Null
        Invoke-Checked $Runtime @("run", "--rm", "-it", "-e", "NEXCODER_AGENT_CLI=$Cli", "-v", "${Volume}:/home/agent", $Image, "login")
    }
    "check" {
        Invoke-Checked $Runtime @("run", "--rm", "-e", "NEXCODER_AGENT_CLI=$Cli", "-v", "${Volume}:/home/agent", $Image, "check")
    }
    "up" {
        Invoke-Checked $Runtime @("compose", "-f", $Compose, "up", "-d", "--build")
    }
    "down" {
        Invoke-Checked $Runtime @("compose", "-f", $Compose, "down")
    }
    "dispatch" {
        if ($Rest.Count -lt 1) {
            Write-Error "usage: scripts/agent-cli.ps1 dispatch `"task text`" [extra nexcoder-agents dispatch options]"
            exit 2
        }
        $arguments = @("-m", "nexcoder_agents.cli", "dispatch", "--backend", "container", "--runtime", $Runtime,
            "--image", $Image, "--volume", $Volume, "--cli", $Cli) + $Rest
        Invoke-Checked $Python $arguments
    }
    default {
        Get-Help $PSCommandPath -Detailed
    }
}
