import { useState, useEffect, useMemo } from "react";

// ─── Design tokens (Bloomberg dark terminal aesthetic) ─────────────────────
const C = {
  bg:       "#0A0E1A",
  panel:    "#111827",
  panelAlt: "#1A2235",
  border:   "#1E3A5F",
  accent:   "#00D4FF",
  gold:     "#F59E0B",
  green:    "#10B981",
  red:      "#EF4444",
  purple:   "#8B5CF6",
  white:    "#F8FAFC",
  muted:    "#64748B",
  mid:      "#94A3B8",
};

// ─── Cloud API ──────────────────────────────────────────────────────────────
// Must match agent/config.yaml's cloud.api_url (the same Railway instance the
// local agent talks to). Override via cockpit/.env's VITE_CLOUD_API_URL — see
// .env.example. As of 2026-07-29: System Health, Regime, Signal Feed,
// Morning Shortlist, and the two Momentum Shortlist panels (Nifty Alpha 50 +
// Nifty200 Momentum 30 — formerly one Discovery Watchlist panel, retired,
// zero evidenced edge, see S7-3) are all wired to real cloud data (see
// per-panel comments below for each route). Open Positions, Alpha-vs-Nifty,
// and Claude Analyst were removed 2026-07-29 (dead placeholders or unused)
// to make room. Greeks still has no real feed — real backend
// (POST /options/greeks/panel) but no data pipeline yet syncs live options
// positions, so it renders an honest empty state instead of fabricated
// numbers.
// 2026-07-31: cloud API moved off Railway (trial expired) onto self-hosting
// on the same VM/origin nginx serves this SPA from -- default is now "" (same
// origin) rather than a hardcoded external URL, so it never goes stale if
// the VM's IP changes. .env.development.local overrides this for local dev
// against a standalone backend.
const CLOUD_API_URL = import.meta.env.VITE_CLOUD_API_URL || "";

// Fallback shown only until scripts/run_momentum_shortlist.py's first daily
// market-snapshot sync lands (or after a Railway redeploy wipes the
// in-memory mirror) — not fabricated data, just a neutral placeholder so
// the panel isn't blank on first paint.
const MOCK_MARKET_SNAPSHOT = {
  nifty_ltp: null,
  nifty_trend_up: null,
  vix_current: null,
};

// ─── Helpers ──────────────────────────────────────────────────────────────

// Morning Shortlist derives from the Momentum + Base Quality Shortlist
// (core/discovery/momentum_shortlist.py, synced daily by
// scripts/run_momentum_shortlist.py) rather than the older CSV-upload
// screener pipeline (core/screener/ranker.py), which has no automated
// daily feed. Server already sorts entries by bucket priority then
// momentum — this just takes the top 5 for a compact digest. Discretionary
// review only: not a signal, no execution path.
// Mirrors core/discovery/momentum_shortlist.py's BUCKET_PRIORITY — combined
// entries come from two independently-sorted universes (Alpha 50 + Nifty200
// Momentum 30), so they need re-sorting together before taking the top 5,
// not just concatenating.
const BUCKET_PRIORITY = { LEADER_TIGHT_BASE: 0, LEADER_EXTENDED: 1, BUILDING_BASE: 2, WATCH: 3 };

function rankByBucketThenMomentum(entries) {
  return [...entries]
    .sort((a, b) => (BUCKET_PRIORITY[a.bucket] ?? 9) - (BUCKET_PRIORITY[b.bucket] ?? 9)
      || b.momentum_pct - a.momentum_pct);
}

function buildMorningShortlist(entries) {
  return rankByBucketThenMomentum(entries)
    .slice(0, 5)
    .map((e, i) => ({
      rank: i + 1,
      symbol: e.symbol,
      score: `${e.momentum_pct.toFixed(1)}%`,
      rationale: [
        e.bucket.replace(/_/g, " "),
        e.base_status !== "NO BASE" ? e.base_status : null,
      ].filter(Boolean).join(" · "),
    }));
}

// Nifty 500 isn't pre-screened like Alpha 50 / Momentum 30 (see
// scripts/run_momentum_shortlist.py's DEFAULT_UNIVERSE_FILES comment), so
// its panel truncates to the top N by the same bucket-then-momentum rank
// instead of showing the full pass list.
function topByRank(entries, n) {
  return rankByBucketThenMomentum(entries).slice(0, n);
}

// Momentum + Base Quality Shortlist — see cloud/api/momentum_shortlist_routes.py.
// Polled rather than pushed since scripts/run_momentum_shortlist.py syncs
// once a day, not on a fixed schedule the client could otherwise predict.
function useMomentumShortlist(universe, setState) {
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/discovery/momentum-shortlist/${universe}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setState({ entries: data.entries ?? [], updatedAt: data.updated_at, error: false });
        }
      } catch {
        if (!cancelled) setState(d => ({ ...d, error: true }));
      }
    };
    load();
    const id = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, [universe]);
}

const fmt = (n, dp = 2) => n?.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp }) ?? "—";
const fmtINR = n => n != null ? `₹${fmt(n, 0)}` : "—";

// Shortlist symbols are bare NSE tickers (e.g. "APOLLOHOSP", no exchange
// suffix — see core/discovery/momentum_shortlist.py), which is exactly the
// format TradingView's chart URL expects under the NSE prefix.
const tradingViewUrl = symbol => `https://www.tradingview.com/chart/?symbol=NSE%3A${encodeURIComponent(symbol)}`;
const fmtMs = n => n != null ? `${Math.round(n)} ms` : "—";
const fmtAge = s => {
  if (s == null) return "never";
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
};

const statusBadge = s => ({
  PENDING_CONFIRMATION: { label: "Pending", color: C.gold },
  CONFIRMED: { label: "Confirmed", color: C.green },
  REJECTED_LOW_CONFLUENCE: { label: "Rejected", color: C.muted },
  BLOCKED_EVENT_RISK: { label: "Blocked", color: C.red },
  SKIPPED: { label: "Skipped", color: C.muted },
})[s] ?? { label: s, color: C.muted };

// ─── Sub-components ────────────────────────────────────────────────────────

function Card({ children, style = {}, className = "" }) {
  return (
    <div style={{
      background: C.panelAlt, border: `1px solid ${C.border}`,
      borderRadius: 10, padding: "16px 20px", ...style,
    }} className={className}>
      {children}
    </div>
  );
}

function Label({ children, color = C.muted }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: 1.5,
      textTransform: "uppercase", color }}>
      {children}
    </span>
  );
}

function Divider() {
  return <div style={{ height: 1, background: C.border, margin: "12px 0" }} />;
}

// ─── Panels ───────────────────────────────────────────────────────────────

// Deliberately not a regime classifier (bull/bear/ranging) — that depended
// entirely on the mothballed quantos-agent and hasn't synced in days (see
// cloud/api/market_snapshot_routes.py's module docstring). Three real
// facts instead: NIFTY's LTP + short-term trend (same EMA9/EMA21 check
// applied to every stock in the Momentum Shortlist tables below, so this
// reading and theirs never disagree on what "uptrend" means), India VIX's
// raw LTP (no classification layered on top), and whether the Momentum
// Shortlist scans are actually running (replaces the old "Darvas
// Active/Gated" chip — Darvas has had zero evidenced edge since S7-3 and
// no live feed since the agent was mothballed; this is the tool that's
// actually in use now).
function MarketSnapshotPanel({ snapshot, error, shortlistFreshness }) {
  const trendUp = snapshot.nifty_trend_up;
  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Label color={C.accent}>Market Snapshot</Label>
        <span style={{ fontSize: 10, color: C.muted }}>
          {error ? "offline" : "daily, from Momentum Shortlist's own scan"}
        </span>
      </div>
      <div style={{ display: "flex", gap: 24, marginTop: 4 }}>
        <div>
          <Label>Nifty 50</Label>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.white, marginTop: 2 }}>
            {snapshot.nifty_ltp != null ? fmt(snapshot.nifty_ltp, 1) : "—"}
          </div>
          <div style={{
            fontSize: 12, fontWeight: 600, marginTop: 2,
            color: trendUp == null ? C.muted : trendUp ? C.green : C.red,
          }}>
            {trendUp == null ? "no data" : trendUp ? "▲ up (EMA9>21)" : "▼ down (EMA9<21)"}
          </div>
        </div>
        <div>
          <Label>India VIX</Label>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.white, marginTop: 2 }}>
            {snapshot.vix_current != null ? snapshot.vix_current.toFixed(2) : "—"}
          </div>
        </div>
        <div>
          <Label>Momentum Shortlist</Label>
          <div style={{
            fontSize: 13, fontWeight: 600, marginTop: 2,
            color: shortlistFreshness.live ? C.green : C.muted,
          }}>
            {shortlistFreshness.live ? "✅ Active" : "— waiting"}
          </div>
          {shortlistFreshness.label && (
            <div style={{ fontSize: 11, color: C.muted, marginTop: 1 }}>{shortlistFreshness.label}</div>
          )}
        </div>
      </div>
    </Card>
  );
}

// No options-position sync pipeline exists yet (nothing pushes live options
// holdings to the cloud the way /positions/sync does for equities), so there
// is no real data this panel could show. core/options/greeks.py's Black-
// Scholes math and POST /options/greeks/panel are real and tested — this
// panel just has no positions to feed them. Honest empty state rather than
// fabricated numbers.
function GreeksPanel() {
  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <Label color={C.purple}>Portfolio Greeks</Label>
      <div style={{
        marginTop: 4, padding: "14px 12px", borderRadius: 6,
        background: C.bg, border: `1px solid ${C.border}`,
        fontSize: 12, color: C.muted, textAlign: "center",
      }}>
        No options positions tracked yet — live options execution isn't wired
        to the cloud sync path.
      </div>
    </Card>
  );
}

function SignalFeed({ signals, error }) {
  return (
    <Card>
      <Label color={C.accent}>Signal Feed</Label>
      {signals.length === 0 ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>
          {error ? "Could not reach cloud API." : "No signals yet today."}
        </div>
      ) : (
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
        {signals.map(sig => {
          const badge = statusBadge(sig.status);
          return (
            <div key={sig.signal_id} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "10px 12px", background: C.bg, borderRadius: 6,
              border: `1px solid ${C.border}`,
            }}>
              <div style={{
                width: 32, height: 32, borderRadius: "50%", display: "flex",
                alignItems: "center", justifyContent: "center", fontWeight: 700,
                fontSize: 11, flexShrink: 0,
                background: sig.action === "BUY" ? `${C.green}20` : `${C.red}20`,
                color: sig.action === "BUY" ? C.green : C.red,
                border: `1px solid ${sig.action === "BUY" ? C.green : C.red}50`,
              }}>{sig.action}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14 }}>
                  <a
                    className="qs-symbol-link"
                    href={tradingViewUrl(sig.symbol)}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontWeight: 700 }}
                  >
                    {sig.symbol}
                  </a>
                  <span style={{ fontWeight: 400, color: C.muted, fontSize: 12, marginLeft: 8 }}>
                    @ {fmtINR(sig.price)}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: C.muted, marginTop: 1 }}>
                  Confluence {sig.confluence_score}
                  {sig.confidence_score != null && ` · Claude ${sig.confidence_score}`}
                  {" · "}{sig.signal_id.slice(-8)}
                </div>
              </div>
              <span style={{
                fontSize: 10, padding: "3px 8px", borderRadius: 4, fontWeight: 600,
                background: `${badge.color}20`, color: badge.color,
                border: `1px solid ${badge.color}40`,
              }}>{badge.label}</span>
            </div>
          );
        })}
      </div>
      )}
    </Card>
  );
}

function ScreenerPanel({ candidates }) {
  return (
    <Card>
      <Label color={C.gold}>Morning Shortlist</Label>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>
        Top 5 from the Momentum Shortlist below — for discretionary review,
        not a signal.
      </div>
      {candidates.length === 0 ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>
          Waiting for the daily momentum-shortlist run.
        </div>
      ) : (
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 10 }}>
        {candidates.map(c => (
          <div key={c.symbol} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "8px 10px", background: C.bg, borderRadius: 6,
            border: `1px solid ${C.border}`,
          }}>
            <div style={{
              width: 22, height: 22, borderRadius: "50%",
              background: `${C.gold}20`, border: `1px solid ${C.gold}50`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, fontWeight: 700, color: C.gold, flexShrink: 0,
            }}>{c.rank}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <a
                className="qs-symbol-link"
                href={tradingViewUrl(c.symbol)}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontWeight: 700 }}
              >
                {c.symbol}
              </a>
              <span style={{ marginLeft: 8, fontSize: 11, color: C.muted }}>{c.rationale}</span>
            </div>
            <div style={{
              fontSize: 12, fontWeight: 700, color: C.gold,
              background: `${C.gold}15`, padding: "2px 8px", borderRadius: 4,
              border: `1px solid ${C.gold}30`,
            }}>{c.score}</div>
          </div>
        ))}
      </div>
      )}
    </Card>
  );
}

// Replaces the raw Darvas base_status in the table (2026-08-11). base_status
// collapses "broke out days ago", "above the ceiling without a volume surge"
// and "still inside the box" all into WATCHING; breakout_state (see
// core/discovery/momentum_shortlist.py) separates them. base_status is still
// carried in the payload, just not shown.
const breakoutMeta = {
  "FRESH":   { label: "FRESH",  color: C.green },
  "OUT":     { label: "OUT",    color: C.accent },
  "NEAR":    { label: "NEAR",   color: C.gold },
  "IN BOX":  { label: "IN BOX", color: C.muted },
  "NO BASE": { label: "—",      color: C.muted },
};

const bucketMeta = {
  LEADER_TIGHT_BASE: { label: "Leader · Tight Base", color: C.green },
  LEADER_EXTENDED:   { label: "Leader · Extended",   color: C.gold },
  BUILDING_BASE:     { label: "Building Base",       color: C.accent },
  WATCH:             { label: "Watch",               color: C.muted },
};

// One Card with a tab strip instead of three stacked panels — same three
// feeds (see scripts/run_momentum_shortlist.py's DEFAULT_UNIVERSE_FILES),
// just switched instead of scrolled past.
function MomentumShortlistTabs({ tabs, active, onSelect }) {
  const current = tabs.find(t => t.key === active) ?? tabs[0];
  const { entries, error } = current;

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Label color={C.gold}>Momentum Shortlist</Label>
        <span style={{ fontSize: 10, color: C.muted, whiteSpace: "nowrap", marginLeft: 12 }}>
          {current.error ? "offline"
            : current.updatedAt ? `updated ${new Date(current.updatedAt).toLocaleString("en-IN", { hour12: false })}`
            : "waiting for first daily run…"}
        </span>
      </div>

      <div style={{ display: "flex", gap: 4, marginTop: 12, borderBottom: `1px solid ${C.border}` }}>
        {tabs.map(t => {
          const isActive = t.key === current.key;
          return (
            <button
              key={t.key}
              onClick={() => onSelect(t.key)}
              style={{
                background: "none", border: "none", cursor: "pointer",
                padding: "8px 16px", fontSize: 12, fontWeight: 600,
                color: isActive ? C.accent : C.muted,
                borderBottom: `2px solid ${isActive ? C.accent : "transparent"}`,
                marginBottom: -1,
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div style={{ fontSize: 10, color: C.muted, marginTop: 10 }}>
        {current.universeName}, ranked by 52-week-high proximity, overlaid with
        each name's Darvas weekly base state — a "tight" base only
        counts if daily EMA9 is also above EMA21, so a name merely
        rolling over (not making new highs/lows, but trending down)
        isn't mislabeled as a constructive base. Discretionary review
        only — not a signal, no execution path.
      </div>

      {entries.length === 0 ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>
          {error ? "Could not reach cloud API." : "No data yet — waiting for the daily scan."}
        </div>
      ) : (
        <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Symbol", "Bucket", "Momentum", "Trend", "Breakout", "50/200", "Width%", "R:R"].map(h => (
                <th key={h} style={{
                  textAlign: (h === "Symbol" || h === "Bucket" || h === "Breakout" || h === "50/200") ? "left" : "right",
                  fontSize: 10, fontWeight: 600, letterSpacing: 1.2,
                  color: C.muted, padding: "4px 6px", borderBottom: `1px solid ${C.border}`,
                  textTransform: "uppercase",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map(e => {
              const meta = bucketMeta[e.bucket] ?? { label: e.bucket, color: C.muted };
              return (
                <tr key={e.symbol}>
                  <td style={{ padding: "8px 6px", fontWeight: 600 }}>
                    <a
                      className="qs-symbol-link"
                      href={tradingViewUrl(e.symbol)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {e.symbol}
                    </a>
                  </td>
                  <td style={{ padding: "8px 6px" }}>
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                      color: meta.color, background: `${meta.color}20`,
                      border: `1px solid ${meta.color}40`,
                    }}>{meta.label}</span>
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", color: C.mid }}>
                    {e.momentum_pct.toFixed(1)}%
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", color: e.trend_up ? C.green : C.red, fontSize: 11 }}>
                    {e.trend_up ? "▲ up" : "▼ down"}
                  </td>
                  <td style={{ padding: "8px 6px", fontSize: 11 }}>
                    {(() => {
                      const b = breakoutMeta[e.breakout_state] ?? { label: e.breakout_state ?? "—", color: C.muted };
                      const age = e.breakout_state === "OUT" && e.days_above_ceil != null
                        ? ` ${e.days_above_ceil}d` : "";
                      return (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                          color: b.color, background: `${b.color}20`,
                          border: `1px solid ${b.color}40`, whiteSpace: "nowrap",
                        }}>{b.label}{age}</span>
                      );
                    })()}
                  </td>
                  <td style={{ padding: "8px 6px", fontSize: 11, whiteSpace: "nowrap",
                               color: e.ma_cross === "BULL" ? C.green : e.ma_cross === "BEAR" ? C.red : C.muted }}>
                    {e.ma_cross
                      ? `${e.ma_cross}${e.ma_cross_days != null ? ` ${e.ma_cross_days}d` : ""}`
                      : "—"}
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", color: C.mid }}>
                    {e.box_width_pct != null ? `${e.box_width_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ padding: "8px 6px", textAlign: "right", color: C.mid }}>
                    {e.rr_ratio != null ? e.rr_ratio.toFixed(2) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// ─── System health (S5-6 observability, real data) ─────────────────────────

const SIGNAL_STATUS_COLOR = s => ({
  PENDING_CONFIRMATION: C.gold, CONFIRMED: C.green, EXECUTED: C.accent,
  CLOSED: C.mid, FAILED: C.red, BLOCKED_EVENT_RISK: C.red,
  REJECTED_LOW_CONFLUENCE: C.muted, REJECTED_DUPLICATE: C.muted, SKIPPED: C.muted,
})[s] ?? C.muted;

function Metric({ label, value, sub, color = C.white }) {
  return (
    <div style={{
      background: C.bg, borderRadius: 6, padding: "10px 12px",
      border: `1px solid ${C.border}`, flex: 1, minWidth: 0,
    }}>
      <Label color={C.muted}>{label}</Label>
      <div style={{ fontSize: 16, fontWeight: 700, marginTop: 4, color }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function SystemHealthPanel({ obs, error }) {
  const hb = obs?.heartbeat;
  const counts = obs?.signal_counts_today ?? {};
  const wl = obs?.webhook_latency ?? {};
  const cl = obs?.claude_latency ?? {};
  const spend = obs?.claude_spend_today ?? {};
  const hbColor = !hb || hb.stale ? C.red : C.green;

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Label color={C.accent}>System Health</Label>
        <span style={{ fontSize: 10, color: hbColor, fontWeight: 600 }}>
          {error ? "offline"
            : !hb || hb.last_contact == null ? "agent never synced"
            : `agent ${hb.stale ? "STALE" : "live"} · ${fmtAge(hb.age_seconds)}`}
        </span>
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
        <Metric
          label="Agent Heartbeat"
          value={!hb || hb.stale ? "STALE" : "LIVE"}
          color={hbColor}
          sub={hb?.last_contact ? fmtAge(hb.age_seconds) : "no sync yet"}
        />
        <Metric
          label="Signals Today"
          value={obs?.signals_today_total ?? "—"}
          sub={`${counts.EXECUTED ?? 0} executed`}
        />
        <Metric
          label="Webhook p50 / p95"
          value={`${fmtMs(wl.p50_ms)} / ${fmtMs(wl.p95_ms)}`}
          sub={`${wl.count ?? 0} samples`}
        />
        <Metric
          label="Claude p50 / p95"
          value={`${fmtMs(cl.p50_ms)} / ${fmtMs(cl.p95_ms)}`}
          sub={`${cl.count ?? 0} calls`}
        />
        <Metric
          label="Claude Spend (today)"
          value={spend.est_usd != null ? `$${spend.est_usd.toFixed(3)}` : "—"}
          color={C.gold}
          sub={`${spend.calls ?? 0} calls · est.`}
        />
      </div>

      {Object.keys(counts).length > 0 && (
        <>
          <Divider />
          <Label>Signals by Status (today)</Label>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
            {Object.entries(counts).map(([status, n]) => {
              const color = SIGNAL_STATUS_COLOR(status);
              return (
                <span key={status} style={{
                  fontSize: 10, padding: "3px 8px", borderRadius: 4, fontWeight: 600,
                  background: `${color}20`, color, border: `1px solid ${color}40`,
                }}>
                  {status.replace(/_/g, " ")} · {n}
                </span>
              );
            })}
          </div>
        </>
      )}
    </Card>
  );
}

// ─── Top bar ──────────────────────────────────────────────────────────────

function TopBar({ lastRefresh, heartbeat, obsError }) {
  // The LIVE indicator is now real: green only when the agent's most recent
  // sync (regime/watchlist) is within the heartbeat window (S5-6 dead-man).
  const stale = obsError || !heartbeat || heartbeat.stale || heartbeat.last_contact == null;
  const dotColor = stale ? C.red : C.green;
  const statusText = obsError ? "API DOWN"
    : !heartbeat || heartbeat.last_contact == null ? "NO AGENT"
    : heartbeat.stale ? "AGENT STALE" : "LIVE";
  return (
    <div style={{
      background: C.panel, borderBottom: `1px solid ${C.border}`,
      padding: "10px 24px", display: "flex", alignItems: "center", gap: 20,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
        <span style={{ fontSize: 18, fontWeight: 900, color: C.white, letterSpacing: 2 }}>QUANT</span>
        <span style={{ fontSize: 18, fontWeight: 900, color: C.accent, letterSpacing: 2 }}>OS</span>
      </div>
      <div style={{ width: 1, height: 18, background: C.border }} />
      <span style={{ fontSize: 11, color: C.muted }}>Bloomberg. But Smarter.</span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: dotColor,
            animation: stale ? "none" : "pulse 2s infinite" }} />
          <span style={{ fontSize: 11, color: dotColor }}>{statusText}</span>
        </div>
        <span style={{ fontSize: 11, color: C.muted }}>
          {lastRefresh ? `Updated ${lastRefresh}` : "Connecting…"}
        </span>
      </div>
    </div>
  );
}

// ─── Main app ─────────────────────────────────────────────────────────────

export default function QuantOSCockpit() {
  const [lastRefresh, setLastRefresh] = useState(null);
  const [marketSnapshot, setMarketSnapshot] = useState({ ...MOCK_MARKET_SNAPSHOT, error: false });
  const [signals, setSignals] = useState({ list: [], error: false });
  const [shortlistAlpha50, setShortlistAlpha50] = useState({ entries: [], updatedAt: null, error: false });
  const [shortlistMomentum30, setShortlistMomentum30] = useState({ entries: [], updatedAt: null, error: false });
  const [shortlistNifty500, setShortlistNifty500] = useState({ entries: [], updatedAt: null, error: false });
  const screener = useMemo(
    () => buildMorningShortlist([...shortlistAlpha50.entries, ...shortlistMomentum30.entries]),
    [shortlistAlpha50.entries, shortlistMomentum30.entries],
  );
  const nifty500Top10 = useMemo(
    () => topByRank(shortlistNifty500.entries, 10),
    [shortlistNifty500.entries],
  );
  const [shortlistTab, setShortlistTab] = useState("alpha50");
  const shortlistTabs = useMemo(() => ([
    {
      key: "alpha50", label: "Alpha 50", universeName: "Nifty Alpha 50",
      entries: shortlistAlpha50.entries, updatedAt: shortlistAlpha50.updatedAt, error: shortlistAlpha50.error,
    },
    {
      key: "nifty200momentum30", label: "Momentum 30", universeName: "Nifty200 Momentum 30",
      entries: shortlistMomentum30.entries, updatedAt: shortlistMomentum30.updatedAt, error: shortlistMomentum30.error,
    },
    {
      key: "nifty500", label: "Nifty 500 (Top 10)",
      universeName: "Nifty 500, full 500-symbol scan truncated to the top 10 by rank",
      entries: nifty500Top10, updatedAt: shortlistNifty500.updatedAt, error: shortlistNifty500.error,
    },
  ]), [shortlistAlpha50, shortlistMomentum30, nifty500Top10, shortlistNifty500.updatedAt, shortlistNifty500.error]);
  // Same 36h daily-cadence window cloud/api/observability_routes.py's
  // heartbeat uses — one missed day doesn't false-alarm, two does.
  const shortlistFreshness = useMemo(() => {
    const timestamps = [shortlistAlpha50.updatedAt, shortlistMomentum30.updatedAt, shortlistNifty500.updatedAt]
      .filter(Boolean).map(t => new Date(t).getTime());
    if (timestamps.length === 0) return { live: false, label: null };
    const freshest = Math.max(...timestamps);
    const ageSeconds = (Date.now() - freshest) / 1000;
    return {
      live: ageSeconds < 36 * 3600,
      label: `last scan ${fmtAge(ageSeconds)}`,
    };
  }, [shortlistAlpha50.updatedAt, shortlistMomentum30.updatedAt, shortlistNifty500.updatedAt]);
  const [obs, setObs] = useState(null);
  const [obsError, setObsError] = useState(false);

  useEffect(() => {
    const fmt = new Intl.DateTimeFormat("en-IN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
    const tick = () => setLastRefresh(fmt.format(new Date()));
    tick();
    const id = setInterval(tick, 60000);
    return () => clearInterval(id);
  }, []);

  // Momentum + Base Quality Shortlist — see cloud/api/momentum_shortlist_routes.py.
  // One universe per slot (2026-07-29: Alpha 50 and Nifty200 Momentum 30 sync
  // independently so neither clobbers the other's daily post).
  useMomentumShortlist("alpha50", setShortlistAlpha50);
  useMomentumShortlist("nifty200momentum30", setShortlistMomentum30);
  useMomentumShortlist("nifty500", setShortlistNifty500);

  // Signal feed: recent signals across all sources (Pine + internal Stage B),
  // see cloud/api/main.py's GET /signals. Polled since signals arrive at
  // irregular times, not on a fixed schedule.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/signals?limit=20`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setSignals({ list: data.signals ?? [], error: false });
      } catch {
        if (!cancelled) setSignals(s => ({ ...s, error: true }));
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Market snapshot — see cloud/api/market_snapshot_routes.py. Synced once a
  // day by scripts/run_momentum_shortlist.py, not by the mothballed agent
  // (that was /regime/status, now unused by the cockpit — see its module
  // docstring for why this isn't a repurposing of that dead endpoint).
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/market/snapshot`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setMarketSnapshot({ ...data, error: false });
      } catch {
        if (!cancelled) setMarketSnapshot(s => ({ ...s, error: true }));
      }
    };
    load();
    const id = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // System health (S5-6): signal counts, webhook/Claude latency, spend, and
  // the agent heartbeat. Polled every 15s so a dead agent surfaces promptly.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/observability`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) { setObs(data); setObsError(false); }
      } catch {
        if (!cancelled) setObsError(true);
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <div style={{
      background: C.bg, minHeight: "100vh", color: C.white,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    }}>
      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: ${C.bg}; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 2px; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        input::placeholder { color: ${C.muted}; }
        .qs-symbol-link { color: ${C.white}; text-decoration: none; }
        .qs-symbol-link:hover { color: ${C.accent}; text-decoration: underline; }
      `}</style>

      <TopBar lastRefresh={lastRefresh} heartbeat={obs?.heartbeat} obsError={obsError} />

      <div style={{ padding: "20px 24px" }}>
        {/* Row 0: System health (real data — S5-6 observability) */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16, marginBottom: 16 }}>
          <SystemHealthPanel obs={obs} error={obsError} />
        </div>

        {/* Row 1: Market Snapshot · Greeks */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16, marginBottom: 16,
        }}>
          <MarketSnapshotPanel
            snapshot={marketSnapshot}
            error={marketSnapshot.error}
            shortlistFreshness={shortlistFreshness}
          />
          <GreeksPanel />
        </div>

        {/* Row 2: Signals · Morning Shortlist */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16, marginBottom: 16,
        }}>
          <SignalFeed signals={signals.list} error={signals.error} />
          <ScreenerPanel candidates={screener} />
        </div>

        {/* Row 3: Momentum + Base Quality Shortlist (discretionary review) —
            replaced Alpha-vs-Nifty, Open Positions, and Claude Analyst
            2026-07-29, all three either dead placeholders or unused. Three
            universes (Alpha 50 / Momentum 30 / Nifty 500), tabbed instead of
            stacked as of 2026-08-05. */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16 }}>
          <MomentumShortlistTabs tabs={shortlistTabs} active={shortlistTab} onSelect={setShortlistTab} />
        </div>
      </div>
    </div>
  );
}
