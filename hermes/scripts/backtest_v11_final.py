#!/usr/bin/env python3
"""V11最终验证——趋势质量过滤+单次检测+最优参数"""
import json, time, sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.data_loader import load_cached_ohlcv
from v11.backtest_v11 import backtest_single_stock_v11

CACHE_DIR = Path('/root/.hermes/kline_cache')
OPT_DIR = Path('/root/.hermes/smc_opt_v11')
OUTFILE = OPT_DIR / 'backtest_v11_final.json'

symbols = sorted([
    f.stem.replace('_daily_300', '').replace('_', '.')
    for f in CACHE_DIR.glob('*_daily_300.json')
])

# 取100只
test_symbols = [s for s in symbols if s.startswith(tuple('0123456789'))][:100]

print("=" * 70)
print("V11 FINAL — 趋势质量过滤 + 最优参数 (100 stocks)")
print("=" * 70)

t0_total = time.time()
results = []

for idx, sym in enumerate(test_symbols):
    t0 = time.time()
    ohlcv = load_cached_ohlcv(sym, 'daily', 300)
    if not ohlcv or len(ohlcv) < 80:
        print(f"  [{idx+1:>3d}/100] {sym:12s} | NO-DATA")
        continue

    phase = detect_market_phase(ohlcv)
    params = calc_stock_params(ohlcv, sym, phase=phase, tf='daily')

    # 趋势质量过滤: 只用最近100根K线
    recent = ohlcv[-100:]
    recent_phase = detect_market_phase(recent)

    if recent_phase not in ('breakout', 'volatile'):
        print(f"  [{idx+1:>3d}/100] {sym:12s} | SKIP phase={recent_phase}")
        continue

    # 单次完整检测+回测 (用backtest_single_stock_v11)
    try:
        bt = backtest_single_stock_v11(
            ohlcv, symbol=sym, params=params, tf='daily',
            min_resonance=0.45, min_rr=1.5,
        )
    except Exception as e:
        print(f"  [{idx+1:>3d}/100] {sym:12s} | ERROR {e}")
        continue

    trades = bt.get('trades', [])
    # Bull-only过滤
    trades = [t for t in trades if t.direction == 'bull']

    if not trades:
        print(f"  [{idx+1:>3d}/100] {sym:12s} | NO-BULL-TRADES ({time.time()-t0:.1f}s)")
        continue

    n = len(trades)
    wins = sum(1 for t in trades if t.won)
    wr = wins / n * 100
    avg_rr = sum(t.rr for t in trades) / n
    total_pnl = sum(t.pnl_pct for t in trades)
    avg_pnl = total_pnl / n
    win_pnl = sum(max(t.pnl_pct, 0) for t in trades)
    loss_pnl = abs(sum(min(t.pnl_pct, 0) for t in trades))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else float('inf')

    results.append({
        'symbol': sym,
        'n_trades': n, 'wins': wins, 'losses': n - wins,
        'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
        'profit_factor': round(pf, 2), 'avg_pnl': round(avg_pnl, 2),
        'phase': phase,
    })

    elapsed = time.time() - t0
    print(f"  [{idx+1:>3d}/100] {sym:12s} | trades={n:>3d} WR={wr:>5.1f}% RR={avg_rr:.2f}x PF={pf:.1f} P&L={avg_pnl:+.2f}% phase={phase} | {elapsed:.1f}s")

dt = time.time() - t0_total
tradable = [r for r in results]

print()
print("=" * 70)
print(f"SUMMARY — {len(tradable)} tradable out of {len(test_symbols)}, {dt:.0f}s")
print("=" * 70)

n = sum(s['n_trades'] for s in tradable)
wr = sum(s['n_trades'] * s['win_rate'] for s in tradable) / n if n > 0 else 0
print(f"  Stocks: {len(tradable)}")
print(f"  Total trades: {n}")
print(f"  Avg WR: {wr:.1f}%")
print(f"  WR>=70%: {len([s for s in tradable if s['win_rate'] >= 70])}/{len(tradable)}")
print(f"  WR>=60%: {len([s for s in tradable if s['win_rate'] >= 60])}/{len(tradable)}")

# Top 10
print("\n  TOP 10:")
for s in sorted(tradable, key=lambda x: x['win_rate'], reverse=True)[:10]:
    print(f"  {s['symbol']:12s} WR={s['win_rate']:>5.1f}% RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} trades={s['n_trades']}")

# Save
output = {
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    'summary': {
        'total_stocks': len(test_symbols), 'tradable': len(tradable),
        'total_trades': n, 'weighted_wr': round(wr, 1),
    },
    'stocks': tradable,
}
OUTFILE.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
print(f"\n  Saved: {OUTFILE}")
