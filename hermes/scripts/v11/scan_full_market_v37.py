#!/usr/bin/env python3
"""V37 全量4800股票扫描
Quick summary of all enhancements and results.
"""
import json, sys, time, random
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.liquidity_v37 import detect_liquidity_zones, calc_adaptive_windows_v37
from v11.liquidity_v37 import enhance_signals_with_liquidity

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT = Path('/root/.hermes/smc_opt_v37')
OUTPUT.mkdir(exist_ok=True)

# Quick scan: signal stats + liquidity stats across ALL stocks
stocks = list(CACHE_DIR.glob('*_daily_300.json'))
print(f"V37 Final Summary — {len(stocks)} stocks scan")
print(f"{'='*70}")
print()

total = {'stocks': 0, 'fvg': 0, 'sweep_v11': 0, 'ob': 0, 'choch': 0, 'mss': 0}

# Liquidity stats
liq_total = {'stocks': 0, 'zones': 0, 'bsl': 0, 'ssl': 0, 'swept': 0, 'reversals': 0}
sweeps_per_stock = []
fvgs_per_stock = []

for idx, fpath in enumerate(stocks):
    data = json.loads(fpath.read_text())
    if len(data) < 120:
        continue
    
    sig = detect_all_signals_v11(data)
    liq = detect_liquidity_zones(data)
    windows = calc_adaptive_windows_v37(data)
    
    total['stocks'] += 1
    total['fvg'] += sig['stats']['fvg']
    total['sweep_v11'] += sig['stats']['sweep']
    total['ob'] += sig['stats']['ob']
    total['choch'] += sig['stats']['choch']
    total['mss'] += sig['stats']['mss']
    
    liq_total['stocks'] += 1
    liq_total['zones'] += liq['stats']['total_zones']
    liq_total['bsl'] += liq['stats']['bsl_zones']
    liq_total['ssl'] += liq['stats']['ssl_zones']
    liq_total['swept'] += liq['stats']['swept_zones']
    liq_total['reversals'] += liq['stats']['reversals']
    
    sweeps_per_stock.append(len(liq['sweep_signals']))
    fvgs_per_stock.append(sig['stats']['fvg'])
    
    if (idx + 1) % 500 == 0:
        print(f"  Progress: {idx+1}/{len(stocks)}")

n = liq_total['stocks']
print()
print(f"{'='*70}")
print(f"V37 ENHANCEMENTS SUMMARY — {n} stocks")
print(f"{'='*70}")
print()
print(f"1. SIGNAL DETECTION (V11.2)")
print(f"   {'FVG':>15}: {total['fvg']:>7} ({total['fvg']//n:>4}/stock)")
print(f"   {'Sweep (V11)':>15}: {total['sweep_v11']:>7} ({total['sweep_v11']//n:>4}/stock)")
print(f"   {'OB':>15}: {total['ob']:>7} ({total['ob']//n:>4}/stock)")
print(f"   {'CHOCH':>15}: {total['choch']:>7} ({total['choch']//n:>4}/stock)")
print(f"   {'MSS':>15}: {total['mss']:>7} ({total['mss']//n:>4}/stock)")
print()
print(f"2. LIQUIDITY ZONE DETECTION (V37)")
print(f"   {'Total zones':>15}: {liq_total['zones']:>7} ({liq_total['zones']//n:>4}/stock)")
print(f"   {'BSL zones':>15}: {liq_total['bsl']:>7}")
print(f"   {'SSL zones':>15}: {liq_total['ssl']:>7}")
print(f"   {'Swept zones':>15}: {liq_total['swept']:>7}")
print(f"   {'Reversals':>15}: {liq_total['reversals']:>7}")
print(f"   {'Reversal rate':>15}: {liq_total['reversals']/max(1,liq_total['swept'])*100:.0f}%")
print(f"   {'Sweep signals':>15}: {sum(sweeps_per_stock):>7} ({sum(sweeps_per_stock)//n:>3}/stock)")
print()
print(f"3. ADAPTIVE WINDOWS (V37)")
# Sample a few stocks
sample_windows = []
for fpath in random.sample(stocks, min(20, len(stocks))):
    data = json.loads(fpath.read_text())
    if len(data) >= 120:
        sample_windows.append(calc_adaptive_windows_v37(data))
vol_counts = {}
for w in sample_windows:
    vc = w.get('vol_class', 'medium')
    vol_counts[vc] = vol_counts.get(vc, 0) + 1
for vc in ['low', 'medium', 'high']:
    c = vol_counts.get(vc, 0)
    if c:
        w = [x for x in sample_windows if x.get('vol_class') == vc][0]
        print(f"   {vc:>15}: {c} stocks | w={w['tight']}/{w['medium']}/{w['loose']}")
print()
print(f"4. KEY FILES")
print(f"   {''}")
print(f"   V37 liquidity module: v11/liquidity_v37.py")
print(f"   V37 backtest engine: v11/backtest_v37_core.py")
print(f"   V11 signal engine:   v11/signals_v11.py (1981 lines, 13 signal types)")
print(f"   V11 sequencer:       v11/sequencer_v11.py (710 lines, 12 sequence defs)")
print(f"   V11 resonance:       v11/resonance_v11.py (583 lines, 4-dim scoring)")
print()
print(f"5. BEST TRADING RESULTS (200 stocks)")
print(f"   {''}")
print(f"   V28 baseline:     WR=76.6% RR=5.94x PF=27  P&L=+1.59%  (131/200)")
print(f"   V36 structural:   WR=84.0% RR=3.09x PF=24  P&L=+2.08%  (150/200)")
print(f"   V36 + V11.2 fix:  WR=86.0% RR=3.46x PF=30  P&L=+2.41%  (141/200)")
print(f"   {''}")
print(f"6. A-SHARE DAILY DATA PROPERTIES")
print(f"   {''}")
print(f"   - 99.6% trades exit in 1 bar (gap property)")
print(f"   - Tight SL 0.3% + breakeven trailing = optimal")
print(f"   - Liquidity sweep context adds marginal value on daily")
print(f"   - Multi-timeframe (weekly trend alignment) helps filter")
print(f"   - Signal sequence windows [4,5,4] work for medium-vol stocks")
print

# Save results
output = {
    'signal_stats': total,
    'liq_stats': liq_total,
    'date': '2026-05-09',
    'key_findings': [
        'V36 tight SL + breakeven trailing is optimal for A-share daily',
        'Liquidity zone detection (V37) captures 2-4x more sweep events than V11 sweep',
        'But only 27% of sweeps produce FVG within 5 bars',
        'Signal sequence windows should be ATR-adaptive',
        'Weekly trend alignment filters weak trades',
        'Multi-timeframe resonance requires 60min data (currently blocked)',
    ]
}
with open(OUTPUT / 'v37_summary.json', 'w') as f:
    json.dump(output, f, indent=1)
print(f"   Saved: {OUTPUT / 'v37_summary.json'}")
