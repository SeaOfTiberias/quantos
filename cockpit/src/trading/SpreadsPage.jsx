// ─── Spreads (#/spreads) ────────────────────────────────────────────────────
// What the ICICI Direct spread watcher (scripts/run_spread_watcher.py) sees,
// from GET /spreads (cloud/api/spreads_routes.py): every open spread with its
// live P&L, payoff, stops and the alerts it has sent; uncovered shorts; the
// alert timeline. Alerts only: nothing here places an order. The one thing you
// can change is your own stock-price exit level per stock (POST /spreads/level).
import { useCallback, useEffect, useState } from "react";
import PayoffChart from "./PayoffChart.jsx";
import Shell, { getJson, postJson } from "./Shell.jsx";
import { T, ago, clock, inr, pct, px, sessionBefore, sessionsTo, shortDate, signedInr, tone } from "./theme.js";

const KIND_TONE = { "bull call": "green", "bull put": "green", "bear put": "red", "bear call": "red" };
const ALERT_NAMES = {
  trail_armed: "Trail armed", trail_stock: "Stock stop hit", giveback: "Give-back hit",
  breakeven: "Back at breakeven", near_max: "Near max", exit_day: "Exit day",
};

function useSpreads() {
  const [s, set] = useState({ data: null, error: false });
  const load = useCallback(async () => {
    const d = await getJson("/spreads");
    set(d ? { data: d, error: false } : prev => ({ ...prev, error: true }));
  }, []);
  useEffect(() => {
    let live = true;
    const tick = async () => {
      const d = await getJson("/spreads");
      if (live) set(d ? { data: d, error: false } : prev => ({ ...prev, error: true }));
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => { live = false; clearInterval(id); };
  }, []);
  return [s, load];
}

function RiskBar({ pnl, best, maxLoss, maxProfit }) {
  if (pnl == null || !maxLoss || !maxProfit) return null;
  const pos = v => `${Math.min(Math.max((v + maxLoss) / (maxLoss + maxProfit), 0), 1) * 100}%`;
  return (
    <div style={{ marginTop: 14 }}>
      <div className="q-bar">
        <div style={{ position: "absolute", left: pos(0), top: -3, bottom: -3, width: 1, background: T.faint }} />
        {best > 0 && <div title="best so far" style={{ position: "absolute", left: pos(best), top: -2, width: 2, height: 12,
                                                       background: T.muted, borderRadius: 1 }} />}
        <div style={{ position: "absolute", left: `calc(${pos(pnl)} - 7px)`, top: -3, width: 14, height: 14,
                      borderRadius: "50%", background: tone(pnl), border: `3px solid ${T.surface}` }} />
      </div>
      <div className="q-between" style={{ marginTop: 6, fontSize: 11 }}>
        <span className="q-num" style={{ color: T.red }}>−{inr(maxLoss)} max loss</span>
        <span className="q-num" style={{ color: T.green }}>max profit {inr(maxProfit)}</span>
      </div>
    </div>
  );
}

function LevelEditor({ code, level, onSaved }) {
  const [v, setV] = useState("");
  const [err, setErr] = useState("");
  const save = async value => {
    setErr("");
    try {
      await postJson("/spreads/level", { stock_code: code, level: value });
      setV(""); onSaved();
    } catch (e) { setErr(String(e.message || e)); }
  };
  return (
    <div className="q-row" style={{ fontSize: 12 }}>
      <span className="q-muted">Your exit level</span>
      {level ? (
        <>
          <span className="q-pill amber q-num">{typeof level === "object"
            ? [level.close && `close ${px(level.close)}`, level.touch && `touch ${px(level.touch)}`, level.target && `target ${px(level.target)}`].filter(Boolean).join(" · ")
            : px(level)}</span>
          <button className="q-btn ghost" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => save(null)}>Clear</button>
        </>
      ) : (
        <>
          <input className="q-input" style={{ width: 110, padding: "5px 8px" }} inputMode="decimal" placeholder="e.g. 1775"
                 value={v} onChange={e => setV(e.target.value)} />
          <button className="q-btn" style={{ padding: "5px 10px", fontSize: 12 }} disabled={!(Number(v) > 0)}
                  onClick={() => save(Number(v))}>Set</button>
        </>
      )}
      <span className="q-faint">replaces the trailing stop for {code}</span>
      {err && <span style={{ color: T.red }}>{err}</span>}
    </div>
  );
}

function SpreadCard({ s, rules, onChanged }) {
  const cp = s.right === "call" ? "CE" : "PE";
  const left = sessionsTo(s.expiry);
  const pctMax = s.max_profit > 0 && s.last_pnl != null ? (s.last_pnl / s.max_profit) * 100 : null;
  const armAt = rules ? (rules.giveback_arm_pct / 100) * s.max_profit : null;
  const bArmed = armAt != null && s.peak_pnl >= armAt;
  const lq = s.long_quote, sq = s.short_quote;
  const fired = (s.sent || []).filter(k => k !== "trail_armed");
  return (
    <div className="q-card">
      <div className="q-between">
        <div>
          <div className="q-row">
            <span style={{ fontSize: 18, fontWeight: 700 }}>{s.stock_code}</span>
            <span className={`q-pill ${KIND_TONE[s.kind] || "blue"}`}>{s.kind}</span>
          </div>
          <div className="q-sub q-num">
            {s.long_strike}/{s.short_strike} {cp} · {shortDate(s.expiry)}
            {left != null && ` · ${left} session${left === 1 ? "" : "s"} left`} · ×{s.qty}
          </div>
        </div>
        <div className="q-head-right" style={{ textAlign: "right" }}>
          <div className="q-big" style={{ color: tone(s.last_pnl) }}>{signedInr(s.last_pnl)}</div>
          <div className="q-sub q-num">{pctMax == null ? "waiting for prices" : `${pct(pctMax, 0)} of max · best ${signedInr(s.peak_pnl)}`}</div>
        </div>
      </div>

      <RiskBar pnl={s.last_pnl} best={s.peak_pnl} maxLoss={s.max_loss} maxProfit={s.max_profit} />

      <div style={{ marginTop: 12 }}>
        <PayoffChart right={s.right} longStrike={s.long_strike} shortStrike={s.short_strike} entry={s.entry}
                     qty={s.qty} spot={s.last_spot} breakeven={s.breakeven} stop={s.stock_stop} />
      </div>

      <div className="q-stats" style={{ marginTop: 12 }}>
        <div className="q-stat"><div className="q-label">Stock</div><div className="v">{px(s.last_spot)}</div>
          <div className="s">best {px(s.best_spot)}</div></div>
        <div className="q-stat"><div className="q-label">Stop</div>
          <div className="v" style={{ color: s.stock_stop ? T.amber : T.faint }}>{px(s.stock_stop)}</div>
          <div className="s">{s.level ? "your level" : s.stock_stop ? `${rules?.stock_trail_pct ?? 0.8}% trail` : "arms in profit"}</div></div>
        <div className="q-stat"><div className="q-label">Breakeven</div><div className="v">{px(s.breakeven)}</div>
          <div className="s">at expiry</div></div>
        <div className="q-stat"><div className="q-label">Value now</div><div className="v">{px(s.last_value)}</div>
          <div className="s">{s.entry > 0 ? `paid ${px(s.entry)}` : `received ${px(-s.entry)}`}</div></div>
      </div>

      <div className="q-row" style={{ marginTop: 12 }}>
        <span className={`q-pill ${s.stock_stop ? "green" : ""}`}><span className="dot" />Stock trail {s.stock_stop ? "armed" : "waiting"}</span>
        <span className={`q-pill ${bArmed ? "green" : ""}`}><span className="dot" />
          Give-back {bArmed ? `armed · fires ≤ ${inr(s.peak_pnl * (rules?.giveback_keep ?? 0.5))}` : `arms at ${inr(armAt)}`}</span>
        <span className={`q-pill ${left != null && left <= 1 ? "amber" : ""}`}><span className="dot" />Exit by {shortDate(sessionBefore(s.expiry))}</span>
        {fired.map(k => <span key={k} className={`q-pill ${["trail_stock", "giveback", "exit_day"].includes(k) ? "red" : "amber"}`}>{ALERT_NAMES[k] || k}</span>)}
      </div>

      {lq && sq && (
        <div className="q-sub q-num" style={{ marginTop: 12 }}>
          To close: SELL {s.long_strike} {cp} @ {px(lq[0])} · BUY {s.short_strike} {cp} @ {px(sq[1])}
          <span className="q-faint"> · {s.quoted ? "bid/ask" : "last traded"} {clock(s.updated_at)}</span>
        </div>
      )}
      <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${T.border}` }}>
        <LevelEditor code={s.stock_code} level={s.level} onSaved={onChanged} />
      </div>
    </div>
  );
}

function AlertList({ alerts }) {
  if (!alerts?.length) return <div className="q-sub">No alerts yet.</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {alerts.map((a, i) => {
        const [first, ...rest] = a.text.split("\n");
        const c = first.startsWith("🔴") || first.startsWith("🚨") ? T.red : first.startsWith("⚠️") ? T.amber
          : first.startsWith("✅") ? T.green : T.muted;
        return (
          <details key={i} className="q-det" style={{ padding: "10px 0", borderBottom: i < alerts.length - 1 ? `1px solid ${T.border}` : "none" }}>
            <summary style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
              <span className="q-num q-faint" style={{ fontSize: 12, minWidth: 92 }}>{shortDate(a.at)} {clock(a.at)}</span>
              <span style={{ color: c, fontSize: 13 }}>{first}</span>
            </summary>
            {rest.length > 0 && <div className="q-sub" style={{ whiteSpace: "pre-wrap", marginLeft: 104 }}>{rest.join("\n")}</div>}
          </details>
        );
      })}
    </div>
  );
}

export default function SpreadsPage() {
  const [{ data, error }, reload] = useSpreads();
  const w = data?.watcher;
  const spreads = data?.spreads || [];
  const total = spreads.reduce((a, s) => a + (s.last_pnl || 0), 0);
  const atRisk = spreads.reduce((a, s) => a + (s.max_loss || 0), 0);
  const today = new Date().toISOString().slice(0, 10);
  const alertsToday = (data?.alerts || []).filter(a => a.at?.slice(0, 10) === today).length;
  const watcherPill = !w ? null
    : w.alive ? <span className="q-pill green"><span className="dot" />Watcher live · {ago(w.heartbeat_at)}</span>
    : w.market_open ? <span className="q-pill red"><span className="dot" />Watcher not running</span>
    : <span className="q-pill"><span className="dot" />Market closed · watcher sleeps</span>;
  return (
    <Shell active="spreads">
      <div className="q-between">
        <div>
          <h1 className="q-h1">Spreads</h1>
          <div className="q-sub">ICICI Direct · live exit alerts to Telegram. Alerts only: the watcher never places orders.</div>
        </div>
        <div className="q-row">
          {watcherPill}
          {w && w.alive && !w.session_ok && <span className="q-pill amber"><span className="dot" />ICICI session needed</span>}
        </div>
      </div>

      {error && <div className="q-banner red" style={{ marginTop: 16 }}>Can't reach the cockpit API.</div>}

      {(data?.uncovered || []).map(u => (
        <div key={`${u.stock_code}${u.label}`} className="q-banner red" style={{ marginTop: 16 }}>
          <b>Uncovered short:</b> {u.stock_code} {u.label} {shortDate(u.expiry)} ×{u.qty}, sold @ {px(u.avg_price)}, with no long
          leg against it. The loss is open-ended. Buy it back or add a long leg.
        </div>
      ))}

      <div className="q-stats" style={{ marginTop: 20 }}>
        <div className="q-stat"><div className="q-label">Open spreads</div><div className="v">{spreads.length}</div></div>
        <div className="q-stat"><div className="q-label">P&L now</div><div className="v" style={{ color: tone(total) }}>{signedInr(total)}</div>
          <div className="s">close-out value, before charges</div></div>
        <div className="q-stat"><div className="q-label">At risk</div><div className="v">{inr(atRisk)}</div><div className="s">sum of max losses</div></div>
        <div className="q-stat"><div className="q-label">Alerts today</div><div className="v">{alertsToday}</div></div>
      </div>

      <div style={{ marginTop: 20 }}>
        {data && spreads.length === 0 ? (
          <div className="q-card q-empty">
            <div style={{ fontSize: 16, color: T.text, fontWeight: 600 }}>No open spreads</div>
            <div className="q-sub" style={{ maxWidth: 520, margin: "6px auto 0" }}>
              Open a spread in ICICI Direct and it appears here within a minute, with its payoff, stops and a Telegram
              "watching" message. Bull and bear, debit and credit spreads are all recognised.
            </div>
          </div>
        ) : (
          <div className="q-grid">{spreads.map(s => <SpreadCard key={s.key} s={s} rules={data?.rules} onChanged={reload} />)}</div>
        )}
      </div>

      <div className="q-grid" style={{ marginTop: 20 }}>
        <div className="q-card" style={{ gridColumn: "1 / -1" }}>
          <div className="q-between">
            <div className="q-label">Alert timeline</div>
            {data?.rules && (
              <div className="q-faint" style={{ fontSize: 12 }}>
                Rules: stock trail {data.rules.stock_trail_pct}% · give-back keeps {Math.round(data.rules.giveback_keep * 100)}% after {data.rules.giveback_arm_pct}% of max ·
                exit {data.rules.exit_sessions_before_expiry} session before expiry
              </div>
            )}
          </div>
          <div style={{ marginTop: 8 }}><AlertList alerts={data?.alerts} /></div>
        </div>
      </div>
    </Shell>
  );
}
