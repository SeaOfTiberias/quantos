# QuantOS — Cloud API Environment Variables (self-hosted on the Oracle VM)

Superseded `deploy/railway_env.md` 2026-07-31 when the project moved off
Railway (trial expired) onto self-hosting `cloud/api` on the same Oracle
VM the trading agent already runs on (161.118.189.29). The variable names
are unchanged from Railway — only where they live changed.

## Where they live

`/home/ubuntu/quantos/.env.cloud-api` on the VM — **VM-only, never
committed** (matches this repo's standing convention: no secrets in git).
Loaded by `quantos-cloud-api.service` via `EnvironmentFile=`.

## Template

```
ANTHROPIC_API_KEY=
WEBHOOK_SECRET=
CLOUD_API_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_WEBHOOK_SECRET=
DATABASE_URL=sqlite:////home/ubuntu/quantos/data_cache/quantos_cloud.db
PUBLIC_API_URL=http://161.118.189.29
ENVIRONMENT=production
LOG_LEVEL=INFO
```

- `WEBHOOK_SECRET` / `CLOUD_API_SECRET` — must match `agent/config.yaml`'s
  `cloud.webhook_secret` / `cloud.api_secret` on this same VM (already set
  there; copy the values across rather than regenerating).
- `ANTHROPIC_API_KEY` / `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` /
  `TELEGRAM_WEBHOOK_SECRET` — only ever existed in Railway's dashboard.
  Grab them from there before that project becomes unreachable; there is
  no other recorded copy.
- `DATABASE_URL` — SQLite now, not Postgres (see `cloud/api/db.py`'s
  module docstring for why). 4 slashes = absolute path.
- `PUBLIC_API_URL` — used by `cloud/api/notifier.py` to self-register the
  Telegram webhook on startup. Plain HTTP, no domain yet (deliberate,
  see `deploy/nginx/quantos-cockpit.conf`'s comment).

## TradingView / external webhook URLs (changed)

Anywhere `https://web-production-b5527.up.railway.app` was pasted into an
external service's config, replace with `http://161.118.189.29`:

- TradingView alert → Webhook URL: `http://161.118.189.29/webhook/tradingview`
- Options webhook: `http://161.118.189.29/webhook/options`
- Telegram: re-registers itself automatically from `PUBLIC_API_URL` above
  on the next `quantos-cloud-api.service` boot — no manual step.

## Verifying

```
curl http://161.118.189.29/health                                  # public, no auth
curl -u quantos:PASSWORD http://161.118.189.29/status               # basic-auth gated now
curl -u quantos:PASSWORD "http://161.118.189.29/signals?limit=5"
```
