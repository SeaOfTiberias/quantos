"""core/orders/checks.py -- the deterministic gate every order passes."""

from datetime import date, datetime

from core.orders.checks import Context, Intent, Limits, check, round_tick

EXP = date(2026, 11, 23)
MON = datetime(2026, 10, 26, 10, 0)          # a Monday, 10:00 IST
FUT = ("INDHOT", EXP, "others", 0.0)


def fut(action="buy", qty=1000, price=782.0, purpose="entry", **kw):
    return Intent("icici-spouse", "futures", "INDHOT", EXP, action, qty, price, purpose, **kw)


def opt(action, strike, qty=1000, price=10.0, purpose="entry", right="call", **kw):
    return Intent("icici-spouse", "options", "INDHOT", EXP, action, qty, price, purpose, right=right, strike=strike, **kw)


def ctx(**kw):
    base = dict(now=MON, lot=1000, bid=781.5, ask=782.0, quote_age_s=2.0)
    return Context(**{**base, **kw})


def test_a_clean_futures_entry_passes():
    assert check(fut(), ctx()) == []


def test_kill_switch_account_and_shape():
    assert any("kill switch" in r for r in check(fut(), ctx(kill_switch=True)))
    son = Intent("icici-son", "futures", "INDHOT", EXP, "buy", 1000, 782.0, "entry")
    assert any("not allowed" in r for r in check(son, ctx()))
    assert any("multiple of the lot" in r for r in check(fut(qty=500), ctx()))
    assert any("over the cap of" in r for r in check(fut(qty=5000), ctx()))
    assert any("tick" in r for r in check(fut(price=782.03), ctx()))
    assert any("orders sent today" in r for r in check(fut(), ctx(orders_today=40)))


def test_hours_and_quote_freshness_except_gtt():
    sat = datetime(2026, 10, 24, 10, 0)
    assert any("market closed" in r for r in check(fut(), ctx(now=sat)))
    assert any("market closed" in r for r in check(fut(), ctx(now=datetime(2026, 10, 26, 15, 31))))
    assert any("old" in r for r in check(fut(), ctx(quote_age_s=45)))
    assert any("bid/ask" in r for r in check(fut(), ctx(bid=None)))
    held = {FUT: 1000}
    gtt = fut("sell", price=830.0, purpose="target", gtt=True)
    assert check(gtt, ctx(now=sat, bid=None, ask=None, quote_age_s=None, positions=held)) == []


def test_price_band_and_typos():
    assert any("over the ask" in r for r in check(fut(price=800.0), ctx()))          # 2.3% through the ask
    assert check(fut(price=789.0), ctx()) == []                                       # within 1% + a tick
    assert any("typo" in r for r in check(fut(price=600.0), ctx()))
    held = {FUT: 1000}
    assert any("under the bid" in r for r in check(fut("sell", price=770.0, purpose="exit"), ctx(positions=held)))
    assert any("typo" in r for r in check(fut("sell", price=990.0, purpose="exit"), ctx(positions=held)))
    assert check(fut("sell", price=775.0, purpose="exit"), ctx(positions=held)) == []


def test_exits_must_reduce_the_position():
    assert any("must reduce" in r for r in check(fut("sell", price=781.5, purpose="exit"), ctx()))
    assert any("must reduce" in r for r in check(fut("buy", price=782.0, purpose="exit"), ctx(positions={FUT: 1000})))
    assert any("more than the" in r for r in check(fut("sell", qty=2000, price=781.5, purpose="exit"),
                                                    ctx(positions={FUT: 1000})))
    short = {FUT: -1000}
    assert check(fut("buy", price=782.0, purpose="stop", trigger=800.0, gtt=True), ctx(positions=short)) == []


def test_option_sells_must_be_covered():
    c = dict(bid=5.4, ask=5.5)
    assert any("uncovered" in r for r in check(opt("sell", 860, price=5.4), ctx(**c)))
    long_820 = {("INDHOT", EXP, "call", 820.0): 1000}
    assert check(opt("sell", 860, price=5.4), ctx(positions=long_820, **c)) == []        # short leg of a vertical
    both = {**long_820, ("INDHOT", EXP, "call", 860.0): -1000}
    assert any("uncovered" in r for r in check(opt("sell", 880, price=5.4), ctx(positions=both, **c)))
    assert any("uncovered" in r for r in check(opt("sell", 860, price=5.4, right="put"), ctx(positions=long_820, **c)))
    assert check(opt("sell", 820, price=5.4, purpose="exit"), ctx(positions=long_820, **c)) == []


def test_size_caps():
    assert any("notional" in r for r in check(fut(qty=2000), ctx()))                  # ₹15.6L over ₹10L
    big = opt("buy", 820, qty=4000, price=13.0)
    assert any("premium" in r for r in check(big, ctx(bid=12.9, ask=13.0)))
    assert check(big, ctx(bid=12.9, ask=13.0), Limits(max_opt_premium=60_000)) == []


def test_round_tick():
    assert round_tick(782.03, up=True) == 782.05
    assert round_tick(782.03, up=False) == 782.0
    assert round_tick(782.05, up=True) == 782.05


def test_contract_tick_other_than_005():
    # 27-Oct: a 0.10-tick future refused "Price should be in multiples of: 0.10" (a 3442.25 trigger)
    assert round_tick(3150.47, up=True, tick=0.1) == 3150.5
    assert round_tick(3442.23, up=True, tick=0.1) == 3442.3
    assert round_tick(3442.23, up=False, tick=0.1) == 3442.2
    assert round_tick(41234.0, up=True, tick=5.0) == 41235.0
    c = ctx(tick=0.1, bid=3150.0, ask=3150.5, lot=100)
    assert any("0.1 tick" in r for r in check(fut(qty=100, price=3150.45), c))
    assert check(fut(qty=100, price=3150.5), c) == []
