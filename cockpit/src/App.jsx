import { useState, useEffect, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";

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
// .env.example. System Health (S5-6), Discovery Watchlist, and Signal Feed are
// wired to real cloud data; Positions/Greeks/Alpha Curve/Screener are still
// mock (need agent→cloud sync plumbing that doesn't exist yet).
const CLOUD_API_URL = import.meta.env.VITE_CLOUD_API_URL
  || "https://web-production-b5527.up.railway.app";

// ─── Mock data (real app fetches from cloud API) ───────────────────────────
const MOCK_REGIME = {
  regime: "TRENDING_BULL",
  confidence: 83,
  trend_signal: "BULL",
  vix_signal: "LOW",
  breadth_signal: "STRONG",
  advance_count: 312,
  decline_count: 168,
  unchanged_count: 8,
  ad_ratio: 1.86,
  darvas_enabled: true,
  allowed_strategies: ["darvas_breakout", "bull_call_spread", "covered_call"],
};

const MOCK_ALPHA_CURVE = Array.from({ length: 30 }, (_, i) => ({
  day: `D${i + 1}`,
  quantos: +(Math.random() * 2 + i * 0.25).toFixed(2),
  nifty: +(Math.random() * 1.5 + i * 0.15).toFixed(2),
}));

const MOCK_GREEKS = {
  net_delta: -0.08,
  net_gamma: 0.0012,
  net_theta: 48.50,
  net_vega: -6.20,
  is_theta_positive: true,
};

// ─── Helpers ──────────────────────────────────────────────────────────────

// Morning Shortlist derives from the Discovery Watchlist (Stage A) rather
// than the older CSV-upload screener pipeline (core/screener/ranker.py),
// which has no automated daily feed — this stays fully live with no manual
// upload step. "score" is the real R:R ratio, not a fabricated composite.
const SHORTLIST_TIER_PRIORITY = { HOT: 3, WARM: 2, "VOL-SURGE": 1.5, WATCH: 1 };

function buildMorningShortlist(entries) {
  return entries
    .filter(e => e.status === "APPROACHING" || e.status === "FRESH BREAKOUT")
    .sort((a, b) => {
      const tierDiff = (SHORTLIST_TIER_PRIORITY[b.alert_tier] ?? 0)
        - (SHORTLIST_TIER_PRIORITY[a.alert_tier] ?? 0);
      if (tierDiff !== 0) return tierDiff;
      return (a.dist_to_ceil ?? 999) - (b.dist_to_ceil ?? 999);
    })
    .slice(0, 5)
    .map((e, i) => ({
      rank: i + 1,
      symbol: e.symbol,
      score: e.rr_ratio != null ? Math.round(e.rr_ratio * 10) / 10 : "—",
      rationale: [
        e.status,
        e.alert_tier || null,
        e.dist_to_ceil != null ? `${e.dist_to_ceil.toFixed(1)}% from ceiling` : null,
      ].filter(Boolean).join(" · "),
    }));
}

const fmt = (n, dp = 2) => n?.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp }) ?? "—";
const fmtPct = n => n != null ? `${n > 0 ? "+" : ""}${n.toFixed(2)}%` : "—";
const fmtINR = n => n != null ? `₹${fmt(n, 0)}` : "—";
const fmtMs = n => n != null ? `${Math.round(n)} ms` : "—";
const fmtAge = s => {
  if (s == null) return "never";
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
};

const regimeColor = r => ({
  TRENDING_BULL: C.green, TRENDING_BEAR: C.red,
  RANGING: C.gold, VOLATILE: "#F97316", UNCERTAIN: C.muted,
})[r] ?? C.muted;

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

function RegimePanel({ regime }) {
  const color = regimeColor(regime.regime);
  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <Label color={C.accent}>Market Regime</Label>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
        <div style={{
          width: 10, height: 10, borderRadius: "50%", background: color,
          boxShadow: `0 0 8px ${color}`,
        }} />
        <span style={{ fontSize: 20, fontWeight: 700, color: C.white }}>
          {regime.regime.replace("_", " ")}
        </span>
        <span style={{ fontSize: 13, color: C.muted, marginLeft: "auto" }}>
          {regime.confidence}% confidence
        </span>
      </div>
      <Divider />
      <div style={{ display: "flex", gap: 24 }}>
        {[
          { label: "Trend", val: regime.trend_signal },
          { label: "VIX", val: regime.vix_signal },
          { label: "Darvas", val: regime.darvas_enabled ? "✅ Active" : "❌ Gated" },
        ].map(({ label, val }) => (
          <div key={label}>
            <Label>{label}</Label>
            <div style={{ fontSize: 13, color: C.mid, marginTop: 2 }}>{val}</div>
          </div>
        ))}
      </div>
      {(regime.advance_count > 0 || regime.decline_count > 0) && (
        <>
          <Divider />
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Label>Breadth</Label>
            <span style={{ fontSize: 13, fontWeight: 600, color: C.green }}>
              {regime.advance_count} ▲
            </span>
            <span style={{ fontSize: 13, color: C.muted }}>/</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: C.red }}>
              {regime.decline_count} ▼
            </span>
            {regime.unchanged_count > 0 && (
              <span style={{ fontSize: 11, color: C.muted }}>
                · {regime.unchanged_count} unch
              </span>
            )}
            <span style={{ fontSize: 12, color: C.mid, marginLeft: "auto" }}>
              A/D {(regime.ad_ratio ?? (regime.advance_count / (regime.decline_count || 1))).toFixed(2)}
              {regime.breadth_signal ? ` · ${regime.breadth_signal}` : ""}
            </span>
          </div>
        </>
      )}
      <Divider />
      <Label>Active Strategies</Label>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
        {regime.allowed_strategies.map(s => (
          <span key={s} style={{
            fontSize: 10, padding: "3px 8px", borderRadius: 4,
            background: C.bg, border: `1px solid ${C.border}`, color: C.mid,
          }}>{s.replace(/_/g, " ")}</span>
        ))}
      </div>
    </Card>
  );
}

function GreeksPanel({ greeks }) {
  const items = [
    { label: "Δ Delta", val: greeks.net_delta, fmt: v => `${v > 0 ? "+" : ""}${v.toFixed(3)}` },
    { label: "Γ Gamma", val: greeks.net_gamma, fmt: v => `${v > 0 ? "+" : ""}${v.toFixed(5)}` },
    { label: "Θ Theta", val: greeks.net_theta, fmt: v => `₹${v > 0 ? "+" : ""}${v.toFixed(0)}/d` },
    { label: "Vega", val: greeks.net_vega, fmt: v => `${v > 0 ? "+" : ""}${v.toFixed(2)}` },
  ];
  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <Label color={C.purple}>Portfolio Greeks</Label>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 4 }}>
        {items.map(({ label, val, fmt: f }) => (
          <div key={label} style={{
            background: C.bg, borderRadius: 6, padding: "10px 12px",
            border: `1px solid ${C.border}`,
          }}>
            <Label color={C.muted}>{label}</Label>
            <div style={{
              fontSize: 16, fontWeight: 700, marginTop: 4,
              color: val > 0 ? C.green : val < 0 ? C.red : C.mid,
            }}>{f(val)}</div>
          </div>
        ))}
      </div>
      <div style={{
        marginTop: 4, padding: "8px 10px", borderRadius: 6,
        background: greeks.is_theta_positive ? `${C.green}20` : `${C.red}20`,
        border: `1px solid ${greeks.is_theta_positive ? C.green : C.red}40`,
        fontSize: 12, color: greeks.is_theta_positive ? C.green : C.red,
        fontWeight: 600,
      }}>
        {greeks.is_theta_positive ? "✅ Collecting theta" : "⚠️ Paying theta"}
      </div>
    </Card>
  );
}

function AlphaCurve({ data }) {
  const latest = data[data.length - 1] || {};
  const alpha = ((latest.quantos || 0) - (latest.nifty || 0)).toFixed(2);
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Label color={C.accent}>Alpha vs Nifty</Label>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: alpha >= 0 ? C.green : C.red }}>
            {alpha >= 0 ? "+" : ""}{alpha}%
          </div>
          <div style={{ fontSize: 10, color: C.muted }}>cumulative alpha</div>
        </div>
      </div>
      <div style={{ height: 140, marginTop: 12 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
            <XAxis dataKey="day" hide />
            <YAxis tickFormatter={v => `${v}%`} tick={{ fill: C.muted, fontSize: 10 }}
                   width={40} />
            <Tooltip
              contentStyle={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6 }}
              labelStyle={{ color: C.muted, fontSize: 11 }}
              formatter={(v, name) => [`${v}%`, name === "quantos" ? "QuantOS" : "Nifty"]}
            />
            <ReferenceLine y={0} stroke={C.border} />
            <Line type="monotone" dataKey="quantos" stroke={C.accent} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="nifty" stroke={C.muted} strokeWidth={1.5}
                  strokeDasharray="4 2" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
        {[
          { color: C.accent, label: "QuantOS" },
          { color: C.muted, label: "Nifty 50" },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 14, height: 2, background: color }} />
            <span style={{ fontSize: 10, color: C.muted }}>{label}</span>
          </div>
        ))}
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
                <div style={{ fontWeight: 700, color: C.white, fontSize: 14 }}>
                  {sig.symbol}
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

function PositionsTable({ positions, error }) {
  const totalPnl = positions.reduce((s, p) => s + p.pnl, 0);
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Label color={C.accent}>Open Positions</Label>
        {positions.length > 0 && (
          <div style={{
            fontSize: 14, fontWeight: 700,
            color: totalPnl >= 0 ? C.green : C.red,
          }}>
            {totalPnl >= 0 ? "+" : ""}₹{fmt(Math.abs(totalPnl), 0)} today
          </div>
        )}
      </div>
      {positions.length === 0 ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>
          {error ? "Could not reach cloud API." : "No open positions."}
        </div>
      ) : (
      <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Symbol", "Qty", "Entry", "LTP", "P&L", "%"].map(h => (
              <th key={h} style={{
                textAlign: h === "Symbol" ? "left" : "right",
                fontSize: 10, fontWeight: 600, letterSpacing: 1.2,
                color: C.muted, padding: "4px 6px", borderBottom: `1px solid ${C.border}`,
                textTransform: "uppercase",
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map(p => (
            <tr key={p.symbol}>
              <td style={{ padding: "8px 6px", color: C.white, fontWeight: 600 }}>
                {p.symbol}
              </td>
              <td style={{ padding: "8px 6px", textAlign: "right", color: C.mid }}>{p.qty}</td>
              <td style={{ padding: "8px 6px", textAlign: "right", color: C.mid }}>
                {fmtINR(p.entry)}
              </td>
              <td style={{ padding: "8px 6px", textAlign: "right", color: C.white }}>
                {fmtINR(p.ltp)}
              </td>
              <td style={{
                padding: "8px 6px", textAlign: "right", fontWeight: 600,
                color: p.pnl >= 0 ? C.green : C.red,
              }}>
                {p.pnl >= 0 ? "+" : ""}₹{fmt(Math.abs(p.pnl), 0)}
              </td>
              <td style={{
                padding: "8px 6px", textAlign: "right", fontWeight: 600,
                color: p.pnl_pct >= 0 ? C.green : C.red,
              }}>
                {fmtPct(p.pnl_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
    </Card>
  );
}

function ScreenerPanel({ candidates }) {
  return (
    <Card>
      <Label color={C.gold}>Morning Shortlist</Label>
      {candidates.length === 0 ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>
          Nothing approaching a breakout right now.
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
              <span style={{ fontWeight: 700, color: C.white }}>{c.symbol}</span>
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

const tierColor = t => ({
  HOT: C.red, WARM: C.gold, WATCH: C.mid, "VOL-SURGE": C.purple,
})[t] ?? C.muted;

const discoveryStatusColor = s => ({
  "FRESH BREAKOUT": C.green, APPROACHING: C.gold, WATCHING: C.accent,
  "BOX FORMING": C.muted, POSITION_OPEN: C.purple,
})[s] ?? C.muted;

function DiscoveryWatchlistPanel({ entries, updatedAt, error }) {
  const today = new Date().toISOString().slice(0, 10);
  const firedToday = entries.filter(e => e.last_fired_date === today);

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Label color={C.gold}>Discovery Watchlist</Label>
        <span style={{ fontSize: 10, color: C.muted }}>
          {error ? "offline"
            : updatedAt ? `synced ${new Date(updatedAt).toLocaleTimeString("en-IN", { hour12: false })}`
            : "waiting for agent…"}
        </span>
      </div>

      {entries.length === 0 ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>
          {error ? "Could not reach cloud API." : "No candidates yet — Stage A runs once/day."}
        </div>
      ) : (
        <table style={{ width: "100%", marginTop: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Symbol", "Status", "Tier", "Ceiling", "Dist%", "R:R"].map(h => (
                <th key={h} style={{
                  textAlign: (h === "Symbol" || h === "Status") ? "left" : "right",
                  fontSize: 10, fontWeight: 600, letterSpacing: 1.2,
                  color: C.muted, padding: "4px 6px", borderBottom: `1px solid ${C.border}`,
                  textTransform: "uppercase",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map(e => (
              <tr key={e.symbol}>
                <td style={{ padding: "8px 6px", color: C.white, fontWeight: 600 }}>{e.symbol}</td>
                <td style={{ padding: "8px 6px", color: discoveryStatusColor(e.status), fontSize: 11 }}>
                  {e.status}
                </td>
                <td style={{ padding: "8px 6px" }}>
                  {e.alert_tier && (
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                      color: tierColor(e.alert_tier), background: `${tierColor(e.alert_tier)}20`,
                      border: `1px solid ${tierColor(e.alert_tier)}40`,
                    }}>{e.alert_tier}</span>
                  )}
                </td>
                <td style={{ padding: "8px 6px", textAlign: "right", color: C.mid }}>
                  {fmtINR(e.box_ceiling)}
                </td>
                <td style={{ padding: "8px 6px", textAlign: "right", color: C.mid }}>
                  {e.dist_to_ceil != null ? fmtPct(e.dist_to_ceil) : "—"}
                </td>
                <td style={{ padding: "8px 6px", textAlign: "right", color: C.mid }}>
                  {e.rr_ratio != null ? e.rr_ratio.toFixed(2) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {firedToday.length > 0 && (
        <>
          <Divider />
          <Label color={C.accent}>Fired Today (Stage B → webhook)</Label>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
            {firedToday.map(e => (
              <div key={e.symbol} style={{ fontSize: 11, color: C.mid }}>
                <span style={{ color: C.white, fontWeight: 600 }}>{e.symbol}</span>
                {" "}confluence={e.last_fired_confluence ?? "—"}
                {" → "}{e.last_fired_signal_id || "—"}
                {" "}({e.last_fired_status || "unknown"})
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

function ClaudeChat() {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "QuantOS analyst ready. Ask me about current signals, regime, or open positions." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(m => [...m, { role: "user", text: userMsg }]);
    setLoading(true);

    try {
      const response = await fetch(`${CLOUD_API_URL}/analyst/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg }),
      });
      const data = await response.json();
      const text = data.reply ?? "Unable to get response.";
      setMessages(m => [...m, { role: "assistant", text }]);
    } catch {
      setMessages(m => [...m, { role: "assistant", text: "Connection error — try again." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Label color={C.purple}>Claude Analyst</Label>
      <div style={{
        flex: 1, overflowY: "auto", marginTop: 10,
        display: "flex", flexDirection: "column", gap: 8,
        maxHeight: 300,
      }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            padding: "8px 10px", borderRadius: 6, fontSize: 12, lineHeight: 1.5,
            ...(m.role === "user"
              ? { background: `${C.purple}20`, border: `1px solid ${C.purple}40`,
                  color: C.white, alignSelf: "flex-end", maxWidth: "85%" }
              : { background: C.bg, border: `1px solid ${C.border}`,
                  color: C.mid, alignSelf: "flex-start", maxWidth: "90%" }
            ),
          }}>{m.text}</div>
        ))}
        {loading && (
          <div style={{ color: C.purple, fontSize: 12, padding: "4px 10px" }}>
            Claude is thinking…
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send()}
          placeholder="Ask Claude about your positions…"
          style={{
            flex: 1, background: C.bg, border: `1px solid ${C.border}`,
            borderRadius: 6, padding: "8px 12px", color: C.white,
            fontSize: 12, outline: "none",
          }}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          style={{
            background: C.purple, color: C.white, border: "none",
            borderRadius: 6, padding: "8px 14px", cursor: "pointer",
            fontSize: 12, fontWeight: 600, opacity: loading ? 0.5 : 1,
          }}
        >→</button>
      </div>
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
  const [regime, setRegime] = useState(MOCK_REGIME);
  const [signals, setSignals] = useState({ list: [], error: false });
  const [positions, setPositions] = useState({ list: [], error: false });
  const [alphaCurve] = useState(MOCK_ALPHA_CURVE);
  const [greeks] = useState(MOCK_GREEKS);
  const [discovery, setDiscovery] = useState({ entries: [], updatedAt: null, error: false });
  const screener = useMemo(() => buildMorningShortlist(discovery.entries), [discovery.entries]);
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

  // The only panel below wired to real data — see cloud/api/discovery_routes.py.
  // Polled rather than pushed since the agent syncs at most once/day (Stage A)
  // plus whenever Stage B fires, not on a fixed schedule.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/discovery/watchlist`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setDiscovery({ entries: data.entries ?? [], updatedAt: data.updated_at, error: false });
        }
      } catch {
        if (!cancelled) setDiscovery(d => ({ ...d, error: true }));
      }
    };
    load();
    const id = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

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

  // Open positions: broker-reported qty/entry/LTP/PnL, see
  // cloud/api/positions_routes.py's GET /positions/status. Polled every 15s
  // to match the trailing-stop check's ~60s push cadence with headroom.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/positions/status`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setPositions({ list: data.positions ?? [], error: false });
      } catch {
        if (!cancelled) setPositions(p => ({ ...p, error: true }));
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Market regime (S5-4): the agent classifies regime locally (only it has a
  // broker, ADR-01) and syncs it here; we poll the read-only mirror. Falls back
  // to MOCK_REGIME until the agent's first sync lands so the panel is never empty.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/regime/status`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled && data && data.regime) setRegime(data);
      } catch {
        /* keep last-known / mock — TopBar's LIVE/STALE badge conveys agent liveness */
      }
    };
    load();
    const id = setInterval(load, 15000);
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
      `}</style>

      <TopBar lastRefresh={lastRefresh} heartbeat={obs?.heartbeat} obsError={obsError} />

      <div style={{ padding: "20px 24px" }}>
        {/* Row 0: System health (real data — S5-6 observability) */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16, marginBottom: 16 }}>
          <SystemHealthPanel obs={obs} error={obsError} />
        </div>

        {/* Row 1: Regime · Greeks · Alpha curve */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 2fr",
          gap: 16, marginBottom: 16,
        }}>
          <RegimePanel regime={regime} />
          <GreeksPanel greeks={greeks} />
          <AlphaCurve data={alphaCurve} />
        </div>

        {/* Row 2: Signals · Positions */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16, marginBottom: 16,
        }}>
          <SignalFeed signals={signals.list} error={signals.error} />
          <PositionsTable positions={positions.list} error={positions.error} />
        </div>

        {/* Row 3: Screener · Claude Chat */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16, marginBottom: 16,
        }}>
          <ScreenerPanel candidates={screener} />
          <ClaudeChat />
        </div>

        {/* Row 4: Discovery Watchlist (Stage A/B two-stage Darvas pipeline) */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16 }}>
          <DiscoveryWatchlistPanel
            entries={discovery.entries}
            updatedAt={discovery.updatedAt}
            error={discovery.error}
          />
        </div>
      </div>
    </div>
  );
}
