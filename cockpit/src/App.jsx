import { useState, useEffect, useCallback } from "react";
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
// .env.example. Everything below except the Discovery Watchlist panel is
// still mock data.
const CLOUD_API_URL = import.meta.env.VITE_CLOUD_API_URL
  || "https://web-production-b5527.up.railway.app";

// ─── Mock data (real app fetches from cloud API) ───────────────────────────
const MOCK_REGIME = {
  regime: "TRENDING_BULL",
  confidence: 83,
  trend_signal: "BULL",
  vix_signal: "LOW",
  darvas_enabled: true,
  allowed_strategies: ["darvas_breakout", "bull_call_spread", "covered_call"],
};

const MOCK_SIGNALS = [
  { signal_id: "SIG-DARV-A1B2C3D4", symbol: "RELIANCE", action: "BUY", price: 2950.50, strategy: "darvas_breakout", confluence_score: 88, confidence_score: 81, status: "PENDING_CONFIRMATION", created_at: "2026-07-02T04:12:00Z" },
  { signal_id: "SIG-DARV-E5F6G7H8", symbol: "TCS", action: "BUY", price: 3820.00, strategy: "darvas_breakout", confluence_score: 74, confidence_score: 68, status: "CONFIRMED", created_at: "2026-07-02T03:55:00Z" },
  { signal_id: "SIG-DARV-I9J0K1L2", symbol: "INFY", action: "BUY", price: 1520.00, strategy: "darvas_breakout", confluence_score: 61, confidence_score: null, status: "REJECTED_LOW_CONFLUENCE", created_at: "2026-07-02T03:30:00Z" },
];

const MOCK_POSITIONS = [
  { symbol: "HDFCBANK", qty: 50, entry: 1680, ltp: 1705, pnl: 1250, pnl_pct: 1.49, strategy: "darvas_breakout" },
  { symbol: "ICICIBANK", qty: 75, entry: 1200, ltp: 1188, pnl: -900, pnl_pct: -1.0, strategy: "darvas_breakout" },
  { symbol: "RELIANCE", qty: 25, entry: 2900, ltp: 2950, pnl: 1250, pnl_pct: 1.72, strategy: "darvas_breakout" },
];

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

const MOCK_SCREENER = [
  { rank: 1, symbol: "RELIANCE", score: 88, rationale: "Clean Darvas box, 1.8× relative volume vs avg" },
  { rank: 2, symbol: "BAJFINANCE", score: 82, rationale: "Daily + 1H confluence, above 200 SMA" },
  { rank: 3, symbol: "TITAN", score: 75, rationale: "Tight consolidation, sector strength" },
];

// ─── Helpers ──────────────────────────────────────────────────────────────

const fmt = (n, dp = 2) => n?.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp }) ?? "—";
const fmtPct = n => n != null ? `${n > 0 ? "+" : ""}${n.toFixed(2)}%` : "—";
const fmtINR = n => n != null ? `₹${fmt(n, 0)}` : "—";

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

function SignalFeed({ signals }) {
  return (
    <Card>
      <Label color={C.accent}>Signal Feed</Label>
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
    </Card>
  );
}

function PositionsTable({ positions }) {
  const totalPnl = positions.reduce((s, p) => s + p.pnl, 0);
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Label color={C.accent}>Open Positions</Label>
        <div style={{
          fontSize: 14, fontWeight: 700,
          color: totalPnl >= 0 ? C.green : C.red,
        }}>
          {totalPnl >= 0 ? "+" : ""}₹{fmt(Math.abs(totalPnl), 0)} today
        </div>
      </div>
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
    </Card>
  );
}

function ScreenerPanel({ candidates }) {
  return (
    <Card>
      <Label color={C.gold}>Morning Shortlist</Label>
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
    { role: "assistant", text: "QuantOS analyst ready. Ask me about current signals, regime, or position sizing." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const send = useCallback(async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(m => [...m, { role: "user", text: userMsg }]);
    setLoading(true);

    try {
      const systemCtx = `You are the QuantOS AI analyst embedded in the trading cockpit. Current regime: TRENDING_BULL (83% confidence). Open positions: HDFCBANK, ICICIBANK, RELIANCE. Be concise and data-driven. Answer questions about signals, positions, regime, options, or strategy sizing in 2-3 sentences max.`;

      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 300,
          system: systemCtx,
          messages: [{ role: "user", content: userMsg }],
        }),
      });
      const data = await response.json();
      const text = data.content?.[0]?.text ?? "Unable to get response.";
      setMessages(m => [...m, { role: "assistant", text }]);
    } catch {
      setMessages(m => [...m, { role: "assistant", text: "Connection error — try again." }]);
    } finally {
      setLoading(false);
    }
  }, [input, loading]);

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

// ─── Top bar ──────────────────────────────────────────────────────────────

function TopBar({ lastRefresh }) {
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
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: C.green,
            animation: "pulse 2s infinite" }} />
          <span style={{ fontSize: 11, color: C.green }}>LIVE</span>
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
  const [regime] = useState(MOCK_REGIME);
  const [signals] = useState(MOCK_SIGNALS);
  const [positions] = useState(MOCK_POSITIONS);
  const [alphaCurve] = useState(MOCK_ALPHA_CURVE);
  const [greeks] = useState(MOCK_GREEKS);
  const [screener] = useState(MOCK_SCREENER);
  const [discovery, setDiscovery] = useState({ entries: [], updatedAt: null, error: false });

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

      <TopBar lastRefresh={lastRefresh} />

      <div style={{ padding: "20px 24px" }}>
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
          <SignalFeed signals={signals} />
          <PositionsTable positions={positions} />
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
