// ─── Options picks (#/picks) ────────────────────────────────────────────────
// The evening F&O screener's call and put picks (scripts/run_fno_screener.py),
// each with its spread alternatives (core/fno_screener/spreads.py) and what
// every pick did over the next 5 sessions (core/fno_screener/outcomes.py),
// from GET /fno-picks. A screening aid with no tested edge: the pick log is
// the test, so every average carries its N; returns are close to close,
// before costs.
import { useEffect, useState } from "react";
import PayoffChart from "./PayoffChart.jsx";
import Shell, { getJson } from "./Shell.jsx";
import { T, inr, pct, px, shortDate, tone } from "./theme.js";

const LABELS = ["near", "mid", "far"];

function setupText(p) {
  const call = p.side === "CE";
  const edge = call ? "box top" : "box floor";
  const level = p.box_level ? px(p.box_level) : "?";
  if (p.breakout_state === "FRESH") return `Fresh ${call ? "breakout above" : "breakdown below"} ${edge} ${level}`;
  if (p.breakout_state === "OUT") return `${p.days_out} session${p.days_out === 1 ? "" : "s"} ${call ? "above" : "below"} ${edge} ${level}`;
  return `Near ${edge} ${level}`;
}

function SpreadIdeas({ p }) {
  const ideas = p.spreads?.ideas || [];
  const [sel, setSel] = useState("mid");
  if (!ideas.length) return <div className="q-sub">No sensible spread on this chain.</div>;
  const i = ideas.find(x => x.label === sel) || ideas[0];
  const right = p.side === "CE" ? "call" : "put";
  const lot = p.contract?.quote?.lot_size;
  return (
    <div style={{ marginTop: 14 }}>
      <div className="q-between">
        <div className="q-label">{p.side === "CE" ? "Bull call" : "Bear put"} spread</div>
        <div className="q-tabs">
          {ideas.map(x => <button key={x.label} className={x.label === i.label ? "on" : ""} onClick={() => setSel(x.label)}>{x.label}</button>)}
        </div>
      </div>
      <div className="q-row" style={{ marginTop: 10, fontSize: 13 }}>
        <span className="q-num" style={{ fontWeight: 600 }}>Buy {i.long_strike} · Sell {i.short_strike}</span>
        {i.target_move_pct != null && <span className="q-faint q-num">short strike {pct(i.target_move_pct)} away</span>}
        <span className={`q-pill ${i.priced_from === "quotes" ? "" : "amber"}`}>{i.priced_from === "quotes" ? "bid/ask" : "close prices"}</span>
        {i.cost_pct != null && <span className={`q-pill ${i.cost_flag ? "red" : ""}`}>bid-ask {i.cost_pct}%{i.cost_flag ? " ⚠" : ""}</span>}
      </div>
      {lot && i.debit != null && (
        <div style={{ marginTop: 8 }}>
          <PayoffChart right={right} longStrike={i.long_strike} shortStrike={i.short_strike} entry={i.debit ?? i.debit_close}
                       qty={lot} spot={p.close} breakeven={i.breakeven} height={120} />
        </div>
      )}
      <div className="q-stats" style={{ marginTop: 8 }}>
        <div className="q-stat"><div className="q-label">Max loss</div><div className="v" style={{ color: T.red }}>{inr(i.max_loss)}</div></div>
        <div className="q-stat"><div className="q-label">Max profit</div><div className="v" style={{ color: T.green }}>{inr(i.max_profit)}</div>
          <div className="s">R:R {i.reward_risk ?? "—"}</div></div>
        <div className="q-stat"><div className="q-label">Breakeven</div><div className="v">{px(i.breakeven)}</div>
          <div className="s">{i.breakeven_move_pct == null ? "" : `${pct(i.breakeven_move_pct)} move`}</div></div>
        <div className="q-stat" title="P&L per lot if the stock is at the short strike after 5 sessions, same IV">
          <div className="q-label">Day 5 at target</div>
          <div className="v" style={{ color: tone(i.day5_spread_pnl) }}>{i.day5_spread_pnl == null ? "—" : `${i.day5_spread_pnl > 0 ? "+" : "−"}${inr(i.day5_spread_pnl)}`}</div>
          <div className="s">single option {i.day5_single_pnl == null ? "—" : `${i.day5_single_pnl > 0 ? "+" : "−"}${inr(i.day5_single_pnl)}`}</div></div>
      </div>
    </div>
  );
}

function PickCard({ p }) {
  const k = p.contract || {};
  const q = k.quote || {};
  return (
    <div className="q-card">
      <div className="q-between">
        <div>
          <div className="q-row">
            <span style={{ fontSize: 18, fontWeight: 700 }}>{p.symbol}</span>
            <span className={`q-pill ${p.side === "CE" ? "green" : "red"}`}>{p.side === "CE" ? "Call" : "Put"}</span>
            {p.oi?.label && <span className="q-pill">{p.oi.label}</span>}
          </div>
          <div className="q-sub">{setupText(p)}{p.box_width_pct ? ` · box ${p.box_width_pct}% wide` : ""}</div>
        </div>
        <div className="q-head-right" style={{ textAlign: "right" }}>
          <div className="q-num" style={{ fontSize: 20, fontWeight: 650 }}>{px(p.close)}</div>
          <div className="q-sub">close</div>
        </div>
      </div>
      <div className="q-row" style={{ marginTop: 12, fontSize: 13 }}>
        <span className="q-num" style={{ fontWeight: 600 }}>{q.strike} {q.option_type} · {shortDate(q.expiry)}</span>
        <span className="q-muted q-num">@ {px(q.close)}</span>
        <span className="q-muted q-num">lot {inr(k.lot_cost)} ({q.lot_size})</span>
        {k.delta != null && <span className="q-faint q-num">Δ {Math.abs(k.delta).toFixed(2)}</span>}
        {k.theta_pct != null && <span className="q-faint q-num">θ {k.theta_pct}%/day</span>}
      </div>
      <SpreadIdeas p={p} />
    </div>
  );
}

function Agg({ a }) {
  if (!a) return <span className="q-faint">—</span>;
  return <span><span style={{ color: tone(a.mean_pct), fontWeight: 600 }}>{pct(a.mean_pct)}</span><span className="q-faint"> · {a.win_pct}% up</span></span>;
}

function TrackRecord({ stats }) {
  return (
    <div className="q-grid">
      {[["CE", "Calls"], ["PE", "Puts"]].map(([side, label]) => {
        const s = stats?.[side];
        return (
          <div key={side} className="q-card">
            <div className="q-between">
              <div className="q-row"><span style={{ fontWeight: 700 }}>{label}</span>
                <span className="q-faint" style={{ fontSize: 12 }}>{s?.picks ?? 0} picks · {s?.complete ?? 0} complete</span></div>
              {s?.median_spread_cost_pct != null && <span className="q-pill">median bid-ask {s.median_spread_cost_pct}%</span>}
            </div>
            <div className="q-scroll" style={{ marginTop: 10 }}>
              <table className="q-table">
                <thead><tr><th>After</th><th>N</th><th>Stock</th><th>Option</th>{LABELS.map(l => <th key={l}>Spread {l}</th>)}</tr></thead>
                <tbody>
                  {["1", "3", "5"].map(h => {
                    const r = s?.horizons?.[h];
                    return (
                      <tr key={h}>
                        <td className="w q-muted">{h} session{h === "1" ? "" : "s"}</td>
                        <td>{r?.option?.n ?? 0}</td>
                        <td><Agg a={r?.stock} /></td>
                        <td><Agg a={r?.option} /></td>
                        {LABELS.map(l => <td key={l}><Agg a={r?.spreads?.[l]} /></td>)}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Log({ history }) {
  if (!history?.length) return <div className="q-card q-empty">No picks logged yet.</div>;
  return (
    <div className="q-card">
      <div className="q-sub" style={{ marginTop: 0 }}>Single option / mid spread return after 1, 3 and 5 sessions. "…" = not there yet.</div>
      {history.map((r, idx) => (
        <details key={r.trade_date} className="q-det" open={idx === 0} style={{ marginTop: 14 }}>
          <summary className="q-row" style={{ fontWeight: 600 }}>
            {shortDate(r.trade_date)} <span className="q-faint" style={{ fontWeight: 400, fontSize: 12 }}>{r.calls.length} calls · {r.puts.length} puts</span>
          </summary>
          <div className="q-scroll">
            <table className="q-table" style={{ marginTop: 6 }}>
              <thead><tr><th>Pick</th><th>Contract</th><th>Premium</th><th>Mid spread</th><th>1 session</th><th>3 sessions</th><th>5 sessions</th></tr></thead>
              <tbody>
                {[...r.calls, ...r.puts].map(p => {
                  const q = p.contract?.quote || {};
                  const mid = p.spreads?.ideas?.find(x => x.label === "mid");
                  const rr = p.outcome?.returns || {};
                  return (
                    <tr key={`${p.side}${p.symbol}`}>
                      <td className="w"><span style={{ color: p.side === "CE" ? T.green : T.red, fontWeight: 600 }}>{p.side === "CE" ? "▲" : "▼"}</span> {p.symbol}</td>
                      <td>{q.strike} {q.option_type} {shortDate(q.expiry)}</td>
                      <td>{px(q.close)}</td>
                      <td className="q-muted">{mid ? `${mid.long_strike}/${mid.short_strike}` : "—"}</td>
                      {["1", "3", "5"].map(h => {
                        const x = rr[h];
                        return <td key={h}>{x ? <><span style={{ color: tone(x.option_pct) }}>{pct(x.option_pct, 0)}</span>
                          <span className="q-faint"> / </span><span style={{ color: tone(x.spreads?.mid) }}>{pct(x.spreads?.mid, 0)}</span></> : <span className="q-faint">…</span>}</td>;
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </div>
  );
}

export default function PicksPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [tab, setTab] = useState("tonight");
  useEffect(() => {
    let live = true;
    const load = async () => {
      const d = await getJson("/fno-picks");
      if (!live) return;
      if (d) { setData(d); setError(false); } else setError(true);
    };
    load();
    const id = setInterval(load, 300000);
    return () => { live = false; clearInterval(id); };
  }, []);
  const latest = data?.latest;
  const rebuilt = latest && [...latest.calls, ...latest.puts].some(p => p.spreads?.rebuilt);
  return (
    <Shell active="picks">
      <div className="q-between">
        <div>
          <h1 className="q-h1">Options picks</h1>
          <div className="q-sub">
            {latest ? `Close of ${shortDate(latest.trade_date)} · ${latest.scanned} F&O stocks scanned · re-price at the live bid/ask before entering`
              : "Evening F&O screener"}
          </div>
        </div>
        <div className="q-tabs">
          {[["tonight", "Tonight"], ["record", "Track record"], ["log", "Pick log"]].map(([k, l]) =>
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
        </div>
      </div>
      <div className="q-banner amber" style={{ marginTop: 16 }}>
        No tested edge yet. The pick log is the test: with about 30 complete picks per side, compare the single option with
        the spreads on the same picks. Until then every average here is anecdote. Results dates are not checked.
      </div>
      {error && <div className="q-banner red" style={{ marginTop: 12 }}>Can't reach the cockpit API.</div>}
      <div style={{ marginTop: 20 }}>
        {tab === "tonight" && (latest ? (
          <>
            {rebuilt && <div className="q-sub" style={{ marginBottom: 12, color: T.amber }}>These picks predate the spread feature; their spreads were rebuilt from closing prices.</div>}
            {[["CE", "Calls", latest.calls], ["PE", "Puts", latest.puts]].map(([side, label, picks]) => (
              <section key={side} style={{ marginBottom: 24 }}>
                <div className="q-label" style={{ marginBottom: 10 }}>{label} · {picks.length}</div>
                {picks.length ? <div className="q-grid">{picks.map(p => <PickCard key={p.symbol} p={p} />)}</div>
                  : <div className="q-card q-empty">None tonight.</div>}
              </section>
            ))}
          </>
        ) : data && <div className="q-card q-empty">No screener run yet.</div>)}
        {tab === "record" && data && <TrackRecord stats={data.stats} />}
        {tab === "log" && data && <Log history={data.history} />}
      </div>
    </Shell>
  );
}
