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
| `CLOUD_API_SECRET` | Shared secret for `/signals*` — must match `agent/config.yaml`'s `cloud.api_secret` | Any strong random string |
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

1. In TradingView → Alert → **Webhook URL**: `https://your-app.railway.app/webhook/tradingview`
2. Alert message (JSON):
```json
{
  "symbol":           "{{ticker}}",
  "action":           "{{strategy.order.action}}",
  "price":            {{close}},
  "timeframe":        "{{interval}}",
  "strategy":         "darvas_breakout",
  "confluence_score": {{plot_0}},
  "stop_loss":        {{plot_1}},
  "secret":           "YOUR_WEBHOOK_SECRET"
}
```
3. `YOUR_WEBHOOK_SECRET` must match `WEBHOOK_SECRET` in Railway variables.

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
