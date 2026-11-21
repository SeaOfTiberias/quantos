// ─── Evening brief (#/brief) ────────────────────────────────────────────────
// GET /reports/brief (scripts/evening_brief.py, weekdays 20:15 IST; execution plan E6): the NIFTY and
// BANKNIFTY v3 reads, top-500 breadth, tonight's screener and Darvas calls with their plans and the
// vetoes code flags (core/ops/evening_brief.py V1-V4). Map v3 is UNTESTED: markers, never signals.
// Records only, never orders; calls go into the ledger by hand (scripts/ledger.py add).
import { useEffect, useState } from "react";
import Shell, { getJson } from "./Shell.jsx";
import { T, px, shortDate } from "./theme.js";

const lv = d => px(d?.px);

function IndexCard({ sym, c }) {
  if (!c || c.error) return <div className="q-stat"><div className="q-label">{sym}</div><div className="s">no read: {c?.error || "missing"}</div></div>;
  const s = c.structure || {};
  const strong = k => (c.zones?.[k] || []).find(z => z.strong);
  const zb = strong("below"), za = strong("above");
  const zt = z => (z ? `${px(z.lo)}–${px(z.hi)} (${Math.abs(z.edge_pct).toFixed(1)}%)` : "none");
  return (
    <div className="q-stat">
      <div className="q-label"><a href={`#/map/${sym}`} style={{ color: "inherit" }}>{sym}</a></div>
      <div className="v">{px(c.price)}</div>
      <div className="s">{c.alignment}</div>
      <div className="s">W {s.W?.state}: protected {lv(s.W?.protected)}, weak {lv(s.W?.weak)}</div>
      <div className="s">D {s.D?.state}: protected {lv(s.D?.protected)}, weak {lv(s.D?.weak)}</div>
      <div className="s">strong below {zt(zb)} · above {zt(za)}</div>
    </div>
  );
}

function Breadth({ b }) {
  if (!b) return null;
  const sw = side => (b.sweeps?.[side] || []);
  return (
    <div className="q-card" style={{ marginTop: 20 }}>
      <div className="q-label" style={{ marginBottom: 8 }}>Breadth, top {b.n}{b.errors ? ` (${b.errors} unread)` : ""}</div>
      <div>W up <b>{b.W.up}</b> · down <b>{b.W.down}</b> · none {b.W.none} &nbsp;|&nbsp; D up <b>{b.D.up}</b> · down <b>{b.D.down}</b> · none {b.D.none}</div>
      {["low", "high"].map(side => (
        <div key={side} style={{ color: T.muted, fontSize: 12, marginTop: 6 }}>
          Swept {side}s today ({sw(side).length}): {sw(side).length ? sw(side).map(s => `${s.sym}${s.tf === "W" ? " (W)" : ""}`).join(", ") : "none"}
        </div>
      ))}
    </div>
  );
}

function Candidate({ c }) {
  return (
    <div className="q-card" style={{ marginTop: 12 }}>
      <div className="q-between">
        <div><b><a href={`#/map/${c.sym}`} style={{ color: "inherit" }}>{c.sym}</a></b> {c.side} <span className="q-pill">{c.src}</span> at {px(c.spot)}</div>
        <a href={`#/plans/${encodeURIComponent(c.key)}`} style={{ color: T.blue, fontSize: 12 }}>plan page →</a>
      </div>
      {c.error && <div style={{ color: T.red, marginTop: 6 }}>{c.error}</div>}
      {c.results && <div style={{ color: T.muted, fontSize: 12, marginTop: 4 }}>Results {shortDate(c.results)} ({c.results_in} sessions)</div>}
      <table className="q-table" style={{ marginTop: 8 }}>
        <thead><tr><th>Trade</th><th>Entry</th><th>Stop</th><th>Target</th><th>Vetoes (markers)</th></tr></thead>
        <tbody>
          {(c.trades || []).map((t, i) => (
            <tr key={i}>
              <td>{t.basis}</td><td>{px(t.entry)}</td><td>{px(t.stop)}{t.estimate ? " est." : ""}</td><td>{px(t.target)}</td>
              <td>{t.vetoes?.length
                ? t.vetoes.map(v => <div key={v.code} style={{ color: T.amber || T.red }}>{v.code} {v.text}</div>)
                : <span style={{ color: T.muted }}>none flagged</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function BriefPage() {
  const [b, setB] = useState(null);
  useEffect(() => {
    let live = true;
    getJson("/reports/brief").then(d => { if (live && d) setB(d); });
    return () => { live = false; };
  }, []);
  return (
    <Shell active="brief">
      <h1 className="q-h1">Evening brief{b?.session ? ` · ${shortDate(b.session)}` : ""}</h1>
      <div className="q-sub">Index, breadth and tonight's calls with the vetoes code flags. Map v3 is untested: markers, never signals.
        Calls go into the <a href="#/ledger" style={{ color: T.blue }}>ledger</a> by hand (docs/TRADE_REASONING.md).</div>
      {!b ? <div className="q-empty" style={{ marginTop: 18 }}>Loading…</div> : b.error ? <div className="q-empty" style={{ marginTop: 18 }}>{b.error}</div> : (
        <>
          {(b.warnings || []).map(w => <div key={w} style={{ color: T.red, marginTop: 10 }}>⚠ {w}</div>)}
          <div className="q-stats" style={{ marginTop: 18 }}>
            <IndexCard sym="NIFTY" c={b.index?.NIFTY} />
            <IndexCard sym="BANKNIFTY" c={b.index?.BANKNIFTY} />
          </div>
          <Breadth b={b.breadth} />
          <div className="q-label" style={{ marginTop: 20 }}>Candidates ({(b.candidates || []).length})</div>
          {(b.candidates || []).length ? b.candidates.map(c => <Candidate key={c.key} c={c} />)
            : <div className="q-empty">No screener or Darvas calls tonight.</div>}
        </>
      )}
    </Shell>
  );
}
