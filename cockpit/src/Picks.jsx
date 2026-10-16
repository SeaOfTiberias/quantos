// ─── Options Picks (#/picks) ────────────────────────────────────────────────
// The evening F&O screener's 5 call and 5 put picks (scripts/run_fno_screener.py),
// each with debit-spread alternatives (core/fno_screener/spreads.py), and what
// every pick did over its next 5 sessions (core/fno_screener/outcomes.py), from
// GET /fno-picks (cloud/api/fno_picks_routes.py).
// The screener is a screening aid with no tested edge. The outcome log is the
// test, so every number carries its N, and returns are close-to-close before
// costs (the spread table shows the quoted bid-ask cost separately).
import { useEffect, useState } from "react";
import { C, CLOUD_API_URL, Card, Label, PanelBoundary } from "./App.jsx";

const inr = v => (v == null ? "—" : `₹${Math.round(Number(v)).toLocaleString("en-IN")}`);
const signedInr = v => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${inr(Math.abs(v))}`);
const pct = (v, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(d)}%`);
const tone = v => (v == null || v === 0 ? C.mid : v > 0 ? C.green : C.red);
const px = v => (v == null ? "—" : Number(v) < 1000 ? Number(v).toFixed(2) : Number(v).toFixed(1));
const shortDate = iso => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", {
  day: "2-digit", month: "short",
}) : "—");
const LABELS = ["near", "mid", "far"];

function useFnoPicks() {
  const [state, setState] = useState({ data: null, loading: true, error: false });
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${CLOUD_API_URL}/fno-picks`);
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

const th = { textAlign: "left", fontSize: 9, color: C.muted, fontWeight: 700, textTransform: "uppercase",
             letterSpacing: 0.6, padding: "6px 8px", borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap" };
const td = { fontSize: 11, color: C.white, padding: "6px 8px", borderBottom: `1px solid ${C.border}`,
             fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" };

// Mirrors core/fno_screener/screener.py's _setup_text.
function setupText(p) {
  const call = p.side === "CE";
  const edge = call ? "box top" : "box floor";
  const level = p.box_level ? px(p.box_level) : "?";
  if (p.breakout_state === "FRESH") return `fresh ${call ? "breakout above" : "breakdown below"} ${edge} ${level}`;
  if (p.breakout_state === "OUT") return `${p.days_out}d ${call ? "above" : "below"} ${edge} ${level}`;
  return `near ${edge} ${level}`;
}

function Agg({ a }) {
  if (!a) return <span style={{ color: C.muted }}>—</span>;
  return (
    <span>
      <span style={{ color: tone(a.mean_pct), fontWeight: 700 }}>{pct(a.mean_pct)}</span>
      <span style={{ color: C.muted }}> · {a.win_pct}% up</span>
    </span>
  );
}

function StatsCard({ stats }) {
  return (
    <Card>
      <Label color={C.accent}>How the picks have done</Label>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>
        Average return after 1, 3 and 5 sessions, close to close, before costs. Single option vs each spread on the
        same picks. Stock move is signed in the pick's direction.
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 12 }}>
        {[["CE", "Calls"], ["PE", "Puts"]].map(([side, name]) => {
          const s = stats?.[side];
          return (
            <div key={side} style={{ flex: "1 1 420px", overflowX: "auto" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: side === "CE" ? C.green : C.red }}>
                {name} · {s?.picks ?? 0} picks, {s?.complete ?? 0} with all 5 sessions
                {s?.median_spread_cost_pct != null && (
                  <span style={{ color: C.muted, fontWeight: 400 }}> · median spread bid-ask {s.median_spread_cost_pct}% of debit</span>
                )}
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 6 }}>
                <thead>
                  <tr>
                    <th style={th}>After</th><th style={th}>N</th><th style={th}>Stock</th>
                    <th style={th}>Single option</th>
                    {LABELS.map(l => <th key={l} style={th}>Spread {l}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {["1", "3", "5"].map(h => {
                    const r = s?.horizons?.[h];
                    return (
                      <tr key={h}>
                        <td style={{ ...td, color: C.mid }}>{h} session{h === "1" ? "" : "s"}</td>
                        <td style={td}>{r?.option?.n ?? 0}</td>
                        <td style={td}><Agg a={r?.stock} /></td>
                        <td style={td}><Agg a={r?.option} /></td>
                        {LABELS.map(l => <td key={l} style={td}><Agg a={r?.spreads?.[l]} /></td>)}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function SpreadTable({ spreads, side }) {
  const ideas = spreads?.ideas || [];
  if (!ideas.length) {
    return <div style={{ fontSize: 10, color: C.muted, padding: "4px 8px 10px" }}>No spread: no listed strike beyond the long leg with a sane debit.</div>;
  }
  const kind = side === "CE" ? "Bull call" : "Bear put";
  return (
    <div style={{ overflowX: "auto", margin: "0 0 10px 16px" }}>
      <table style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={th}>{kind} spread</th><th style={th}>Priced</th><th style={th}>Max loss</th>
            <th style={th}>Max profit</th><th style={th}>R:R</th><th style={th}>Breakeven</th>
            <th style={th}>Bid-ask</th><th style={th} title="P&L per lot if the stock is at the short strike after 5 sessions, same IV">Day 5 at short strike: spread / single</th>
          </tr>
        </thead>
        <tbody>
          {ideas.map(i => (
            <tr key={i.label}>
              <td style={td}>
                <span style={{ color: C.muted, marginRight: 6 }}>{i.label}</span>
                buy {i.long_strike} / sell {i.short_strike}
                {i.target_move_pct != null && <span style={{ color: C.muted }}> ({pct(i.target_move_pct)})</span>}
              </td>
              <td style={{ ...td, color: i.priced_from === "quotes" ? C.white : C.gold }}>
                {i.priced_from === "quotes" ? "bid/ask" : "close"}
              </td>
              <td style={{ ...td, color: C.red }}>{inr(i.max_loss)}</td>
              <td style={{ ...td, color: C.green }}>{inr(i.max_profit)}</td>
              <td style={td}>{i.reward_risk ?? "—"}</td>
              <td style={td}>
                {i.breakeven ?? "—"}
                {i.breakeven_move_pct != null && <span style={{ color: C.muted }}> ({pct(i.breakeven_move_pct)})</span>}
              </td>
              <td style={{ ...td, color: i.cost_flag ? C.red : C.mid }}>
                {i.cost_pct == null ? "n/a" : `${i.cost_pct}%`}{i.cost_flag ? " ⚠" : ""}
              </td>
              <td style={td}>
                <span style={{ color: tone(i.day5_spread_pnl) }}>{signedInr(i.day5_spread_pnl)}</span>
                <span style={{ color: C.muted }}> / </span>
                <span style={{ color: tone(i.day5_single_pnl) }}>{signedInr(i.day5_single_pnl)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PickRow({ p }) {
  const k = p.contract || {};
  const q = k.quote || {};
  return (
    <>
      <tr>
        <td style={{ ...td, fontWeight: 700 }}>{p.symbol}</td>
        <td style={td}>{px(p.close)}</td>
        <td style={{ ...td, color: C.mid }}>{setupText(p)}</td>
        <td style={{ ...td, color: C.mid }}>{p.oi?.label ?? "—"}</td>
        <td style={td}>{q.strike} {q.option_type} {shortDate(q.expiry)}</td>
        <td style={td}>{px(q.close)}</td>
        <td style={td}>{inr(k.lot_cost)} <span style={{ color: C.muted }}>({q.lot_size})</span></td>
        <td style={td}>{k.delta == null ? "—" : Math.abs(k.delta).toFixed(2)}</td>
        <td style={td}>{k.theta_pct == null ? "—" : `${k.theta_pct}%`}</td>
      </tr>
      <tr><td colSpan={9} style={{ padding: 0 }}><SpreadTable spreads={p.spreads} side={p.side} /></td></tr>
    </>
  );
}

function TonightCard({ latest }) {
  if (!latest) {
    return <Card><Label color={C.accent}>Tonight's picks</Label><div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>No screener run yet.</div></Card>;
  }
  const rebuilt = [...latest.calls, ...latest.puts].some(p => p.spreads?.rebuilt);
  return (
    <Card>
      <Label color={C.accent}>Picks · close of {shortDate(latest.trade_date)}</Label>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>
        {latest.scanned} F&O stocks scanned. Premiums are the bhavcopy close; re-price at the live bid/ask before entering.
        Spreads: short strike at about ½, 1 and 1½ expected moves to expiry. Bid-ask is round-trip, as % of the debit
        (⚠ above 10%). Results dates are not checked.
        {rebuilt && <span style={{ color: C.gold }}> These picks predate the spread feature, so their spreads were rebuilt from closes.</span>}
      </div>
      {[["CE", "Calls", latest.calls], ["PE", "Puts", latest.puts]].map(([side, name, picks]) => (
        <div key={side} style={{ marginTop: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: side === "CE" ? C.green : C.red }}>{name}</div>
          {picks.length === 0 ? (
            <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>None today.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 4 }}>
                <thead>
                  <tr>
                    <th style={th}>Stock</th><th style={th}>Close</th><th style={th}>Setup</th><th style={th}>OI (5d)</th>
                    <th style={th}>Contract</th><th style={th}>Premium</th><th style={th}>Lot cost</th>
                    <th style={th}>Δ</th><th style={th}>θ/day</th>
                  </tr>
                </thead>
                <tbody>{picks.map(p => <PickRow key={p.symbol} p={p} />)}</tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </Card>
  );
}

function OutcomeCells({ p }) {
  const r = p.outcome?.returns || {};
  return ["1", "3", "5"].map(h => {
    const x = r[h];
    const mid = x?.spreads?.mid;
    return (
      <td key={h} style={td}>
        {x ? (
          <>
            <span style={{ color: tone(x.option_pct) }}>{pct(x.option_pct, 0)}</span>
            <span style={{ color: C.muted }}> / </span>
            <span style={{ color: tone(mid) }}>{pct(mid, 0)}</span>
          </>
        ) : <span style={{ color: C.muted }}>…</span>}
      </td>
    );
  });
}

function HistoryCard({ history }) {
  return (
    <Card>
      <Label color={C.accent}>Pick log</Label>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>
        Each evening's picks and what they did: single option / mid spread return after 1, 3 and 5 sessions
        (close to close, before costs). "…" = not there yet.
      </div>
      {history.length === 0 && <div style={{ fontSize: 12, color: C.muted, marginTop: 10 }}>No picks logged yet.</div>}
      {history.map((r, i) => (
        <details key={r.trade_date} open={i === 0} style={{ marginTop: 10 }}>
          <summary style={{ fontSize: 11, color: C.white, cursor: "pointer" }}>
            {shortDate(r.trade_date)} · {r.calls.length} calls, {r.puts.length} puts
          </summary>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 4 }}>
              <thead>
                <tr>
                  <th style={th}>Side</th><th style={th}>Stock</th><th style={th}>Contract</th><th style={th}>Premium</th>
                  <th style={th}>Mid spread</th><th style={th}>1 session</th><th style={th}>3 sessions</th><th style={th}>5 sessions</th>
                </tr>
              </thead>
              <tbody>
                {[...r.calls, ...r.puts].map(p => {
                  const q = p.contract?.quote || {};
                  const mid = p.spreads?.ideas?.find(x => x.label === "mid");
                  return (
                    <tr key={`${p.side}-${p.symbol}`}>
                      <td style={{ ...td, color: p.side === "CE" ? C.green : C.red }}>{p.side === "CE" ? "Call" : "Put"}</td>
                      <td style={{ ...td, fontWeight: 700 }}>{p.symbol}</td>
                      <td style={td}>{q.strike} {q.option_type} {shortDate(q.expiry)}</td>
                      <td style={td}>{px(q.close)}</td>
                      <td style={{ ...td, color: C.mid }}>{mid ? `${mid.long_strike}/${mid.short_strike} @ ${px(mid.debit_close)}` : "—"}</td>
                      <OutcomeCells p={p} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </Card>
  );
}

export default function PicksPage() {
  const { data, loading, error } = useFnoPicks();
  return (
    <div style={{
      background: C.bg, minHeight: "100vh", color: C.white,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    }}>
      <style>{`* { box-sizing: border-box; margin: 0; padding: 0; }`}</style>
      <div style={{
        background: C.panel, borderBottom: `1px solid ${C.border}`,
        padding: "10px 24px", display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap",
      }}>
        <a href="#/" style={{ fontSize: 11, color: C.accent, textDecoration: "none", fontWeight: 700 }}>← Dashboard</a>
        <div style={{ width: 1, height: 18, background: C.border }} />
        <span style={{ fontSize: 14, fontWeight: 900, letterSpacing: 1.5 }}>OPTIONS PICKS</span>
        <span style={{ marginLeft: "auto", fontSize: 10, color: C.muted }}>Screening aid, not a signal · no orders</span>
      </div>

      <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{
          fontSize: 11, color: C.gold, padding: "6px 10px",
          border: `1px solid ${C.gold}55`, borderRadius: 6, background: `${C.gold}10`,
        }}>
          No tested edge yet. The pick log is the test: once there are about 30 completed picks per side, compare the
          single option with the spreads on the same picks. Until then, treat every average here as anecdote.
        </div>
        {loading && <div style={{ fontSize: 12, color: C.muted }}>Loading…</div>}
        {error && !loading && <div style={{ fontSize: 12, color: C.red }}>Could not reach cloud API.</div>}
        {data && (
          <>
            <PanelBoundary name="Picks stats"><StatsCard stats={data.stats} /></PanelBoundary>
            <PanelBoundary name="Tonight's picks"><TonightCard latest={data.latest} /></PanelBoundary>
            <PanelBoundary name="Pick log"><HistoryCard history={data.history} /></PanelBoundary>
          </>
        )}
      </div>
    </div>
  );
}
