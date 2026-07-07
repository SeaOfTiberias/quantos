# QuantOS — Deployment Runbook

## Overview

```
GitHub (SeaOfTiberias/quantos)
       │
       │  push to main
       ▼
Railway (auto-deploy)
  ├── Cloud API  (FastAPI, always-on)
  └── Postgres   (Sprint 2)

Local Agent (your machine / Raspberry Pi)
  ├── agent/main.py        — order execution proxy
  └── deploy/monitor.py   — uptime watchdog
```

---

## Step 1 — Deploy to Railway

### 1a. Create Railway project

1. Go to **railway.app** → **New Project** → **Deploy from GitHub repo**
2. Authorise Railway to access `SeaOfTiberias/quantos`
3. Select the `quantos` repo → Railway auto-detects `railway.json`

### 1b. Set environment variables

In Railway → your service → **Variables**, add every variable from `deploy/railway_env.md`.

The minimum set to get started:
```
ANTHROPIC_API_KEY   = sk-ant-...
WEBHOOK_SECRET      = (generate a strong random string)
CALLMEBOT_PHONE     = +917xxxxxxxxx
CALLMEBOT_API_KEY   = (from CallMeBot setup)
```

### 1c. Deploy

Railway deploys automatically on every push to `main`.
Manual deploy: Railway dashboard → **Deploy** button.

### 1d. Verify

```bash
curl https://YOUR-APP.railway.app/health
# → {"status": "ok", "version": "1.0.0", ...}

curl https://YOUR-APP.railway.app/status
# → full operational status including config checks
```

---

## Step 2 — Run Local Agent

```bash
# 1. Clone repo (if not already done)
git clone https://github.com/SeaOfTiberias/quantos.git
cd quantos

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and edit config
cp agent/config.yaml.example agent/config.yaml
# Edit agent/config.yaml — add broker keys, set cloud.api_url

# 4. Copy .env
cp .env.example .env
# Edit .env — add CALLMEBOT_PHONE, CALLMEBOT_API_KEY

# 5. Run agent
python agent/main.py
```

To enable the two-stage Darvas discovery pipeline (Stage A daily scan + Stage
B intraday timing — ADR-07), set `cloud.webhook_secret` in `agent/config.yaml`
to match Railway's `WEBHOOK_SECRET`, review `agent/universe.txt`, then flip
`scanner.enabled: true`. It's `false` by default since it's a new live-signal
source.

---

## Step 2b — Run Cockpit Dashboard

```bash
cd cockpit
npm install
cp .env.example .env   # set VITE_CLOUD_API_URL if it differs from the default
npm run dev            # http://localhost:5173
```

Only the **Discovery Watchlist** panel reads real data (from
`GET /discovery/watchlist`, populated by the local agent's Stage A/B sync —
see Step 2 above); everything else is still mock data. `npm run build`
produces a static `dist/` bundle you can host anywhere (Railway static site,
Netlify, Vercel, etc.) — it isn't currently part of the Railway deploy in
Step 1.

Keep `cockpit/` dependencies current — `npm audit` periodically, since Vite's
dev server has had several real CVEs (arbitrary-origin requests to the dev
server, `server.fs.deny` bypass on Windows). Pin to the latest patch within
whatever major version you're on; run `npm audit` after any `package.json`
change and treat non-zero output as a blocker, not a formality.

---

## Step 3 — Run Uptime Monitor

Run this alongside the agent (separate terminal or as a background process):

```bash
python deploy/monitor.py \
  --url https://YOUR-APP.railway.app \
  --phone +917xxxxxxxxx \
  --api-key YOUR_CALLMEBOT_KEY
```

Or with environment variables:
```bash
export QUANTOS_API_URL=https://YOUR-APP.railway.app
export CALLMEBOT_PHONE=+917xxxxxxxxx
export CALLMEBOT_API_KEY=YOUR_KEY
python deploy/monitor.py
```

You'll receive a WhatsApp alert if the API goes down, and an all-clear when it recovers.

---

## Step 4 — Configure TradingView

See `deploy/railway_env.md` for the exact Pine Script alert JSON template and TradingView webhook setup steps.

---

## Ongoing Operations

### View logs
```bash
# Railway CLI
railway logs --tail

# Or in Railway dashboard → your service → Logs
```

### Redeploy after code changes
```bash
git push origin main
# Railway auto-deploys within ~2 minutes
```

### Environment variable changes
Update in Railway dashboard → Variables → **Redeploy** (Railway restarts the service automatically).

### Check regime cache status
```bash
curl https://YOUR-APP.railway.app/status
# Look for regime_cache_age_seconds in response (Sprint 2 — adds this field)
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/health` returns 502 | App crashed on startup | Check Railway logs for import errors |
| Webhook returns 401 | Wrong `secret` in TV alert | Match `WEBHOOK_SECRET` env var exactly |
| WhatsApp not received | CallMeBot not configured | Check `CALLMEBOT_PHONE` and `CALLMEBOT_API_KEY` |
| `confidence_score: null` | `ANTHROPIC_API_KEY` missing | Add key in Railway Variables |
| Signal status `REJECTED_LOW_CONFLUENCE` | TV alert score too low | Lower `MIN_CONFLUENCE_SCORE` or tune Pine Script |
| Signal status `REJECTED_DUPLICATE` | Another source (Pine Script or the internal scanner) already fired for that symbol today | Expected behavior (ADR-07 dedup guard) — check `/signals` for the original |
| Cockpit Discovery Watchlist shows "offline" | Cloud API unreachable, or `/discovery/watchlist` 404s on an older deployed backend | Redeploy cloud API with the discovery routes; confirm `VITE_CLOUD_API_URL` in `cockpit/.env` |
| Discovery Watchlist never populates | Agent's `scanner.enabled` is `false` (the default), or `cloud.webhook_secret` unset | Set both in `agent/config.yaml`, restart the agent |

---

## Railway Free Tier Notes

Railway's free tier provides $5 of compute/month — sufficient for development and paper trading.
The QuantOS API uses ~0.1 vCPU at idle and ~0.3 vCPU when processing signals.
Estimated monthly cost at NSE market hours (6.25 hrs/day): **~$2–3/month** on the Hobby plan.

For production, upgrade to Railway's **Pro plan** ($20/month) for guaranteed uptime SLAs.
