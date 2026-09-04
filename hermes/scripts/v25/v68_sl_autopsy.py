#!/usr/bin/env python3
"""V68 SL_HIT autopsy — root cause of 41.65% SL rate.

For every SL_HIT trade, classify against kline cache:
  WICK_STOP        exit bar low<=sl but close>sl (noise wick took the stop)
  GAP_THROUGH      exit bar open<sl (gap loss, SL price not real)
  CLOSE_THROUGH    exit bar close<=sl (decisive violation)
  RECOVERED_TO_TP  after SL bar, hits original tp1 within remaining window
  ZONE_DEAD        exit bar close < zone_low (demand truly failed)
Also MFE before SL in R-multiples (was TP reachable / trail missing?).
"""
import json
from pathlib import Path
from collections import Counter, defaultdict

KLINE_DIR = Path('/root/.hermes/kline_cache')
TR = json.loads(Path('/root/.hermes/smc_opt_v68_strict_ld/v68_trades.json').read_text())
MAX_HOLD = 60

def f(x):
    try: return float(x or 0)
    except Exception: return 0.0

_kcache = {}
def load_ks(sym):
    if sym in _kcache: return _kcache[sym]
    p = KLINE_DIR / (sym.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ') + '_daily_750.json')
    try:
        ks = json.loads(p.read_text())
    except Exception:
        ks = None
    _kcache[sym] = ks
    return ks

sl_trades = [t for t in TR if t['exit_reason'] == 'SL_HIT']
tp_trades = [t for t in TR if t['exit_reason'] == 'TP1_HIT']
print(f"total={len(TR)} SL={len(sl_trades)} TP={len(tp_trades)} TIME={len(TR)-len(sl_trades)-len(tp_trades)}")

cls = Counter()
mfe_bins = Counter()
detail = []
by_combo = defaultdict(list)

for t in sl_trades:
    ks = load_ks(t['symbol'])
    if not ks: continue
    ei, xi = t['entry_idx'], t['exit_idx']
    ep, sl, tp1, zl = t['entry_price'], t['sl'], t['tp1'], t['zone_low']
    R = ep - sl
    bar = ks[xi]
    op, cl, lo = f(bar.get('o')), f(bar.get('c')), f(bar.get('l'))
    tags = []
    if op < sl: tags.append('GAP_THROUGH')
    elif cl > sl: tags.append('WICK_STOP')
    else: tags.append('CLOSE_THROUGH')
    if cl < zl: tags.append('ZONE_DEAD')
    # MFE before SL bar
    mfe = 0.0
    for j in range(ei+1, xi):
        mfe = max(mfe, f(ks[j].get('h')) - ep)
    mfe_r = mfe / R if R > 0 else 0
    if mfe_r >= 0.8: mfe_bins['>=0.8R'] += 1
    elif mfe_r >= 0.5: mfe_bins['0.5-0.8R'] += 1
    elif mfe_r >= 0.25: mfe_bins['0.25-0.5R'] += 1
    else: mfe_bins['<0.25R'] += 1
    # recovery: after SL bar does price hit tp1 within remaining hold window?
    recovered = False
    for j in range(xi+1, min(len(ks), ei + MAX_HOLD + 1)):
        if f(ks[j].get('h')) >= tp1: recovered = True; break
        if f(ks[j].get('c')) < zl * 0.97: break
    if recovered: tags.append('RECOVERED_TO_TP')
    for tag in tags: cls[tag] += 1
    primary = tags[0]
    by_combo[(primary, 'REC' if recovered else 'noREC')].append(t)
    detail.append({'symbol': t['symbol'], 'entry_date': t['entry_date'], 'tags': tags, 'mfe_r': round(mfe_r,2), 'risk_pct': t['risk_pct'], 'retrace_pct': t['retrace_pct'], 'disp_atr': t['disp_atr'], 'pierce_atr': t['pierce_atr'], 'fill_delay': t['entry_idx']-t['confirm_bar'], 'hold_bars': t['hold_bars']})

n = len(detail)
print("\n== SL_HIT classification ==")
for k, v in cls.most_common():
    print(f"  {k:16s} {v:5d}  {v/n*100:5.1f}%")
print("\n== combo (primary, recovered) ==")
for k, v in sorted(by_combo.items(), key=lambda kv: -len(kv[1])):
    print(f"  {str(k):32s} {len(v):5d}  {len(v)/n*100:5.1f}%")
print("\n== MFE before SL (R-multiple) ==")
for k in ['>=0.8R','0.5-0.8R','0.25-0.5R','<0.25R']:
    print(f"  {k:10s} {mfe_bins[k]:5d}  {mfe_bins[k]/n*100:5.1f}%")

# factor concentration of SL trades vs TP trades
def dist(ts, fn):
    c = Counter(fn(t) for t in ts)
    tot = sum(c.values())
    return {k: round(v/tot*100,1) for k,v in sorted(c.items())}

factors = {
    'risk_bin': lambda t: '<3' if t['risk_pct']<3 else ('3-6' if t['risk_pct']<6 else '6-8'),
    'retrace_bin': lambda t: '30-60' if t['retrace_pct']<60 else '60-90',
    'disp_bin': lambda t: '<0.8' if t['disp_atr']<0.8 else ('0.8-1.5' if t['disp_atr']<1.5 else '>=1.5'),
    'pierce_bin': lambda t: '<0.3' if t['pierce_atr']<0.3 else ('0.3-1.0' if t['pierce_atr']<1.0 else '>=1.0'),
    'fill_delay': lambda t: '1-3' if t['entry_idx']-t['confirm_bar']<=3 else ('4-8' if t['entry_idx']-t['confirm_bar']<=8 else '>8'),
    'hold_to_sl': lambda t: '1-2' if t['hold_bars']<=2 else ('3-8' if t['hold_bars']<=8 else '>8'),
    'year': lambda t: t['entry_date'][:4],
}
print("\n== factor distribution SL vs TP (%) ==")
for name, fn in factors.items():
    print(f"  [{name}] SL={dist(sl_trades, fn)}")
    print(f"  [{name}] TP={dist(tp_trades, fn)}")

Path('/root/.hermes/smc_opt_v68_strict_ld/v68_sl_autopsy.json').write_text(json.dumps({'classification': dict(cls), 'mfe_bins': dict(mfe_bins), 'n_sl': n, 'detail': detail[:500]}, ensure_ascii=False, indent=2))
print('\nSaved autopsy json.')
