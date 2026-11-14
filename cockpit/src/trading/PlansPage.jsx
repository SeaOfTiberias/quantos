// ─── Map plans (#/plans, #/plans/<key>) ─────────────────────────────────────
// user 2026-11-14: one page per pick (F&O screener calls and Darvas breakouts) with the
// map plan the 20:00 IST job made for it (scripts/call_plans.py): the chart with the daily
// and higher-timeframe zones and the plan's levels, where the plan stands, its events, the
// map context and every re-plan. Data: GET /plans and GET /plans/{key}
// (cloud/api/plans_routes.py), read from the job's files; nothing is computed here except
// chart geometry. Paper plans on an UNTESTED rule: nothing here places an order.
import { useEffect, useMemo, useRef, useState } from "react";
import Shell, { getJson } from "./Shell.jsx";
import { T, pct, px, shortDate } from "./theme.js";

// ─── shared bits ────────────────────────────────────────────────────────────

const STATE = {
  waiting: { label: "Waiting for the level", tone: "blue" },
  swept: { label: "Swept, waiting for the reclaim", tone: "amber" },
  trigger_pending: { label: "Triggered: enter at the next open", tone: "amber" },
  triggered: { label: "In the trade", tone: "green" },
  target: { label: "Target hit", tone: "green" },
  stopped: { label: "Stopped", tone: "red" },
  time: { label: "Time exit", tone: "" },
  skipped: { label: "Skipped at the open", tone: "" },
  broke: { label: "Level broke", tone: "" },
  lapsed: { label: "Lapsed", tone: "" },
  "no plan": { label: "No plan", tone: "" },
};
const stateLabel = s => STATE[s]?.label ?? s;
const StatePill = ({ s }) => <span className={`q-pill ${STATE[s]?.tone ?? ""}`}><span className="dot" />{stateLabel(s)}</span>;
const SidePill = ({ side }) => <span className={`q-pill ${side === "CE" ? "green" : "red"}`}>{side === "CE" ? "Call · long" : "Put · short"}</span>;
const SrcPill = ({ src }) => <span className="q-pill">{src === "Darvas" ? "Darvas breakout" : "F&O screener"}</span>;
const R = v => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(2)}R`);
const toneOf = v => (v == null || v === 0 ? T.muted : v > 0 ? T.green : T.red);
const keyHref = k => `#/plans/${encodeURIComponent(k)}`;

function Footnote() {
  return (
    <div className="q-faint" style={{ fontSize: 12, marginTop: 20 }}>
      Paper plans made by code from the map (definitions v3, untested) and recorded before the outcome. They're
      scored against the calls as sent after 4–6 weeks. Not orders: nothing on this page places a trade.
    </div>
  );
}

// ─── list ───────────────────────────────────────────────────────────────────

function Result({ t }) {
  if (!t || t.r == null) return <span className="q-faint">—</span>;
  return (
    <span className="q-num" style={{ color: toneOf(t.r) }}>
      {R(t.r)} <span className="q-faint">({pct(t.pct)}{t.open ? ", open" : ""})</span>
    </span>
  );
}

function Levels({ l }) {
  if (!l) return <span className="q-faint">—</span>;
  return <span className="q-num">{px(l.level)}<span className="q-faint"> → {px(l.target)}</span></span>;
}

function PlanList() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [show, setShow] = useState("open");
  const [src, setSrc] = useState("all");
  useEffect(() => {
    getJson("/plans").then(x => (x ? setD(x) : setErr("Couldn't load the plans. The API may be restarting; try again in a minute.")));
  }, []);
  const rows = (d?.plans || []).filter(r => (show === "all" || (show === "open") === r.open) && (src === "all" || r.src === src));
  const traded = rows.flatMap(r => r.tracks.filter(t => t.r != null));
  return (
    <Shell active="plans">
      <div className="q-between">
        <div>
          <h1 className="q-h1">Map plans</h1>
          <div className="q-sub">Every pick from the F&O screener and the Darvas scan, with the entry the map would take:
            wait for the sweep, enter on the reclaim, stop beyond the sweep, bank at the opposing zone.</div>
        </div>
        <div className="q-row">
          <div className="q-tabs">
            {[["open", "Open"], ["closed", "Closed"], ["all", "All"]].map(([k, l]) =>
              <button key={k} className={show === k ? "on" : ""} onClick={() => setShow(k)}>{l}</button>)}
          </div>
          <div className="q-tabs">
            {[["all", "All picks"], ["F&O", "F&O"], ["Darvas", "Darvas"]].map(([k, l]) =>
              <button key={k} className={src === k ? "on" : ""} onClick={() => setSrc(k)}>{l}</button>)}
          </div>
        </div>
      </div>
      {err && <div className="q-banner red" style={{ marginTop: 16 }}>{err}</div>}
      {!d && !err && <div className="q-empty">Loading plans…</div>}
      {d && (
        <>
          <div className="q-stats" style={{ marginTop: 18 }}>
            <div className="q-stat"><div className="q-label">Open plans</div><div className="v">{d.n_open}</div></div>
            <div className="q-stat"><div className="q-label">Shown</div><div className="v">{rows.length}</div></div>
            <div className="q-stat"><div className="q-label">Entered (shown)</div><div className="v">{traded.length}</div>
              <div className="s">{traded.length ? `mean ${R(traded.reduce((a, t) => a + t.r, 0) / traded.length)}` : "none yet"}</div></div>
            <div className="q-stat"><div className="q-label">Status</div><div className="v" style={{ fontSize: 13 }}>Paper · untested</div>
              <div className="s">first score ~late Dec</div></div>
          </div>
          <div className="q-card" style={{ marginTop: 16, padding: 0 }}>
            {rows.length === 0 ? <div className="q-empty">No {show === "all" ? "" : show} plans{src !== "all" ? ` from ${src}` : ""} yet.
              The job runs at 20:00 IST on weekdays.</div> : (
              <div className="q-scroll">
                <table className="q-table">
                  <thead><tr>
                    <th>Pick</th><th>Called</th><th>Plan status</th><th>Sweep → target</th><th>Breakout → target</th>
                    <th>Last close</th><th>Plan result</th><th>As sent</th>
                  </tr></thead>
                  <tbody>
                    {rows.map(r => {
                      const t = r.tracks.find(x => x.r != null);
                      return (
                        <tr key={r.key} style={{ cursor: "pointer" }} onClick={() => { window.location.hash = keyHref(r.key); }}>
                          <td className="w">
                            <a href={keyHref(r.key)} style={{ color: T.text, fontWeight: 650, textDecoration: "none" }}>{r.sym}</a>
                            <span className="q-faint" style={{ fontSize: 12 }}> · {r.side} · {r.src}</span>
                          </td>
                          <td>{shortDate(r.date)} <span className="q-faint">@ {px(r.called)}</span></td>
                          <td className="w"><StatePill s={r.status} /></td>
                          <td><Levels l={r.sweep} /></td>
                          <td><Levels l={r.breakout} /></td>
                          <td>{px(r.last_close)}</td>
                          <td><Result t={t} /></td>
                          <td style={{ color: toneOf(r.as_sent_pct) }}>{pct(r.as_sent_pct)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className="q-faint" style={{ fontSize: 12, marginTop: 8 }}>
            "As sent" is the call held from its close to the last close, for comparison. Plan result is in R (risk to the stop) and %.
          </div>
        </>
      )}
      <Footnote />
    </Shell>
  );
}

// ─── chart ──────────────────────────────────────────────────────────────────
// Daily candles with the daily zones (filled), the higher-timeframe zones (outlined) and the
// plan's lines. One price axis; hover shows the session's bar.

const LINE = {
  sweep: { color: T.blue, dash: "6 4", label: "sweep" },
  breakout: { color: T.amber, dash: "6 4", label: "breakout" },
  target: { color: T.green, dash: "2 3", label: "target" },
  stop: { color: T.red, dash: "2 3", label: "stop" },
  entry: { color: T.text, dash: "", label: "entry" },
};
const SUPPLY = new Set(["supply", "bear_ob", "bear_fvg"]);

function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    if (!ref.current) return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function planLines(plan) {
  // the latest version's levels, then the levels each track actually used
  const v = plan.versions[plan.versions.length - 1] || {};
  const out = [];
  if (v.sweep) {
    out.push({ ...LINE.sweep, p: v.sweep.level });
    if (v.sweep.target) out.push({ ...LINE.target, p: v.sweep.target.level, label: "target (sweep)" });
  }
  if (v.breakout) {
    out.push({ ...LINE.breakout, p: v.breakout.level });
    if (v.breakout.target) out.push({ ...LINE.target, p: v.breakout.target.level, label: "target (breakout)" });
  }
  for (const t of plan.tracks) {
    if (t.entry != null) out.push({ ...LINE.entry, p: t.entry, label: `entry (${t.kind})` });
    if (t.stop != null) out.push({ ...LINE.stop, p: t.stop, label: `stop (${t.kind})` });
  }
  // one label per price: merge lines within a hair of each other
  const merged = [];
  for (const l of out.sort((a, b) => b.p - a.p)) {
    const m = merged.find(x => Math.abs(x.p - l.p) < 1e-6);
    if (m) { if (!m.label.includes(l.label)) m.label += " · " + l.label; } else merged.push({ ...l });
  }
  return merged;
}

function PlanChart({ plan, page }) {
  const [ref, W] = useWidth();
  const [hover, setHover] = useState(null);
  const call = plan.call;
  const all = page?.bars || [];
  const callIdx = Math.max(0, all.findIndex(b => b[0] >= call.date));
  const bars = all.slice(Math.max(0, callIdx - 60));
  const lines = useMemo(() => planLines(plan), [plan]);
  const card = page?.card || {};
  if (!bars.length) return <div className="q-empty">No bars yet for this pick's chart. The page fills in after the next 20:00 IST run.</div>;

  const H = 440, padL = 8, padR = 168, padT = 14, padB = 26;
  const lo0 = Math.min(...bars.map(b => b[3])), hi0 = Math.max(...bars.map(b => b[2]));
  const span0 = hi0 - lo0 || hi0 * 0.05;
  const inView = p => p >= lo0 - span0 * 0.35 && p <= hi0 + span0 * 0.35;     // keep the scale readable
  const shown = lines.filter(l => inView(l.p));
  const lo = Math.min(lo0, ...shown.map(l => l.p)) - span0 * 0.04;
  const hi = Math.max(hi0, ...shown.map(l => l.p)) + span0 * 0.04;
  const y = p => padT + ((hi - p) / (hi - lo)) * (H - padT - padB);
  const cw = (W - padL - padR) / bars.length;
  const x = i => padL + cw * i + cw / 2;
  const bw = Math.max(1.5, Math.min(9, cw * 0.62));

  const zd = card.zones_d || {};
  const dz = [...(zd.inside || []), ...(zd.above || []), ...(zd.below || [])].filter(z => z.hi >= lo && z.lo <= hi);
  const zh = card.zones || {};
  const hz = [...(zh.inside || []), ...(zh.above || []), ...(zh.below || [])].filter(z => z.hi >= lo && z.lo <= hi);
  const clampY = p => Math.max(padT, Math.min(H - padB, y(p)));

  // event markers on the chart: swept extreme, entry, exit
  const idx = d => bars.findIndex(b => b[0] === d);
  const marks = [];
  for (const t of plan.tracks) {
    for (const e of t.events || []) {
      const i = idx(e.date);
      if (i < 0) continue;
      if (e.what === "swept") marks.push({ i, p: e.extreme, kind: "swept", color: T.blue });
      if (e.what === "entered at the open") marks.push({ i, p: e.entry, kind: "entry", color: T.text });
      if (e.what.startsWith("exit")) marks.push({ i, p: e.price, kind: e.what.replace("exit: ", ""), color: t.r > 0 ? T.green : T.red });
    }
  }
  const ci = idx(call.date);
  const ticks = Array.from({ length: 6 }, (_, k) => lo + ((hi - lo) * (k + 0.5)) / 6);
  const months = bars.map((b, i) => [b[0], i]).filter(([d], i) => i === 0 || d.slice(5, 7) !== bars[i - 1][0].slice(5, 7));

  // label placement: avoid overlaps on the right rail
  const labels = [...shown.map(l => ({ ...l, y: y(l.p) })),
                  { p: bars[bars.length - 1][4], y: y(bars[bars.length - 1][4]), color: T.blue, label: "last close", solid: true }]
    .sort((a, b) => a.y - b.y);
  for (let k = 1; k < labels.length; k++) if (labels[k].y - labels[k - 1].y < 15) labels[k].y = labels[k - 1].y + 15;

  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.floor((e.clientX - r.left - padL) / cw);
    setHover(i >= 0 && i < bars.length ? i : null);
  };
  const hb = hover != null ? bars[hover] : null;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <svg width={W} height={H} style={{ display: "block" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}
           role="img" aria-label={`${call.sym} daily chart with the plan's levels`}>
        {ticks.map(t => <line key={t} x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke={T.border} strokeWidth="1" opacity=".5" />)}
        {hz.map((z, k) => (
          <rect key={`h${k}`} x={padL} width={W - padR - padL} y={clampY(z.hi)} height={Math.max(2, clampY(z.lo) - clampY(z.hi))}
                fill="none" stroke={T.faint} strokeDasharray="4 4" strokeWidth="1"><title>{`HTF zone ${px(z.lo)}–${px(z.hi)}: ${z.why}`}</title></rect>
        ))}
        {dz.map((z, k) => (
          <rect key={`d${k}`} x={padL} width={W - padR - padL} y={clampY(z.hi)} height={Math.max(2, clampY(z.lo) - clampY(z.hi))}
                fill={SUPPLY.has(z.kind) ? "rgba(240,82,82,.10)" : "rgba(34,197,94,.09)"}
                stroke={SUPPLY.has(z.kind) ? "rgba(240,82,82,.35)" : "rgba(34,197,94,.32)"} strokeWidth="1">
            <title>{`${z.name} (formed ${z.formed}${z.touched ? `, ${z.touched}` : ""})`}</title></rect>
        ))}
        {ci >= 0 && <g>
          <line x1={x(ci)} x2={x(ci)} y1={padT} y2={H - padB} stroke={T.muted} strokeDasharray="2 4" />
          <text x={x(ci) + 4} y={padT + 10} fill={T.muted} fontSize="11">called @ {px(call.spot)}</text>
        </g>}
        {bars.map((b, i) => {
          const up = b[4] >= b[1];
          const col = up ? T.green : T.red;
          return (
            <g key={b[0]} opacity={hover == null || hover === i ? 1 : 0.75}>
              <line x1={x(i)} x2={x(i)} y1={y(b[2])} y2={y(b[3])} stroke={col} strokeWidth="1" />
              <rect x={x(i) - bw / 2} width={bw} y={y(Math.max(b[1], b[4]))} height={Math.max(1, Math.abs(y(b[1]) - y(b[4])))}
                    fill={up ? "transparent" : col} stroke={col} strokeWidth="1" rx="1" />
            </g>
          );
        })}
        {shown.map(l => <line key={l.label} x1={padL} x2={W - padR + 6} y1={y(l.p)} y2={y(l.p)}
                              stroke={l.color} strokeDasharray={l.dash} strokeWidth="1.5" />)}
        {labels.map(l => (
          <g key={`lab-${l.label}`}>
            <line x1={W - padR + 6} x2={W - padR + 12} y1={y(l.p)} y2={l.y} stroke={l.color} strokeWidth="1" />
            <text x={W - padR + 14} y={l.y + 4} fontSize="11.5" fill={T.text}>
              <tspan fill={l.color}>■ </tspan><tspan fontFamily={T.mono}>{px(l.p)}</tspan>
              <tspan fill={T.muted}> {l.label}</tspan></text>
          </g>
        ))}
        {marks.map((m, k) => (
          <g key={`m${k}`}>
            <circle cx={x(m.i)} cy={y(m.p)} r="5" fill={T.bg} stroke={m.color} strokeWidth="2" />
            <title>{`${m.kind} ${px(m.p)} on ${bars[m.i][0]}`}</title>
          </g>
        ))}
        {months.map(([d, i]) => <text key={d} x={x(i)} y={H - 8} fill={T.faint} fontSize="11">{shortDate(d)}</text>)}
        {hb && <line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} stroke={T.muted} strokeWidth="1" opacity=".6" />}
      </svg>
      {hb && (
        <div className="q-num" style={{ position: "absolute", top: 6, left: Math.min(x(hover) + 12, W - padR - 190), pointerEvents: "none",
                                         background: T.raised, border: `1px solid ${T.border}`, borderRadius: 8, padding: "6px 10px", fontSize: 12 }}>
          <div style={{ fontFamily: T.sans, fontWeight: 600 }}>{shortDate(hb[0])}</div>
          <div><span className="q-faint">O</span> {px(hb[1])} <span className="q-faint">H</span> {px(hb[2])}</div>
          <div><span className="q-faint">L</span> {px(hb[3])} <span className="q-faint">C</span> {px(hb[4])}</div>
        </div>
      )}
      <div className="q-row q-faint" style={{ fontSize: 12, marginTop: 10, gap: 16 }}>
        <span><Swatch fill="rgba(240,82,82,.10)" stroke="rgba(240,82,82,.35)" /> daily supply</span>
        <span><Swatch fill="rgba(34,197,94,.09)" stroke="rgba(34,197,94,.32)" /> daily demand</span>
        <span><Swatch fill="none" stroke={T.faint} dashed /> weekly / monthly zone</span>
        {Object.values(LINE).map(l => <span key={l.label}><Dash color={l.color} dash={l.dash} /> {l.label}</span>)}
        <span><svg width="12" height="12"><circle cx="6" cy="6" r="4" fill={T.bg} stroke={T.muted} strokeWidth="2" /></svg> event</span>
        {lines.length > shown.length && <span>{lines.length - shown.length} level(s) off the scale: see the plan</span>}
      </div>
    </div>
  );
}
const Swatch = ({ fill, stroke, dashed }) => (
  <svg width="16" height="10" style={{ verticalAlign: "-1px" }}>
    <rect x="0.5" y="0.5" width="15" height="9" rx="2" fill={fill} stroke={stroke} strokeDasharray={dashed ? "3 2" : ""} /></svg>);
const Dash = ({ color, dash }) => (
  <svg width="18" height="8" style={{ verticalAlign: "0px" }}><line x1="0" x2="18" y1="4" y2="4" stroke={color} strokeWidth="2" strokeDasharray={dash} /></svg>);

// ─── one-pager ──────────────────────────────────────────────────────────────

const across = side => (side === "CE" ? "above" : "below");
const dip = side => (side === "CE" ? "a dip through" : "a spike through");

// The plan in words, from the track's own fields (no new numbers are made here).
function TrackStory({ t, v, side }) {
  const lv = t.kind === "sweep" ? v.sweep : v.breakout;
  const tgt = t.target ?? lv?.target?.level;
  const tk = lv?.target?.kind;
  const ev = (t.events || []).slice(-1)[0];
  let head, body;
  if (t.state === "waiting" && t.kind === "sweep") {
    head = `Wait for ${dip(side)} ${px(lv?.level)}`;
    body = `${lv?.kinds?.join(", ")}. Enter at the next open after a daily close back ${across(side)} it; stop beyond the sweep's extreme. Target ${px(tgt)}${tk ? ` (${tk})` : ""}.`;
  } else if (t.state === "waiting") {
    head = `Wait for a daily close ${across(side)} ${px(lv?.level)}`;
    body = `${lv?.kinds?.join(", ")}. Enter at the next open; stop beyond the last 3 sessions' extreme. Target ${px(tgt)}.`;
  } else if (t.state === "swept") {
    head = `Swept ${px(t.level)}: ${side === "CE" ? "low" : "high"} so far ${px(t.extreme)}`;
    body = `Needs a daily close back ${across(side)} ${px(t.level)} within 3 sessions of the sweep, or the level counts as broken.`;
  } else if (t.state === "trigger_pending") {
    head = "Triggered: enter at the next open";
    body = `Stop ${px(t.stop)}, target ${px(tgt)}. No entry if it opens beyond the stop, at the target, or with the target under 1R away.`;
  } else if (t.state === "triggered") {
    head = `In the trade from ${px(t.entry)} (${shortDate(t.entry_date)})`;
    body = `Stop ${px(t.stop)}, target ${px(tgt)}, ${t.held ?? 0} of 15 sessions held. Exits are rule-driven: stop, target or time.`;
  } else {
    head = stateLabel(t.state) + (t.exit != null ? ` at ${px(t.exit)}` : "");
    body = ev ? `${shortDate(ev.date)}: ${ev.what}.` : "";
  }
  return (
    <div style={{ display: "grid", gap: 4 }}>
      <div className="q-row" style={{ gap: 8 }}>
        <span className="q-label" style={{ width: 74 }}>{t.kind}</span>
        <StatePill s={t.state} />
        {t.r != null && <span className="q-num" style={{ color: toneOf(t.r), fontWeight: 650 }}>{R(t.r)} ({pct(t.pct)})</span>}
      </div>
      <div style={{ fontWeight: 600 }}>{head}</div>
      {body && <div className="q-muted" style={{ fontSize: 13 }}>{body}</div>}
    </div>
  );
}

function Timeline({ plan }) {
  const items = [{ date: plan.call.date, what: `Called at ${px(plan.call.spot)}; plan made`, kind: "call" }];
  plan.versions.slice(1).forEach(v => items.push({ date: v.as_of, what: "Re-planned from the new map", kind: "map" }));
  plan.tracks.forEach(t => (t.events || []).forEach(e => {
    const extra = ["level", "extreme", "entry", "stop", "target", "price"].filter(k => e[k] != null).map(k => `${k} ${px(e[k])}`).join(", ");
    items.push({ date: e.date, what: e.what + (extra ? ` (${extra})` : ""), kind: t.kind });
  }));
  items.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  return (
    <div className="q-card">
      <div className="q-label">Timeline</div>
      <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
        {items.map((it, k) => (
          <div key={k} style={{ display: "grid", gridTemplateColumns: "64px 74px 1fr", gap: 8, fontSize: 13 }}>
            <span className="q-num q-faint">{shortDate(it.date)}</span>
            <span className="q-faint" style={{ fontSize: 12 }}>{it.kind}</span>
            <span>{it.what}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const TF = { M: "Monthly", W: "Weekly", D: "Daily" };
function MapContext({ card, asOf }) {
  if (!card || card.error) return <div className="q-card"><div className="q-label">Map</div>
    <div className="q-sub">{card?.error ? `No map read: ${card.error}` : "No map snapshot yet."}</div></div>;
  const zd = card.zones_d || {}, zh = card.zones || {};
  const zrow = (z, k, d) => (
    <div key={k} style={{ display: "grid", gridTemplateColumns: "70px 1fr", gap: 8, fontSize: 13 }}>
      <span className="q-faint" style={{ fontSize: 12 }}>{d}</span>
      <span><span className="q-num">{px(z.lo)}–{px(z.hi)}</span>{" "}
        <span className="q-faint">{z.name ? `${z.name.replace(/^D /, "").replace(/ [\d.]+-[\d.]+$/, "")}${z.touched ? `, ${z.touched}` : ""}` : `${z.strong ? "strong · " : ""}${(z.why || "").split(";")[0]}`}</span></span>
    </div>
  );
  return (
    <div className="q-card">
      <div className="q-between"><div className="q-label">Map at {shortDate(asOf)}</div><span className="q-pill amber">untested</span></div>
      <div className="q-sub">Close {px(card.price)} · ATR {px(card.atr_d)} · {card.alignment}</div>
      <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
        {["M", "W", "D"].filter(k => card.structure?.[k]).map(k => {
          const s = card.structure[k];
          return (
            <div key={k} style={{ fontSize: 13 }}>
              <b style={{ display: "inline-block", width: 70 }}>{TF[k]}</b>
              <span style={{ color: s.state === "up" ? T.green : s.state === "down" ? T.red : T.muted, fontWeight: 650 }}>{s.state}</span>
              <span className="q-faint"> · protected <span className="q-num" style={{ color: T.text }}>{px(s.protected?.px)}</span>
                {" "}· weak <span className="q-num" style={{ color: T.text }}>{px(s.weak?.px)}</span> · {s.range}</span>
            </div>
          );
        })}
      </div>
      <div className="q-label" style={{ marginTop: 16 }}>Daily zones</div>
      <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
        {[...(zd.above || [])].reverse().map((z, k) => zrow(z, `a${k}`, "above"))}
        {(zd.inside || []).map((z, k) => zrow(z, `i${k}`, "price in"))}
        {(zd.below || []).map((z, k) => zrow(z, `b${k}`, "below"))}
        {!(zd.above || zd.below || zd.inside) && <span className="q-faint" style={{ fontSize: 13 }}>Not in this snapshot (made before daily zones).</span>}
      </div>
      <div className="q-label" style={{ marginTop: 16 }}>Weekly / monthly zones</div>
      <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
        {[...(zh.above || [])].reverse().map((z, k) => zrow(z, `ha${k}`, "above"))}
        {(zh.inside || []).map((z, k) => zrow(z, `hi${k}`, "price in"))}
        {(zh.below || []).map((z, k) => zrow(z, `hb${k}`, "below"))}
      </div>
      {card.pivots && <div className="q-faint" style={{ fontSize: 12, marginTop: 14 }}>
        {["W", "M"].filter(k => card.pivots[k]).map(k => `${k} CPR ${px(card.pivots[k].BC)}–${px(card.pivots[k].TC)} (${card.pivots[k].bias}, close ${card.pivots[k].close_vs_cpr})`).join(" · ")}
      </div>}
    </div>
  );
}

function History({ plan }) {
  const fmt = (x, tk) => (x ? <>{px(x.level)}{x.target ? <span className="q-faint"> → {px(x.target.level)}</span> : null}
    <div className="q-faint" style={{ fontFamily: T.sans, fontSize: 11.5, whiteSpace: "normal" }}>{(x.kinds || []).slice(0, 3).join(", ")}{tk && x.target ? ` · target: ${x.target.kind}` : ""}</div></>
    : <span className="q-faint">—</span>);
  return (
    <div className="q-card" style={{ padding: 0 }}>
      <div style={{ padding: "16px 20px 6px" }}>
        <div className="q-label">Plan versions</div>
        <div className="q-sub">A waiting plan is re-drawn each evening from the new map; each version applies only to the sessions after it.</div>
      </div>
      <div className="q-scroll">
        <table className="q-table">
          <thead><tr><th>Made after</th><th>Sweep → target</th><th>Breakout → target</th></tr></thead>
          <tbody>
            {[...plan.versions].reverse().map(v => (
              <tr key={v.as_of}>
                <td>{shortDate(v.as_of)}</td>
                <td style={{ verticalAlign: "top" }}>{v.error ? <span className="q-faint">{v.error}</span> : fmt(v.sweep, true)}</td>
                <td style={{ verticalAlign: "top" }}>{fmt(v.breakout, true)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PlanOne({ k }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    getJson(`/plans/${encodeURIComponent(k)}`).then(x => { if (live) (x ? setD(x) : setErr(`No plan ${k}.`)); });
    return () => { live = false; };
  }, [k]);
  if (err) return <Shell active="plans"><a href="#/plans" className="q-faint" style={{ fontSize: 13 }}>← All plans</a>
    <div className="q-banner red" style={{ marginTop: 16 }}>{err}</div></Shell>;
  if (!d) return <Shell active="plans"><div className="q-empty">Loading the plan…</div></Shell>;
  const { summary: s, plan, page } = d;
  const v = plan.versions[plan.versions.length - 1] || {};
  const done = s.tracks.find(t => t.r != null);
  return (
    <Shell active="plans">
      <a href="#/plans" className="q-faint" style={{ fontSize: 13, textDecoration: "none" }}>← All plans</a>
      <div className="q-between" style={{ marginTop: 10 }}>
        <div>
          <div className="q-row" style={{ gap: 12 }}>
            <h1 className="q-h1">{s.sym}</h1>
            <SidePill side={s.side} /><SrcPill src={s.src} /><StatePill s={s.status} />
          </div>
          <div className="q-sub">Called {shortDate(s.date)} at {px(s.called)} · plan {s.open ? `expires ${shortDate(s.expires)} if nothing triggers` : "closed"}
            {s.replans ? ` · re-planned ${s.replans}×` : ""} · data to {shortDate(s.through)}</div>
        </div>
        <a className="q-btn ghost" href={`#/map/${s.sym}`} style={{ textDecoration: "none" }}>Open the stock map →</a>
      </div>

      <div className="q-stats" style={{ marginTop: 18 }}>
        <div className="q-stat"><div className="q-label">Last close</div><div className="v">{px(s.last_close)}</div>
          <div className="s">called {px(s.called)}</div></div>
        <div className="q-stat"><div className="q-label">Sweep level</div><div className="v" style={{ color: T.blue }}>{px(s.sweep?.level)}</div>
          <div className="s">target {px(s.sweep?.target)}</div></div>
        <div className="q-stat"><div className="q-label">Breakout close</div><div className="v" style={{ color: T.amber }}>{px(s.breakout?.level)}</div>
          <div className="s">{s.breakout ? `target ${px(s.breakout.target)}` : "no breakout plan"}</div></div>
        <div className="q-stat"><div className="q-label">Plan result</div>
          <div className="v" style={{ color: toneOf(done?.r) }}>{done ? R(done.r) : "—"}</div>
          <div className="s">{done ? `${pct(done.pct)}${done.open ? " open" : ""}` : "not entered"}</div></div>
        <div className="q-stat"><div className="q-label">Call as sent</div>
          <div className="v" style={{ color: toneOf(s.as_sent_pct) }}>{pct(s.as_sent_pct)}</div>
          <div className="s">close to last close</div></div>
      </div>

      <div className="q-card" style={{ marginTop: 16 }}>
        <div className="q-between">
          <div><div className="q-label">Chart</div>
            <div className="q-sub">Daily, adjusted · zones from the map of {shortDate(page?.card_as_of)} · hover for the session</div></div>
        </div>
        <div style={{ marginTop: 14 }}><PlanChart plan={plan} page={page} /></div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 16, marginTop: 16 }}>
        <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
          <div className="q-card">
            <div className="q-label">What the plan says now</div>
            <div style={{ display: "grid", gap: 16, marginTop: 12 }}>
              {plan.tracks.length ? plan.tracks.map(t => <TrackStory key={t.kind} t={t} v={v} side={s.side} />)
                : <div className="q-muted">{v.error ? `No plan: ${v.error}.` : "No level within 0.2–4 ATR: the call stands alone."}</div>}
            </div>
          </div>
          <Timeline plan={plan} />
        </div>
        <MapContext card={page?.card} asOf={page?.card_as_of} />
      </div>
      <div style={{ marginTop: 16 }}><History plan={plan} /></div>
      <Footnote />
    </Shell>
  );
}

export default function PlansPage({ hash }) {
  const k = decodeURIComponent((hash || "").split("/").slice(2).join("/") || "");
  return k ? <PlanOne key={k} k={k} /> : <PlanList />;
}
