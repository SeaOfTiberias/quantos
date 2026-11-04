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
import { GREY, TestBadge, TradeLines, ZoneLine } from "./MapRead.jsx";

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
                          background: z.strong ? "rgba(163,172,189,.16)" : "transparent",
                          border: `1px ${z.strong ? "solid" : "dashed"} ${z.strong ? "rgba(163,172,189,.45)" : "rgba(93,102,121,.6)"}` }}>
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
        <span><span style={{ display: "inline-block", width: 14, height: 9, background: "rgba(163,172,189,.16)", border: `1px solid ${GREY}`, borderRadius: 2 }} /> strong zone</span>
        {weak && <span><span style={{ display: "inline-block", width: 14, height: 9, border: `1px dashed ${T.faint}`, borderRadius: 2 }} /> weak zone</span>}
        <span>scale ±{SPAN_ATR} ATR ({px(rd.atr)}) · zone width {px(rd.zone_width)}</span>
      </div>
    </div>
  );
}

function TradeCheck({ sym, onResult }) {
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
      <div className="q-sub">Where a trade sits on this map. Advisory: it places nothing, and the zones it measures against failed their test.</div>
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
          <div className="q-banner amber" style={{ marginTop: 16 }}>
            <b>Short-sighted map.</b> Built from {rd.layers.shown.join(", ")}. Not built yet: {rd.layers.missing.join("; ")}.
            A multi-year base can sit where this map shows "no strong zone" (the 23 Oct HDFCBANK short).
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 16, marginTop: 16 }}>
            <div className="q-card">
              <div className="q-between">
                <div>
                  <div className="q-label">Price ladder</div>
                  <div className="q-sub">
                    Map built for {rd.built_for} ({rd.source === "file" ? "saved map" : "built now"}) · price {px(rd.price)}
                    {rd.price_source === "live" ? " live" : " (the map's close; live price unavailable)"}
                  </div>
                </div>
                <div className="q-row">
                  <TestBadge test={rd.status} />
                  <label className="q-row" style={{ gap: 6, fontSize: 13 }}>
                    <input type="checkbox" checked={weak} onChange={e => setWeak(e.target.checked)} /> weak zones</label>
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
              <TradeCheck sym={sym} onResult={setCheck} />
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
