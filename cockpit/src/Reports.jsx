// ─── Paper Strategy Reports (#/reports) ─────────────────────────────────────
// Cost-adjusted paper equity curves + trade tables for candidate 18 (ORB) and
// the Darvas ATR-stop, from GET /reports/paper-strategies
// (cloud/api/reports_routes.py). Candidate 18b is deliberately absent: its
// 2026-11-17 gate is decided on P&L and its protocol forbids peeking before
// then. Paper samples are tiny next to the backtests — every card says so, and
// shows the backtest's own numbers beside the paper ones.
// The last card is candidate 18's 1-lot LIVE pilot: real fills vs paper, for
// execution defects -- not an edge measure, and it feeds no verdict.
import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { C, CLOUD_API_URL, Card, Label, PanelBoundary } from "./App.jsx";

const inr = (v, d = 0) => (v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", {
  minimumFractionDigits: d, maximumFractionDigits: d,
})}`);
const signedInr = v => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${inr(Math.abs(v))}`);
const pnlColor = v => (v == null || v === 0 ? C.mid : v > 0 ? C.green : C.red);
const istDateTime = iso => new Date(iso).toLocaleString("en-IN", {
  timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
});
const istDate = iso => new Date(iso).toLocaleDateString("en-IN", {
  timeZone: "Asia/Kolkata", day: "2-digit", month: "short",
});

function usePaperReports() {
  const [state, setState] = useState({ data: null, loading: true, error: false });
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/reports/paper-strategies`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setState({ data, loading: false, error: false });
      } catch {
        if (!cancelled) setState(s => ({ ...s, loading: false, error: true }));
      }
    };
    load();
    const id = setInterval(load, 300000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);
  return state;
}

function Stat({ label, value, color = C.white, sub }) {
  return (
    <div style={{
      background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6,
      padding: "8px 12px", minWidth: 110, flex: "1 1 110px",
    }}>
      <div style={{ fontSize: 9, color: C.muted, textTransform: "uppercase", letterSpacing: 0.8 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color, fontVariantNumeric: "tabular-nums", marginTop: 2 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function CurveTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div style={{
      background: C.panelAlt, border: `1px solid ${C.border}`, borderRadius: 6,
      padding: "6px 10px", fontSize: 11, color: C.white,
    }}>
      <div style={{ color: C.muted }}>{istDateTime(p.t)}</div>
      <div style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{inr(p.equity)}</div>
      <div style={{ color: C.mid }}>{p.label === "start" ? "Starting capital" : `after ${p.label}`}</div>
    </div>
  );
}

function EquityChart({ curve, startingCapital, sizingChanges = [] }) {
  const points = curve.map((p, i) => ({ ...p, i }));
  // A marker sits just before the first trade exiting on/after the change
  // date; changes with no trade after them yet aren't drawn.
  const markers = sizingChanges
    .map(c => ({ ...c, i: points.findIndex(p => p.label !== "start" && p.t.slice(0, 10) >= c.date) }))
    .filter(m => m.i > 0);
  return (
    <div style={{ height: 240, marginTop: 12 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid stroke={C.border} strokeOpacity={0.5} vertical={false} />
          <XAxis dataKey="i" type="number" domain={[0, Math.max(points.length - 1, 1)]}
                 allowDecimals={false} tick={{ fill: C.muted, fontSize: 10 }}
                 tickFormatter={i => (points[i] ? istDate(points[i].t) : "")}
                 stroke={C.border} />
          <YAxis domain={["auto", "auto"]} width={72} tick={{ fill: C.muted, fontSize: 10 }}
                 tickFormatter={v => inr(v)} stroke={C.border} />
          <ReferenceLine y={startingCapital} stroke={C.muted} strokeDasharray="4 4"
                         label={{ value: "start", fill: C.muted, fontSize: 10, position: "insideTopLeft" }} />
          {markers.map(m => (
            <ReferenceLine key={m.date} x={m.i - 0.5} stroke={C.gold} strokeDasharray="2 3"
                           label={{ value: m.label, fill: C.gold, fontSize: 10, position: "insideTopRight" }} />
          ))}
          <Tooltip content={<CurveTooltip />} cursor={{ stroke: C.mid, strokeDasharray: "3 3" }} />
          <Line type="stepAfter" dataKey="equity" stroke={C.accent} strokeWidth={2}
                dot={{ r: 4, fill: C.accent, stroke: C.panel, strokeWidth: 2 }}
                activeDot={{ r: 5, fill: C.accent, stroke: C.panel, strokeWidth: 2 }}
                isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

const th = { textAlign: "left", fontSize: 9, color: C.muted, fontWeight: 700, textTransform: "uppercase",
             letterSpacing: 0.6, padding: "6px 8px", borderBottom: `1px solid ${C.border}` };
const td = { fontSize: 11, color: C.white, padding: "6px 8px", borderBottom: `1px solid ${C.border}`,
             fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" };

function TradeTable({ trades, kind }) {
  return (
    <div style={{ overflowX: "auto", marginTop: 12 }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={th}>Exit</th>
            <th style={th}>{kind === "orb" ? "Leg" : "Symbol"}</th>
            <th style={th}>Qty</th>
            <th style={th}>Entry</th>
            <th style={th}>Exit</th>
            <th style={th}>Reason</th>
            <th style={th}>Gross</th>
            <th style={th}>Costs</th>
            <th style={th}>Net</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={`${t.label}-${t.exit_timestamp}-${i}`}>
              <td style={{ ...td, color: C.mid }}>{istDateTime(t.exit_timestamp)}</td>
              <td style={td}>
                {t.label}
                {t.expiry_day && <span style={{ color: C.gold, fontSize: 9, marginLeft: 6 }}>EXPIRY</span>}
              </td>
              <td style={td}>{t.quantity}</td>
              <td style={td}>{t.entry_price.toFixed(2)}</td>
              <td style={td}>{t.exit_price.toFixed(2)}</td>
              <td style={{ ...td, color: C.mid }}>
                {t.exit_reason.replace(/_/g, " ")}
                {t.premium_stop_missed && <span style={{ color: C.gold, fontSize: 9, marginLeft: 6 }}>NO PREM STOP</span>}
              </td>
              <td style={{ ...td, color: pnlColor(t.gross_pnl) }}>{signedInr(t.gross_pnl)}</td>
              <td style={{ ...td, color: C.mid }}>{inr(t.costs)}</td>
              <td style={{ ...td, color: pnlColor(t.net_pnl), fontWeight: 700 }}>{signedInr(t.net_pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StrategyReport({ report, kind, emptyNote }) {
  if (report?.error) {
    return (
      <Card>
        <Label color={C.accent}>{kind === "orb" ? "Candidate 18 — ORB" : "Darvas ATR-stop"}</Label>
        <div style={{ fontSize: 12, color: C.red, marginTop: 10 }}>Report failed: {report.error}</div>
      </Card>
    );
  }
  const s = report.summary;
  const bt = report.backtest;
  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Label color={C.accent}>{report.name}</Label>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: 0.8, padding: "2px 6px", borderRadius: 4,
          color: report.dry_run === false ? C.red : C.gold,
          border: `1px solid ${report.dry_run === false ? C.red : C.gold}`,
        }}>
          {report.dry_run === false ? "LIVE" : "PAPER"}
        </span>
      </div>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>
        Net of costs: {report.cost_basis}. Equity = {inr(s.starting_capital)} + closed-trade net P&L.
      </div>

      <div style={{
        fontSize: 11, color: C.gold, marginTop: 10, padding: "6px 10px",
        border: `1px solid ${C.gold}55`, borderRadius: 6, background: `${C.gold}10`,
      }}>
        N = {s.trades} paper trade{s.trades === 1 ? "" : "s"} vs {bt.trades.toLocaleString("en-IN")} in the
        backtest. Too few to confirm or contradict the edge; this watches the plumbing and costs, not the verdict.
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <Stat label="Equity" value={inr(s.equity)}
              sub={s.return_pct == null ? null : `${s.return_pct > 0 ? "+" : ""}${s.return_pct.toFixed(2)}%`} />
        <Stat label="Net P&L" value={signedInr(s.net_pnl)} color={pnlColor(s.net_pnl)}
              sub={`gross ${signedInr(s.gross_pnl)}`} />
        {report.premium_stop_missed > 0 && report.summary_stop_enforced && (
          <Stat label="Net · stop enforced" value={signedInr(report.summary_stop_enforced.net_pnl)}
                color={pnlColor(report.summary_stop_enforced.net_pnl)}
                sub={`PF ${report.summary_stop_enforced.profit_factor ?? "—"} · used for go-live`} />
        )}
        <Stat label="Costs" value={inr(s.costs)} color={C.mid} />
        <Stat label="Trades" value={s.trades}
              sub={report.unpriced ? `+${report.unpriced} unpriced exit${report.unpriced === 1 ? "" : "s"}` : null} />
        <Stat label="Win rate" value={s.win_rate_pct == null ? "—" : `${s.win_rate_pct}%`} />
        <Stat label="Profit factor" value={s.profit_factor ?? "—"} />
        <Stat label="Max drawdown" value={inr(s.max_drawdown)} color={s.max_drawdown > 0 ? C.red : C.mid} />
      </div>

      <div style={{ fontSize: 10, color: C.muted, marginTop: 8 }}>
        Backtest ({bt.source}):{" "}
        {bt.rows.map(r => `${r.label} ${r.trades} trades, ${r.win_rate_pct}% win, PF ${r.profit_factor}`).join(" · ")}
      </div>

      {report.sizing_changes?.map(c => (
        <div key={c.date} style={{ fontSize: 10, color: C.gold, marginTop: 4 }}>
          Sizing change from {c.date}: {c.label}. Earlier trades were sized differently; the curve uses the current starting capital.
        </div>
      ))}

      {report.premium_stop_missed > 0 && (
        <div style={{ fontSize: 10, color: C.gold, marginTop: 4 }}>
          {report.premium_stop_missed} trade{report.premium_stop_missed === 1 ? "" : "s"} marked NO PREM STOP fell through the 25% premium stop,
          which paper did not enforce before 2026-09-30 (live, a resting stop order would have closed it near the trigger). The curve and table show them as logged; "Net · stop enforced" re-marks them at the trigger and is the figure the go-live call uses (pre-registered 2026-09-30).
        </div>
      )}

      {report.unpriced > 0 && (
        <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>
          {report.unpriced} exit{report.unpriced === 1 ? "" : "s"} had no quote (Fyers rate limit) and {report.unpriced === 1 ? "is" : "are"} left
          out of the curve rather than guessed.
        </div>
      )}

      {s.trades === 0 ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 14 }}>{emptyNote}</div>
      ) : (
        <>
          <EquityChart curve={report.curve} startingCapital={s.starting_capital}
                       sizingChanges={report.sizing_changes} />
          <TradeTable trades={report.trades} kind={kind} />
        </>
      )}
    </Card>
  );
}

// ─── 1-lot LIVE pilot (candidate 18, from 2026-10-01) ──────────────────────
// Real fills, matched to paper 18's trade on the same day. What matters here is
// the gap between live execution and paper (shortfall, exit paths, anomalies),
// not the P&L, which at 1 lot and a handful of trades says nothing about edge.
function PilotReport({ report }) {
  if (report?.error) {
    return (
      <Card>
        <Label color={C.accent}>Candidate 18 — 1-lot LIVE pilot</Label>
        <div style={{ fontSize: 12, color: C.red, marginTop: 10 }}>Report failed: {report.error}</div>
      </Card>
    );
  }
  const s = report.summary;
  const status = report.halted ? "HALTED" : !report.enabled ? "OFF"
    : report.dry_run === false ? "LIVE" : "REHEARSAL";
  const statusColor = status === "LIVE" || status === "HALTED" ? C.red : status === "OFF" ? C.muted : C.gold;
  const hasTrades = s.trades > 0;
  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Label color={C.accent}>{report.name}</Label>
        <span style={{
          fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
          color: statusColor, border: `1px solid ${statusColor}`,
        }}>{status}</span>
      </div>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>
        Net of: {report.cost_basis}. Curve = cumulative net P&L from ₹0.
      </div>

      <div style={{
        fontSize: 11, color: C.gold, marginTop: 10, padding: "6px 10px",
        border: `1px solid ${C.gold}55`, borderRadius: 6, background: `${C.gold}10`,
      }}>
        Execution test, not an edge measurement. This P&L does not feed candidate 18's go-live figure or
        18b's verdict. Read the shortfall vs paper, the exit paths and the anomalies.
      </div>

      {report.halted && (
        <div style={{
          marginTop: 10, padding: "6px 10px", borderRadius: 6, fontSize: 11, color: C.white,
          border: `1px solid ${C.red}`, background: `${C.red}22`,
        }}>
          <b style={{ color: C.red }}>PILOT HALTED</b> — no new entries; open positions are still managed to
          their exit. {report.halted} Review below, then reset with
          <code> python scripts/pilot_guard.py --reset</code> on the VM.
        </div>
      )}
      {report.limits && (
        <div style={{ fontSize: 10, color: C.muted, marginTop: 6 }}>
          Breaker: any anomaly, a trade {inr(report.limits.shortfall_limit_rs)}+ worse than paper, or net
          −{inr(report.limits.budget_rs)} since the last reset stops new entries.
        </div>
      )}

      {report.anomalies?.length > 0 && (
        <div style={{
          marginTop: 10, padding: "6px 10px", borderRadius: 6,
          border: `1px solid ${C.red}66`, background: `${C.red}12`,
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.red, marginBottom: 4 }}>
            {report.anomalies.length} ANOMAL{report.anomalies.length === 1 ? "Y" : "IES"} — possible live-only defect
          </div>
          {report.anomalies.map((a, i) => (
            <div key={i} style={{ fontSize: 10, color: C.white, marginTop: 2 }}>• {a}</div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <Stat label="Net P&L" value={signedInr(s.net_pnl)} color={pnlColor(s.net_pnl)}
              sub={`gross ${signedInr(s.gross_pnl)} · costs ${inr(s.costs)}`} />
        <Stat label="Trades" value={s.trades}
              sub={report.open_positions?.length ? `${report.open_positions.length} open now` : null} />
        <Stat label="Avg shortfall vs paper"
              value={report.avg_shortfall_vs_paper == null ? "—" : signedInr(report.avg_shortfall_vs_paper)}
              color={report.avg_shortfall_vs_paper > 0 ? C.red : C.mid}
              sub={`per trade · ${report.matched_to_paper} matched · + = live worse`} />
        <Stat label="Exit paths" value={Object.keys(report.exit_reasons || {}).length || "—"}
              sub={Object.entries(report.exit_reasons || {})
                .map(([r, n]) => `${r.replace(/_/g, " ")} ${n}`).join(" · ") || null} />
      </div>

      {report.open_positions?.map(p => (
        <div key={p.underlying} style={{ fontSize: 10, color: p.stop_resting ? C.mid : C.red, marginTop: 6 }}>
          Open: {p.underlying} since {istDateTime(p.since)} @ {p.entry_price ?? "—"} ·
          {p.stop_resting ? " stop resting at broker" : " NO STOP RESTING"}
        </div>
      ))}

      {!hasTrades ? (
        <div style={{ fontSize: 12, color: C.muted, marginTop: 14 }}>
          No closed live pilot trades yet{status === "OFF" ? " (the pilot is not enabled)" : ""}.
        </div>
      ) : (
        <>
          <EquityChart curve={report.curve} startingCapital={0} />
          <div style={{ overflowX: "auto", marginTop: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={th}>Exit</th><th style={th}>Leg</th><th style={th}>Qty</th>
                  <th style={th}>Quote → fill</th><th style={th}>Exit fill</th><th style={th}>Reason</th>
                  <th style={th}>Net</th><th style={th}>Paper entry / exit</th><th style={th}>Shortfall</th>
                </tr>
              </thead>
              <tbody>
                {report.trades.map((t, i) => (
                  <tr key={`${t.label}-${t.exit_timestamp}-${i}`}>
                    <td style={{ ...td, color: C.mid }}>{istDateTime(t.exit_timestamp)}</td>
                    <td style={td}>{t.label}</td>
                    <td style={td}>{t.quantity}</td>
                    <td style={td}>{t.entry_quote?.toFixed(2) ?? "—"} → {t.entry_price.toFixed(2)}</td>
                    <td style={td}>{t.exit_price.toFixed(2)}</td>
                    <td style={{ ...td, color: C.mid }}>{t.exit_reason.replace(/_/g, " ")}</td>
                    <td style={{ ...td, color: pnlColor(t.net_pnl), fontWeight: 700 }}>{signedInr(t.net_pnl)}</td>
                    <td style={{ ...td, color: C.mid }}>
                      {t.paper_entry == null ? "no paper trade"
                        : `${t.paper_entry.toFixed(2)} / ${t.paper_exit?.toFixed(2) ?? "—"} (${(t.paper_reason || "").replace(/_/g, " ")})`}
                    </td>
                    <td style={{ ...td, color: t.shortfall_vs_paper > 0 ? C.red : C.mid }}>
                      {signedInr(t.shortfall_vs_paper)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}

export default function ReportsPage() {
  const { data, loading, error } = usePaperReports();
  return (
    <div style={{
      background: C.bg, minHeight: "100vh", color: C.white,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    }}>
      <style>{`* { box-sizing: border-box; margin: 0; padding: 0; }`}</style>
      <div style={{
        background: C.panel, borderBottom: `1px solid ${C.border}`,
        padding: "10px 24px", display: "flex", alignItems: "center", gap: 20,
      }}>
        <a href="#/" style={{ fontSize: 11, color: C.accent, textDecoration: "none", fontWeight: 700 }}>
          ← Dashboard
        </a>
        <div style={{ width: 1, height: 18, background: C.border }} />
        <span style={{ fontSize: 14, fontWeight: 900, letterSpacing: 1.5 }}>PAPER STRATEGY REPORTS</span>
        <span style={{ marginLeft: "auto", fontSize: 10, color: C.muted }}>
          Candidate 18b hidden until its 2026-11-17 gate (no-peeking rule)
        </span>
      </div>

      <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
        {loading && <div style={{ fontSize: 12, color: C.muted }}>Loading…</div>}
        {error && !loading && <div style={{ fontSize: 12, color: C.red }}>Could not reach cloud API.</div>}
        {data && (
          <>
            <PanelBoundary name="ORB report">
              <StrategyReport report={data.orb} kind="orb" emptyNote="No closed paper trades yet." />
            </PanelBoundary>
            <PanelBoundary name="Darvas report">
              <StrategyReport report={data.darvas} kind="darvas"
                emptyNote="No closed paper trades yet. Open positions are on the dashboard's Darvas ATR-Stop panel; a trade appears here once its stop or target is hit." />
            </PanelBoundary>
            {data.pilot && (
              <PanelBoundary name="Live pilot report">
                <PilotReport report={data.pilot} />
              </PanelBoundary>
            )}
          </>
        )}
      </div>
    </div>
  );
}
