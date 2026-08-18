<#
.SYNOPSIS
    Deploy the current committed state of this repo to the QuantOS VM.

.DESCRIPTION
    Replaces the ad-hoc "scp a file, ssh in, hope" flow. On 2026-08-11 that
    flow had left the VM four commits behind main, running two hand-edits that
    were never committed FROM the VM (the Nifty 500 shortlist addition, applied
    directly on the box) while equivalent changes landed separately on main.
    Nothing was lost that time, but only because the edits happened to have
    converged. This script exists so that cannot silently happen again.

    The VM is a PULL target, not a PUSH target: it fetches from origin, so
    anything not pushed cannot be deployed. Only deploy/systemd/ and the built
    cockpit are copied over SSH; all other code arrives via git.

    Order of operations:
      1. Preflight (local) — HEAD must be pushed; unit tests must pass.
      2. Preflight (VM)    — working tree must be clean.
      3. Deploy            — git pull, sync systemd units, rebuild cockpit
                             if cockpit/ changed, restart the API if it needs it.
      4. Verify            — units in sync, API healthy, shortlist slots served.

    NOTE: ssh/scp ship with Git and are NOT on the plain PowerShell PATH, so
    this script calls them by full path (C:\Program Files\Git\usr\bin\), same
    as scripts/push-universe.ps1.

    This does NOT refresh the Fyers token — that step is interactive and must
    be run ON the VM. See docs/DailyRunbook.md.

.PARAMETER SkipTests
    Skip the local unit suite. Use when deploying a change that cannot affect
    Python (a systemd unit comment, say), not to get past a real failure.

.PARAMETER Cockpit
    Force a cockpit rebuild + upload even if cockpit/ did not change between
    the VM's old and new HEAD.

.PARAMETER Force
    Downgrade the preflight drift blocks to warnings. This will DISCARD
    uncommitted changes on the VM. Everything it discards is printed first.

.PARAMETER DryRun
    Run every check and print the deploy plan, but change nothing.

.EXAMPLE
    .\scripts\deploy-vm.ps1
    .\scripts\deploy-vm.ps1 -DryRun
    .\scripts\deploy-vm.ps1 -Cockpit
#>
[CmdletBinding()]
param(
    [string]$KeyPath    = "D:\Exodus_14_14\QuantOS\Oracle SSH\ssh-key-2026-07-14.key",
    [string]$RemoteHost = "ubuntu@161.118.189.29",
    [string]$RemoteRepo = "/home/ubuntu/quantos",
    [string]$WebRoot    = "/var/www/quantos-cockpit",
    [switch]$SkipTests,
    [switch]$Cockpit,
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ssh  = "C:\Program Files\Git\usr\bin\ssh.exe"
$scp  = "C:\Program Files\Git\usr\bin\scp.exe"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Tests that are known-failing for a reason unrelated to deployability, so a
# strict gate stays usable instead of being permanently red. Keep this list
# SHORT and always say why + what clears it. Anything not listed here that
# fails will block the deploy.
$KnownFailures = @(
    # Date-expired fixture, not a regression: asserts date(2026,7,21) is a
    # future NIFTY expiry, which stopped being true on 2026-07-22.
    # Remove this entry once the test is rewritten against a relative date.
    "tests/unit/test_fyers_symbol_master.py::TestListExpiries::test_lists_only_future_or_today_expiries"
)

function Section($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Ok($text)      { Write-Host "  [ok]   $text" -ForegroundColor Green }
function Warn($text)    { Write-Host "  [warn] $text" -ForegroundColor Yellow }
function Fail($text)    { throw $text }

# Remote commands are base64'd rather than passed as a plain string, for two
# PowerShell 5.1 reasons that both bit this script during development:
#   1. PS mangles/strips the double quotes when handing an argument to a native
#      exe, so a bash line like changed="$changed $n" arrived unquoted and bash
#      tried to EXECUTE the value as a command.
#   2. A native command writing to stderr becomes a terminating
#      NativeCommandError under $ErrorActionPreference='Stop', so an ordinary
#      warning on the far end would abort the deploy.
# base64 is [A-Za-z0-9+/=] only, so nothing survives for PS to mangle.
function Invoke-Remote([string]$cmd) {
    $b64  = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($cmd))
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $ssh -i $KeyPath -o StrictHostKeyChecking=accept-new $RemoteHost "echo $b64 | base64 -d | bash" 2>&1
    } finally {
        $ErrorActionPreference = $prev
    }
    return ($out | Out-String)
}

foreach ($exe in @($ssh, $scp)) {
    if (-not (Test-Path $exe)) { Fail "Not found: $exe  (install Git for Windows, or edit the path in this script)" }
}
if (-not (Test-Path $KeyPath)) { Fail "SSH key not found: $KeyPath" }

Push-Location $repo
try {
    # ─── 1. Preflight: local ──────────────────────────────────────────────
    Section "Preflight (local)"

    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    Write-Host "  branch: $branch"

    git fetch origin --quiet
    $localHead  = (git rev-parse HEAD).Trim()
    $remoteHead = (git rev-parse "origin/$branch" 2>$null)
    if ($LASTEXITCODE -ne 0) { Fail "Branch '$branch' has no origin counterpart. Push it first: git push -u origin $branch" }
    $remoteHead = $remoteHead.Trim()

    if ($localHead -ne $remoteHead) {
        $ahead = (git rev-list --count "origin/$branch..HEAD").Trim()
        if ($ahead -ne "0") {
            Fail "HEAD is $ahead commit(s) ahead of origin/$branch. The VM pulls from origin, so unpushed work cannot deploy. Run: git push origin $branch"
        }
        Fail "HEAD ($localHead) does not match origin/$branch ($remoteHead). Reconcile before deploying."
    }
    Ok "HEAD is pushed ($($localHead.Substring(0,7)))"

    # Dirty tracked files are a warning, not a block: they simply will not be
    # deployed, and blocking would make it impossible to deploy a hotfix while
    # unrelated work is in progress.
    $dirty = (git status --porcelain --untracked-files=no) | Where-Object { $_ -ne "" }
    if ($dirty) {
        Warn "$($dirty.Count) uncommitted tracked file(s) — these will NOT be deployed:"
        $dirty | ForEach-Object { Write-Host "         $_" -ForegroundColor DarkYellow }
    } else {
        Ok "working tree clean"
    }

    # ─── 2. Preflight: tests ──────────────────────────────────────────────
    Section "Preflight (tests)"
    if ($SkipTests) {
        Warn "-SkipTests set; unit suite not run"
    } else {
        $deselect = @()
        foreach ($t in $KnownFailures) { $deselect += "--deselect"; $deselect += $t }
        if ($KnownFailures.Count -gt 0) {
            Warn "$($KnownFailures.Count) known-failing test(s) deselected (see `$KnownFailures in this script)"
        }
        Write-Host "  running: python -m pytest tests/unit -q"
        & python -m pytest tests/unit -q -p no:warnings @deselect
        if ($LASTEXITCODE -ne 0) { Fail "Unit tests failed (exit $LASTEXITCODE). Fix them, or re-run with -SkipTests if genuinely unrelated." }
        Ok "unit suite passed"
    }

    # ─── 3. Preflight: VM ─────────────────────────────────────────────────
    Section "Preflight (VM)"

    $vmHeadBefore = (Invoke-Remote "cd $RemoteRepo && git rev-parse HEAD").Trim()
    Write-Host "  VM HEAD: $($vmHeadBefore.Substring(0,7))"
    if ($vmHeadBefore -eq $localHead) { Ok "VM already at target commit" }

    # What changed is measured from the last SUCCESSFULLY deployed commit, not
    # from the VM's git HEAD. They differ whenever a previous run died between
    # the pull and the restart -- which happened on 2026-08-11: the retry saw
    # HEAD already at target, concluded "no backend change", and skipped the
    # API restart, leaving freshly pulled code sitting unloaded on disk.
    $marker = "/home/ubuntu/.quantos/last_deployed_head"
    $lastDeployed = (Invoke-Remote "cat $marker 2>/dev/null || true").Trim()
    $unknownBaseline = $false
    if ($lastDeployed -match '^[0-9a-f]{40}$') {
        $baseRef = $lastDeployed
        if ($baseRef -ne $vmHeadBefore) {
            Warn "last successful deploy was $($baseRef.Substring(0,7)) but VM HEAD is $($vmHeadBefore.Substring(0,7)) - a previous run stopped mid-way; diffing from the deploy marker"
        }
    } else {
        $baseRef = $vmHeadBefore
        $unknownBaseline = $true
        Warn "no deploy marker yet - restarting the API regardless, since what is loaded cannot be inferred"
    }

    # Uncommitted tracked changes on the VM are the real hazard: they are work
    # that exists nowhere else, and a pull would either conflict or bury it.
    $vmDirty = (Invoke-Remote "cd $RemoteRepo && git status --porcelain --untracked-files=no").Trim()
    if ($vmDirty) {
        Write-Host "  VM has uncommitted tracked changes:" -ForegroundColor Yellow
        $vmDirty -split "`n" | ForEach-Object { Write-Host "         $_" -ForegroundColor DarkYellow }
        if (-not $Force) {
            Fail "VM working tree is dirty. Inspect and reconcile (they may be edits made directly on the box), then re-run. -Force discards them."
        }
        Warn "-Force set; these VM changes will be DISCARDED"
    } else {
        Ok "VM working tree clean"
    }

    # Untracked files that the incoming commits also add would abort the pull.
    $vmBlockers = (Invoke-Remote "cd $RemoteRepo && git fetch origin --quiet && git merge-tree --name-only HEAD origin/$branch >/dev/null 2>&1; git ls-files --others --exclude-standard").Trim()
    # Membership test against one tree listing rather than a git cat-file per
    # file: cat-file writes to stderr for a miss, and in PowerShell 5.1 a
    # native command's stderr becomes a terminating NativeCommandError under
    # $ErrorActionPreference='Stop' -- a normal "not found" would abort the run.
    $trackedAtHead = New-Object System.Collections.Generic.HashSet[string]
    foreach ($t in (git ls-tree -r --name-only $localHead)) {
        if ($t) { [void]$trackedAtHead.Add($t.Trim()) }
    }
    $collisions = @()
    if ($vmBlockers) {
        foreach ($f in ($vmBlockers -split "`n")) {
            $f = $f.Trim()
            if ($f -eq "") { continue }
            if ($trackedAtHead.Contains($f)) { $collisions += $f }
        }
    }
    if ($collisions.Count -gt 0) {
        Write-Host "  Untracked VM files that the target commit also adds:" -ForegroundColor Yellow
        $collisions | ForEach-Object { Write-Host "         $_" -ForegroundColor DarkYellow }
        if (-not $Force) {
            Fail "These would abort the pull. Confirm they are identical to the committed versions, remove them on the VM, then re-run. -Force removes them."
        }
        Warn "-Force set; these untracked VM files will be REMOVED"
    } else {
        Ok "no untracked-file collisions"
    }

    if ($DryRun) {
        Section "Dry run"
        Write-Host "  would deploy $($vmHeadBefore.Substring(0,7)) -> $($localHead.Substring(0,7))"
        Write-Host "  no changes made."
        return
    }

    # ─── 4. Deploy: code ──────────────────────────────────────────────────
    Section "Deploy"

    if ($Force -and ($vmDirty -or $collisions.Count -gt 0)) {
        Write-Host "  discarding VM drift (-Force) ..."
        $backup = "/home/ubuntu/vm-local-backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
        $backupCmd = @'
set -e
cd __REPO__
mkdir -p __BACKUP__
git diff > __BACKUP__/uncommitted.patch 2>/dev/null || true
git checkout -- .
'@
        Invoke-Remote ($backupCmd.Replace("__REPO__", $RemoteRepo).Replace("__BACKUP__", $backup)) | Out-Null
        foreach ($f in $collisions) {
            $moveCmd = @'
cd __REPO__ && mkdir -p "__BACKUP__/$(dirname __FILE__)" && cp "__FILE__" "__BACKUP__/__FILE__" && rm -f "__FILE__"
'@
            Invoke-Remote ($moveCmd.Replace("__REPO__", $RemoteRepo).Replace("__BACKUP__", $backup).Replace("__FILE__", $f)) | Out-Null
        }
        Ok "VM drift backed up to $backup and discarded"
    }

    $pull = Invoke-Remote "cd $RemoteRepo && git pull --ff-only origin $branch 2>&1"
    if ($pull -match "error:|CONFLICT|Aborting") { Write-Host $pull -ForegroundColor Red; Fail "git pull failed on the VM." }
    $vmHeadAfter = (Invoke-Remote "cd $RemoteRepo && git rev-parse HEAD").Trim()
    if ($vmHeadAfter -ne $localHead) { Fail "VM HEAD is $vmHeadAfter after pull, expected $localHead." }
    Ok "VM at $($vmHeadAfter.Substring(0,7))"

    # ─── 5. Deploy: systemd units ─────────────────────────────────────────
    # Copied rather than symlinked so /etc/systemd/system stays the source of
    # truth systemd actually reads, and drift is detectable with a plain diff.
    # Single-quoted here-string + token replace, NOT PowerShell interpolation:
    # these scripts are full of $ and " that bash owns, and escaping them
    # through a double-quoted PS string is how this file first failed to parse.
    $unitSyncCmd = @'
cd __REPO__ && changed=''
for u in deploy/systemd/*; do
  n=$(basename "$u")
  if ! diff -q "$u" "/etc/systemd/system/$n" >/dev/null 2>&1; then
    sudo cp "$u" "/etc/systemd/system/$n" && changed="$changed $n"
  fi
done
if [ -n "$changed" ]; then sudo systemctl daemon-reload; echo "UNITS_CHANGED:$changed"; else echo "UNITS_CHANGED:"; fi
'@
    $unitSync = Invoke-Remote ($unitSyncCmd.Replace("__REPO__", $RemoteRepo))
    $unitsChanged = ""
    if ($unitSync -match "UNITS_CHANGED:(.*)") { $unitsChanged = $Matches[1].Trim() }
    if ($unitsChanged) { Ok "units updated + daemon-reload: $unitsChanged" } else { Ok "systemd units already in sync" }

    # ─── 6. Deploy: restart the API only when it needs it ─────────────────
    $apiTouched = $unknownBaseline
    if ($baseRef -ne $vmHeadAfter) {
        git diff --quiet $baseRef $vmHeadAfter -- cloud/ core/
        if ($LASTEXITCODE -ne 0) { $apiTouched = $true }
    }
    if ($unitsChanged -match "quantos-cloud-api") { $apiTouched = $true }

    if ($apiTouched) {
        # Poll for readiness rather than sleeping a fixed interval: uvicorn on
        # this 1 GB box took 8s to finish startup on 2026-08-11, and a sleep 4
        # made the verify step report a spurious 000 on a perfectly healthy API.
        $restartCmd = @'
sudo systemctl restart quantos-cloud-api
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' localhost:8000/health 2>/dev/null)
  if [ "$code" = "200" ]; then echo "READY_AFTER:${i}s"; exit 0; fi
  sleep 1
done
echo "NOT_READY"
'@
        $restart = Invoke-Remote $restartCmd
        if ($restart -match "NOT_READY") { Fail "quantos-cloud-api did not answer /health within 30s of restart. Check: journalctl -u quantos-cloud-api -n 50" }
        $waited = ""
        if ($restart -match "READY_AFTER:(\S+)") { $waited = " (ready in $($Matches[1]))" }
        Ok "quantos-cloud-api restarted$waited"
    } else {
        Ok "quantos-cloud-api left running (no backend change)"
    }

    # ─── 7. Deploy: cockpit ───────────────────────────────────────────────
    # Built HERE, never on the VM: the box has no node/npm, and only ~500 MB
    # free — this project has already OOM-killed itself once (2026-07-15).
    $cockpitTouched = $Cockpit.IsPresent
    if (-not $cockpitTouched -and $baseRef -ne $vmHeadAfter) {
        git diff --quiet $baseRef $vmHeadAfter -- cockpit/
        if ($LASTEXITCODE -ne 0) { $cockpitTouched = $true }
    }

    if ($cockpitTouched) {
        Write-Host "  building cockpit locally ..."
        & npm --prefix cockpit run build
        if ($LASTEXITCODE -ne 0) { Fail "cockpit build failed (exit $LASTEXITCODE)" }

        $dist = Join-Path $repo "cockpit\dist"
        if (-not (Test-Path (Join-Path $dist "index.html"))) { Fail "No cockpit/dist/index.html after build." }

        # Copy the DIRECTORY, not "$dist\*": scp comes from Git for Windows and
        # does not glob a Windows path, so the wildcard arrives literally and it
        # fails with `stat local ...\dist\*: No such file or directory`. With no
        # pre-existing /tmp/quantos-dist, scp -r creates it as a copy of dist.
        Invoke-Remote "rm -rf /tmp/quantos-dist" | Out-Null
        & $scp -i $KeyPath -r -o StrictHostKeyChecking=accept-new "$dist" "${RemoteHost}:/tmp/quantos-dist"
        if ($LASTEXITCODE -ne 0) { Fail "scp of cockpit dist failed (exit $LASTEXITCODE)" }

        $landed = (Invoke-Remote "test -f /tmp/quantos-dist/index.html && echo OK || echo MISSING").Trim()
        if ($landed -notmatch "OK") { Fail "cockpit dist did not land on the VM (no index.html in /tmp/quantos-dist)." }

        # rm the old assets/ first: filenames are content-hashed, so copying
        # over the top accumulates every past build forever.
        Invoke-Remote "sudo rm -rf $WebRoot/assets && sudo cp -r /tmp/quantos-dist/. $WebRoot/ && sudo chown -R www-data:www-data $WebRoot && rm -rf /tmp/quantos-dist" | Out-Null
        Ok "cockpit rebuilt and published to $WebRoot"
    } else {
        Ok "cockpit unchanged (not rebuilt)"
    }

    # ─── 8. Verify ────────────────────────────────────────────────────────
    Section "Verify"

    $driftCmd = @'
cd __REPO__ && for u in deploy/systemd/*; do
  n=$(basename "$u")
  diff -q "$u" "/etc/systemd/system/$n" >/dev/null 2>&1 || echo "DRIFT $n"
done
'@
    $drift = (Invoke-Remote ($driftCmd.Replace("__REPO__", $RemoteRepo))).Trim()
    if ($drift) { Write-Host $drift -ForegroundColor Red; Fail "systemd units still differ from the repo after sync." }
    Ok "all systemd units match the repo"

    $apiState = (Invoke-Remote "systemctl is-active quantos-cloud-api").Trim()
    if ($apiState -ne "active") { Fail "quantos-cloud-api is '$apiState', expected active." }
    $health = (Invoke-Remote "curl -s -o /dev/null -w '%{http_code}' localhost:8000/health").Trim()
    if ($health -ne "200") { Fail "GET /health returned $health, expected 200." }
    Ok "cloud API active, /health 200"

    # python one-liner uses single quotes internally so nothing needs escaping.
    $slotsCmd = @'
for s in alpha50 nifty200momentum30 nifty500; do
  n=$(curl -s "localhost:8000/discovery/momentum-shortlist/$s" | python3 -c "import sys,json;print(len(json.load(sys.stdin).get('entries',[])))" 2>/dev/null)
  echo "$s=$n"
done
'@
    $slots = (Invoke-Remote $slotsCmd).Trim()
    $slotLine = ($slots -split "`n" | ForEach-Object { $_.Trim() }) -join "  "
    Write-Host "  shortlist slots: $slotLine"
    if ($slots -match "=0\b") {
        Warn "a shortlist slot is empty — it repopulates on the next Fyers token refresh (quantos-token-refreshed.path), or force one now:"
        Write-Host "         ssh ... 'rm -f ~/.quantos/last_shortlist_run && sudo systemctl start quantos-momentum-shortlist.service'" -ForegroundColor DarkYellow
    } else {
        Ok "all three shortlist slots served"
    }

    # Marker advances only here, after every verification has passed, so a run
    # that dies earlier leaves the previous value and the next run re-does the
    # work rather than assuming it landed.
    Invoke-Remote "mkdir -p /home/ubuntu/.quantos && printf '%s' '$vmHeadAfter' > $marker" | Out-Null

    Section "Done"
    Write-Host "  $($baseRef.Substring(0,7)) -> $($vmHeadAfter.Substring(0,7)) on $RemoteHost" -ForegroundColor Green
}
finally {
    Pop-Location
}
