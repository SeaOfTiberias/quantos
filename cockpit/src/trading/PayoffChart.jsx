// Expiry payoff of a vertical spread, in rupees for the whole position, with
// today's stock price, the breakeven and (optionally) the stop marked.
// Hand-drawn SVG: two kinks at the strikes, flat outside them.
import { T, px } from "./theme.js";

const intrinsic = (right, k, s) => (right === "call" ? Math.max(s - k, 0) : Math.max(k - s, 0));

export default function PayoffChart({ right, longStrike, shortStrike, entry, qty, spot, breakeven, stop, height = 150 }) {
  if (!longStrike || !shortStrike || entry == null || !qty) return null;
  const W = 440, H = height, padL = 8, padR = 8, padT = 18, padB = 26;
  const pnl = s => (intrinsic(right, longStrike, s) - intrinsic(right, shortStrike, s) - entry) * qty;
  const lo = Math.min(longStrike, shortStrike), hi = Math.max(longStrike, shortStrike);
  const marks = [lo, hi, spot, breakeven, stop].filter(v => v != null && v > 0);
  const span = Math.max(hi - lo, (spot || hi) * 0.02);
  const x0 = Math.min(...marks) - span * 0.6, x1 = Math.max(...marks) + span * 0.6;
  const top = Math.max(pnl(lo), pnl(hi)), bot = Math.min(pnl(lo), pnl(hi));
  const yr = Math.max(top - bot, 1);
  const X = s => padL + (s - x0) / (x1 - x0) * (W - padL - padR);
  const Y = v => padT + (top - v) / yr * (H - padT - padB);
  const pts = [x0, lo, hi, x1].map(s => `${X(s).toFixed(1)},${Y(pnl(s)).toFixed(1)}`).join(" ");
  const zero = Y(0);
  const area = `${X(x0)},${zero} ${pts} ${X(x1)},${zero}`;
  const id = `pc${Math.round(longStrike)}${Math.round(shortStrike)}${right}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Payoff at expiry" style={{ display: "block" }}>
      <defs>
        <clipPath id={`${id}-up`}><rect x="0" y="0" width={W} height={Math.max(zero, 0)} /></clipPath>
        <clipPath id={`${id}-dn`}><rect x="0" y={zero} width={W} height={Math.max(H - zero, 0)} /></clipPath>
      </defs>
      <polygon points={area} fill={T.green} fillOpacity="0.13" clipPath={`url(#${id}-up)`} />
      <polygon points={area} fill={T.red} fillOpacity="0.13" clipPath={`url(#${id}-dn)`} />
      <line x1={padL} x2={W - padR} y1={zero} y2={zero} stroke={T.border} strokeWidth="1" />
      <polyline points={pts} fill="none" stroke={T.text} strokeOpacity="0.85" strokeWidth="1.6" strokeLinejoin="round" />
      {[lo, hi].map(k => (
        <g key={k}>
          <line x1={X(k)} x2={X(k)} y1={H - padB} y2={H - padB + 4} stroke={T.faint} />
          <text x={X(k)} y={H - 8} fontSize="11.5" fill={T.faint} textAnchor="middle" fontFamily={T.mono}>{k}</text>
        </g>
      ))}
      {breakeven > 0 && (
        <g>
          <circle cx={X(breakeven)} cy={zero} r="3" fill={T.muted} />
          <text x={X(breakeven)} y={zero - 7} fontSize="11.5" fill={T.muted} textAnchor="middle" fontFamily={T.mono}>BE {px(breakeven)}</text>
        </g>
      )}
      {stop > 0 && (
        <line x1={X(stop)} x2={X(stop)} y1={padT - 6} y2={H - padB} stroke={T.amber} strokeDasharray="4 4" strokeWidth="1.2" />
      )}
      {spot > 0 && (
        <g>
          <line x1={X(spot)} x2={X(spot)} y1={padT - 6} y2={H - padB} stroke={T.blue} strokeWidth="1.4" />
          <circle cx={X(spot)} cy={Y(pnl(spot))} r="4" fill={T.blue} stroke={T.surface} strokeWidth="2" />
          <text x={Math.min(Math.max(X(spot), 40), W - 40)} y={padT - 8} fontSize="12" fill={T.blue}
                textAnchor="middle" fontFamily={T.mono}>now {px(spot)}</text>
        </g>
      )}
    </svg>
  );
}
