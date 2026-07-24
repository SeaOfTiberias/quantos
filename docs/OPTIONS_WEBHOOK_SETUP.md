# TradingView-Driven Options Webhook — Setup

Added 2026-07-25 to replace the killed regime-gated AI suggestion (see
`core/options/recommender.py`'s module docstring for why that was removed).
Your TradingView chart decides *when* and *what* — QuantOS handles the
mechanical part: real option chain analysis, real Greeks, safe multi-leg
order placement, all behind the same Telegram confirm gate every other
order in this system uses (entries only — exits fire immediately, see
below).

## Why no custom Pine script is required

Unlike the Darvas alert (`pine/darvas_breakout_alert.pine`), this doesn't
need a custom indicator computing anything. TradingView's native **Create
Alert** dialog lets you set a literal JSON **Message** body on *any*
condition you build — a price cross, a drawing tool alert, or your own
Pine `strategy.exit(trail_points=..., trail_offset=...)` logic for a
trailing stop. Point the alert's Webhook URL at this endpoint and paste
the JSON below as the Message. That's the whole setup.

## Entry alert

1. On your chart, build whatever condition represents your entry decision
   (a breakout, a level cross, a strategy backtested in Pine — your call).
2. **Create Alert** → Webhook URL:
   `https://web-production-b5527.up.railway.app/webhook/options`
3. Message body (exact JSON, edit `underlying`/`template`):
   ```json
   {
     "underlying": "NIFTY",
     "template": "bull_call_spread",
     "action": "open",
     "secret": "YOUR_WEBHOOK_SECRET",
     "timestamp": {{timenow}}
   }
   ```
   `{{timenow}}` is a TradingView placeholder — it fills in the alert's
   fire time automatically (epoch seconds), which is what the replay guard
   checks (rejects anything older than 120s by the time it's received).
4. `secret` — same `WEBHOOK_SECRET` value already configured for the
   Darvas alert (Railway env var, mirrored in your `agent/config.yaml`'s
   `cloud.webhook_secret`).
5. `template` — one of: `bull_call_spread`, `bear_put_spread`,
   `iron_condor`, `covered_call`, `cash_secured_put`, `debit_spread`,
   `short_strangle`. (`calendar_spread` is a defined template but has no
   builder implemented yet — don't use it.)

What happens next: the agent picks this up (polls every ~5s), fetches the
**real** live option chain for `underlying`, computes real legs/Greeks/
max-profit/max-loss/probability-of-profit for `template`, and sends you a
Telegram message to confirm — exactly like every other signal. Nothing
executes until you reply `execute`.

If a position is already open for that underlying, the alert is ignored
(logged, not queued) — at most one open options position per underlying
at a time.

## Exit alert (trailing stop)

Same webhook, `action: "close"` instead of `"open"`:
```json
{
  "underlying": "NIFTY",
  "template": "bull_call_spread",
  "action": "close",
  "secret": "YOUR_WEBHOOK_SECRET",
  "timestamp": {{timenow}}
}
```

Build your trailing-stop condition in Pine (`strategy.exit` with
`trail_points`/`trail_offset`, or your own high-watermark logic) and wire
its alert to this same message shape. **This fires immediately — no
Telegram confirm.** That's deliberate: a stop-loss is a risk-management
action, and waiting on a confirm-tap defeats the point of a trailing stop
(same precedent as the equity Darvas flow's `auto_exit`, which places its
stop order automatically too). You'll get a Telegram *notification* after
the fact, not a prompt.

`template` here is checked against the open position's actual strategy —
a mismatch still closes the position (there's only ever one open per
underlying) but logs a warning, so you'll see in the agent logs if an
exit alert fired that didn't match what you thought was open.

## What can go wrong

- **Wrong `underlying`/`template` spelling** → open alert silently ignored
  (unknown template) or fails at chain-fetch (bad underlying) — check
  `journalctl -u quantos-agent` on the VM if a confirm prompt doesn't
  arrive within a minute or so of the alert firing.
- **Queue is in-memory on the cloud API** → resets on every Railway
  redeploy (same as the regime/watchlist mirrors). An alert that fired
  right as a deploy landed is simply lost, not delayed — refire it.
- **Agent must be running** (`systemctl status quantos-agent` on the VM) —
  nothing processes the queue if it's stopped, same as every other agent
  feature.
