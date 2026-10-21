// ─── Trade ideas (#/ideas) ──────────────────────────────────────────────────
// Every logged trade idea with its levels, what the market did since, and the
// paper result next to the actual one (GET /ideas, scored daily at 15:25 by
// scripts/trade_ideas.py), plus the structure picker: for a view (target,
// stop, horizon) it prices futures, single options and spreads on the live
// chain and ranks them by the hit rate each needs to break even
// (POST /ideas/structure -> core/ideas/structure.py). Prices only, no orders.
import { Fragment, useEffect, useState } from "react";
import Shell, { getJson, postJson } from "./Shell.jsx";
import { T, inr, pct, px, shortDate, signedInr, tone } from "./theme.js";

const ACTION = { enter_if: "Enter if", enter_now: "Entered now", avoid: "Avoid" };
const FAMILY = { future: "Futures", single: "Single option", debit: "Debit spread", credit: "Credit spread" };

function cond(c) {
  if (!c) return null;
  if (c.kind === "close_between") return `close ${px(c.low)}–${px(c.high)}`;
  return `close ${c.kind === "close_above" ? ">" : "<"} ${px(c.level)}`;
}

function structText(s) {
  if (!s) return "—";
  const right = s.kind.endsWith("call") ? "CE" : "PE";
  return `${s.kind.replace("_", " ")} ${s.long_strike}/${s.short_strike} ${right} · ${shortDate(s.expiry)}`;
}

function statusPill(ev, idea) {
  const st = ev?.status || "not scored yet";
  const cls = st === "closed" || st === "taken" ? "blue" : st === "triggered" ? "green"
    : st.startsWith("avoided") ? "" : st === "cancelled" || st.startsWith("expired") ? "red" : "amber";
  return <span className={`q-pill ${cls}`}>{idea.action === "avoid" && st === "avoided" ? "passed on" : st}</span>;
}

function Scoreboard({ sb }) {
  const rows = Object.entries(sb || {});
  if (!rows.length) return null;
  const tot = rows.reduce((a, [, v]) => ({ ideas: a.ideas + v.ideas, actual: a.actual + (v.actual_pnl || 0), taken: a.taken + (v.taken || 0) }),
    { ideas: 0, actual: 0, taken: 0 });
  return (
    <div className="q-stats" style={{ marginTop: 18 }}>
      <div className="q-stat"><div className="q-label">Ideas logged</div><div className="v">{tot.ideas}</div>
        <div className="s">{tot.taken} taken</div></div>
      <div className="q-stat"><div className="q-label">Actual P&L</div>
        <div className="v" style={{ color: tone(tot.actual) }}>{signedInr(tot.actual)}</div><div className="s">closed trades, before charges</div></div>
      {rows.map(([k, v]) => (
        <div className="q-stat" key={k}>
          <div className="q-label">{ACTION[k] || k}</div>
          <div className="v" style={{ color: tone(v.pnl) }}>{v.scored ? signedInr(v.pnl) : "—"}</div>
          <div className="s">{v.ideas} ideas · {v.triggered} triggered · {v.scored ? `${v.wins}/${v.scored} paper wins` : "none scored yet"}</div>
        </div>
      ))}
    </div>
  );
}

function IdeasTable({ ideas, onPrice }) {
  if (!ideas.length) return <div className="q-empty">No ideas logged yet.</div>;
  return (
    <div className="q-scroll">
      <table className="q-table">
        <thead><tr>
          <th>Logged</th><th>Stock</th><th>Idea</th><th>Plan</th><th>Status</th>
          <th style={{ textAlign: "right" }}>Spot since</th><th style={{ textAlign: "right" }}>Paper P&L</th>
          <th style={{ textAlign: "right" }}>Actual</th><th />
        </tr></thead>
        <tbody>
          {ideas.map(i => {
            const ev = i.eval || {};
            const plan = [i.action === "enter_if" ? `in on ${cond(i.trigger)}` : ACTION[i.action],
              i.stop && `out on ${cond(i.stop)}`, i.cancel && `void on ${cond(i.cancel)}`].filter(Boolean).join(" · ");
            return (
              <Fragment key={i.id}>
                <tr>
                  <td>{shortDate(i.created_at)}</td>
                  <td className="w"><span style={{ fontWeight: 650 }}>{i.symbol}</span>{" "}
                    <span className={`q-pill ${i.view === "bull" ? "green" : i.view === "bear" ? "red" : ""}`}>{i.view}</span></td>
                  <td>{structText(i.structure)}</td>
                  <td className="w q-muted" style={{ fontSize: 12.5 }}>{plan}</td>
                  <td className="w">{statusPill(ev, i)}</td>
                  <td style={{ textAlign: "right", color: T.muted }}>{ev.spot_move_pct == null ? "—" : pct(ev.spot_move_pct)}</td>
                  <td style={{ textAlign: "right", color: tone(ev.pnl) }}>{ev.pnl == null ? "—" : signedInr(ev.pnl)}</td>
                  <td style={{ textAlign: "right", color: tone(ev.actual_pnl) }}>{ev.actual_pnl == null ? (i.taken ? "open" : "—") : signedInr(ev.actual_pnl)}</td>
                  <td><button className="q-btn ghost" style={{ padding: "3px 10px", fontSize: 12 }} onClick={() => onPrice(i)}>Price</button></td>
                </tr>
                {i.note && (
                  <tr><td colSpan={9} className="w q-faint" style={{ whiteSpace: "normal", fontSize: 12.5, paddingTop: 0 }}>{i.note}</td></tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ResultTable({ rows, highlight }) {
  return (
    <div className="q-scroll">
      <table className="q-table">
        <thead><tr>
          <th>Structure</th><th>Expiry</th><th style={{ textAlign: "right" }}>Entry</th>
          <th style={{ textAlign: "right" }}>If target</th><th style={{ textAlign: "right" }}>If stop / stall</th>
          <th style={{ textAlign: "right" }}>Worst case</th><th style={{ textAlign: "right" }}>Needs hit rate</th>
          <th style={{ textAlign: "right" }}>EV / worst</th>
        </tr></thead>
        <tbody>
          {rows.map((c, n) => (
            <tr key={`${c.name}${c.expiry}`} style={n === 0 && highlight ? { boxShadow: `inset 3px 0 0 ${T.blue}` } : undefined}>
              <td className="w"><span style={{ fontWeight: 600 }}>{c.name}</span>{highlight && <span className="q-faint"> · {FAMILY[c.family]}</span>}</td>
              <td>{c.expiry ? shortDate(c.expiry) : "—"}</td>
              <td style={{ textAlign: "right" }}>{c.entry < 0 ? `${px(-c.entry)} cr` : px(c.entry)}</td>
              <td style={{ textAlign: "right", color: T.green }}>{signedInr(c.gain_target)}</td>
              <td style={{ textAlign: "right", color: T.red }}>{signedInr(c.loss_stop)}</td>
              <td style={{ textAlign: "right" }}>{inr(c.worst_case)}</td>
              <td style={{ textAlign: "right", fontWeight: 650, color: c.be_p <= 0.45 ? T.green : c.be_p <= 0.55 ? T.amber : T.red }}>
                {Math.round(c.be_p * 100)}%</td>
              <td style={{ textAlign: "right", color: tone(c.score) }}>{c.score.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Picker({ seed }) {
  // Seeded once from a clicked idea; the parent remounts this (key) for a new seed.
  const [f, setF] = useState(() => ({
    symbol: seed?.symbol || "", direction: seed?.view === "bear" ? "bear" : "bull",
    target: seed?.target ?? "", stop: seed?.stop?.level ?? "", days: 5, p: 0.5, intraday: false, budget: "",
  }));
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const run = async () => {
    setBusy(true); setErr("");
    try {
      setRes(await postJson("/ideas/structure", {
        symbol: f.symbol.trim(), direction: f.direction, target: Number(f.target), stop: Number(f.stop),
        days: Number(f.days), p: Number(f.p), intraday: f.intraday, budget: f.budget ? Number(f.budget) : null,
      }));
    } catch (e) { setErr(String(e.message || e)); setRes(null); }
    setBusy(false);
  };
  const ready = f.symbol.trim() && Number(f.target) > 0 && Number(f.stop) > 0 && Number(f.days) > 0;
  const top = res?.top?.[0];
  return (
    <div className="q-card" id="picker">
      <div className="q-between">
        <div>
          <div className="q-label">Structure picker</div>
          <div className="q-sub">Prices futures, single options and spreads on the live chain for your view, and ranks them by the hit rate each needs to break even.</div>
        </div>
      </div>
      <div className="q-row" style={{ marginTop: 14, alignItems: "flex-end" }}>
        <label><div className="q-label">Stock</div>
          <input className="q-input" style={{ width: 130 }} value={f.symbol} onChange={e => set("symbol", e.target.value.toUpperCase())} placeholder="NESTLEIND" /></label>
        <div><div className="q-label">View</div>
          <div className="q-tabs">
            {["bull", "bear"].map(d => <button key={d} className={f.direction === d ? "on" : ""} onClick={() => set("direction", d)}>{d}</button>)}
          </div></div>
        <label><div className="q-label">Target</div>
          <input className="q-input" style={{ width: 90 }} value={f.target} onChange={e => set("target", e.target.value)} inputMode="decimal" /></label>
        <label><div className="q-label">Stop</div>
          <input className="q-input" style={{ width: 90 }} value={f.stop} onChange={e => set("stop", e.target.value)} inputMode="decimal" /></label>
        <label><div className="q-label">Days</div>
          <input className="q-input" style={{ width: 60 }} value={f.days} onChange={e => set("days", e.target.value)} inputMode="numeric" /></label>
        <label><div className="q-label">Hit rate</div>
          <select className="q-input" value={f.p} onChange={e => set("p", e.target.value)}>
            {[0.4, 0.5, 0.6, 0.7].map(v => <option key={v} value={v}>{v * 100}%</option>)}
          </select></label>
        <label><div className="q-label">Budget ₹</div>
          <input className="q-input" style={{ width: 90 }} value={f.budget} onChange={e => set("budget", e.target.value)} placeholder="none" inputMode="numeric" /></label>
        <label className="q-row" style={{ gap: 6, fontSize: 13, paddingBottom: 6 }}>
          <input type="checkbox" checked={f.intraday} onChange={e => set("intraday", e.target.checked)} /> intraday</label>
        <button className="q-btn primary" disabled={!ready || busy} onClick={run}>{busy ? "Pricing…" : "Price structures"}</button>
      </div>
      {err && <div className="q-banner red" style={{ marginTop: 12 }}>{err}</div>}
      {res && (
        <div style={{ marginTop: 16 }}>
          <div className="q-sub">
            {res.symbol} at <span className="q-num">{px(res.spot)}</span> · lot {res.lot} · {res.count} structures priced ·
            {res.research_mode ? " research mode (no budget)" : ` budget ${inr(Number(f.budget))}`} · scored at a {Math.round(res.p * 100)}% hit rate
          </div>
          {top && (
            <div className="q-banner" style={{ marginTop: 10, borderColor: T.border, color: T.text }}>
              {top.be_p > 0.55
                ? <>Every structure needs a hit rate above 55% — the target is too close or the stop too far. Rework the levels or skip.</>
                : <>Best: <b>{top.name}</b> ({shortDate(top.expiry)}) needs the target first <b>{Math.round(top.be_p * 100)}%</b> of the time to break even;
                  worst case {inr(top.worst_case)} per lot.{top.family === "future" ? " Futures need the stop order actually placed; the worst case includes a 2% gap through it." : ""}</>}
            </div>
          )}
          <div className="q-label" style={{ marginTop: 16 }}>Best of each kind</div>
          <ResultTable rows={res.best} highlight />
          <div className="q-label" style={{ marginTop: 16 }}>Top 10 overall</div>
          <ResultTable rows={res.top} />
          <div className="q-faint" style={{ fontSize: 12, marginTop: 10 }}>
            Model: target reached at the horizon, stop hit halfway through it, or a stall halfway to target; each option leg repriced at its own implied vol;
            bid/ask paid on entry and exit. "If stop / stall" shows the worse of the two. A structure must outlive the horizon.
          </div>
        </div>
      )}
    </div>
  );
}

export default function IdeasPage() {
  const [data, setData] = useState(null);
  const [seed, setSeed] = useState(null);
  useEffect(() => {
    let live = true;
    const load = () => getJson("/ideas").then(d => { if (live && d) setData(d); });
    load();
    const id = setInterval(load, 120000);
    return () => { live = false; clearInterval(id); };
  }, []);
  const price = i => { setSeed({ ...i, _t: Date.now() }); document.getElementById("picker")?.scrollIntoView({ behavior: "smooth" }); };
  return (
    <Shell active="ideas">
      <div className="q-between">
        <div>
          <h1 className="q-h1">Trade ideas</h1>
          <div className="q-sub">Every idea logged with its levels before the outcome, scored daily at 15:25 — including the ones passed on. Paper P&L uses the bid/ask you'd actually have got.</div>
        </div>
      </div>
      <Scoreboard sb={data?.scoreboard} />
      <div style={{ marginTop: 20 }}><Picker key={seed?._t || 0} seed={seed} /></div>
      <div className="q-card" style={{ marginTop: 20 }}>
        <div className="q-label" style={{ marginBottom: 8 }}>Idea log</div>
        {data ? <IdeasTable ideas={data.ideas} onPrice={price} /> : <div className="q-empty">Loading…</div>}
      </div>
    </Shell>
  );
}
