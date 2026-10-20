// ─── Trading pages: design tokens, CSS and formatters ──────────────────────
// The "clean trading terminal" look for #/spreads and #/picks (2026-10-20):
// dark and calm, colour only for gain / loss / warnings, proportional type
// for words and tabular monospace for numbers. The rest of the cockpit keeps
// its old style until the terminal re-architecture (docs/TERMINAL_ARCHITECTURE.md).

export const T = {
  bg: "#0B0F17",
  surface: "#121826",
  raised: "#171F31",
  border: "#222B3D",
  borderHover: "#2E3953",
  text: "#E6EAF2",
  muted: "#8B95A8",
  faint: "#5D6679",
  green: "#22C55E",
  red: "#F05252",
  amber: "#F5A524",
  blue: "#6EA8FE",
  sans: 'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  mono: 'ui-monospace, "JetBrains Mono", "SF Mono", "Cascadia Mono", Consolas, monospace',
};

export const tone = v => (v == null || v === 0 ? T.muted : v > 0 ? T.green : T.red);

export const inr = v => (v == null || Number.isNaN(v) ? "—"
  : `₹${Math.round(Math.abs(Number(v))).toLocaleString("en-IN")}`);
export const signedInr = v => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${inr(v)}`);
export const pct = (v, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(d)}%`);
export const px = v => (v == null ? "—" : Number(v).toLocaleString("en-IN", {
  minimumFractionDigits: Number(v) < 1000 ? 2 : 1, maximumFractionDigits: Number(v) < 1000 ? 2 : 1,
}));
export const shortDate = iso => (iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", {
  day: "numeric", month: "short",
}) : "—");
export const clock = iso => (iso ? new Date(iso).toLocaleTimeString("en-IN", {
  timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false,
}) : "—");
export const ago = iso => {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
};
// Weekdays after today up to and including the expiry (holidays not known).
export const sessionsTo = iso => {
  if (!iso) return null;
  let n = 0;
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  const end = new Date(`${iso}T00:00:00`);
  while (d < end) {
    d.setDate(d.getDate() + 1);
    if (d.getDay() !== 0 && d.getDay() !== 6) n += 1;
  }
  return n;
};

// The weekday session before an expiry, as YYYY-MM-DD in LOCAL time
// (toISOString would shift an IST midnight back to the previous UTC day).
export const sessionBefore = iso => {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  do { d.setDate(d.getDate() - 1); } while (d.getDay() === 0 || d.getDay() === 6);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const CSS = `
.q-app { background: ${T.bg}; min-height: 100vh; color: ${T.text}; font-family: ${T.sans};
  font-size: 14px; line-height: 1.45; -webkit-font-smoothing: antialiased; }
.q-app * { box-sizing: border-box; }
.q-top { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
  padding: 12px 28px; background: rgba(11,15,23,.86); backdrop-filter: blur(10px);
  border-bottom: 1px solid ${T.border}; }
.q-brand { font-weight: 800; letter-spacing: .08em; font-size: 15px; color: ${T.text}; text-decoration: none; }
.q-brand b { color: ${T.blue}; }
.q-nav { display: flex; gap: 4px; overflow-x: auto; max-width: 100%; scrollbar-width: none; }
.q-nav a { color: ${T.muted}; text-decoration: none; font-size: 13px; font-weight: 550; padding: 6px 12px; white-space: nowrap;
  border-radius: 8px; transition: background .15s, color .15s; }
.q-nav a:hover { color: ${T.text}; background: ${T.raised}; }
.q-nav a.on { color: ${T.text}; background: ${T.raised}; box-shadow: inset 0 0 0 1px ${T.border}; }
.q-main { max-width: 1320px; margin: 0 auto; padding: 28px; }
.q-h1 { font-size: 24px; font-weight: 700; letter-spacing: -.01em; margin: 0; }
.q-sub { color: ${T.muted}; font-size: 13px; margin-top: 4px; }
.q-grid > *, .q-stats > * { min-width: 0; }
.q-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 460px), 1fr)); gap: 16px; }
.q-card { background: ${T.surface}; border: 1px solid ${T.border}; border-radius: 14px; padding: 18px 20px;
  transition: border-color .15s; }
.q-card:hover { border-color: ${T.borderHover}; }
.q-label { font-size: 11px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: ${T.muted}; }
.q-num { font-family: ${T.mono}; font-variant-numeric: tabular-nums; }
.q-big { font-family: ${T.mono}; font-variant-numeric: tabular-nums; font-size: 30px; font-weight: 650; letter-spacing: -.02em; }
.q-muted { color: ${T.muted}; }
.q-faint { color: ${T.faint}; }
.q-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.q-between { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.q-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
.q-stat { background: ${T.raised}; border: 1px solid ${T.border}; border-radius: 10px; padding: 10px 12px; }
.q-stat .v { font-family: ${T.mono}; font-variant-numeric: tabular-nums; font-size: 16px; font-weight: 600; margin-top: 2px; }
.q-stat .s { font-size: 11px; color: ${T.faint}; margin-top: 2px; }
.q-pill { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 600; padding: 3px 10px;
  border-radius: 999px; border: 1px solid ${T.border}; color: ${T.muted}; white-space: nowrap; }
.q-pill .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.q-pill.green { color: ${T.green}; border-color: rgba(34,197,94,.35); background: rgba(34,197,94,.08); }
.q-pill.red { color: ${T.red}; border-color: rgba(240,82,82,.4); background: rgba(240,82,82,.08); }
.q-pill.amber { color: ${T.amber}; border-color: rgba(245,165,36,.4); background: rgba(245,165,36,.08); }
.q-pill.blue { color: ${T.blue}; border-color: rgba(110,168,254,.35); background: rgba(110,168,254,.08); }
.q-btn { font: inherit; font-size: 13px; font-weight: 600; padding: 7px 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid ${T.border}; background: ${T.raised}; color: ${T.text}; transition: border-color .15s, background .15s; }
.q-btn:hover { border-color: ${T.borderHover}; }
.q-btn:disabled { opacity: .5; cursor: default; }
.q-btn.primary { background: ${T.blue}; border-color: ${T.blue}; color: #0B1220; }
.q-btn.ghost { background: transparent; }
.q-input { font: inherit; font-family: ${T.mono}; font-size: 13px; padding: 7px 10px; border-radius: 8px;
  border: 1px solid ${T.border}; background: ${T.bg}; color: ${T.text}; outline: none; min-width: 0; }
.q-input:focus { border-color: ${T.blue}; }
.q-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.q-table th { text-align: left; font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: ${T.faint}; padding: 8px 10px; border-bottom: 1px solid ${T.border}; white-space: nowrap; }
.q-table td { padding: 9px 10px; border-bottom: 1px solid ${T.border}; white-space: nowrap;
  font-family: ${T.mono}; font-variant-numeric: tabular-nums; }
.q-table td.w { font-family: ${T.sans}; }
.q-table tr:last-child td { border-bottom: none; }
.q-table tbody tr:hover td { background: rgba(255,255,255,.015); }
.q-scroll { overflow-x: auto; }
.q-banner { border-radius: 12px; padding: 12px 16px; font-size: 13px; border: 1px solid; }
.q-banner.amber { color: #F8C471; border-color: rgba(245,165,36,.35); background: rgba(245,165,36,.07); }
.q-banner.red { color: #FCA5A5; border-color: rgba(240,82,82,.45); background: rgba(240,82,82,.09); }
.q-tabs { display: inline-flex; gap: 2px; padding: 3px; border-radius: 10px; background: ${T.surface}; border: 1px solid ${T.border}; }
.q-tabs button { font: inherit; font-size: 13px; font-weight: 600; padding: 6px 14px; border-radius: 8px; border: none;
  background: transparent; color: ${T.muted}; cursor: pointer; }
.q-tabs button.on { background: ${T.raised}; color: ${T.text}; }
.q-bar { position: relative; height: 8px; border-radius: 99px; background: ${T.raised}; }
.q-empty { text-align: center; padding: 48px 20px; color: ${T.muted}; }
.q-pop { position: absolute; right: 0; top: calc(100% + 8px); width: min(92vw, 380px); z-index: 20;
  background: ${T.surface}; border: 1px solid ${T.border}; border-radius: 12px; padding: 14px;
  box-shadow: 0 16px 40px rgba(0,0,0,.45); }
details.q-det summary { cursor: pointer; list-style: none; }
details.q-det summary::-webkit-details-marker { display: none; }
@media (max-width: 640px) {
  .q-main { padding: 16px; }
  .q-top { padding: 10px 16px; gap: 10px; }
  .q-top .q-chips { margin-left: 0 !important; }
  .q-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .q-head-right { text-align: left !important; }
  .q-big { font-size: 24px; }
  .q-card { padding: 14px; }
}
`;
