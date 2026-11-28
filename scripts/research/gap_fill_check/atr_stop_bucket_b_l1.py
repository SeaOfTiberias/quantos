"""Darvas ATR-stop Bucket B, OOS 2016-23 and in-sample 2024-26 caches, gap-through stops filled at the open,
checked against the frozen L1 snapshot (trades on another price scale left as published). Lab verification 2026-11-28."""
import json, sys, statistics, collections
sys.path.insert(0, '.')
import pandas as pd
from pathlib import Path
from core.market_map.l1_store import Store
import scripts.backtest_darvas_box_width as box
from scripts.backtest_darvas_atr_stop_oos import net_return
st = Store(Path.home() / '.quantos' / 'l1_snap_20261113'); A = st.actions(); cache = {}
def frame(s, asof):
    k = (s, asof)
    if k not in cache:
        df, _ = st.adjusted(s, {s: [a for a in A.get(s, []) if str(a.get('ex', ''))[:10] <= asof]})
        if not df.empty:
            df['date'] = pd.to_datetime(df['date']); df = df[df.series == 'EQ'].set_index('date')
        cache[k] = df
    return cache[k]
def run(cachef, asofs, lo, hi):
    res = json.load(open(Path.home() / '.quantos' / cachef))
    trades = [t for v in res.values() for t in v.get('trades', []) if 35 < t['width_pct'] <= 50 and lo <= t['entry_date'][:10] <= hi]
    c = collections.Counter(); a, b = [], []
    for t in trades:
        t2 = dict(t); ed, xd = pd.Timestamp(t['entry_date'][:10]), pd.Timestamp(t['exit_date'][:10]); df = None
        for asof in asofs:
            f = frame(t['symbol'], asof)
            if not f.empty and ed in f.index and abs(float(f.loc[ed].o) / t['entry_price'] - 1) < 0.005:
                df = f; break
        if df is None or xd not in df.index:
            c['unchecked (no bar / scale)'] += 1
        else:
            o, h = float(df.loc[xd].o), float(df.loc[xd].h)
            if t['reason'] == 'stop' and t['exit_price'] > o + 0.01:
                c['stop above the open -> filled at open'] += 1; t2['exit_price'] = o
                if t['exit_price'] > h + 0.01: c['  of which above the day high'] += 1
            else:
                c['ok'] += 1
        a.append(net_return(t, box.STRESSED_COST_MODEL)); b.append(net_return(t2, box.STRESSED_COST_MODEL))
    pf = lambda x: sum(v for v in x if v > 0) / -sum(v for v in x if v < 0)
    print(f"{cachef} {lo}..{hi}: n {len(a)}  mean net {statistics.mean(a):+.2%} -> {statistics.mean(b):+.2%}  PF {pf(a):.2f} -> {pf(b):.2f}  delta {statistics.mean(b)-statistics.mean(a):+.2%}/trade")
    print('   ', dict(c))
run('darvas_atr_stop_oos_results.json', ['2023-12-31', '2026-11-13'], '2016-01-01', '2023-12-31')
run('darvas_atr_stop_results.json', ['2026-09-24', '2026-11-13'], '2023-01-01', '2026-12-31')
