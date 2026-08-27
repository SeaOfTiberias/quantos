import { Component, useState, useEffect, useMemo } from "react";

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

// "OUT 12d" / "FRESH" / "NEAR" / null. Shared by the tables and the morning
// shortlist so both describe a stock the same way. Tolerates an entry restored
// from a cache written before these fields existed (renders nothing).
function describeBreakout(e) {
  if (!e.breakout_state || e.breakout_state === "NO BASE") return null;
  if (e.breakout_state === "OUT" && e.days_above_ceil != null) {
    return `OUT ${e.days_above_ceil}d`;
  }
  return e.breakout_state;
}

function buildMorningShortlist(entries) {
  return rankByBucketThenMomentum(entries)
    .slice(0, 5)
    .map((e, i) => ({
      rank: i + 1,
      symbol: e.symbol,
      score: `${e.momentum_pct.toFixed(1)}%`,
      // Same breakout_state the tables show, not the raw Darvas base_status:
      // this panel sits on the same page, and two labels disagreeing about the
      // same stock is worse than either label alone.
      rationale: [
        e.bucket.replace(/_/g, " "),
        describeBreakout(e),
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

// Morning Brief — see cloud/api/momentum_shortlist_routes.py::get_shortlist_brief.
// Polled at 5 minutes rather than the 30s the shortlist panels use: the
// response can trigger one Claude call for the generated note, and although
// the server caches that per (universe, scan_date) so repeat polls are free,
// there is no reason to hammer an endpoint whose data changes once a day.
function useShortlistBrief(universe) {
  // The universe this state belongs to is stored WITH it. The obvious version
  // resets the state synchronously at the top of the effect, which triggers a
  // cascading render and, for one frame, shows the previous universe's brief
  // under the newly-selected universe's heading. Deriving staleness during
  // render instead means the switch is correct on the first frame.
  const [state, setState] = useState({
    brief: null, universe: null, loading: true, error: false,
  });
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/discovery/shortlist-brief/${universe}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setState({ brief: data, universe, loading: false, error: false });
      } catch {
        if (!cancelled) {
          setState(d => ({ ...d, universe, loading: false, error: true }));
        }
      }
    };
    load();
    const id = setInterval(load, 300000);
    return () => { cancelled = true; clearInterval(id); };
  }, [universe]);

  if (state.universe !== universe) {
    return { brief: null, loading: true, error: false };
  }
  return state;
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

// ─── Panel error boundary ──────────────────────────────────────────────────
// One panel throwing used to take the whole dashboard with it: on 2026-08-27
// the Morning Brief called a helper that did not exist, React unmounted the
// entire tree, and System Health, the regime card, the signal feed and all
// three shortlist tabs went blank alongside it. Nothing about those panels
// was broken -- they were collateral.
//
// A boundary per panel makes a crash local. The failed panel says so and
// names the error; every other panel keeps rendering its own data. This is
// deliberately NOT one boundary around the whole grid, which would restore
// the same all-or-nothing behaviour with a nicer message.
//
// Must be a class: getDerivedStateFromError/componentDidCatch have no hook
// equivalent. Boundaries also only catch errors thrown while RENDERING a
// descendant -- an event handler or an async fetch rejection is not caught,
// which is fine here because those already have their own error states.
class PanelBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep the stack in the console -- the fallback below is deliberately
    // terse, and without this the detail is gone.
    console.error(`Panel "${this.props.name}" crashed:`, error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Card>
        <Label color={C.red}>{this.props.name} unavailable</Label>
        <div style={{ fontSize: 12, color: C.mid, marginTop: 10, lineHeight: 1.7 }}>
          This panel hit an error and was isolated so the rest of the
          dashboard keeps working. The other panels are unaffected.
        </div>
        <div style={{
          fontSize: 11, color: C.muted, marginTop: 8,
          fontFamily: "ui-monospace, monospace", wordBreak: "break-word",
        }}>
          {String(this.state.error?.message || this.state.error)}
        </div>
      </Card>
    );
  }
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

// Obsidian vault audit (2026-08-14) — whether the name satisfies the written
// rules in the brain/ strategy notes (Minervini VCP, Weinstein Stage
// Analysis). Annotation only: this shortlist has no execution path, so a FAIL
// is a reason to look closer, not a block. Hover for the per-note breakdown.
//
// The cell shows the RULE TALLY, not the verdict, because both bundled notes
// are strict conjunctive screens: measured 2026-08-14, 0 of 50 Alpha 50 names
// cleared both, so a binary column would read "fail" every day and carry no
// information. 9/11 vs 5/11 is the part worth scanning. Colour still encodes
// the verdict, so a genuine clean pass is unmissable.
const vaultMeta = {
  "PASS":              { label: "PASS",    color: C.green },
  "FAIL":              { label: "fail",    color: C.red },
  "INSUFFICIENT_DATA": { label: "no data", color: C.gold },
  "UNAVAILABLE":       { label: "n/a",     color: C.muted },
};

// Within FAIL, distance from clearing. The thresholds are for reading speed
// only — nothing branches on them.
function vaultColor(verdict, passed, total) {
  if (verdict === "PASS") return C.green;
  if (verdict === "INSUFFICIENT_DATA") return C.gold;
  if (verdict === "UNAVAILABLE" || !total) return C.muted;
  const ratio = passed / total;
  if (ratio >= 0.8) return C.accent;      // one rule away
  if (ratio >= 0.5) return C.mid;
  return C.muted;
}

// One column per strategy note, NOT one aggregate column. Measured 2026-08-14
// across 482 Nifty 500 names: 5 cleared Minervini, 11 cleared Weinstein, 0
// cleared both — the sets are disjoint, because Minervini's volume dry-up and
// Weinstein's volume expansion are opposed conditions describing consecutive
// phases (the quiet pivot before a breakout, and the breakout itself). A
// combined score conflates two disciplines that structurally cannot both
// fire, so the notes are shown side by side and never summed here.
//
// Derived from the data rather than hardcoded: the audited notes come from
// config (vault.shortlist_notes), so a hardcoded pair of columns would go
// stale silently the moment a note is added or swapped.
function vaultColumns(entries) {
  const seen = new Map();
  for (const e of entries) {
    for (const n of e.vault_notes ?? []) {
      if (!seen.has(n.strategy_id)) seen.set(n.strategy_id, n.label);
    }
  }
  return [...seen].map(([strategyId, label]) => ({ strategyId, label }));
}

// Weinstein stage (2026-08-17) — core/vault/stages.py, mirrored on TradingView
// by pine/weinstein_stage_journey.pine.
//
// This is a CLASSIFICATION, not a score, and it deliberately sits in its own
// column rather than joining the tallies above. The vault columns answer "do
// this note's conditions hold?" (conjunctive, PASS/FAIL); this answers "where
// in the cycle is this name?" (mutually exclusive, 1-4). Adding them together
// would repeat exactly the mistake the vaultColumns comment describes.
//
// null means UNCLASSIFIED, never stage 1 — a name without enough history is
// unknown, not basing. It renders "—" with the reason on hover.
const stageMeta = {
  1: { label: "1 · Basing",    color: C.accent, title: "Flat 30-week MA after a decline. Watch, no position." },
  2: { label: "2 · Advancing", color: C.green,  title: "Rising 30-week MA. Weinstein's only buy zone." },
  3: { label: "3 · Topping",   color: C.gold,   title: "Flat 30-week MA after an advance. Tighten stops." },
  4: { label: "4 · Declining", color: C.red,    title: "Falling 30-week MA. Out." },
};

// The phase refines Stage 2 without changing it, so it is appended to the
// label rather than given a colour of its own: `2 · pivot` is still Stage 2
// and must not read as a fifth state. These two phases are what resolve the
// Minervini/Weinstein volume contradiction — dry-up and expansion describe
// consecutive phases of one advance, not competing verdicts.
function stageText(entry) {
  const meta = stageMeta[entry.stage];
  if (!meta) return null;
  return entry.stage_phase ? `${entry.stage} · ${entry.stage_phase}` : meta.label;
}

const bucketMeta = {
  LEADER_TIGHT_BASE: { label: "Leader · Tight Base", color: C.green },
  LEADER_EXTENDED:   { label: "Leader · Extended",   color: C.gold },
  BUILDING_BASE:     { label: "Building Base",       color: C.accent },
  WATCH:             { label: "Watch",               color: C.muted },
};

// ─── Morning Brief ─────────────────────────────────────────────────────────
// What changed on the board overnight. The three universe tabs above show a
// ranked position; this shows a MOVE, which a ranked table cannot — a name
// that went IN BOX -> NEAR on a tight base looks identical to one that sat
// still until you diff two sessions.
//
// Two layers, and the order is load-bearing. The flags are computed by
// core/discovery/shortlist_brief.py and are the signal. The paragraph at the
// bottom is written by Claude from those same flags (never from the raw
// board) and is labelled as commentary, because it is. If the note is
// missing the tab is still complete.

const FLAG_META = {
  NEW_BREAKOUT:   { label: "Broke out",    color: C.green,  weight: 700 },
  NEW_LEADER:     { label: "New leader",   color: C.green,  weight: 700 },
  TURNED_NEAR:    { label: "Turned NEAR",  color: C.accent, weight: 600 },
  NEW_BULL_CROSS: { label: "50/200 BULL",  color: C.accent, weight: 600 },
  LOST_LEADER:    { label: "Lost leader",  color: C.red,    weight: 600 },
  VAULT_IMPROVED: { label: "Rules gained", color: C.mid,    weight: 500 },
  VAULT_WEAKENED: { label: "Rules lost",   color: C.mid,    weight: 500 },
  NEW_ENTRY:      { label: "New entry",    color: C.purple, weight: 500 },
  DROPPED:        { label: "Dropped",      color: C.muted,  weight: 500 },
};

// Signed numbers, sign always shown, and a null rendered as an em dash rather
// than a zero — "did not move" and "no previous session to compare against"
// are different facts (see shortlist_brief.diff_entry) and a panel that draws
// them identically is lying to the reader.
function Delta({ value, dp = 1 }) {
  if (value == null) return <span style={{ color: C.muted }}>—</span>;
  if (value === 0) return <span style={{ color: C.muted }}>0</span>;
  return (
    <span style={{ color: value > 0 ? C.green : C.red }}>
      {value > 0 ? "+" : ""}{value.toFixed(dp)}
    </span>
  );
}

function BriefCensus({ census }) {
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
      {census.map(c => {
        const meta = bucketMeta[c.bucket] ?? { label: c.bucket, color: C.muted };
        return (
          <div key={c.bucket} style={{
            background: C.panel, border: `1px solid ${C.border}`,
            borderRadius: 6, padding: "6px 10px", minWidth: 108,
          }}>
            <div style={{
              fontSize: 9, color: meta.color, fontWeight: 600,
              textTransform: "uppercase", letterSpacing: 0.6,
            }}>
              {meta.label}
            </div>
            <div style={{ fontSize: 16, color: C.white, fontVariantNumeric: "tabular-nums" }}>
              {c.count}
              <span style={{ fontSize: 11, marginLeft: 6 }}>
                <Delta value={c.delta} dp={0} />
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BriefFlags({ flags }) {
  if (flags.length === 0) {
    return (
      <div style={{ fontSize: 12, color: C.mid, marginTop: 14 }}>
        No transitions since the previous session — the board did not move.
      </div>
    );
  }
  // Preserve the server's ordering (most important first) while grouping, so
  // a breakout can never be rendered below a lost rule.
  const groups = [];
  for (const f of flags) {
    const last = groups[groups.length - 1];
    if (last && last.kind === f.kind) last.items.push(f);
    else groups.push({ kind: f.kind, items: [f] });
  }
  return (
    <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
      {groups.map(g => {
        const meta = FLAG_META[g.kind] ?? { label: g.kind, color: C.mid, weight: 500 };
        return (
          <div key={g.kind} style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: 0.8,
              textTransform: "uppercase", color: meta.color,
              minWidth: 96, flexShrink: 0,
            }}>
              {meta.label}
            </span>
            <span style={{ fontSize: 12, color: C.mid, lineHeight: 1.7 }}>
              {g.items.map((f, i) => (
                <span key={f.symbol + i}>
                  {i > 0 && <span style={{ color: C.border }}> · </span>}
                  <a href={tradingViewUrl(f.symbol)} target="_blank" rel="noreferrer"
                     style={{ color: C.white, fontWeight: meta.weight, textDecoration: "none" }}>
                    {f.symbol}
                  </a>
                  <span style={{ color: C.muted, fontSize: 11 }}> ({f.detail})</span>
                </span>
              ))}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function BriefNote({ note, error }) {
  return (
    <div style={{ marginTop: 16, paddingTop: 14, borderTop: `1px solid ${C.border}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Label color={C.purple}>Generated commentary</Label>
        <span style={{ fontSize: 9, color: C.muted }}>
          written by Claude from the flags above — not a signal, not advice
        </span>
      </div>
      {note ? (
        <div style={{ fontSize: 12, color: C.mid, marginTop: 8, lineHeight: 1.75 }}>
          {note}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: C.muted, marginTop: 8 }}>
          {error ? "Unavailable (" + error + ")." : "Not generated for this session."}
          {" The computed flags above are unaffected."}
        </div>
      )}
    </div>
  );
}

const BRIEF_UNIVERSES = [
  { key: "alpha50", label: "Alpha 50" },
  { key: "nifty200momentum30", label: "Momentum 30" },
  { key: "nifty500", label: "Nifty 500" },
];

const BRIEF_COLUMNS = [
  "Symbol", "Bucket", "Momentum", "Mom Δ", "Rank Δ",
  "Breakout", "Was", "50/200", "Width", "Vault",
];

function MorningBrief({ universe, onUniverse }) {
  const { brief, loading, error } = useShortlistBrief(universe);

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, color: C.muted, marginRight: 4, letterSpacing: 1 }}>
          UNIVERSE
        </span>
        {BRIEF_UNIVERSES.map(u => (
          <button key={u.key} onClick={() => onUniverse(u.key)} style={{
            background: u.key === universe ? C.panel : "none",
            border: `1px solid ${u.key === universe ? C.accent : C.border}`,
            color: u.key === universe ? C.accent : C.muted,
            borderRadius: 5, padding: "3px 10px", fontSize: 11,
            cursor: "pointer", fontWeight: 600,
          }}>
            {u.label}
          </button>
        ))}
      </div>

      {loading && (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 14 }}>Loading brief…</div>
      )}
      {error && !loading && (
        <div style={{ fontSize: 12, color: C.red, marginTop: 14 }}>
          Could not reach cloud API.
        </div>
      )}
      {brief && !brief.available && (
        <div style={{ fontSize: 12, color: C.mid, marginTop: 14, lineHeight: 1.7 }}>
          {brief.reason}
        </div>
      )}

      {brief && brief.available && (
        <>
          <div style={{ fontSize: 10, color: C.muted, marginTop: 12, lineHeight: 1.7 }}>
            Scan <span style={{ color: C.white }}>{brief.scan_date}</span>
            {brief.prev_scan_date
              ? <> compared against <span style={{ color: C.white }}>{brief.prev_scan_date}</span></>
              : <> — no previous session on record, so nothing is diffed yet</>}
            {" · "}{brief.counts.ranked} ranked, {brief.counts.focus} on tight bases
            {" · store "}{brief.backend}
          </div>

          <BriefCensus census={brief.census} />
          <BriefFlags flags={brief.flags} />

          {brief.entries.length > 0 && (
            <table style={{ width: "100%", marginTop: 16, borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {BRIEF_COLUMNS.map(h => (
                    <th key={h} style={{
                      textAlign: h === "Symbol" || h === "Bucket" ? "left" : "right",
                      padding: "6px", fontSize: 9, color: C.muted,
                      borderBottom: `1px solid ${C.border}`,
                      textTransform: "uppercase", letterSpacing: 0.6,
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {brief.entries.map(e => {
                  const meta = bucketMeta[e.bucket] ?? { label: e.bucket, color: C.muted };
                  const moved = e.breakout_state !== e.prev_breakout_state;
                  return (
                    <tr key={e.symbol} style={{ borderBottom: `1px solid ${C.panel}` }}>
                      <td style={{ padding: "7px 6px" }}>
                        <a href={tradingViewUrl(e.symbol)} target="_blank" rel="noreferrer"
                           style={{ color: C.white, fontWeight: 600, textDecoration: "none", fontSize: 12 }}>
                          {e.symbol}
                        </a>
                        {e.is_new && (
                          <span style={{ color: C.purple, fontSize: 9, marginLeft: 6 }}>NEW</span>
                        )}
                      </td>
                      <td style={{ padding: "7px 6px", fontSize: 10, color: meta.color }}>
                        {meta.label}
                      </td>
                      <td style={{
                        padding: "7px 6px", textAlign: "right", fontSize: 12,
                        color: C.white, fontVariantNumeric: "tabular-nums",
                      }}>
                        {e.momentum_pct != null ? e.momentum_pct.toFixed(1) + "%" : "—"}
                      </td>
                      <td style={{
                        padding: "7px 6px", textAlign: "right", fontSize: 11,
                        fontVariantNumeric: "tabular-nums",
                      }}>
                        <Delta value={e.momentum_delta} dp={1} />
                      </td>
                      <td style={{
                        padding: "7px 6px", textAlign: "right", fontSize: 11,
                        fontVariantNumeric: "tabular-nums",
                      }}>
                        <Delta value={e.rank_delta} dp={0} />
                      </td>
                      <td style={{
                        padding: "7px 6px", textAlign: "right", fontSize: 11,
                        color: moved ? C.accent : C.mid, fontWeight: moved ? 700 : 400,
                      }}>
                        {e.breakout_state ?? "—"}
                      </td>
                      <td style={{ padding: "7px 6px", textAlign: "right", fontSize: 10, color: C.muted }}>
                        {moved ? (e.prev_breakout_state ?? "—") : ""}
                      </td>
                      <td style={{ padding: "7px 6px", textAlign: "right", fontSize: 10, color: C.mid }}>
                        {e.ma_cross ?? "—"}{e.ma_cross_days != null ? " " + e.ma_cross_days + "d" : ""}
                      </td>
                      <td style={{
                        padding: "7px 6px", textAlign: "right", fontSize: 11, color: C.mid,
                        fontVariantNumeric: "tabular-nums",
                      }}>
                        {e.box_width_pct != null ? e.box_width_pct.toFixed(1) + "%" : "—"}
                      </td>
                      <td style={{ padding: "7px 6px", textAlign: "right", fontSize: 10 }}>
                        {/* Per note, never summed — the same rule the tables
                            above follow. A Minervini rule and a Weinstein rule
                            are not interchangeable units, so there is no
                            single number here to show. */}
                        {(e.vault_moves ?? []).length === 0
                          ? <span style={{ color: C.muted }}>—</span>
                          : e.vault_moves.map(m => (
                              <span key={m.label} style={{ marginLeft: 8, whiteSpace: "nowrap" }}>
                                <span style={{ color: C.muted }}>{m.label.slice(0, 4)} </span>
                                <span style={{ color: C.mid }}>{m.rules_passed}/{m.rules_total}</span>
                                {m.delta != null && m.delta !== 0 && (
                                  <span style={{ color: m.delta > 0 ? C.green : C.red, marginLeft: 3 }}>
                                    {m.delta > 0 ? "▲" : "▼"}
                                  </span>
                                )}
                              </span>
                            ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <BriefNote note={brief.note} error={brief.note_error} />
        </>
      )}
    </div>
  );
}

// One Card with a tab strip instead of three stacked panels — same three
// feeds (see scripts/run_momentum_shortlist.py's DEFAULT_UNIVERSE_FILES),
// just switched instead of scrolled past.
function MomentumShortlistTabs({ tabs, active, onSelect,
                                 briefUniverse, onBriefUniverse }) {
  const current = tabs.find(t => t.key === active) ?? tabs[0];
  const { entries, error } = current;
  const vaultCols = useMemo(() => vaultColumns(entries), [entries]);
  const vaultLabels = useMemo(() => new Set(vaultCols.map(c => c.label)), [vaultCols]);

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

      {current.kind === "brief" ? (
        <MorningBrief universe={briefUniverse} onUniverse={onBriefUniverse} />
      ) : (
      <>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 10 }}>
        {current.universeName}, ranked by 52-week-high proximity, overlaid with
        each name's Darvas weekly base state — a "tight" base only
        counts if daily EMA9 is also above EMA21, so a name merely
        rolling over (not making new highs/lows, but trending down)
        isn't mislabeled as a constructive base. The right-hand columns show
        how many of each Obsidian strategy note's written rules the name
        satisfies; hover one for its reason. They are shown separately and
        never summed — Minervini wants volume drying up before a breakout and
        Weinstein wants it expanding on one, so the two describe consecutive
        phases and a name clearing both is rare by construction. Discretionary
        review only — not a signal, no execution path.
      </div>

      {entries.length === 0 ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>
          {error ? "Could not reach cloud API." : "No data yet — waiting for the daily scan."}
        </div>
      ) : (
        <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {[
                ...["Symbol", "Bucket", "Momentum", "Trend", "Breakout", "50/200", "Stage"],
                ...vaultCols.map(c => c.label),
                ...["Width%", "R:R"],
              ].map(h => (
                <th key={h} style={{
                  textAlign: (h === "Symbol" || h === "Bucket" || h === "Breakout"
                              || h === "50/200" || h === "Stage"
                              || vaultLabels.has(h)) ? "left" : "right",
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
                      const b = breakoutMeta[e.breakout_state] ?? { label: "—", color: C.muted };
                      const text = describeBreakout(e) ?? b.label;
                      return (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                          color: b.color, background: `${b.color}20`,
                          border: `1px solid ${b.color}40`, whiteSpace: "nowrap",
                        }}>{text}</span>
                      );
                    })()}
                  </td>
                  <td style={{ padding: "8px 6px", fontSize: 11, whiteSpace: "nowrap",
                               color: e.ma_cross === "BULL" ? C.green : e.ma_cross === "BEAR" ? C.red : C.muted }}>
                    {e.ma_cross
                      ? `${e.ma_cross}${e.ma_cross_days != null ? ` ${e.ma_cross_days}d` : ""}`
                      : "—"}
                  </td>
                  <td style={{ padding: "8px 6px", fontSize: 11 }}>
                    {(() => {
                      const meta = stageMeta[e.stage];
                      // Unclassified and never-classified are different states
                      // and must stay distinguishable: stage_detail carries the
                      // reason when the classifier ran and could not place the
                      // name, and is absent entirely on a row that predates the
                      // column or a scan with no stage note configured.
                      if (!meta) {
                        return (
                          <span title={e.stage_detail || "not classified"}
                                style={{ color: C.muted }}>—</span>
                        );
                      }
                      return (
                        <span
                          title={e.stage_detail || meta.title}
                          style={{
                            fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                            color: meta.color, background: `${meta.color}20`,
                            border: `1px solid ${meta.color}40`, whiteSpace: "nowrap",
                          }}>{stageText(e)}</span>
                      );
                    })()}
                  </td>
                  {vaultCols.map(col => {
                    const score = (e.vault_notes ?? []).find(n => n.strategy_id === col.strategyId);
                    // No score means this row predates the note, or the scan
                    // ran with it switched off — distinct from UNAVAILABLE,
                    // which means the audit ran and could not answer.
                    if (!score) {
                      return (
                        <td key={col.strategyId} style={{ padding: "8px 6px", fontSize: 11, color: C.muted }}>
                          —
                        </td>
                      );
                    }
                    const color = vaultColor(score.verdict, score.rules_passed, score.rules_total);
                    const label = vaultMeta[score.verdict]?.label ?? score.verdict;
                    const text = score.rules_total
                      ? `${score.rules_passed}/${score.rules_total}` : label;
                    return (
                      <td key={col.strategyId} style={{ padding: "8px 6px", fontSize: 11 }}>
                        <span
                          title={`${col.label}: ${label}`}
                          style={{
                            fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                            color, background: `${color}20`,
                            border: `1px solid ${color}40`, whiteSpace: "nowrap",
                            fontVariantNumeric: "tabular-nums", cursor: "help",
                          }}>{text}</span>
                      </td>
                    );
                  })}
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
      </>
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

// One row per scheduled timer. `last fired` is deliberate wording: this reads
// systemd, which knows the schedule ran, not whether the work inside it was
// any good — the shortlist's own updated_at is the check for that.
function JobRow({ job }) {
  const color = job.ok ? C.green : job.failed ? C.red : C.gold;
  return (
    <div style={{
      display: "flex", alignItems: "baseline", gap: 10,
      padding: "5px 0", borderBottom: `1px solid ${C.panel}`,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0 }} />
      <span style={{ fontSize: 12, color: C.white, minWidth: 108, fontWeight: 600 }}>
        {job.label}
      </span>
      <span style={{ fontSize: 11, color: C.mid, minWidth: 92 }}>
        {job.age_seconds != null ? fmtAge(job.age_seconds) : "never"}
      </span>
      <span style={{ fontSize: 10, color, minWidth: 58 }}>{job.result}</span>
      <span style={{ fontSize: 10, color: C.muted, flex: 1 }} title={job.note}>
        {job.why}
      </span>
    </div>
  );
}

function SystemHealthPanel({ obs, error }) {
  // `obs.heartbeat` is still in the payload but is not read here: it tracked
  // the retired quantos-agent and has been null since 2026-07-27.
  const jobs = obs?.scheduled_jobs;
  const jobList = jobs?.jobs ?? [];
  const okCount = jobs?.ok_count ?? 0;
  const allOk = jobs?.available && jobList.length > 0 && okCount === jobList.length;
  const counts = obs?.signal_counts_today ?? {};
  const wl = obs?.webhook_latency ?? {};
  const cl = obs?.claude_latency ?? {};
  const spend = obs?.claude_spend_today ?? {};
  const hbColor = allOk ? C.green : jobs?.available ? C.gold : C.muted;

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Label color={C.accent}>System Health</Label>
        <span style={{ fontSize: 10, color: hbColor, fontWeight: 600 }}>
          {error ? "offline"
            : !jobs?.available ? "job status unavailable"
            : `${okCount}/${jobList.length} scheduled jobs healthy`}
        </span>
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
        <Metric
          label="Daily Jobs"
          value={jobs?.available ? `${okCount}/${jobList.length}` : "—"}
          color={hbColor}
          sub={jobs?.available ? "firing on schedule" : "systemd not readable"}
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

      {jobList.length > 0 && (
        <>
          <Divider />
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <Label>Scheduled Jobs</Label>
            <span style={{ fontSize: 9, color: C.muted }}>
              last fired · systemd result · verdict
            </span>
          </div>
          <div style={{ marginTop: 6 }}>
            {jobList.map(j => <JobRow key={j.key} job={j} />)}
          </div>
        </>
      )}

      {jobs && !jobs.available && (
        <>
          <Divider />
          <div style={{ fontSize: 11, color: C.muted }}>{jobs.reason}</div>
        </>
      )}

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

function TopBar({ lastRefresh, jobs, obsError }) {
  // Reads the scheduled timers, not the retired agent's heartbeat. This said
  // "NO AGENT" in red continuously from 2026-07-27 — when quantos-agent was
  // mothballed and nothing replaced its sync — while four timers ran the
  // daily work. A permanently red light is one nobody reads.
  const list = jobs?.jobs ?? [];
  const okCount = jobs?.ok_count ?? 0;
  const stale = obsError || !jobs?.available || okCount < list.length;
  const dotColor = obsError || (jobs?.available && okCount === 0) ? C.red
    : stale ? C.gold : C.green;
  const statusText = obsError ? "API DOWN"
    : !jobs?.available ? "JOBS UNKNOWN"
    : list.length === 0 ? "NO JOBS"
    : okCount === list.length ? "LIVE"
    : `${okCount}/${list.length} JOBS`;
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
  // Wall clock as state, so anything deriving an age stays pure.
  const [nowMs, setNowMs] = useState(() => Date.now());
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
  // The brief's universe is separate from the tab strip's selection: the strip
  // picks WHICH VIEW, and inside the brief view its own row of buttons picks
  // which universe to diff. Folding them together would have made the brief a
  // fourth universe, which it is not.
  const [briefUniverse, setBriefUniverse] = useState("nifty500");
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
    // Not a fourth universe — a different question about the same three.
    // The tabs above answer "where does each name rank today"; this one
    // answers "what moved since the last session", which no ranked table can
    // show. `entries: []` because it renders its own body (see the
    // current.kind === "brief" branch) and never touches the shared table.
    {
      key: "brief", kind: "brief", label: "Morning Brief",
      universeName: "Day-over-day transitions",
      entries: [], updatedAt: null, error: false,
    },
  ]), [shortlistAlpha50, shortlistMomentum30, nifty500Top10, shortlistNifty500.updatedAt, shortlistNifty500.error]);
  // Same 36h daily-cadence window cloud/api/observability_routes.py's
  // heartbeat uses — one missed day doesn't false-alarm, two does.
  const shortlistFreshness = useMemo(() => {
    const timestamps = [shortlistAlpha50.updatedAt, shortlistMomentum30.updatedAt, shortlistNifty500.updatedAt]
      .filter(Boolean).map(t => new Date(t).getTime());
    if (timestamps.length === 0) return { live: false, label: null };
    const freshest = Math.max(...timestamps);
    const ageSeconds = (nowMs - freshest) / 1000;
    return {
      live: ageSeconds < 36 * 3600,
      label: `last scan ${fmtAge(ageSeconds)}`,
    };
    // `nowMs` is a dependency, not decoration: this read Date.now() during
    // render, which meant the memo only recomputed when a shortlist timestamp
    // CHANGED -- so "last scan 2m ago" stayed frozen at 2m for the rest of the
    // day. Ticking it off the same 60s clock the header uses makes the label
    // count up the way it always claimed to.
  }, [nowMs, shortlistAlpha50.updatedAt, shortlistMomentum30.updatedAt, shortlistNifty500.updatedAt]);
  const [obs, setObs] = useState(null);
  const [obsError, setObsError] = useState(false);

  useEffect(() => {
    const fmt = new Intl.DateTimeFormat("en-IN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
    const tick = () => {
      setLastRefresh(fmt.format(new Date()));
      setNowMs(Date.now());
    };
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

      <TopBar lastRefresh={lastRefresh} jobs={obs?.scheduled_jobs} obsError={obsError} />

      <div style={{ padding: "20px 24px" }}>
        {/* Row 0: System health (real data — S5-6 observability) */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16, marginBottom: 16 }}>
          <PanelBoundary name="System Health">
            <SystemHealthPanel obs={obs} error={obsError} />
          </PanelBoundary>
        </div>

        {/* Row 1: Market Snapshot · Greeks */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16, marginBottom: 16,
        }}>
          <PanelBoundary name="Market Snapshot">
            <MarketSnapshotPanel
              snapshot={marketSnapshot}
              error={marketSnapshot.error}
              shortlistFreshness={shortlistFreshness}
            />
          </PanelBoundary>
          <PanelBoundary name="Greeks">
            <GreeksPanel />
          </PanelBoundary>
        </div>

        {/* Row 2: Signals · Morning Shortlist */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16, marginBottom: 16,
        }}>
          <PanelBoundary name="Signal Feed">
            <SignalFeed signals={signals.list} error={signals.error} />
          </PanelBoundary>
          <PanelBoundary name="Morning Shortlist">
            <ScreenerPanel candidates={screener} />
          </PanelBoundary>
        </div>

        {/* Row 3: Momentum + Base Quality Shortlist (discretionary review) —
            replaced Alpha-vs-Nifty, Open Positions, and Claude Analyst
            2026-07-29, all three either dead placeholders or unused. Three
            universes (Alpha 50 / Momentum 30 / Nifty 500), tabbed instead of
            stacked as of 2026-08-05. */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16 }}>
          <PanelBoundary name="Momentum Shortlist">
            <MomentumShortlistTabs
              tabs={shortlistTabs} active={shortlistTab} onSelect={setShortlistTab}
              briefUniverse={briefUniverse} onBriefUniverse={setBriefUniverse}
            />
          </PanelBoundary>
        </div>
      </div>
    </div>
  );
}
