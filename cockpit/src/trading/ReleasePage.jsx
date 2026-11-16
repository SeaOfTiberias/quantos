// ─── Order release (#/release) ──────────────────────────────────────────────
// user 2026-11-16: the order rule is unchanged (code drafts, code checks, the user releases);
// this page replaces typing `qorder.py --yes` on the VM. Tickets are drafted by code
// (core/orders/tickets.py); a release needs a 6-digit code from the user's authenticator app,
// then the server runs every leg through core/orders/gateway.py (checks on a fresh quote, then
// the journal). PAPER unless agent/config.yaml has both orders.live and orders.release_page: live.
// Exits are not here: the position manager places them. Every number comes from the API.
import { useEffect, useState } from "react";
import Shell, { getJson, postJson } from "./Shell.jsx";
import { T, inr, px, clock, shortDate } from "./theme.js";

const MODE = {
  paper: { label: "PAPER: releases are journalled, nothing reaches the broker", tone: "blue" },
  live: { label: "LIVE: releases send real orders to ICICI Direct", tone: "red" },
  off: { label: "OFF: the kill switch is on, no orders", tone: "amber" },
};
const STATUS = {
  pending: "amber", released: "green", refused: "red", rejected: "", expired: "", releasing: "amber",
};

function legText(l) {
  const what = l.product === "futures" ? "FUT" : `${l.strike} ${l.right === "call" ? "CE" : "PE"}`;
  return `${l.action.toUpperCase()} ${l.qty} ${l.code} ${shortDate(l.expiry)} ${what} @ ${px(l.price)}`;
}

function Ticket({ t, mode, onDone }) {
  const [code, setCode] = useState("");
  const [scale, setScale] = useState(1);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const pending = t.status === "pending";
  const act = async (what) => {
    setBusy(true); setMsg("");
    try {
      if (what === "release") {
        await postJson(`/release/${t.id}/release`, { code, qty_scale: scale < 1 ? scale : null });
      } else {
        await postJson(`/release/${t.id}/reject`);
      }
      onDone();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy(false); setCode("");
  };
  return (
    <div className="q-card" style={{ marginTop: 12 }}>
      <div className="q-between">
        <div className="q-row">
          <b style={{ fontSize: 16 }}>{t.symbol}</b>
          <span className="q-pill">{t.strategy}</span>
          <span className={`q-pill ${STATUS[t.status] ?? ""}`}><span className="dot" />{t.status}</span>
          {t.paper && t.status === "released" && <span className="q-pill blue">paper</span>}
        </div>
        <div className="q-faint" style={{ fontSize: 12 }}>
          drafted {shortDate(t.created)} {clock(t.created)} · valid until {shortDate(t.valid_until)} {t.valid_until.slice(11, 16)} IST
        </div>
      </div>
      <div className="q-sub" style={{ marginTop: 8 }}>{t.why}</div>
      <div style={{ marginTop: 10 }}>
        {t.legs.map((l, k) => <div key={k} className="q-num" style={{ fontSize: 13.5 }}>{legText(l)}</div>)}
      </div>
      <div className="q-row" style={{ marginTop: 10, fontSize: 13 }}>
        <span>Max loss <b className="q-num" style={{ color: T.red }}>{t.max_loss == null ? "unknown" : inr(t.max_loss)}</b></span>
        {t.stop != null && <span className="q-faint">stop <span className="q-num">{px(t.stop)}</span></span>}
        {t.target != null && <span className="q-faint">target <span className="q-num">{px(t.target)}</span></span>}
        <span className="q-faint">void if price moves over {t.max_move_pct}%</span>
      </div>
      {t.results?.length > 0 && (
        <div style={{ marginTop: 10, fontSize: 12.5 }}>
          {t.results.map((r, k) => (
            <div key={k} className="q-num" style={{ color: r.ok ? T.green : T.red }}>
              {legText(r.leg)} → {r.ok ? (r.sent ? `sent, order ${r.order_id}` : "paper") : `refused: ${(r.reasons || []).join("; ")}`}
            </div>
          ))}
        </div>
      )}
      {pending && mode !== "off" && (
        <div className="q-row" style={{ marginTop: 14 }}>
          <select className="q-input" value={scale} onChange={e => setScale(Number(e.target.value))} title="Quantity can only go down">
            {[1, 0.75, 0.5, 0.25].map(s => <option key={s} value={s}>{s === 1 ? "full size" : `${s * 100}% size`}</option>)}
          </select>
          <input className="q-input" style={{ width: 110 }} inputMode="numeric" maxLength={6} placeholder="6-digit code"
                 value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ""))} />
          <button className={`q-btn ${mode === "live" ? "" : "primary"}`} style={mode === "live" ? { background: T.red, color: "#fff", borderColor: T.red } : {}}
                  disabled={busy || code.length !== 6} onClick={() => act("release")}>
            {mode === "live" ? "Release LIVE order" : "Release (paper)"}
          </button>
          <button className="q-btn ghost" disabled={busy} onClick={() => act("reject")}>Reject</button>
        </div>
      )}
      {msg && <div className="q-banner red" style={{ marginTop: 10 }}>{msg}</div>}
    </div>
  );
}

export default function ReleasePage() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const load = () => getJson("/release").then(x => (x ? (setD(x), setErr("")) : setErr("Couldn't load tickets. The API may be restarting.")));
  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, []);
  const kill = async () => {
    if (!window.confirm("Turn the kill switch ON? Every new order stops. Turning it off again is done with enable-orders.ps1.")) return;
    try { await postJson("/release/kill"); load(); } catch (e) { setErr(String(e.message || e)); }
  };
  const m = d && MODE[d.mode];
  const pending = (d?.tickets || []).filter(t => t.status === "pending");
  const done = (d?.tickets || []).filter(t => t.status !== "pending");
  return (
    <Shell active="release">
      <div className="q-between">
        <div>
          <h1 className="q-h1">Order release</h1>
          <div className="q-sub">Entry tickets drafted by code. You release them with a code from your authenticator app;
            the order checks run again on a fresh quote. Exits are placed by the position manager, not here.</div>
        </div>
        {d && !d.kill_switch && <button className="q-btn" style={{ borderColor: T.red, color: T.red }} onClick={kill}>Kill switch ON</button>}
      </div>
      {err && <div className="q-banner red" style={{ marginTop: 16 }}>{err}</div>}
      {!d && !err && <div className="q-empty">Loading…</div>}
      {d && (
        <>
          <div className={`q-banner ${m.tone}`} style={{ marginTop: 16, fontWeight: 650 }}>{m.label}</div>
          {!d.codes_ready && <div className="q-banner amber" style={{ marginTop: 10 }}>
            Release codes aren't set up yet. On the VM, in your own terminal: <span className="q-num">python scripts/release_setup.py</span>, then add the link to your authenticator app.</div>}
          <h2 style={{ fontSize: 15, marginTop: 22 }}>Waiting for you ({pending.length})</h2>
          {pending.length === 0 ? <div className="q-empty">No tickets waiting. Strategies draft them in the evening; they expire at the time shown.</div>
            : pending.map(t => <Ticket key={t.id} t={t} mode={d.mode} onDone={load} />)}
          {done.length > 0 && <>
            <h2 style={{ fontSize: 15, marginTop: 26 }}>Decided</h2>
            {done.slice(0, 20).map(t => <Ticket key={t.id} t={t} mode={d.mode} onDone={load} />)}
          </>}
          {d.journal?.length > 0 && <>
            <h2 style={{ fontSize: 15, marginTop: 26 }}>Order journal (last {d.journal.length})</h2>
            <div className="q-card" style={{ padding: 0 }}><div className="q-scroll"><table className="q-table">
              <thead><tr><th>Time</th><th>Order</th><th>Result</th></tr></thead>
              <tbody>{d.journal.map((r, k) => (
                <tr key={k}><td>{shortDate(r.ts)} {clock(r.ts)}</td>
                  <td>{(r.action || "").toUpperCase()} {r.qty} {r.code} @ {px(r.price)} <span className="q-faint">[{r.purpose}]</span></td>
                  <td className="w" style={{ color: r.ok ? (r.sent ? T.green : T.blue) : T.red }}>
                    {r.ok ? (r.sent ? "sent" : "paper") : `refused: ${(r.reasons || []).join("; ")}`}</td></tr>))}
              </tbody></table></div></div>
          </>}
        </>
      )}
    </Shell>
  );
}
