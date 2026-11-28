"""Box-width and trailing-stop backtests (2026-09-22): their saved trades, with a stop that sits above
the exit day's open filled at the open, re-scored with the scripts' own split and Stressed metrics.
Prices checked against the frozen L1 snapshot adjusted to 2026-09-22; trades whose entry doesn't
match the NSE open within 0.5% (a different adjustment) are left as published. Lab verification 2026-11-28.

    python scripts/research/gap_fill_check/box_width_trailing.py
"""
import json, sys, collections
sys.path.insert(0, '.')
import pandas as pd
from pathlib import Path
from core.market_map.l1_store import Store
import scripts.backtest_darvas_box_width as box
import scripts.backtest_darvas_trailing_stop as tr
st = Store(Path.home() / '.quantos' / 'l1_snap_20261113'); A = st.actions(); cache = {}
def frame(s):
    if s not in cache:
        df, _ = st.adjusted(s, {s: [a for a in A.get(s, []) if str(a.get('ex', ''))[:10] <= '2026-09-22']})
        if not df.empty:
            df['date'] = pd.to_datetime(df['date']); df = df[df.series == 'EQ'].set_index('date')
        cache[s] = df
    return cache[s]
for mod, cachef in ((box, 'darvas_width_backtest_results.json'), (tr, 'darvas_trailing_stop_results.json')):
    raw = mod.all_trades(json.load(open(Path.home() / '.quantos' / cachef)))
    c = collections.Counter(); fixed = []
    for t in raw:
        t2 = dict(t); df = frame(t['symbol']); ed, xd = pd.Timestamp(t['entry_date'][:10]), pd.Timestamp(t['exit_date'][:10])
        if df.empty or ed not in df.index or xd not in df.index or abs(float(df.loc[ed].o) / t['entry_price'] - 1) > 0.005:
            c['unchecked'] += 1
        elif t['reason'] == 'stop' and t['exit_price'] > float(df.loc[xd].o) + 0.01:
            c['stop above open -> open'] += 1; c['  above day high'] += t['exit_price'] > float(df.loc[xd].h) + 0.01
            t2['exit_price'] = float(df.loc[xd].o)
        fixed.append(t2)
    print(mod.__name__.split('.')[-1], dict(c))
    for lab, pred in box.BUCKETS:
        for before, sp in ((True, 'mining'), (False, 'holdout')):
            ma = box._metrics(mod._split(raw, pred, before), box.STRESSED_COST_MODEL)
            mb = box._metrics(mod._split(fixed, pred, before), box.STRESSED_COST_MODEL)
            if ma:
                print(f"   {lab:16} {sp:8} PF {ma.profit_factor:.2f} -> {mb.profit_factor:.2f}  edge {ma.has_positive_edge} -> {mb.has_positive_edge}")
