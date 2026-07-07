# QuantOS — Railway Environment Variables

Set these in the Railway dashboard under your service → **Variables**.

---

## Required

| Variable | Description | Example |
|---|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key | `sk-ant-...` |
| `WEBHOOK_SECRET` | Secret shared with TradingView | Any strong random string |
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather | `123456:ABC-...` |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | `895737628` |
| `CLOUD_API_SECRET` | Shared secret for `/signals*` and `POST /discovery/watchlist` — must match `agent/config.yaml`'s `cloud.api_secret` | Any strong random string |
| `TELEGRAM_WEBHOOK_SECRET` | Validates inbound Telegram updates on `/webhook/telegram` (echoed back as a header) | Any strong random string |

## Recommended

| Variable | Default | Description |
|---|---|---|
| `MIN_CONFLUENCE_SCORE` | `70` | Minimum Darvas confluence to pass Claude |
| `REGIME_CACHE_TTL` | `900` | Regime cache duration in seconds (15 min) |
| `PUBLIC_API_URL` | Railway URL | Used to self-register the Telegram webhook on startup |
| `ENVIRONMENT` | `production` | `development` or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Optional (Sprint 2+)

| Variable | Description |
|---|---|
| `DATABASE_URL` | Postgres URL (Railway provides this if you add a Postgres plugin) |
| `DEFAULT_USER_ID` | User ID for single-tenant mode (multi-tenant in v2) |
| `QUANTOS_API_URL` | Your Railway deployment URL (used by monitor.py) |

---

## Railway Postgres (Sprint 2)

1. In Railway dashboard → **New** → **Database** → **PostgreSQL**
2. Railway auto-injects `DATABASE_URL` into your service
3. Run migrations: `railway run alembic upgrade head`

---

## TradingView Webhook Setup

Use `pine/darvas_breakout_alert.pine` — it computes a real multi-timeframe
confluence score (15m/1h/1D, mirrors `core/darvas/box.py`) and fires the
webhook itself via Pine's `alert()` function, since that dynamic JSON body
can't be expressed with TradingView's static `{{plot_N}}` message template.

1. Paste `pine/darvas_breakout_alert.pine` into TradingView's Pine Editor,
   add it to any chart (works on any chart timeframe — it always pulls
   15m/1h/1D internally via `request.security()`).
2. In its settings, paste your webhook secret into the "Webhook Secret" input.
3. Create an alert on it: **Condition** → this indicator → *Any alert() function
   call*. **Webhook URL**: `https://your-app.railway.app/webhook/tradingview`.
   The Message field is ignored — the script supplies the JSON body directly.
4. The secret pasted into the script must match `WEBHOOK_SECRET` in Railway variables.

---

## Discovery Watchlist Sync (ADR-07/08)

No new Railway variable needed — `POST /discovery/watchlist` reuses
`CLOUD_API_SECRET` above. The local agent pushes to it after every Stage A
scan and Stage B fire; `GET /discovery/watchlist` (read by the cockpit) is
intentionally unauthenticated (see ADR-08 for why). Note the *agent-side*
config field for the webhook itself is `cloud.webhook_secret` in
`agent/config.yaml` — matched against `WEBHOOK_SECRET` above, not
`CLOUD_API_SECRET` (same "same value, different names" gotcha as
`cloud.api_secret`/`CLOUD_API_SECRET`).

```bash
curl https://your-app.railway.app/discovery/watchlist
# → {"entries": [...], "updated_at": "2026-07-06T...Z"}
```

---

## Telegram Webhook (human-in-loop confirm/skip — ADR-05)

No manual setup needed — the app calls Telegram's `setWebhook` on every
startup (`register_telegram_webhook()` in `cloud/api/notifier.py`), pointing
it at `{PUBLIC_API_URL}/webhook/telegram`. Just make sure `TELEGRAM_BOT_TOKEN`
is set; deploy logs will show `Telegram webhook registered: ...` on boot.

Reply **directly** (swipe-to-reply, not a new message) to a signal alert
with `execute` or `skip` — the signal ID is parsed out of the original
alert's text, so the reply must target that specific message.

---

## Verify deployment

```bash
# Health check
curl https://your-app.railway.app/health

# Operational status
curl https://your-app.railway.app/status

# Test webhook (replace URL and secret)
curl -X POST https://your-app.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "RELIANCE",
    "action": "BUY",
    "price": 2950.00,
    "timeframe": "1h",
    "strategy": "darvas_breakout",
    "confluence_score": 85,
    "secret": "YOUR_WEBHOOK_SECRET"
  }'
```

Expected response:
```json
{
  "signal_id": "SIG-DARV-XXXXXXXX",
  "symbol": "RELIANCE",
  "action": "BUY",
  "status": "PENDING_CONFIRMATION",
  "confidence_score": 78.5,
  "message": "Signal pending WhatsApp confirmation"
}
```
