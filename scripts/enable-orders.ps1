<#
.SYNOPSIS
    Switch the VM's stage-2 orders on (live or paper) or off, without an editor on the VM.

.DESCRIPTION
    Run from PowerShell on this PC. It connects to the VM, backs up
    agent/config.yaml (config.yaml.bak-YYYYMMDD-HHMMSS), writes the
    `orders:` and `position_manager:` sections (replacing them if present),
    and prints what the VM now reads.

      -Mode live    orders go to ICICI Direct; position manager places exits
      -Mode paper   everything is journalled as paper, nothing is sent
      -Mode off     position manager back to alerts only, orders not live
      -Spreads auto     the spread watcher closes spreads itself on a CLOSE (short leg first)
      -Spreads alerts   the spread watcher back to alerts only
    -Spreads changes only `orders:` inside `spread_watcher:`, so its rule settings stay.

    The position manager reads this when it starts (09:15 IST), so a change
    during market hours applies from the next session. For an immediate stop
    at any time use the kill switch:  -Kill on  /  -Kill off

.EXAMPLE
    .\quantos\scripts\enable-orders.ps1 -Mode paper
    .\quantos\scripts\enable-orders.ps1 -Mode live
    .\quantos\scripts\enable-orders.ps1 -Spreads auto
    .\quantos\scripts\enable-orders.ps1 -Kill on
#>
param(
    [ValidateSet("live", "paper", "off")] [string]$Mode,
    [ValidateSet("on", "off")] [string]$Kill,
    [ValidateSet("auto", "alerts")] [string]$Spreads
)

$Vm = "ubuntu@161.118.189.29"
$Key = Join-Path $HOME ".ssh\oracle.key"

if (-not $Mode -and -not $Kill -and -not $Spreads) { Write-Host "Give -Mode live|paper|off, -Spreads auto|alerts or -Kill on|off"; exit 1 }

if ($Kill) {
    $cmd = if ($Kill -eq "on") { "touch ~/.quantos/ORDERS_OFF && echo 'kill switch ON: no orders will be sent'" }
           else { "rm -f ~/.quantos/ORDERS_OFF && echo 'kill switch OFF: orders allowed'" }
    ssh -i $Key $Vm $cmd
    if (-not $Mode -and -not $Spreads) { exit $LASTEXITCODE }
}

if ($Spreads) {
    $sp = @"
import re, shutil, time, yaml
p = 'agent/config.yaml'
shutil.copy(p, p + '.bak-' + time.strftime('%Y%m%d-%H%M%S'))
text = open(p).read()
m = re.search(r'(?ms)^spread_watcher:\n((?:[ \t#].*\n|\n)*)', text)
line = '  orders: $Spreads   # auto = close spreads on a CLOSE event, short leg first; alerts = Telegram only\n'
if m is None:
    text = text.rstrip('\n') + '\n\nspread_watcher:\n' + line
else:
    body = re.sub(r'(?m)^  orders:.*\n', '', m.group(1))
    text = text[:m.start(1)] + line + body + text[m.end(1):]
open(p, 'w').write(text)
print('spread_watcher:', yaml.safe_load(open(p))['spread_watcher'])
"@
    $sp | ssh -i $Key $Vm "cd ~/quantos && tr -d '\r' > /tmp/enable_spreads.py && .venv/bin/python /tmp/enable_spreads.py; rm -f /tmp/enable_spreads.py"
    if (-not $Mode) { exit $LASTEXITCODE }
}

$live = if ($Mode -eq "live") { "true" } else { "false" }
$pm = if ($Mode -eq "off") { "alerts" } else { "auto" }

$py = @"
import re, shutil, time, yaml
p = 'agent/config.yaml'
shutil.copy(p, p + '.bak-' + time.strftime('%Y%m%d-%H%M%S'))
text = open(p).read()
for sec in ('orders', 'position_manager'):
    text = re.sub(r'(?ms)^' + sec + r':\n(?:[ \t#].*\n|\n)*', '', text)
text = text.rstrip('\n') + '''

orders:
  # stage 2 (approved 2026-10-22 / 2026-10-24). Set by scripts/enable-orders.ps1.
  # live: false = journal as paper, send nothing. Kill switch: ~/.quantos/ORDERS_OFF
  live: $live
  accounts: [icici-spouse]
  max_lots: 4
  max_fut_notional: 1000000
  max_opt_premium: 50000

position_manager:
  # auto = place the exits (resting GTT OCO + 15:20 daily-close exit); alerts = Telegram only
  orders: $pm
'''
open(p, 'w').write(text)
c = yaml.safe_load(open(p))
print('orders:', c['orders'])
print('position_manager:', c['position_manager'])
"@

$py | ssh -i $Key $Vm "cd ~/quantos && tr -d '\r' > /tmp/enable_orders.py && .venv/bin/python /tmp/enable_orders.py; rm -f /tmp/enable_orders.py"
exit $LASTEXITCODE
