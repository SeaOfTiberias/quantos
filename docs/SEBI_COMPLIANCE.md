# S5-7 Spike — SEBI retail algo-trading compliance

**Status:** ✅ **RESOLVED 2026-07-08 — QuantOS as-run (human-in-loop, Fyers API, ≪10 orders/sec) sits in the lightest-touch bucket and needs no exchange algo registration. Full auto-execute and any multi-user offering pull in materially more (detailed below).**
**Backlog item:** S5-7 (2 pts), `docs/SPRINT4_BACKLOG.md`.
**Governs:** ADR-05 (regulatory posture), ADR-01 (deployment/auto-execute gate), ADR-03/06 (multi-tenant SaaS path).
**Reviewed:** 2026-07-08. Re-review when SEBI/NSE publish the >10 OPS approval mechanism, or before enabling auto-execute or onboarding a second user.

> ⚠️ Engineering compliance summary, **not legal advice.** ADR-05 already
> requires a formal legal review before any external customer launch — this
> doc scopes that review, it does not replace it.

## The regime we're under

SEBI circular **SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013, dated 4 Feb 2025**
("Safer participation of retail investors in Algorithmic trading") created a
formal framework for retail API/algo trading. Implementation was extended twice
(Apr 2025 standards extension; Jul 2025 go-live moved to 1 Oct 2025 with a
glide path). It is **fully and legally binding on all brokers from 1 April
2026** — i.e. it is live now. Fyers has implemented it against our account
already (this is the "new app + static-IP whitelist" step the project hit).

## The one threshold that decides everything: 10 OPS

The framework hinges on a single number — **10 orders per second (OPS), per
exchange, per client** (set in the NSE/BSE Implementation Standards):

| Order flow to the broker API | Treatment |
|---|---|
| **≤ 10 OPS** (self-developed, own account) | **No exchange algo registration.** Only requirement is a static IP dedicated to the API key. Orders carry a **generic** algo tag. |
| **> 10 OPS** | Algo must be **registered with the exchange** (approval mechanism TBD, expected ≈ institutional-algo process). Orders carry a **unique** algo ID. |

**QuantOS runs far below this.** It is a swing/Darvas system: a handful of
signals per day, each gated behind a human Telegram/WhatsApp confirmation
(ADR-05). Peak order rate is effectively one manual order at a time — orders of
magnitude under 10 OPS. We are firmly in the top row.

## What QuantOS must satisfy today (and already does / can)

Even in the lightest bucket, the broker-enforced controls apply to every API
order. These are non-negotiable and Fyers rejects violations at the gateway:

1. **Registered App ID ↔ whitelisted static IP.** Fyers accepts orders **only**
   from a registered App ID mapped to a whitelisted static IP ("one app, one
   IP"). ✅ Already done (the registration step noted above). **Action:** the
   local agent (ADR-01) must run from that fixed IP; document it in the runbook
   and re-whitelist if the agent host/IP ever changes.
2. **Daily 2FA, no perpetual sessions.** 2FA must be completed once per trading
   day; continuous refresh-token sessions are no longer supported. **Action:**
   the agent's Fyers auth already requires a daily `auth_code` exchange
   (`agent/auth/fyers_auth.py` — its own docstring notes "Fyers tokens expire
   daily… re-run whenever the token expires, typically once per day"), which
   matches this rule. No perpetual-session code path exists.
3. **Order-rate ceiling 10 OPS / market orders → MPP.** Fyers caps at 10
   orders/sec and auto-converts market orders to Market-Price-Protection
   orders. **Action:** none required (we're nowhere near the cap); note that
   market-order fills may differ slightly from a naive market assumption — the
   S5-1 cost model already treats realized fills as the source of truth.
4. **Algo tagging.** All API orders are tagged (generic ID for us) by the
   broker for audit trail. **Action:** none — broker-side.
5. **Indian-hosted execution.** Retail algos must be hosted on Indian servers.
   **Action:** the *order-placing* process is the local agent on the user's own
   machine in India (ADR-01), which satisfies this. The Railway-hosted cloud
   core does **not** place orders (it only classifies/advises), so its hosting
   location is out of scope for this rule — but see the SaaS note below.

## What FULL auto-execution would ADDITIONALLY require

Removing the human-in-loop confirmation (ADR-05's opt-in auto-execute) does
**not** by itself cross the 10 OPS line, so it does **not** automatically force
exchange algo registration *for the user's own account*. But it changes the
risk/compliance posture enough that the following become live obligations:

- **Static-IP discipline becomes safety-critical, not just onboarding.** With a
  human in the loop, a wrong IP just means a rejected order the user notices.
  Fully automated, a silent auth/IP failure means missed or duplicated orders
  with no human catch. Needs the S4-2 kill-switch + S5-6 dead-man heartbeat
  proven before this is enabled.
- **Broker liability / RMS.** The broker remains liable for all API orders and
  can terminate a "rogue" algo. Auto-execute must respect broker RMS limits and
  our own kill switch so we are never the rogue algo that gets terminated.
- **Legal review (ADR-05).** Mandatory before flipping auto-execute on, even
  for a single self-account user.
- **If order frequency ever design-changes above 10 OPS** (it won't for Darvas,
  but would for any future HFT-style strategy): exchange algo **registration**
  becomes mandatory, orders switch to unique-ID tagging, and the exchange
  approval process applies.

## What OFFERING QuantOS TO OTHERS would require (ADR-03/06 SaaS path)

This is the big regulatory step-up and is **out of scope for single-user use**,
but flagged so the SaaS roadmap prices it in:

- **Self-developed algos may be used only within "family"** (self, spouse,
  dependent children/parents), shared via 2FA-verified consent. Running signals
  for **any** non-family user takes QuantOS out of the retail self-algo
  exemption entirely.
- **Providing/selling algo strategies to others → vendor/provider regime:** the
  provider must be **empanelled with the exchange** and **register every algo
  regardless of order frequency** (the 10 OPS exemption does not apply to
  vendors). Distributing strategies commercially may additionally require
  **SEBI Research Analyst** registration.
- **Third-party platforms must be empanelled and hosted within the broker's
  infrastructure** to place orders — directly relevant if the cloud core ever
  becomes the order path in the v2 SaaS model (ADR-01 v2).

**Implication for the roadmap:** the ADR-06 "Pro/Enterprise" tiers that place
orders for paying users are gated behind exchange empanelment + per-algo
registration (+ likely RA registration), not just the SOC2/track-record trigger
in ADR-01. Keep the v1 model strictly **single-user, own-account, family-only,
human-in-loop** until that regulatory work is funded.

## Bottom line

| Mode | Exchange algo registration? | Gating requirements |
|---|---|---|
| **QuantOS today** (human-in-loop, own account, ≤10 OPS) | **No** | App-ID↔static-IP, daily 2FA, Indian-hosted agent — all met/near-met |
| **Auto-execute, own account, ≤10 OPS** | No | + legal review (ADR-05), proven kill-switch/dead-man, RMS discipline |
| **> 10 OPS** (not our strategy profile) | **Yes** | Exchange algo registration + unique-ID tagging |
| **Serving non-family / paying users** | **Yes** (per-algo) | Vendor empanelment + per-algo registration + likely SEBI RA registration |

## Sources

- SEBI, *Safer participation of retail investors in Algorithmic trading*, Circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013, 4 Feb 2025 — https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html
- SEBI, *Extension of timeline for implementation…* (go-live → 1 Oct 2025, glide path to 1 Apr 2026), Sep 2025 — https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html
- Zerodha Z-Connect, *A comprehensive overview of NSE's circular on the new retail algo trading framework* (10 OPS threshold, generic vs unique tagging, static-IP-per-key, vendor empanelment) — https://zerodha.com/z-connect/general/a-comprehensive-overview-of-nses-circular-on-the-new-retail-algo-trading-framework
- Fyers, *New SEBI Framework for Retail Algo Trading from April 01, 2026* (App-ID↔static-IP, daily 2FA, 10 orders/sec cap, market→MPP conversion, empanelled-platform requirement) — https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/
- Fyers Support, *What are the new SEBI rules for retail algo trading from April 01, 2026?* — https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026
