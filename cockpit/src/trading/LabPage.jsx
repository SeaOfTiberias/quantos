// ─── Strategy Lab (#/lab, #/lab/<id>) ──────────────────────────────────────
// Every strategy we tested: why we tested it, the pre-registered test, the result and why it
// failed (or why it's on paper / shelved), with its equity curve and every trade where the
// backtest saved them (GET /lab/*, cloud/api/lab_routes.py; registry research/lab/strategies.json).
// Clicking a trade draws daily candles for its chart symbol with entry/exit markers
// (TradingView's lightweight-charts). Research records only: no orders, no account data.
import { useEffect, useMemo, useRef, useState } from "react";
import { createChart } from "lightweight-charts";
import Shell, { getJson } from "./Shell.jsx";
import { CLOUD_API_URL } from "../App.jsx";
import { T } from "./theme.js";

const STATUS = {
  FAIL: { tone: "red", label: "Failed", why: "Why it failed" },
  PAPER: { tone: "blue", label: "On paper", why: "Why it's on paper, not live" },
  SHELVED: { tone: "amber", label: "Shelved", why: "Why it's shelved" },
  CLOSED: { tone: "amber", label: "Closed", why: "Why it was closed" },
  PENDING: { tone: "amber", label: "Pending", why: "Status" },
};
const UNIT = { inr: v => `₹${Math.round(v).toLocaleString("en-IN")}`, bps: v => `${v.toFixed(2)} bps`, pct: v => `${v.toFixed(2)}%` };
const VERIF = {
  reproduced: { tone: "green", label: "Reproduced" },
  reproduced_with_differences: { tone: "amber", label: "Reproduced, with differences" },
  corrected: { tone: "amber", label: "Re-verified, corrected" },
  cannot_reproduce: { tone: "red", label: "Can't reproduce" },
  saved_at_run: { tone: "blue", label: "Trades saved at run" },
  not_attempted: { tone: "", label: "Not yet verified" },
};
const PAGE = 50;
const SERIES_COLORS = [T.blue, T.amber, T.green];

const fmt = (v, unit) => (v == null ? "—" : (UNIT[unit] || (x => x.toFixed(2)))(v));
const tone = v => (v == null || v === 0 ? T.muted : v > 0 ? T.green : T.red);

function chartOptions(el, height) {
  return {
    width: el.clientWidth, height,
    layout: { background: { color: T.surface }, textColor: T.muted, fontFamily: T.sans },
    grid: { vertLines: { color: T.border }, horzLines: { color: T.border } },
    rightPriceScale: { borderColor: T.border }, timeScale: { borderColor: T.border },
    crosshair: { mode: 0 },
  };
}

function useChart(height) {
  const ref = useRef(null);
  const [chart, setChart] = useState(null);
  useEffect(() => {
    if (!ref.current) return undefined;
    const c = createChart(ref.current, chartOptions(ref.current, height));
    const ro = new ResizeObserver(() => ref.current && c.applyOptions({ width: ref.current.clientWidth }));
    ro.observe(ref.current);
    setChart(c);
    return () => { ro.disconnect(); c.remove(); setChart(null); };
  }, [height]);
  return [ref, chart];
}

// Last value per day, ascending: lightweight-charts needs strictly increasing times.
const perDay = pts => {
  const m = new Map();
  pts.forEach(p => m.set(p.t, p.v));
  return [...m.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([time, value]) => ({ time, value }));
};

function EquityChart({ curves }) {
  const [ref, chart] = useChart(280);
  useEffect(() => {
    if (!chart) return undefined;
    const series = curves.map((c, i) => {
      const s = chart.addLineSeries({ color: SERIES_COLORS[i % 3], lineWidth: 2, title: c.name });
      s.setData(perDay(c.points));
      return s;
    });
    chart.timeScale().fitContent();
    return () => series.forEach(s => chart.removeSeries(s));
  }, [chart, curves]);
  return <div ref={ref} style={{ width: "100%" }} />;
}

const day = s => (s || "").slice(0, 10);
const shift = (iso, days) => {
  const d = new Date(`${day(iso)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};

function TradeChart({ trade, asOf }) {
  const [ref, chart] = useChart(340);
  const [res, setRes] = useState({ id: null, msg: "" });       // the last load's message, tagged by trade
  const msg = !trade.chart_symbol ? "No price chart for this instrument."
    : res.id === trade.trade_id ? res.msg : "";
  useEffect(() => {
    if (!chart || !trade || !trade.chart_symbol) return undefined;
    let series = null;
    let gone = false;
    getJson(`/lab/bars?symbol=${encodeURIComponent(trade.chart_symbol)}&start=${shift(trade.entry_time, -90)}&end=${shift(trade.exit_time, 45)}&as_of=${asOf || ""}`)
      .then(d => {
        if (gone) return;
        if (!d || !d.bars || !d.bars.length) { setRes({ id: trade.trade_id, msg: `No daily bars for ${trade.chart_symbol} on the VM.` }); return; }
        setRes({ id: trade.trade_id, msg: "" });
        series = chart.addCandlestickSeries({
          upColor: T.green, downColor: T.red, borderVisible: false, wickUpColor: T.green, wickDownColor: T.red,
        });
        series.setData(d.bars);
        const long = trade.side !== "short";
        const markers = [
          { time: day(trade.entry_time), position: long ? "belowBar" : "aboveBar", color: T.blue,
            shape: long ? "arrowUp" : "arrowDown", text: `Entry ${trade.entry_price}` },
          { time: day(trade.exit_time), position: long ? "aboveBar" : "belowBar", color: T.amber,
            shape: long ? "arrowDown" : "arrowUp", text: `Exit ${trade.exit_price}` },
        ].sort((a, b) => (a.time < b.time ? -1 : 1));
        series.setMarkers(markers);
        chart.timeScale().fitContent();
      });
    return () => { gone = true; if (series) chart.removeSeries(series); };
  }, [chart, trade, asOf]);
  return (
    <div>
      <div ref={ref} style={{ width: "100%", display: msg ? "none" : "block" }} />
      {msg && <div className="q-empty">{msg}</div>}
    </div>
  );
}

function Trades({ rows, unit, onPick, picked }) {
  const [page, setPage] = useState(0);                       // parent remounts this per strategy (key)
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const view = rows.slice(page * PAGE, page * PAGE + PAGE);
  return (
    <div>
      <div className="q-scroll">
        <table className="q-table">
          <thead><tr>
            <th>#</th><th>Instrument</th><th>Side</th><th>Entry</th><th>Entry px</th><th>Exit</th><th>Exit px</th>
            <th>Gross</th><th>Cost</th><th>Net</th><th>Note</th>
          </tr></thead>
          <tbody>
            {view.map(r => (
              <tr key={r.trade_id} onClick={() => onPick(r)} style={{
                cursor: "pointer", background: picked && picked.trade_id === r.trade_id ? T.raised : undefined }}>
                <td className="q-num">{r.trade_id}</td><td>{r.symbol}</td><td>{r.side}</td>
                <td className="q-num">{r.entry_time}</td><td className="q-num">{r.entry_price}</td>
                <td className="q-num">{r.exit_time}</td><td className="q-num">{r.exit_price}</td>
                <td className="q-num">{fmt(r.gross, unit)}</td><td className="q-num">{fmt(r.cost, unit)}</td>
                <td className="q-num" style={{ color: tone(r.net) }}>{fmt(r.net, unit)}</td>
                <td className="q-faint">{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="q-row" style={{ gap: 8, marginTop: 10, alignItems: "center" }}>
        <button className="q-btn" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Prev</button>
        <span className="q-muted">Page {page + 1} of {pages} · {rows.length} trades</span>
        <button className="q-btn" disabled={page >= pages - 1} onClick={() => setPage(p => p + 1)}>Next</button>
      </div>
    </div>
  );
}

function Detail({ d }) {
  const [picked, setPicked] = useState(null);                // parent remounts this per strategy (key)
  const st = STATUS[d.status] || STATUS.FAIL;
  const unit = d.pnl_unit;
  const s = d.stats;
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="q-card">
        <div className="q-row" style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: 20 }}>{d.name}</h2>
          <span className={`q-pill ${st.tone}`}><span className="dot" />{st.label}</span>
          <span className="q-muted">{d.family} · tested {d.tested}</span>
        </div>
        {d.verification && (
          <div className="q-row" style={{ gap: 8, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
            <span className={`q-pill ${(VERIF[d.verification.status] || VERIF.not_attempted).tone}`}>
              {(VERIF[d.verification.status] || VERIF.not_attempted).label}{d.verification.date ? ` · ${d.verification.date}` : ""}
            </span>
            {d.verification.detail && <span className="q-muted" style={{ fontSize: 13 }}>{d.verification.detail}</span>}
          </div>
        )}
        <div className="q-grid" style={{ marginTop: 16 }}>
          <div><div className="q-label">Why we tested it</div><p>{d.rationale}</p></div>
          <div><div className="q-label">The pre-registered test</div><p>{d.test}</p></div>
          <div><div className="q-label">Result</div><p>{d.result}</p></div>
          <div><div className="q-label">{st.why}</div><p style={{ color: d.status === "FAIL" ? T.text : undefined }}>{d.why}</p></div>
        </div>
        {(Object.keys(d.metrics || {}).length > 0 || s) && (
          <div className="q-stats" style={{ marginTop: 8 }}>
            {Object.entries(d.metrics || {}).map(([k, v]) => (
              <div className="q-stat" key={k}><div className="q-label">{k}</div><div className="v">{v}</div></div>
            ))}
            {s && s.total != null && <>
              <div className="q-stat"><div className="q-label">Trades in file</div><div className="v">{s.n.toLocaleString("en-IN")}</div></div>
              <div className="q-stat"><div className="q-label">Net total</div><div className="v" style={{ color: tone(s.total) }}>{fmt(s.total, unit)}</div></div>
              <div className="q-stat"><div className="q-label">Net per trade</div><div className="v" style={{ color: tone(s.mean) }}>{fmt(s.mean, unit)}</div></div>
              <div className="q-stat"><div className="q-label">Win rate</div><div className="v">{(s.win_rate * 100).toFixed(1)}%</div></div>
              <div className="q-stat"><div className="q-label">Profit factor</div><div className="v">{s.profit_factor ?? "—"}</div></div>
              <div className="q-stat"><div className="q-label">Max drawdown</div><div className="v" style={{ color: T.red }}>{fmt(s.max_drawdown, unit)}</div></div>
            </>}
          </div>
        )}
        <div className="q-faint" style={{ marginTop: 12, fontSize: 12 }}>
          Records: {d.docs.map((p, i) => <span key={p}>{i ? " · " : ""}<code>{p}</code></span>)}
        </div>
      </div>

      {d.trade_rows && d.trade_rows.length ? <>
        <div className="q-card">
          <div className="q-row q-between" style={{ alignItems: "center", marginBottom: 10 }}>
            <div className="q-label">Equity curve: cumulative net ({unit === "bps" ? "bps of notional" : unit === "pct" ? "sum of % per trade" : "₹"}), by exit date</div>
            <a className="q-btn" href={`${CLOUD_API_URL}/lab/strategies/${d.id}/trades.csv`} download>Download trades (CSV)</a>
          </div>
          {d.trades_note && <div className="q-banner amber" style={{ marginBottom: 10 }}>{d.trades_note}</div>}
          <EquityChart curves={d.equity} />
        </div>
        <div className="q-card">
          <div className="q-label" style={{ marginBottom: 10 }}>
            {picked ? `Trade #${picked.trade_id}: ${picked.symbol}, daily candles for ${picked.chart_symbol || "—"} (prices as of ${d.tested})` : "Click a trade to chart it"}
          </div>
          {picked && <TradeChart trade={picked} asOf={d.tested && d.tested.length >= 10 ? d.tested : ""} />}
          <div style={{ marginTop: 12 }}><Trades key={d.id} rows={d.trade_rows} unit={unit} onPick={setPicked} picked={picked} /></div>
        </div>
      </> : (
        <div className="q-card q-empty">
          This backtest didn't save its individual trades. They'll be added as each old backtest gets a trade export and is re-run.
        </div>
      )}
    </div>
  );
}

export default function LabPage({ hash }) {
  const [list, setList] = useState(null);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(false);
  const id = (hash || "").split("/")[2] || "";

  useEffect(() => { getJson("/lab/strategies").then(d => (d ? setList(d.strategies) : setErr(true))); }, []);
  useEffect(() => {
    if (!list || !list.length) return;
    const want = id && list.some(s => s.id === id) ? id : list[0].id;
    if (want !== id) { window.location.hash = `#/lab/${want}`; return; }
    getJson(`/lab/strategies/${want}`).then(d => (d ? setDetail(d) : setErr(true)));
  }, [list, id]);

  const families = useMemo(() => {
    const m = new Map();
    (list || []).forEach(s => m.set(s.family, [...(m.get(s.family) || []), s]));
    return [...m.entries()];
  }, [list]);
  const counts = useMemo(() => (list || []).reduce((a, s) => ({ ...a, [s.status]: (a[s.status] || 0) + 1 }), {}), [list]);

  return (
    <Shell active="lab">
      <div className="q-row q-between" style={{ alignItems: "flex-end", flexWrap: "wrap", gap: 12, marginBottom: 18 }}>
        <div>
          <h1 className="q-h" style={{ margin: 0 }}>Strategy Lab</h1>
          <div className="q-muted">
            Every strategy we tested, with its rationale, test, result and the reason it failed.
            {list && ` ${list.length} strategies: ${Object.entries(counts).map(([k, v]) => `${v} ${(STATUS[k] || {}).label || k}`).join(", ").toLowerCase()}.`}
          </div>
        </div>
        {list && (
          <select className="q-input" value={id} onChange={e => { window.location.hash = `#/lab/${e.target.value}`; }}
                  style={{ minWidth: 340 }}>
            {families.map(([fam, ss]) => (
              <optgroup key={fam} label={fam}>
                {ss.map(s => <option key={s.id} value={s.id}>{s.name} · {(STATUS[s.status] || {}).label || s.status}{s.has_trades ? " · trades" : ""}{s.verification === "reproduced" || s.verification === "corrected" ? " · verified" : ""}</option>)}
              </optgroup>
            ))}
          </select>
        )}
      </div>
      {err && <div className="q-card q-empty">Couldn't load the Strategy Lab from the API.</div>}
      {!err && (!detail || detail.id !== id) && <div className="q-card q-empty">Loading…</div>}
      {detail && detail.id === id && <Detail key={detail.id} d={detail} />}
    </Shell>
  );
}
