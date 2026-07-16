# QuantOS — Daily Runbook

**The agent runs on the Oracle VM, not your laptop** (since 2026-07-14). It is a
systemd service that survives reboots and crashes. The only thing that needs a
human every day is the Fyers token refresh — it expires daily and is interactive.

> Superseded: this used to document a laptop workflow (`python agent/main.py`,
> Ctrl+C to stop) plus a procedure for rebuilding the Fyers app whenever your ISP
> handed you a new IP. Both are gone. The VM's reserved static IP is whitelisted
> with Fyers permanently, so the 7-day IP-edit lock-in can't strand you again.

---

## 1. Daily pre-market (before 9:15 IST) — the only human step

```bash
# 1. SSH in
ssh -i "D:\Exodus_14_14\QuantOS\Oracle SSH\ssh-key-2026-07-14.key" ubuntu@161.118.189.29

# 2. Refresh the Fyers token (interactive: opens OAuth, you paste the auth code).
#    Expires daily. Skip this and the day is dead — the agent fails on connect().
cd ~/quantos && source .venv/bin/activate
python agent/auth/fyers_auth.py --config agent/config.yaml

# 3. Restart so it picks up the new token
sudo systemctl restart quantos-agent

# 4. Watch
journalctl -u quantos-agent -f
```

**The restart *is* the pre-market scan.** Stage A runs at agent startup, gated by
a per-calendar-day marker (`~/.quantos/last_discovery_scan.txt`) — not by market
hours. So the morning token-refresh-and-restart triggers the day's discovery.

⚠️ `ssh`/`scp` are not on plain PowerShell's PATH — they ship with Git at
`C:\Program Files\Git\usr\bin\`. Use the full path or Git Bash.

---

## 2. What a healthy startup looks like

| Log line | Meaning |
|---|---|
| `Fyers connected: <name>` | Broker up, token good |
| `Regime breadth universe: 500 symbols from agent/universe_nifty500.txt` | Breadth wired to its own universe (see §5) |
| `Stage A: scanning 500 symbols from ...` | Discovery started |
| `Stage A complete: N candidate(s) queued for Stage B` | N should be small — a shortlist, not a haystack |
| (then) 5-second poll loop | Steady state |

**Stage A takes ~4–8 minutes.** 500 symbols throttled to 2 concurrent (`max_concurrent`
in `core/darvas/weekly_discovery.py`) ≈ 250 sequential rounds. Not a hang.

A few `-300 Invalid symbol` warnings are normal and harmless — a Nifty 500
constituent may be suspended or renamed between rebalances.

---

## 3. During market hours (9:15–15:30 IST)

Stage B re-scans Stage A's shortlist every 5 minutes
(`scanner.granular_scan_interval_minutes`).

On `[Stage B] Fired internal signal for <SYMBOL>`, a Telegram confirm/skip prompt
should arrive within seconds. **Reply directly to that message** (swipe-to-reply,
not a new message) with `execute` or `skip` — the signal ID is parsed out of the
original alert's text, so a fresh message won't match.

Everything after your confirmation is automatic: Claude analysis, event-risk
filter, order placement, SL_M stop, trailing.

**If the log line fires but no Telegram prompt arrives**, the cloud rejected it.
Check Railway logs for `Rejected webhook — missing timestamp` (the replay guard,
`MAX_ALERT_AGE_SECONDS=120`). Capture both logs.

---

## 4. Shutdown / intervention

You don't normally stop it — it's a service. But:

```bash
sudo systemctl stop quantos-agent      # don't do this with open positions:
                                       # trailing stops are managed in-process
sudo systemctl status quantos-agent    # state, memory, restart count
journalctl -u quantos-agent -n 200     # recent history
```

Self-healing already in place: `Restart=on-failure`, a daily 16:00 IST restart
timer, and a 650 MB memory cap on the agent's cgroup.

---

## 5. Not-daily chores

### Universe — twice a year, at NSE's rebalance
`agent/universe_nifty500.txt` feeds **both** Stage A discovery
(`scanner.universe_file`) and the regime advance/decline sample
(`regime.breadth_universe_file`).

```bash
python scripts/build_universe.py "<path>/ind_nifty500list.csv" \
    agent/universe_nifty500.txt --index-name "Nifty 500"
.\scripts\push-universe.ps1
```

**Do not hand-edit it.** Two reasons, both learned the hard way:
- A Darvas track record over a hand-picked list measures your curation as much as
  the strategy, and can't be backtested against.
- The same file is the breadth sample, so editing it moves the regime gate. Until
  2026-07-16 these were one config key, which made breadth *non-stationary* —
  regime flipped when a text file was edited, not when the market moved.

They are now two keys pointing at one file, deliberately: tuning the hunting
ground must never silently move the gate that governs it.

### Config changes — remember the VM's config.yaml is gitignored
`agent/config.yaml` is **not in git** (`.gitignore:17`). A `git pull` on the VM
delivers code and universe files but **never** config. Any new config key must be
added on the VM by hand, or the agent silently falls back to its old behaviour.

---

## 6. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Agent fails immediately on start | Token expired — you skipped §1 step 2 |
| Stage B fires, no Telegram prompt | Cloud rejected the webhook (see §3) |
| Breadth counts sum to ~128, not ~500 | VM's `config.yaml` has no `regime:` block — it's falling back to the old universe (§5) |
| Breadth shows 0/0 or neutral | `get_quotes()` threw and was caught into the neutral fallback (by design — breadth is a signal, not a safety stop) |
| Cockpit Morning Shortlist empty | Railway restarted; the watchlist mirror is in-memory and isn't re-pushed until the next Stage A |
| SSH dark + agent gone | Possible OOM (see §7) |

### Verifying regime breadth is live
`GET <cloud>/regime/status` → `advance_count` + `decline_count` non-zero, summing
to roughly 500 (≥ 20 is the `MIN_BREADTH_SAMPLE` floor below which it degrades to
neutral). Or the cockpit's Market Regime panel: `312 ▲ / 168 ▼ · A/D 1.86 · STRONG`.

---

## 7. Known-open: the OOM

On 2026-07-15 the agent OOM-killed itself twice, and the kernel's *global* OOM
killer took journald and snapd with it — SSH went dark both times. Three
mitigations shipped (cgroup memory cap, daily restart, Fyers SDK log
suppression), and both kills are confirmed to predate the cap going live.

**But the root cause is genuinely unknown.** The originally documented hypothesis
— Stage A firing hundreds of concurrent DataFrame builds — is *disproven*: the
scanner is throttled to `max_concurrent=2`. And Stage A's load just went from 247
to 500 symbols.

So: after a Stage A scan, check the high-water mark.

```bash
# Peak RSS is logged after every Stage A — grep it
journalctl -u quantos-agent | grep "peak RSS"

# Has the cgroup cap ever actually fired?
cat /sys/fs/cgroup/system.slice/quantos-agent.service/memory.events
```

`memory.events` all-zero means the cap is installed but has never been exercised —
it is not yet battle-tested. If `high` goes non-zero while the service stays up,
the cap is working as designed. If `oom_kill` goes non-zero and `NRestarts`
climbs, the mitigation needs a second look.
