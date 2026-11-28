"""Darvas ATR-stop OOS 2016-23 (docs/DARVAS_ATR_STOP_OOS_RESULTS.md): the published trades with every stop
that sits above the exit day's open filled at that open, scored by the OOS script's own summarize on its own
adjusted bhavcopy bars. Lab verification 2026-11-28. Same finding as docs/DARVAS_CUES_PREREG_2026-10-23.md
(diagnostic, 2026-10-24), which handles locked bars more carefully (+0.38% there, +0.48% here).

    python scripts/research/gap_fill_check/atr_stop_oos.py
"""
import json, sys, collections
sys.path.insert(0, '.')
import scripts.backtest_darvas_atr_stop_oos as oos
raw = oos.load_bhavcopies(); snaps = oos.build_universe(raw)
members = sorted(frozenset().union(*(s.symbols for s in snaps)))
acts = oos.load_actions(); adj = {s: oos.adjust(raw[s], acts.get(s, [])) for s in members}
res = json.loads(oos.CACHE.read_text())
c = collections.Counter(); fixed = {}
for sym, v in res.items():
    bars = {str(r['date'])[:10]: r for r in adj.get(sym, [])}
    out = []
    for t in v.get('trades', []):
        t2 = dict(t); b = bars.get(t['exit_date'][:10]); e = bars.get(t['entry_date'][:10])
        if b is None or e is None or abs(e['o'] / t['entry_price'] - 1) > 1e-6:
            c['unchecked'] += 1
        elif t['reason'] == 'stop' and t['exit_price'] > b['o'] + 1e-9:
            c['stop above open -> open'] += 1; c['  above day high'] += t['exit_price'] > b['h']; t2['exit_price'] = b['o']
        else:
            c['ok'] += 1
        out.append(t2)
    fixed[sym] = {**v, 'trades': out}
print(dict(c))
ew_days, ew_lvl = oos.ew_index(adj, snaps)
sys.stdout.buffer.write(oos.summarize(fixed, ew_days, ew_lvl).encode('utf-8'))
