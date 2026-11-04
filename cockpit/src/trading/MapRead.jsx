// ─── Market Map pieces shared by #/map and #/ideas ─────────────────────────
// Every map element carries its test status (docs/MARKET_MAP_SCREENS.md rule 2):
// untested amber, passed green, failed its test grey. Numbers are map_read
// fields from the API (core/market_map/read.py); nothing is computed here.
import { T, px } from "./theme.js";

export const GREY = "#A3ACBD";
const STATUS = {
  untested: { color: T.amber, bg: "rgba(245,165,36,.08)", border: "rgba(245,165,36,.4)" },
  passed: { color: T.green, bg: "rgba(34,197,94,.08)", border: "rgba(34,197,94,.35)" },
  "failed its test": { color: GREY, bg: "rgba(163,172,189,.08)", border: "rgba(163,172,189,.35)" },
};

export function TestBadge({ test, title }) {
  const s = STATUS[test] || STATUS.untested;
  return (
    <span className="q-pill" title={title || (test === "failed its test"
      ? "Zone test 2026-11-04: these zones turned price no more often than placebo levels. A marker, not a signal."
      : undefined)}
          style={{ color: s.color, background: s.bg, borderColor: s.border, fontSize: 11 }}>
      {test || "untested"}
    </span>
  );
}

const away = z => `${px(z.distance)} pts · ${z.distance_atr ?? "—"} ATR · ${z.distance_pct}%`;

export function ZoneLine({ label, z }) {
  return (
    <div className="q-row" style={{ gap: 8, alignItems: "baseline" }}>
      <span className="q-label" style={{ width: 52 }}>{label}</span>
      {z ? (
        <>
          <span className="q-num" style={{ fontWeight: 650 }}>{z.range}</span>
          <span className="q-faint" style={{ fontSize: 12.5 }}>{away(z)} away</span>
          <TestBadge test={z.test} />
          <div className="q-faint" style={{ fontSize: 12, width: "100%", paddingLeft: 60 }}>{z.why}</div>
        </>
      ) : <span className="q-muted" style={{ fontSize: 13 }}>no strong zone on this map</span>}
    </div>
  );
}

export function TradeLines({ t }) {
  if (!t) return null;
  const ob = t.first_obstacle;
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div className="q-row" style={{ gap: 14 }}>
        <span><span className="q-label">1R </span><span className="q-num">{t.r == null ? "—" : px(t.r)}</span></span>
        <span><span className="q-label">Target </span><span className="q-num">{t.target_r == null ? "—" : `${t.target_r}R`}</span></span>
        <span><span className="q-label">Room </span><span className="q-num">
          {ob ? `${ob.r}R to ${ob.range}` : t.r ? "no strong zone in the way on this map" : "n/a (no stop)"}</span></span>
        {ob && <TestBadge test={ob.test} />}
      </div>
      <div className="q-sub" style={{ marginTop: 0 }}>
        Stop {t.stop == null ? "—" : px(t.stop)}: {t.stop_in_zone ? <>inside the strong zone <b>{t.stop_in_zone.range}</b></> : "not inside a strong zone"}
      </div>
      {t.flags.map(f => <div key={f} className="q-banner amber" style={{ padding: "8px 12px" }}>{f}</div>)}
    </div>
  );
}

// The read stored with an idea when it was logged (trade_ideas.json "map_read"): shown as it was, never recomputed.
export function FrozenRead({ rd }) {
  if (!rd) return <span className="q-faint">No map read: logged before ideas required one (03 Nov).</span>;
  if (rd.error) return <span className="q-faint">Map read failed when logged: {rd.error}</span>;
  return (
    <div style={{ display: "grid", gap: 6, whiteSpace: "normal" }}>
      <div className="q-row" style={{ gap: 8 }}>
        <span className="q-label">Map at logging</span>
        <span className="q-faint" style={{ fontSize: 12 }}>
          read {rd.read_at ? rd.read_at.slice(0, 16).replace("T", " ") : "—"} IST at {px(rd.price)} · map built for {rd.built_for}
        </span>
        <TestBadge test={rd.status} />
        <a href={`#/map/${rd.symbol}`} style={{ color: T.blue, fontSize: 12 }}>today's map →</a>
      </div>
      {rd.inside && <div className="q-sub" style={{ marginTop: 0 }}>Price was inside the strong zone <b>{rd.inside.range}</b> ({rd.inside.why})</div>}
      <ZoneLine label="Above" z={rd.above} />
      <ZoneLine label="Below" z={rd.below} />
      <TradeLines t={rd.trade} />
    </div>
  );
}
