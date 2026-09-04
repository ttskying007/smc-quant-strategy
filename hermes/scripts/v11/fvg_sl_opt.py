#!/usr/bin/env python3
"""
FVG SL Optimization — 测试tight SL对FVG的效果
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

KLINE = Path('/root/.hermes/kline_cache')
PICKS_FILE = Path('/root/.hermes/smc_opt_v21/LD_picks_v6.json')
OUT = Path('/root/.hermes/smc_opt_v21')

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

print("=" * 60)
print("  FVG SL Optimization")
print("=" * 60)

picks_data = json.loads(PICKS_FILE.read_bytes())
fvg_picks = [p for p in picks_data['picks'] if 'FVG' in p.get('zone_type', '') and p.get('tier') == 'L1']
# Also include L2 FVG combos
fvg_combo_picks = [p for p in picks_data['picks'] if '→FVG' in p.get('signal', '')]
all_fvg = fvg_picks + fvg_combo_picks
print(f"  FVG picks: {len(fvg_picks)} single + {len(fvg_combo_picks)} combo = {len(all_fvg)} total")

# Test different SL approaches
configs = [
    ('tight_zone', lambda ep, pick: pick.get('zone_low', ep) * 0.96),  # Like OB
    ('tight_0.97', lambda ep, pick: ep * 0.97),  # Fixed tight
    ('medium_0.95', lambda ep, pick: ep * 0.95),  # Medium
    ('wide_find_sls', None),  # Original find_sls (None = use original)
]

# Load all daily data once
print("  Loading OHLCV...")
kline_cache = {}
for fpath in KLINE.glob('*_daily_300.json'):
    sym = fpath.stem.replace('_daily_300', '')
    try:
        kline_cache[sym] = json.loads(fpath.read_bytes())
    except:
        pass
print(f"  Loaded {len(kline_cache)} stocks")

results = {}
for cfg_name, sl_func in configs:
    trades = []
    t0 = time.time()
    
    for pick in all_fvg:
        sym_raw = pick['symbol']
        sym_key = sym_raw.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
        
        daily = kline_cache.get(sym_key)
        if daily is None or len(daily) < 50:
            continue
        
        n = len(daily)
        zone_bar = pick.get('zone_bar', 0)
        entry_bar = zone_bar + 1
        if entry_bar >= n - 2:
            continue
        
        ep = daily[entry_bar]['o']
        if ep <= 0:
            continue
        
        # TP
        tp = pick.get('tp', ep * 1.05)
        tp = min(tp, ep * 1.05)
        
        # SL - different approach per config
        if sl_func:
            sl = sl_func(ep, pick)
        else:
            sigs, _, _, swings_dict = detect_all_signals_v20(daily)
            sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
            if sl is None:
                sl = ep * 0.97
        
        if tp <= ep or sl >= ep:
            continue
        
        tpd = (tp - ep) / ep * 100
        sld = (ep - sl) / ep * 100
        if sld <= 0 or tpd / sld < 1.0:
            continue
        
        # Execute
        exit_idx = -1
        exit_price = 0
        exit_method = 'eod'
        for k in range(entry_bar + 1, n):
            bk = daily[k]
            if bk['h'] >= tp:
                exit_idx = k; exit_price = tp; exit_method = 'tp_hit'; break
            if bk['l'] <= sl:
                exit_idx = k; exit_price = sl; exit_method = 'sl_hit'; break
        
        if exit_idx < 0:
            exit_idx = min(n - 1, entry_bar + 20)
            exit_price = daily[exit_idx]['c']
        
        if exit_idx <= entry_bar:
            continue
        
        pnl = (exit_price - ep) / ep * 100
        trades.append({
            'entry_bar': entry_bar,
            'exit_bar': exit_idx,
            'entry_price': round(ep, 2),
            'exit_price': round(exit_price, 2),
            'entry_date': str(daily[entry_bar].get('t', ''))[:8],
            'exit_date': str(daily[exit_idx].get('t', ''))[:8],
            'pnl_pct': round(pnl, 2),
            'won': pnl > 0,
            'entry_signal': pick.get('zone_type', 'FVG_Bull'),
            'pattern': pick['signal'],
            'sl_price': round(sl, 2),
            'tp_price': round(tp, 2),
            'exit_reason': exit_method,
            'hold_bars': exit_idx - entry_bar,
            'entry_mode': 'immediate',
            'sl_method': cfg_name,
        })
    
    n = len(trades)
    if n == 0:
        results[cfg_name] = {'n': 0}
        continue
    
    wr = sum(1 for t in trades if t['won']) / n * 100
    avg = sum(t['pnl_pct'] for t in trades) / n
    cum = sum(t['pnl_pct'] for t in trades)
    tp_hits = sum(1 for t in trades if t['exit_reason'] == 'tp_hit')
    sl_hits = sum(1 for t in trades if t['exit_reason'] == 'sl_hit')
    eod = sum(1 for t in trades if t['exit_reason'] == 'eod')
    sl_rate = sl_hits / n * 100
    
    elapsed = time.time() - t0
    print(f"\n  {cfg_name}: n={n} WR={wr:.1f}% avg={avg:+.2f}% cum={cum:+.1f}% ({elapsed:.0f}s)")
    print(f"    TP={tp_hits}({tp_hits/n*100:.1f}%) SL={sl_hits}({sl_rate:.1f}%) EOD={eod}")
    
    results[cfg_name] = {
        'n': n, 'wr': round(wr, 1), 'avg': round(avg, 2), 'cum': round(cum, 2),
        'tp': tp_hits, 'sl': sl_hits, 'sl_rate': round(sl_rate, 1), 'eod': eod,
    }

# ═══ 对比 ═══
print(f"\n{'=' * 60}")
print(f"  COMPARISON")
print(f"{'=' * 60}")
print(f"  {'Method':<20s} {'n':>5s} {'WR':>7s} {'avg':>7s} {'cum':>8s} {'SL%':>6s}")
print(f"  {'-'*55}")
for cfg_name, r in results.items():
    if r.get('n', 0) == 0:
        continue
    print(f"  {cfg_name:<20s} {r['n']:>5d} {r['wr']:>6.1f}% {r['avg']:>+6.2f}% {r['cum']:>+7.1f}% {r['sl_rate']:>5.1f}%")

print(f"\nDONE")
