
agent/main.py blocks (it's a poll loop that runs until you Ctrl+C), so it and the cockpit need separate terminals, not sequential steps in one: 

Terminal 1:
python agent/auth/fyers_auth.py --config agent/config.yaml
python agent/main.py

Terminal 2 (while Terminal 1 keeps running):
cd cockpit
npm run dev

Then open http://localhost:5173


"update universe.txt" is optional, not a required daily step — only touch it if you want to add/remove symbols from the scan. Leave it alone otherwise.
Also make sure you run python agent/main.py from the repo root (quantos/), not from inside agent/ — it resolves agent/config.yaml and agent/universe.txt as relative paths from wherever you launch it.


Tomorrow's runbook
QuantOS Runbook — Tomorrow (2026-07-08)
1. Pre-market (before 9:15 AM IST)
a. Refresh the Fyers token — it expires daily, this is the #1 thing that will silently break everything else if skipped:

python agent/auth/fyers_auth.py --config agent/config.yaml
This opens a browser OAuth flow and writes ~/.quantos/fyers_token. If you skip this and the old token expired overnight, agent/main.py will fail immediately on broker.connect().

b. Verify Railway env vars match your local config — this is the one thing from today I flagged but never got you to confirm, and it fails silently (no error, signals just never get created):

Railway → your project → Variables: check WEBHOOK_SECRET equals the cloud.webhook_secret value in your local agent/config.yaml.
If WEBHOOK_SECRET is unset on Railway, the check is skipped entirely and Stage B signals sail through regardless — so this only bites you if it's set to something different than your local value, not if it's missing.
CLOUD_API_SECRET (Railway) vs cloud.api_secret (local) — this one's already proven working today (watchlist synced fine), no action needed.
c. Confirm today's Railway deploy is live — I pushed 4 commits today (6be6d1f→4f98e5d), each auto-deploys and restarts the dyno. The /discovery/watchlist store is in-memory on the cloud side, so it resets to empty on every deploy — not a problem, just means the cockpit will show nothing until the agent completes its first sync of the day.

2. Start the agent
python agent/main.py
Expected sequence:

Broker connects.
Stage A runs (today's marker is already set from yesterday's successful run, but that's per-calendar day, so tomorrow it runs automatically — no manual marker-clearing needed).
Full 247-symbol scan takes a few minutes (throttled to 2 concurrent + 429 retry). A handful of -300 Invalid symbol warnings are expected and harmless (delisted/bad tickers in universe.txt, not a bug).
Stage A complete: N candidate(s) queued for Stage B timing: ... — N should now be much smaller than yesterday's 130 (APPROACHING HOT/WARM only). If it's still huge, something regressed — send me the log line.
Agent settles into its normal 5-second poll loop.
3. Start the cockpit UI
cd cockpit
npm run dev
Open http://localhost:5173. The Discovery Watchlist panel polls /discovery/watchlist every 30s and will populate once the agent's Stage A sync lands (a minute or two after Stage A finishes, not instant). Every other panel on the cockpit still renders mock data — that's expected, not a bug, per README.md:96.

4. During market hours (9:15–15:30 IST)
Every 5 minutes (configurable via scanner.granular_scan_interval_minutes), Stage B re-scans the shortlist. Watch the agent terminal for [Stage B] Fired internal signal for <SYMBOL> — that means a signal was POSTed to /webhook/tradingview and you should get a Telegram confirm/skip prompt shortly after.
If a signal fires, respond in Telegram — nothing else to do, the rest of the pipeline (Claude analysis, event filter, order placement, SL_M stop, trailing) runs automatically once you confirm.
The cockpit's Discovery Watchlist panel should visibly update as tiers shift (WATCH → WARM → HOT) or symbols get removed after firing.
5. Shutdown
Ctrl+C the agent when you're done for the day (it manages open positions and trailing stops only while running — if you have open positions, don't stop it mid-session without a reason).
Ctrl+C the cockpit dev server, or just leave it running — it's stateless.