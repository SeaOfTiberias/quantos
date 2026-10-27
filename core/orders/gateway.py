"""
QuantOS — Order gateway: the only code that sends orders to ICICI Direct (Breeze)
──────────────────────────────────────────────────────────────────────────────────
Every place / modify / cancel / GTT call in the project goes through here:

  1. build a Context from live data (positions, a fresh quote, the lot size,
     the kill switch, today's order count)
  2. core/orders/checks.check() -- any reason refuses the order
  3. journal the attempt, sent or refused (~/.quantos/orders.jsonl, chmod 600)
  4. send it only when live=True; otherwise the journal says "paper"

Callers: scripts/qorder.py (orders the user releases) and the position
manager's executor (exits placed by rule). A model never calls this.

Breeze specifics (breeze_connect, 2026-10):
  - dates are ISO with a fixed 06:00Z time, e.g. "2026-11-23T06:00:00.000Z"
  - futures: product "futures", right "others", strike "0"
  - stop orders are day-only, so a resting stop is a GTT: gtt_three_leg_place_order
    with gtt_type "oco" holds a target and a stop on an open position, and
    when one fills the broker cancels the other
  - the OCO payload shape follows ICICI's published example; the first live
    one is checked against gtt_order_book before it is trusted (verify_gtt)
  - gtt_order_book refuses a from/to range over 10 days, and the GTT id sits on
    each leg in order_details, not at the top level (2026-10-27)
  - each contract has its own price step (SUPIND FUT 0.10, HDFBAN FUT 0.05; others
    0.01 .. 5). It comes from Fyers' F&O symbol master; when that misses, ICICI's
    "Price should be in multiples of: X" refusal teaches it and the order goes once more.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import zipfile
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from core.orders.checks import TICK, Context, Intent, Limits, check, round_tick

IST = timezone(timedelta(hours=5, minutes=30))
QUANTOS_DIR = Path.home() / ".quantos"
JOURNAL = QUANTOS_DIR / "orders.jsonl"
KILL_SWITCH = QUANTOS_DIR / "ORDERS_OFF"
FO_BHAVCOPY_DIR = QUANTOS_DIR / "nse_fo_bhavcopy"
QUOTE_TRIES, QUOTE_RETRY_S = 3, 1.5
FO_MASTER = QUANTOS_DIR / "fyers_symbol_master_NSE_FO.csv"     # core/options/fyers_symbol_master.py keeps it fresh
TICK_REFUSAL = re.compile(r"multiples of:?\s*([0-9]*\.?[0-9]+)", re.I)
GTT_BOOK_DAYS = 10            # Breeze: "Number of days between from_date & to_date should not be more than 10"
GTT_BOOK_WINDOWS = 3          # 30 days back: a plan lasts 10 sessions
GTT_DONE = {"cancelled", "canceled", "expired", "rejected", "executed", "triggered", "completed", "complete"}


def limits_from(cfg: dict) -> Limits:
    """`orders:` in agent/config.yaml -> Limits; unknown keys are ignored, missing ones keep the defaults."""
    known = set(Limits.__dataclass_fields__)
    kw = {k: v for k, v in (cfg or {}).items() if k in known}
    if "accounts" in kw:
        kw["accounts"] = tuple(kw["accounts"])
    return Limits(**kw)


def iso(d: date) -> str:
    return f"{d.isoformat()}T06:00:00.000Z"


@dataclass
class Result:
    ok:        bool
    sent:      bool                       # reached the broker (False on refusal or paper)
    order_id:  Optional[str] = None
    reasons:   list = field(default_factory=list)
    raw:       Optional[dict] = None

    def __str__(self) -> str:
        if not self.ok:
            return "REFUSED: " + "; ".join(self.reasons)
        return f"{'SENT' if self.sent else 'PAPER'} order_id={self.order_id}"


def _instrument_of(row: dict) -> Optional[tuple]:
    """Breeze position row -> (code, expiry, right, strike), signed qty."""
    from core.position_manager.rules import _expiry
    exp = _expiry(str(row.get("expiry_date", "")))
    if exp is None:
        return None
    right = str(row.get("right", "")).lower()
    right = {"call": "call", "put": "put"}.get(right, "others")
    try:
        strike = float(row.get("strike_price") or 0) if right != "others" else 0.0
    except ValueError:
        return None
    return (str(row.get("stock_code", "")).upper(), exp, right, strike)


def tick_from_master(path: Path, symbol: str, expiry: date, right: str = "others",
                     strike: float = 0.0) -> Optional[float]:
    """One contract's tick from Fyers' NSE_FO master (no header; col 4 tick, 8 expiry epoch,
    13 underlying, 15 strike, 16 CE/PE/XX), or None if it isn't listed."""
    opt = {"call": "CE", "put": "PE"}.get(right, "XX")
    with open(path, encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 17 or row[13].upper() != symbol.upper() or row[16] != opt:
                continue
            if datetime.fromtimestamp(int(float(row[8])), tz=timezone.utc).date() != expiry:
                continue
            if opt != "XX" and abs(float(row[15]) - float(strike)) > 1e-6:
                continue
            t = float(row[4])
            return t if t > 0 else None
    return None


def _gtt_ids(g: dict) -> set:
    ids = {str(g.get("gtt_order_id"))} if g.get("gtt_order_id") else set()
    return ids | {str(d.get("gtt_order_id")) for d in g.get("order_details") or [] if d.get("gtt_order_id")}


def _gtt_live(g: dict) -> bool:
    """Resting unless every leg says it's done. An unknown status counts as resting, so a GTT
    the code can't read is never mistaken for a missing one and doubled up."""
    legs = g.get("order_details") or []
    return not legs or any(str(d.get("status", "")).lower() not in GTT_DONE for d in legs)


class Gateway:
    def __init__(self, client, account: str = "icici-spouse", limits: Limits = Limits(), live: bool = False,
                 journal: Path = JOURNAL, kill_switch: Path = KILL_SWITCH,
                 clock: Callable[[], datetime] = lambda: datetime.now(IST), fo_master: Path = FO_MASTER):
        self.client, self.account, self.limits, self.live = client, account, limits, live
        self.journal, self.kill_switch, self.clock, self.fo_master = journal, kill_switch, clock, fo_master
        self._lots: dict[str, int] = {}
        self._syms: dict[str, str] = {}
        self._ticks: dict[tuple, float] = {}

    # ── data ────────────────────────────────────────────────────────────────

    def positions(self) -> dict:
        r = self.client.get_portfolio_positions() or {}
        if r.get("Status") != 200:
            raise RuntimeError(f"positions: {r.get('Error')}")
        out: dict = {}
        for row in r.get("Success") or []:
            key = _instrument_of(row)
            try:
                qty = int(float(row.get("quantity") or 0))
            except (TypeError, ValueError):
                continue
            if key is None or qty == 0:
                continue
            if str(row.get("action", "")).lower() == "sell" and qty > 0:
                qty = -qty
            out[key] = out.get(key, 0) + qty
        return out

    def quote(self, i: Intent) -> dict:
        r = self._get_quotes(stock_code=i.code, exchange_code="NFO", expiry_date=iso(i.expiry),
                             product_type=i.product, right=i.right,
                             strike_price=str(int(i.strike)) if i.strike else "0") or {}
        rows = r.get("Success") or []
        if i.right != "others":
            # quotes label the right "P"/"C" (2026-10-26), positions "Put"/"Call": match the first letter
            rows = [x for x in rows if str(x.get("right") or "").lower()[:1] == i.right[:1]]
        x = rows[0] if rows else {}
        f = (lambda k: float(x.get(k) or 0) or None)
        return {"bid": f("best_bid_price"), "ask": f("best_offer_price"), "ltp": f("ltp"), "at": time.monotonic()}

    def _get_quotes(self, **kw) -> dict:
        """Breeze get_quotes, retried: under load it returns an empty body or a 503 and the SDK raises
        "Expecting value" (same handling as scripts/run_spread_watcher.py)."""
        for attempt in range(QUOTE_TRIES):
            try:
                return self.client.get_quotes(**kw)
            except Exception as e:
                if "Expecting value" not in str(e) or attempt == QUOTE_TRIES - 1:
                    raise
                time.sleep(QUOTE_RETRY_S)
        return {}

    def symbol(self, code: str) -> str:
        """ICICI code -> NSE symbol (SUPIND -> SUPREMEIND)."""
        if code not in self._syms:
            names = self.client.get_names(exchange_code="NSE", stock_code=code) or {}
            self._syms[code] = str(names.get("exchange_stock_code") or code).upper()
        return self._syms[code]

    def tick(self, i: Intent) -> float:
        """The contract's price step: Fyers' master, else what ICICI last told us, else TICK."""
        key = i.instrument
        if key not in self._ticks:
            t = None
            try:
                t = tick_from_master(self.fo_master, self.symbol(i.code), i.expiry, i.right, i.strike)
            except Exception:
                t = None
            self._ticks[key] = t or TICK
        return self._ticks[key]

    def snap(self, i: Intent) -> Intent:
        """Prices onto the contract's tick, up for a buy and down for a sell: a fraction of a tick at most."""
        t, up = self.tick(i), i.side > 0
        return replace(i, price=round_tick(i.price, up, t),
                       trigger=None if i.trigger is None else round_tick(i.trigger, up, t))

    def _learn_tick(self, i: Intent, raw: Optional[dict]) -> bool:
        """ICICI's "Price should be in multiples of: 0.10" -> remember it; True if it's news."""
        m = TICK_REFUSAL.search(str((raw or {}).get("Error") or ""))
        if not m or float(m.group(1)) <= 0 or float(m.group(1)) == self._ticks.get(i.instrument):
            return False
        self._ticks[i.instrument] = float(m.group(1))
        return True

    def lot(self, code: str) -> int:
        """Lot size from the latest NSE F&O bhavcopy, via Breeze's code -> NSE symbol map."""
        if code in self._lots:
            return self._lots[code]
        lot = 0
        try:
            sym = self.symbol(code)
            latest = sorted(FO_BHAVCOPY_DIR.glob("*.zip"))[-1]
            with zipfile.ZipFile(latest) as z:
                for row in csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), "utf-8")):
                    if row.get("TckrSymb") == sym and row.get("FinInstrmTp") in ("STF", "STO"):
                        lot = int(float(row.get("NewBrdLotQty") or 0))
                        break
        except Exception:
            lot = 0
        self._lots[code] = lot
        return lot

    def orders_today(self) -> int:
        today = self.clock().date().isoformat()
        try:
            return sum(1 for line in self.journal.read_text().splitlines()
                       if line and json.loads(line).get("day") == today and json.loads(line).get("sent"))
        except OSError:
            return 0

    def context(self, i: Intent, quote: Optional[dict] = None, positions: Optional[dict] = None) -> Context:
        q = quote or ({} if i.gtt else self.quote(i))
        held = positions if positions is not None else self.positions()
        lot = self.lot(i.code)
        if lot <= 0 and i.purpose != "entry":
            lot = abs(held.get(i.instrument, 0)) or i.qty      # an exit of the whole position needs no lot table
        return Context(now=self.clock(), lot=lot, positions=held, bid=q.get("bid"), ask=q.get("ask"),
                       quote_age_s=(time.monotonic() - q["at"]) if q.get("at") else None,
                       kill_switch=self.kill_switch.exists(), orders_today=self.orders_today(), tick=self.tick(i))

    # ── journal ─────────────────────────────────────────────────────────────

    def _log(self, kind: str, payload: dict, res: Result) -> Result:
        rec = {"ts": self.clock().isoformat(timespec="seconds"), "day": self.clock().date().isoformat(),
               "kind": kind, "account": self.account, "live": self.live, **payload,
               "ok": res.ok, "sent": res.sent, "order_id": res.order_id, "reasons": res.reasons, "raw": res.raw}
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        new = not self.journal.exists()
        with self.journal.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        if new:
            os.chmod(self.journal, 0o600)
        return res

    @staticmethod
    def _order_id(raw: Optional[dict]) -> Optional[str]:
        s = (raw or {}).get("Success") or {}
        if isinstance(s, list):
            s = s[0] if s else {}
        return s.get("order_id") or s.get("gtt_order_id")

    # ── orders ──────────────────────────────────────────────────────────────

    def place(self, i: Intent, quote: Optional[dict] = None, positions: Optional[dict] = None,
              retry: bool = True) -> Result:
        """One limit order (or a stop-loss limit when i.trigger is set), day validity."""
        i = self.snap(i)
        reasons = check(i, self.context(i, quote, positions), self.limits)
        payload = {"intent": asdict(i)}
        if reasons:
            return self._log("place", payload, Result(False, False, reasons=reasons))
        if not self.live:
            return self._log("place", payload, Result(True, False, order_id="paper"))
        raw = self.client.place_order(
            stock_code=i.code, exchange_code="NFO", product=i.product, action=i.action,
            order_type="stoploss" if i.trigger else "limit", stoploss=str(i.trigger or 0), quantity=str(i.qty),
            price=f"{i.price:.2f}", validity="day", validity_date=iso(self.clock().date()), disclosed_quantity="0",
            expiry_date=iso(i.expiry), right=i.right, strike_price=str(int(i.strike)) if i.strike else "0",
            user_remark="quantos")
        oid = self._order_id(raw)
        res = self._log("place", payload, Result(oid is not None, True, oid, [] if oid else [str(raw)], raw))
        if oid is None and retry and self._learn_tick(i, raw):
            return self.place(i, quote, positions, retry=False)
        return res

    def place_oco(self, target: Intent, stop: Intent, positions: Optional[dict] = None,
                  retry: bool = True) -> Result:
        """A resting target + stop on an open position (GTT OCO). Both legs pass check() first."""
        target, stop = self.snap(target), self.snap(stop)
        held = positions if positions is not None else self.positions()
        reasons = []
        for leg in (target, stop):
            reasons += [f"{leg.purpose}: {r}" for r in check(leg, self.context(leg, {}, held), self.limits)]
        if (target.code, target.expiry, target.right, target.strike, target.qty, target.action) != \
                (stop.code, stop.expiry, stop.right, stop.strike, stop.qty, stop.action):
            reasons.append("target and stop legs must be the same instrument, side and qty")
        payload = {"target": asdict(target), "stop": asdict(stop)}
        if reasons:
            return self._log("oco", payload, Result(False, False, reasons=reasons))
        if not self.live:
            return self._log("oco", payload, Result(True, False, order_id="paper-gtt"))
        legs = [{"gtt_leg_type": "target", "action": target.action,
                 "limit_price": f"{target.price:.2f}", "trigger_price": f"{target.trigger:.2f}"},
                {"gtt_leg_type": "stoploss", "action": stop.action,
                 "limit_price": f"{stop.price:.2f}", "trigger_price": f"{stop.trigger:.2f}"}]
        raw = self.client.gtt_three_leg_place_order(
            exchange_code="NFO", stock_code=target.code, product=target.product, quantity=str(target.qty),
            expiry_date=iso(target.expiry), right=target.right,
            strike_price=str(int(target.strike)) if target.strike else "0", gtt_type="oco",
            index_or_stock="stock", trade_date=iso(self.clock().date()), order_details=legs)
        oid = self._order_id(raw)
        res = self._log("oco", payload, Result(oid is not None, True, oid, [] if oid else [str(raw)], raw))
        if oid is None and retry and self._learn_tick(target, raw):
            return self.place_oco(target, stop, held, retry=False)
        return res

    def cancel(self, order_id: str) -> Result:
        if not self.live or str(order_id).startswith("paper"):
            return self._log("cancel", {"order_id": order_id}, Result(True, False, order_id))
        raw = self.client.cancel_order(exchange_code="NFO", order_id=order_id)
        ok = (raw or {}).get("Status") == 200
        return self._log("cancel", {"order_id": order_id}, Result(ok, True, order_id, [] if ok else [str(raw)], raw))

    def cancel_gtt(self, gtt_id: str) -> Result:
        if not self.live or str(gtt_id).startswith("paper"):
            return self._log("cancel_gtt", {"gtt_id": gtt_id}, Result(True, False, gtt_id))
        raw = self.client.gtt_three_leg_cancel_order(exchange_code="NFO", gtt_order_id=gtt_id)
        ok = (raw or {}).get("Status") == 200
        return self._log("cancel_gtt", {"gtt_id": gtt_id}, Result(ok, True, gtt_id, [] if ok else [str(raw)], raw))

    def gtt_book(self) -> list:
        """GTTs placed in the last 30 days, in 10-day windows. Raises if the broker won't say:
        an unreadable book must never pass for an empty one (that re-places, i.e. doubles, an OCO)."""
        to, out = self.clock().date(), []
        for _ in range(GTT_BOOK_WINDOWS):
            frm = to - timedelta(days=GTT_BOOK_DAYS - 1)
            r = self.client.gtt_order_book(exchange_code="NFO", from_date=iso(frm), to_date=iso(to)) or {}
            if r.get("Status") != 200:
                raise RuntimeError(f"gtt book: {r.get('Error')}")
            out += r.get("Success") or []
            to = frm - timedelta(days=1)
        return out

    def verify_gtt(self, gtt_id: str) -> Optional[dict]:
        """The GTT as the broker holds it, or None if it isn't in the book or has fired / been cancelled."""
        for g in self.gtt_book():
            if str(gtt_id) in _gtt_ids(g) and _gtt_live(g):
                return g
        return None

    def find_gtt(self, code: str, expiry: date, action: str, qty: int, right: str = "others",
                 strike: float = 0.0) -> Optional[str]:
        """The id of a resting GTT on this contract that closes `qty` with `action` (one the user
        placed, or one a lost state forgot), so it's adopted instead of doubled up."""
        from core.position_manager.rules import _expiry
        for g in self.gtt_book():
            r = {"call": "call", "put": "put"}.get(str(g.get("right", "")).lower(), "others")
            legs = g.get("order_details") or []
            if (str(g.get("stock_code", "")).upper() == code.upper() and _expiry(str(g.get("expiry_date", ""))) == expiry
                    and r == right and (r == "others" or abs(float(g.get("strike_price") or 0) - strike) < 1e-6)
                    and int(float(g.get("quantity") or 0)) == qty and _gtt_live(g)
                    and all(str(d.get("action", "")).lower() == action for d in legs)):
                ids = _gtt_ids(g)
                if ids:
                    return sorted(ids)[0]
        return None

    def status(self, order_id: str) -> dict:
        r = self.client.get_order_detail(exchange_code="NFO", order_id=order_id) or {}
        return (r.get("Success") or [{}])[0]

    def work(self, i: Intent, tries: int = 6, wait_s: float = 10.0,
             sleep: Callable[[float], None] = time.sleep) -> Result:
        """Fill now with a marketable limit at the touch (bid to sell, ask to buy), re-priced to the
        new touch every wait_s until filled or tries run out. Never priced beyond check()'s band,
        so a gap shows up as 'not filled', not as a fill 5% away. Used for exits and spread legs."""
        last: Optional[Result] = None
        for n in range(tries):
            q = self.quote(i)
            touch = q.get("bid") if i.side < 0 else q.get("ask")
            if not touch:
                last = Result(False, False, reasons=["no bid/ask to price the exit"])
                sleep(wait_s)
                continue
            leg = Intent(**{**asdict(i), "price": round_tick(touch, i.side > 0, self.tick(i))})
            if last and last.sent and last.order_id:
                self.cancel(last.order_id)
                if str(self.status(last.order_id).get("status", "")).lower() == "executed":
                    return last                    # filled between the check and the cancel
            last = self.place(leg, quote=q)        # positions re-read: an exit can't exceed what's held
            if not last.ok:
                return last
            if not self.live:
                return last
            for _ in range(int(wait_s)):
                sleep(1.0)
                st = str(self.status(last.order_id).get("status", "")).lower()
                if st == "executed":
                    return last
                if st in ("rejected", "cancelled", "expired"):
                    break
        if last and last.sent and last.order_id:
            self.cancel(last.order_id)
        return Result(False, bool(last and last.sent), last.order_id if last else None,
                      [f"exit not filled after {tries} tries"] + (last.reasons if last else []))

    work_exit = work
