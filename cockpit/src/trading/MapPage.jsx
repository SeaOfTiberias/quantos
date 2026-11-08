// ─── Stock map (#/map/SYMBOL) ───────────────────────────────────────────────
// docs/MARKET_MAP_SCREENS.md screens 1 and 2. A vertical price ladder of the
// stock's zones (GET /map/{symbol} -> core/market_map/read.py), the "where
// price is" read, and the trade check (POST /map/{symbol}/check): R, the room
// to the first strong zone, stop placement, flags. Every element carries its
// test status; the banner names the layers not built yet. Read only: nothing
// here places, sizes or moves an order.
import { useEffect, useState } from "react";
import Shell, { getJson, postJson } from "./Shell.jsx";
import { T, px } from "./theme.js";
import { TestBadge, TradeLines, ZoneLine } from "./MapRead.jsx";

// Strong-zone fill by test status (screens rule 2): untested amber, failed grey.
const FILL = { untested: { bg: "rgba(245,165,36,.10)", line: "rgba(245,165,36,.45)" },
               failed: { bg: "rgba(163,172,189,.16)", line: "rgba(163,172,189,.45)" } };
FILL["failed its test"] = FILL.failed;
const SPAN_ATR = 6;            // the ladder shows price +/- this many ATR (and any trade levels)
const H = 560;

function Ladder({ rd, weak, trade }) {
  const atr = rd.atr || rd.price * 0.02;
  const marks = trade ? [trade.entry, trade.stop, trade.target].filter(v => v != null) : [];
  const lo = Math.min(rd.price - SPAN_ATR * atr, ...marks.map(v => v - atr));
  const hi = Math.max(rd.price + SPAN_ATR * atr, ...marks.map(v => v + atr));
  const y = p => ((hi - p) / (hi - lo)) * H;
  const zs = rd.zones.filter(z => (z.strong || weak) && z.high >= lo && z.low <= hi);
  const off = { above: rd.zones.filter(z => z.strong && z.low > hi).length, below: rd.zones.filter(z => z.strong && z.high < lo).length };
  const ticks = Array.from({ length: 7 }, (_, i) => lo + ((hi - lo) * i) / 6);
  const line = (p, color, label, dash) => (
    <div key={label} style={{ position: "absolute", left: 64, right: 0, top: y(p), borderTop: `1.5px ${dash ? "dashed" : "solid"} ${color}` }}>
      <span className="q-num" style={{ position: "absolute", left: 4, top: -18, fontSize: 11.5, color, background: T.surface, padding: "0 4px" }}>
        {label} {px(p)}</span>
    </div>
  );
  return (
    <div>
      <style>{"@media (max-width: 640px) { .q-zmeta { display: none; } }"}</style>
      {off.above > 0 && <div className="q-faint" style={{ fontSize: 12, marginBottom: 6 }}>↑ {off.above} more strong zone{off.above > 1 ? "s" : ""} above the scale</div>}
      <div style={{ position: "relative", height: H, borderLeft: `1px solid ${T.border}`, marginLeft: 0 }}>
        {ticks.map(t => (
          <div key={t} className="q-num q-faint" style={{ position: "absolute", left: 0, width: 58, top: y(t) - 8, fontSize: 11, textAlign: "right" }}>{px(t)}</div>
        ))}
        {zs.map(z => {
          const top = y(z.high), h = Math.max(3, y(z.low) - top);
          return (
            <div key={`${z.low}-${z.high}`} title={`${z.range} · ${z.why}`}
                 style={{ position: "absolute", left: 64, right: 0, top, height: h, borderRadius: 4,
                          background: z.strong ? FILL[z.test]?.bg ?? FILL.failed.bg : "transparent",
                          border: `1px ${z.strong ? "solid" : "dashed"} ${z.strong ? FILL[z.test]?.line ?? FILL.failed.line : "rgba(93,102,121,.6)"}` }}>
              <div className="q-row" style={{ position: "absolute", right: 8, top: h / 2 - 9, gap: 6, fontSize: 11.5, flexWrap: "nowrap", whiteSpace: "nowrap" }}>
                <span className="q-num" style={{ color: z.strong ? T.text : T.faint, fontWeight: z.strong ? 650 : 400 }}>{z.range}</span>
                <span className="q-faint q-zmeta">{z.families.join(" · ")} · {z.score}</span>
                {z.where !== "inside" && <span className="q-faint q-zmeta">{z.distance_atr} ATR · {z.distance_pct}%</span>}
              </div>
            </div>
          );
        })}
        {trade?.target != null && line(trade.target, T.green, "target", true)}
        {trade && line(trade.stop, T.red, "stop", true)}
        {trade && line(trade.entry, T.text, "entry", true)}
        {!trade && line(rd.price, T.blue, rd.price_source === "live" ? "live" : "close", false)}
      </div>
      {off.below > 0 && <div className="q-faint" style={{ fontSize: 12, marginTop: 6 }}>↓ {off.below} more strong zone{off.below > 1 ? "s" : ""} below the scale</div>}
      <div className="q-row q-faint" style={{ fontSize: 12, marginTop: 10, gap: 14 }}>
        <span><span style={{ display: "inline-block", width: 14, height: 9, background: (FILL[rd.status] || FILL.failed).bg, border: `1px solid ${(FILL[rd.status] || FILL.failed).line}`, borderRadius: 2 }} /> strong zone ({rd.status})</span>
        {weak && <span><span style={{ display: "inline-block", width: 14, height: 9, border: `1px dashed ${T.faint}`, borderRadius: 2 }} /> weak zone</span>}
        <span>scale ±{SPAN_ATR} ATR ({px(rd.atr)}) · zone width {px(rd.zone_width)}</span>
      </div>
    </div>
  );
}

// The L1 structure per timeframe (rd.l1.tf): SMC state, last BOS/CHoCH, protected and weak
// levels, the last sweep of the weak level (display only: its definition is frozen in S7).
const TF_NAME = { M: "Monthly", W: "Weekly", D: "Daily" };
function Structure({ l1 }) {
  if (!l1 || l1.error || !l1.tf) return null;
  const col = st => (st === "up" ? T.green : st === "down" ? T.red : T.faint);
  return (
    <div className="q-card">
      <div className="q-between">
        <div className="q-label">Structure (SMC)</div>
        <TestBadge test={l1.status} />
      </div>
      <div className="q-sub">{l1.alignment?.text}</div>
      <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
        {["M", "W", "D"].map(tf => {
          const s = l1.tf[tf];
          if (!s || s.state === "none") return <div key={tf} className="q-faint" style={{ fontSize: 13 }}>{TF_NAME[tf]}: no structure yet</div>;
          const e = s.last_event, p = s.protected, w = s.weak, sw = (s.sweeps || []).slice(-1)[0];
          const [pk, wk] = s.state === "up" ? ["low", "high"] : ["high", "low"];
          return (
            <div key={tf} style={{ fontSize: 13 }}>
              <div className="q-row" style={{ gap: 8, alignItems: "baseline" }}>
                <b style={{ width: 66 }}>{TF_NAME[tf]}</b>
                <span style={{ color: col(s.state), fontWeight: 650 }}>{s.state}</span>
                <span className="q-faint">for {s.age_bars} bars · last {e.type} {e.direction} at {px(e.level)} ({e.date})</span>
              </div>
              <div className="q-faint" style={{ paddingLeft: 74 }}>
                protected {pk} <span className="q-num" style={{ color: T.text }}>{px(p.price)}</span> ({p.date}) ·
                weak {wk} <span className="q-num" style={{ color: T.text }}>{px(w.price)}</span> ({w.date})
              </div>
              {sw && <div className="q-faint" style={{ paddingLeft: 74, fontSize: 12 }}>
                last sweep: weak {sw.side} {px(sw.level)} taken to {px(sw.extreme)} on {sw.date}, closed back inside ({sw.status})</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// L2, the daily layer (rd.l1.l2): daily pivots and virgin session levels from 5-minute bars.
// Shown beside the zones and never clustered into them (definitions v1 §8).
function DailyLayer({ l2 }) {
  if (!l2) return null;
  const p = l2.pivots;
  const vl = xs => (xs || []).map(x => `${x.kind} ${x.name} ${px(x.price)} (${x.session}, ${x.distance_atr} ATR)`).join(" · ") || "none";
  return (
    <div className="q-card">
      <div className="q-between">
        <div className="q-label">Daily layer</div>
        <TestBadge test={l2.status} />
      </div>
      <div className="q-sub">Intraday levels, shown beside the zones and never counted in them.</div>
      {p && <div style={{ fontSize: 13, marginTop: 10 }}>
        <div>Pivots from {p.from_session}: CPR <span className="q-num">{px(p.cpr.BC)}–{px(p.cpr.TC)}</span>, width {p.cpr.width_pct}% ({p.cpr.reading}), {p.relationship} vs the day before</div>
        <div className="q-faint" style={{ fontSize: 12 }}>{p.levels.map(x => `${x.name} ${px(x.price)}`).join(" · ")}</div>
      </div>}
      <div style={{ fontSize: 13, marginTop: 10 }}>
        {l2.sessions ? <>
          <div>Virgin session levels: {l2.n_virgin} from {l2.sessions} sessions since {l2.history_from}</div>
          <div className="q-faint" style={{ fontSize: 12 }}>above: {vl(l2.virgin_above)}</div>
          <div className="q-faint" style={{ fontSize: 12 }}>below: {vl(l2.virgin_below)}</div>
        </> : <div className="q-faint">No 5-minute bars for session profiles.</div>}
      </div>
    </div>
  );
}

function TradeCheck({ sym, onResult, status }) {
  const [f, setF] = useState({ side: "long", entry: "", stop: "", target: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState(null);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const run = async () => {
    setBusy(true); setErr("");
    try {
      const d = await postJson(`/map/${sym}/check`, {
        side: f.side, entry: Number(f.entry), stop: Number(f.stop), target: f.target ? Number(f.target) : null,
      });
      setRes(d); onResult(d);
    } catch (e) { setErr(String(e.message || e)); setRes(null); onResult(null); }
    setBusy(false);
  };
  const clear = () => { setRes(null); onResult(null); };
  const ready = Number(f.entry) > 0 && Number(f.stop) > 0;
  return (
    <div className="q-card">
      <div className="q-label">Trade check</div>
      <div className="q-sub">Where a trade sits on this map. Advisory: it places nothing, and the zones it measures against are {status === "failed its test" ? "the old map's, which failed their test" : "untested"}.</div>
      <div className="q-row" style={{ marginTop: 12, alignItems: "flex-end" }}>
        <div><div className="q-label">Side</div>
          <div className="q-tabs">
            {["long", "short"].map(s => <button key={s} className={f.side === s ? "on" : ""} onClick={() => set("side", s)}>{s}</button>)}
          </div></div>
        {["entry", "stop", "target"].map(k => (
          <label key={k}><div className="q-label">{k}{k === "target" ? " (opt.)" : ""}</div>
            <input className="q-input" style={{ width: 84 }} value={f[k]} onChange={e => set(k, e.target.value)} inputMode="decimal" /></label>
        ))}
        <button className="q-btn primary" disabled={!ready || busy} onClick={run}>{busy ? "Checking…" : "Check"}</button>
        {res && <button className="q-btn ghost" onClick={clear}>Clear</button>}
      </div>
      {err && <div className="q-banner red" style={{ marginTop: 12 }}>{err}</div>}
      {res && <div style={{ marginTop: 14 }}><TradeLines t={res.trade} /></div>}
    </div>
  );
}

// One mount per stock (keyed in MapPage), so a new symbol starts with a clean read and trade check.
function StockMap({ sym }) {
  const [q, setQ] = useState(sym);
  const [rd, setRd] = useState(null);
  const [err, setErr] = useState("");
  const [weak, setWeak] = useState(false);
  const [check, setCheck] = useState(null);
  useEffect(() => {
    if (!sym) return;
    let live = true;
    getJson(`/map/${sym}`).then(d => { if (live) d ? setRd(d) : setErr(`No map for ${sym}: Fyers may be down, or it isn't an NSE stock.`); });
    return () => { live = false; };
  }, [sym]);
  const go = () => { if (q.trim()) window.location.hash = `#/map/${q.trim().toUpperCase()}`; };
  const shown = check || rd;
  return (
    <Shell active="map">
      <div className="q-between">
        <div>
          <h1 className="q-h1">Stock map{sym ? `: ${sym}` : ""}</h1>
          <div className="q-sub">Where the stock has done business and turned. Markers for reading a trade, never signals.</div>
        </div>
        <div className="q-row">
          <input className="q-input" style={{ width: 140 }} value={q} placeholder="HDFCBANK"
                 onChange={e => setQ(e.target.value.toUpperCase())} onKeyDown={e => e.key === "Enter" && go()} />
          <button className="q-btn" onClick={go}>Open</button>
        </div>
      </div>
      {!sym && <div className="q-empty">Type an NSE stock to open its map.</div>}
      {err && <div className="q-banner red" style={{ marginTop: 16 }}>{err}</div>}
      {sym && !rd && !err && <div className="q-empty">Loading the map…</div>}
      {rd && (
        <>
          {rd.source === "l1" ? (
            <div className="q-banner amber" style={{ marginTop: 16 }}>
              <b>Higher-timeframe map, untested.</b> Built from {rd.layers.shown.join("; ")}. Not built yet: {rd.layers.missing.join("; ")}.
              Most zones count as strong under v1, so "strong" selects little until the tests run.
            </div>
          ) : (
            <div className="q-banner amber" style={{ marginTop: 16 }}>
              <b>Old 100-day map ({rd.fallback}).</b> Built from {rd.layers.shown.join(", ")}. Not built yet: {rd.layers.missing.join("; ")}.
              A multi-year base can sit where this map shows "no strong zone".
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 16, marginTop: 16 }}>
            <div className="q-card">
              <div className="q-between">
                <div>
                  <div className="q-label">Price ladder</div>
                  <div className="q-sub">
                    {rd.source === "l1" ? `Bhavcopy to ${rd.built_for}` : `Map built for ${rd.built_for} (${rd.source === "file" ? "saved map" : "built now"})`} · price {px(rd.price)}
                    {rd.price_source === "live" ? " live" : " (the map's close; live price unavailable)"}
                  </div>
                </div>
                <div className="q-row">
                  <TestBadge test={rd.status} />
                  <label className="q-row" style={{ gap: 6, fontSize: 13 }}>
                    <input type="checkbox" checked={weak} onChange={e => setWeak(e.target.checked)} /> {rd.source === "l1" ? "single-family zones" : "weak zones"}</label>
                </div>
              </div>
              <div style={{ marginTop: 16 }}><Ladder rd={rd} weak={weak} trade={check?.trade} /></div>
            </div>
            <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
              <div className="q-card">
                <div className="q-label">Where price is</div>
                <div className="q-sub">at {px(shown.price)}{check ? " (the trade's entry)" : ""}</div>
                <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
                  {shown.inside && <div className="q-banner" style={{ borderColor: T.border, color: T.text }}>
                    Inside the strong zone <b>{shown.inside.range}</b> <span className="q-faint">({shown.inside.why})</span></div>}
                  <ZoneLine label="Above" z={shown.above} />
                  <ZoneLine label="Below" z={shown.below} />
                </div>
                <div className="q-faint" style={{ fontSize: 12, marginTop: 12 }}>{rd.note}</div>
              </div>
              <Structure l1={rd.l1} />
              <DailyLayer l2={rd.l1?.l2} />
              <TradeCheck sym={sym} onResult={setCheck} status={rd.status} />
            </div>
          </div>
        </>
      )}
    </Shell>
  );
}

export default function MapPage({ hash }) {
  const sym = decodeURIComponent((hash || "").split("/")[2] || "").toUpperCase();
  return <StockMap key={sym} sym={sym} />;
}
