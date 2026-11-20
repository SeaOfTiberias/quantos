// ─── Call ledger (#/ledger) ─────────────────────────────────────────────────
// Every call from every source, written down before the outcome and scored in R
// (GET /ledger; scripts/ledger.py adds and scores, core/ledger/score.py is the rule).
// Each call sits beside two mechanical baselines for the same symbol and day: the
// call as sent (next open, held 15 sessions) and the frozen map plan. Anything
// that didn't trade counts 0R; an avoided call's would-have-been R is shown apart.
// Records only, never orders.
import { Fragment, useEffect, useState } from "react";
import Shell, { getJson } from "./Shell.jsx";
import { T, px, shortDate } from "./theme.js";

const r = v => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(2)}R`);
const rTone = v => (v == null || v === 0 ? T.muted : v > 0 ? T.green : T.red);
const WHO = { user: "You", claude: "Claude", model: "Other model", screener: "Screener", darvas: "Darvas", book: "Book" };

function entryText(e) {
  if (!e) return "—";
  if (e.kind === "open") return "next open";
  if (e.kind === "close_between") return `close ${px(e.low)}–${px(e.high)}`;
  const k = { limit: "limit", stop: "stop-entry", close_above: "close >", close_below: "close <" }[e.kind] || e.kind;
  return `${k} ${px(e.price)}`;
}

function Group({ label, g }) {
  if (!g || !g.n) {
    return <div className="q-stat"><div className="q-label">{label}</div><div className="v">—</div><div className="s">no calls yet</div></div>;
  }
  return (
    <div className="q-stat">
      <div className="q-label">{label}</div>
      <div className="v" style={{ color: rTone(g.mean_r) }}>{r(g.mean_r)}</div>
      <div className="s">n {g.n} ({g.final} final) · as sent {r(g.as_sent)} · map plan {r(g.map_plan)}
        {g.avoided ? ` · ${g.avoided} avoided (if taken ${r(g.avoided_if_taken)})` : ""}</div>
    </div>
  );
}

function Calls({ calls }) {
  const [open, setOpen] = useState({});
  if (!calls.length) return <div className="q-empty">No calls in the ledger yet.</div>;
  return (
    <table className="q-table">
      <thead><tr>
        <th>Called</th><th>Who</th><th>Call</th><th>Entry</th><th>Stop / target</th><th>Decision</th>
        <th>Call</th><th>As sent</th><th>Map plan</th>
      </tr></thead>
      <tbody>
        {calls.map(c => {
          const s = c.score || {};
          return (
            <Fragment key={c.id}>
              <tr onClick={() => setOpen(o => ({ ...o, [c.id]: !o[c.id] }))} style={{ cursor: "pointer" }}>
                <td>{shortDate(c.as_of)}</td>
                <td>{WHO[c.who] || c.who}</td>
                <td><b>{c.symbol}</b> {c.side}</td>
                <td>{entryText(c.entry)}</td>
                <td>{px(c.stop)} / {px(c.target)}</td>
                <td><span className={`q-pill ${c.decision === "taken" ? "blue" : ""}`}>{c.decision}</span></td>
                <td style={{ color: rTone(s.r_if_taken) }}>{s.call ? `${s.call.state} ${r(s.r_if_taken)}` : "not scored"}</td>
                <td style={{ color: rTone(s.r_as_sent) }}>{s.as_sent ? r(s.r_as_sent) : "—"}</td>
                <td style={{ color: rTone(s.r_map_plan) }}>{s.map_plan ? `${s.map_plan.state} ${r(s.r_map_plan)}` : "—"}</td>
              </tr>
              {open[c.id] && (
                <tr><td colSpan={9} style={{ color: T.muted, fontSize: 12, lineHeight: 1.6 }}>
                  <div><b>Why:</b> {c.why}</div>
                  {c.salvage && <div><b>Salvage plan:</b> {c.salvage}</div>}
                  <div><b>Map plan baseline:</b> {c.map_plan ? `sweep ${px(c.map_plan.level)} (${(c.map_plan.kinds || []).join(", ")}), target ${px(c.map_plan.target)}` : "none on the call evening"}</div>
                  {s.error && <div style={{ color: T.red }}>Score error: {s.error}</div>}
                  <div>{c.id}{c.source_ref ? ` · from ${c.source_ref}` : ""}</div>
                </td></tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

export default function LedgerPage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    let live = true;
    const load = () => getJson("/ledger").then(d => { if (live && d) setData(d); });
    load();
    const id = setInterval(load, 300000);
    return () => { live = false; clearInterval(id); };
  }, []);
  const s = data?.summary || {};
  return (
    <Shell active="ledger">
      <div className="q-between">
        <div>
          <h1 className="q-h1">Call ledger</h1>
          <div className="q-sub">Every call written down before the outcome and scored in R against the call as sent and the map plan.
            Untraded = 0R. Records, not orders.{data?.scored_at ? ` Scored ${shortDate(data.scored_at)}.` : ""}</div>
        </div>
      </div>
      <div className="q-stats" style={{ marginTop: 18 }}>
        <Group label="Discretionary" g={s.discretionary} />
        <Group label="Your calls" g={s.user} />
        <Group label="Claude's calls" g={s.claude} />
        <Group label="Mechanical (screener, Darvas)" g={s.mechanical} />
      </div>
      <div className="q-card" style={{ marginTop: 20 }}>
        <div className="q-label" style={{ marginBottom: 8 }}>Calls</div>
        {data ? <Calls calls={data.calls || []} /> : <div className="q-empty">Loading…</div>}
      </div>
    </Shell>
  );
}
