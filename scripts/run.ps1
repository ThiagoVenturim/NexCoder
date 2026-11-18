<#
.SYNOPSIS
Multiplatform execution script for nexcoder (Windows PowerShell).

.DESCRIPTION
Supports starting the application locally or in containers, running test suites,
and configuring pluggable database connectivity.

.PARAMETER Mode
Execution mode: local (default), docker, test, stop.

.PARAMETER HostName
Binding host for local execution (default: 127.0.0.1 or env HOST).

.PARAMETER Port
Listening port (default: 8000 or env PORT).

.PARAMETER DbUrl
Optional database URL override (default: SQLite or env DB_URL).
#>

[CmdletBinding()]
param(
    [ValidateSet("local", "docker", "test", "stop")]
    [string]$Mode = "local",

    [string]$HostName = $(if ($env:HOST) { $env:HOST } else { "127.0.0.1" }),

    [int]$Port = $(if ($env:PORT) { [int]$env:PORT } else { 8000 }),

    [string]$DbUrl = $env:DB_URL
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($DbUrl) {
    $env:DB_URL = $DbUrl
    Write-Host "[nexcoder] Pluggable database configured: $DbUrl"
}

switch ($Mode) {
    "local" {
        Write-Host "[nexcoder] Starting application locally on http://${HostName}:${Port}..."
        & nexcoder serve --transport sse --host $HostName --port $Port --api
    }
    "docker" {
        Write-Host "[nexcoder] Starting application and database with Docker Compose..."
        docker compose up --build
    }
    "test" {
        Write-Host "[nexcoder] Running offline verification tests..."
        python -m pytest packages
    }
    "stop" {
        Write-Host "[nexcoder] Stopping Docker Compose services..."
        docker compose down
    }
}
