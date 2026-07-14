<#
.SYNOPSIS
    Push agent/universe.txt to the QuantOS VM and restart the agent so it
    re-reads the discovery universe.

.DESCRIPTION
    Bundles the two-step daily-ops chore (scp + systemctl restart) documented
    in docs/DailyRunbook.md. Runs from the laptop (Windows PowerShell).

    NOTE: ssh/scp ship with Git and are NOT on the plain PowerShell PATH, so
    this script calls them by full path (C:\Program Files\Git\usr\bin\).

    This does NOT refresh the Fyers token — that step is interactive (you paste
    the auth code) and must be run ON the VM. See docs/DailyRunbook.md.

.PARAMETER Tail
    After restarting, stream `journalctl -u quantos-agent -f` until Ctrl-C.

.PARAMETER NoRestart
    Copy the file but skip the service restart (agent picks it up on next
    restart / next-day Stage A).

.EXAMPLE
    .\scripts\push-universe.ps1
    .\scripts\push-universe.ps1 -Tail
#>
[CmdletBinding()]
param(
    [string]$KeyPath   = "D:\Exodus_14_14\QuantOS\Oracle SSH\ssh-key-2026-07-14.key",
    [string]$RemoteHost = "ubuntu@161.118.189.29",
    [string]$LocalFile  = (Join-Path $PSScriptRoot "..\agent\universe.txt"),
    [string]$RemotePath = "/home/ubuntu/quantos/agent/universe.txt",
    [switch]$Tail,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$ssh = "C:\Program Files\Git\usr\bin\ssh.exe"
$scp = "C:\Program Files\Git\usr\bin\scp.exe"

foreach ($exe in @($ssh, $scp)) {
    if (-not (Test-Path $exe)) { throw "Not found: $exe  (install Git for Windows, or edit the path in this script)" }
}
if (-not (Test-Path $KeyPath))   { throw "SSH key not found: $KeyPath" }
$LocalFile = (Resolve-Path $LocalFile).Path
if (-not (Test-Path $LocalFile)) { throw "Universe file not found: $LocalFile" }

# Quick sanity: count non-comment symbols before pushing.
$symbols = (Get-Content $LocalFile |
    Where-Object { $_.Trim() -ne "" -and -not $_.TrimStart().StartsWith("#") } |
    ForEach-Object { $_ -split "," } |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne "" })
Write-Host ("Local universe: {0} symbols  ({1})" -f $symbols.Count, $LocalFile) -ForegroundColor Cyan

Write-Host "-> scp to $RemoteHost ..." -ForegroundColor Cyan
& $scp -i $KeyPath -o StrictHostKeyChecking=accept-new $LocalFile "${RemoteHost}:${RemotePath}"
if ($LASTEXITCODE -ne 0) { throw "scp failed (exit $LASTEXITCODE)" }

# Verify the symbol count landed intact on the VM.
$remoteCount = (& $ssh -i $KeyPath $RemoteHost "grep -vE '^\s*#|^\s*$' $RemotePath | tr ',' '\n' | grep -cvE '^\s*$'").Trim()
Write-Host "   VM now has $remoteCount symbols." -ForegroundColor Green

if ($NoRestart) {
    Write-Host "-NoRestart set; skipping service restart. Agent will pick it up on next restart / Stage A." -ForegroundColor Yellow
    return
}

Write-Host "-> restarting quantos-agent ..." -ForegroundColor Cyan
& $ssh -i $KeyPath $RemoteHost "sudo systemctl restart quantos-agent && sleep 8 && systemctl is-active quantos-agent"
if ($LASTEXITCODE -ne 0) { throw "restart failed (exit $LASTEXITCODE)" }
Write-Host "Done. Broker reconnect + universe reload happen on boot." -ForegroundColor Green

if ($Tail) {
    Write-Host "-> tailing logs (Ctrl-C to stop) ..." -ForegroundColor Cyan
    & $ssh -i $KeyPath $RemoteHost "journalctl -u quantos-agent -f"
}
