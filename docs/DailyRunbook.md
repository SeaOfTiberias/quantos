
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

⚠️ 0. ONE-TIME (do this FIRST, before the token refresh): rebuild the Fyers app — ISP IP changed
The whitelisted IP on the current app can't be edited (Fyers enforces a 7-day
lock-in on IP changes), so trade tomorrow on a NEW app. Only two config lines
change; the auth flow is otherwise identical.

  0a. Find your CURRENT public IP: run `curl ifconfig.me` (or open whatismyipaddress.com). Note it.
  0b. Fyers API dashboard (https://myapi.fyers.in) → create a new app:
        - Permissions: match the old app (needs order placement + market data).
        - Redirect URI: reuse EXACTLY  https://trade.fyers.in/api-login/redirect-uri/index.html
          (fyers_auth.py's manual auth-code paste flow depends on this exact URI — reusing it = zero code change).
        - Whitelist IP: enter the public IP from 0a. (If the dashboard accepts a CIDR/range,
          whitelist your ISP subnet so a DHCP change within it doesn't lock you out again — check the field.)
  0c. Copy the new App ID + Secret. In agent/config.yaml (local, untracked) under `credentials:` replace
        api_key: <new App ID>   and   api_secret: <new Secret>   — leave redirect_uri unchanged.
  0d. Then do step 1a (token refresh) — it now authenticates against the new app and writes a fresh token.

  ‼️ Durable fix (schedule this — do NOT keep recreating apps): your ISP IP is dynamic and each app
  locks IP edits for 7 days, so if the IP changes again inside a week you're forced to make YET another
  app. Fix the root cause: (1) ask your ISP for a STATIC IP (usually a small monthly add-on) — cleanest;
  or (2) move the agent onto a small cloud VM with a fixed/Elastic IP (~₹400/mo) — since ADR-01 makes the
  agent the only process holding the broker connection, a fixed-IP box solves this permanently AND frees
  it from your laptop being on; or (3) a dedicated-IP VPN routing just Fyers traffic.

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

---

## One-time carryover verification — next market session (Sprint 5/6)

Two things landed in code but were never confirmed against a live, market-hours
agent. Do these once at the next open; after they pass, delete this section.

### A. Agent restart → S4-3 `timestamp` on Stage B signals  ⚠️ can silently zero out ALL signals

The cloud now **rejects any webhook missing `timestamp` with HTTP 400**
(`cloud/api/main.py` replay guard, MAX_ALERT_AGE_SECONDS=120). The agent's
internal Stage B POST already sends it (`agent/main.py:461`, `"timestamp":
time.time()`), so the code is correct — but **any agent process still running
from before that commit landed will have every Stage B signal 400-rejected by
the cloud.** Symptom: agent log says `[Stage B] Fired internal signal for X` but
**no Telegram confirm prompt ever arrives** (the cloud dropped it).

- **Fix:** just start the agent fresh today from repo root — it's the current
  `main` code, so a normal daily start resolves it. No special step.
- **Verify:** on the first Stage B fire of the day, a `[Stage B] Fired internal
  signal…` log line **must** be followed by a Telegram confirm/skip prompt
  within a few seconds. If the log line fires but no Telegram prompt comes,
  the signal was rejected — capture the agent log + check Railway logs for
  `Rejected webhook — missing timestamp` and send it to me.
- If no signal fires all day (quiet market), this stays unverified — that's
  fine, the code path is unit-tested; just re-check on the next firing day.

### B. S5-4 live breadth — `broker.get_quotes()` returns real advance/decline

S5-4 replaced the 250/250 neutral breadth placeholder with a live
advance/decline sample over the discovery universe. It's only exercised when the
market is open (quotes move), so it was never confirmed live.

- **When:** during market hours (9:15–15:30 IST), after the agent has run at
  least one regime refresh (every ~15 min, REGIME_CACHE_TTL).
- **Verify (cockpit):** the Market Regime panel should show a **Breadth** row
  with non-zero counts, e.g. `312 ▲ / 168 ▼ · A/D 1.86 · STRONG` — NOT absent
  and NOT 0/0.
- **Verify (API, equivalent):** `GET <cloud>/regime/status` → `advance_count`
  and `decline_count` are non-zero and their sum is ≥ 20 (MIN_BREADTH_SAMPLE).
- **If it shows neutral/0-0:** `get_quotes()` likely threw and was caught into
  the neutral fallback (by design — breadth is a signal, not a safety stop).
  Grep the agent log for the regime refresh around that time and send me the
  line; the usual suspects are a Fyers quote-endpoint field/paging mismatch or
  an empty breadth universe.