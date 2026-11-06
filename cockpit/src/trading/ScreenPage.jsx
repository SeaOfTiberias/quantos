// ─── Techno-funda screen (#/screen) ─────────────────────────────────────────
// The user's own screener.in screen, saved once a day at 16:30 IST
// (scripts/run_screen_snapshot.py), from GET /discovery/screen. Each name links to
// its TradingView chart. Record only: no tested edge yet, no paper trades until the
// 2021-26 techno-funda backtest passes.
import { useEffect, useState } from "react";
import Shell, { getJson } from "./Shell.jsx";
import { T, shortDate } from "./theme.js";

const fmt = v => (v == null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 }));

function NameCell({ r }) {
  if (r.tradingview_url) {
    return <a href={r.tradingview_url} target="_blank" rel="noopener noreferrer" style={{ color: T.blue, fontWeight: 600 }}>
      {r.name}</a>;
  }
  return <span style={{ fontWeight: 600 }}>{r.name}</span>;
}

export default function ScreenPage() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    getJson("/discovery/screen").then(x => { if (live) x ? setD(x) : setErr("Couldn't load the screen snapshot."); });
    return () => { live = false; };
  }, []);
  const cols = d?.columns || [];
  return (
    <Shell active="screen">
      <div className="q-between">
        <div>
          <h1 className="q-h1">Techno-funda screen</h1>
          <div className="q-sub">Your screener.in screen, saved after each close. A record only: no tested edge yet, so no paper trades
            until the 2021–26 backtest passes.</div>
        </div>
        {d?.url && <a className="q-btn ghost" href={d.url} target="_blank" rel="noopener noreferrer">Open on screener.in</a>}
      </div>
      {err && <div className="q-banner red" style={{ marginTop: 16 }}>{err}</div>}
      {!d && !err && <div className="q-empty">Loading…</div>}
      {d && !d.session && <div className="q-empty">No snapshot yet. The first one is saved at 16:30 IST on the next trading day.</div>}
      {d?.session && (
        <>
          <div className="q-row" style={{ marginTop: 14, gap: 10 }}>
            <span className="q-pill">{shortDate(d.session)} close</span>
            <span className="q-pill">{d.rows.length} stock{d.rows.length === 1 ? "" : "s"}</span>
            <span className="q-pill">{d.sessions_recorded} session{d.sessions_recorded === 1 ? "" : "s"} recorded</span>
            {d.truncated && <span className="q-pill amber">more than one page: only page 1 saved</span>}
          </div>
          <div className="q-card" style={{ marginTop: 14 }}>
            {d.rows.length === 0 ? <div className="q-empty">Nothing passed the screen on this session.</div> : (
              <div className="q-scroll">
                <table className="q-table">
                  <thead><tr>
                    <th>Company</th><th>Listed</th><th>First seen</th>
                    <th title={`Sessions on the list out of the last ${d.lookback}`}>On list</th>
                    {cols.map(c => <th key={c}>{c}</th>)}
                  </tr></thead>
                  <tbody>
                    {d.rows.map(r => (
                      <tr key={r.screener_url || r.name}>
                        <td className="w"><NameCell r={r} />
                          {r.screener_url && <a href={r.screener_url} target="_blank" rel="noopener noreferrer"
                            className="q-faint" style={{ marginLeft: 8, fontSize: 11.5 }}>screener</a>}</td>
                        <td className="w">{r.nse_symbol ? <span className="q-faint">NSE {r.nse_symbol}</span>
                          : <span className="q-pill amber" title="No NSE listing on screener.in: likely BSE-only or SME, thin liquidity">BSE {r.bse_code}</span>}</td>
                        <td>{shortDate(r.first_seen)}</td>
                        <td>{r.days_in_window}/{d.lookback}</td>
                        {cols.map(c => <td key={c}>{fmt(r.values?.[c])}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {d.dropped?.length > 0 && (
            <div className="q-card" style={{ marginTop: 14 }}>
              <div className="q-label">Dropped off since {shortDate(d.previous_session)}</div>
              <div className="q-row" style={{ marginTop: 8, gap: 14 }}>
                {d.dropped.map(r => <NameCell key={r.screener_url || r.name} r={r} />)}
              </div>
            </div>
          )}
          {d.query && (
            <details className="q-det" style={{ marginTop: 14 }}>
              <summary className="q-faint" style={{ fontSize: 12 }}>Screen query ▸</summary>
              <pre className="q-num q-faint" style={{ fontSize: 12, whiteSpace: "pre-wrap", marginTop: 8 }}>{d.query}</pre>
            </details>
          )}
        </>
      )}
    </Shell>
  );
}
