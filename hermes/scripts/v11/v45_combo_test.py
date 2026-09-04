#!/usr/bin/env python3
"""
V45 信号组合测试 — 系统测试不同TRADE_SIGNAL_TYPE组合的效果
==========================================================
测试7种组合, 100只股票子集, ~2min完成
"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')
from pathlib import Path

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v45')
OUTPUT_DIR.mkdir(exist_ok=True)

# 100 stocks for speed
symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])[:100]

print("=" * 100)
print(f"V45 信号组合测试 — {len(symbols)}只股票 × 7组合")
print("=" * 100)

# Define combos to test
# Each combo: (name, trade_types, entry_types, quality_thresholds, enable_bear)
COMBOS = [
    ('A: FVG-only',
     {'FVG_Bull'}, {'FVG_Bull'},
     {'FVG_Bull': 0.55}, False),

    ('B: OB-only',
     {'OB_Bull'}, {'OB_Bull'},
     {'OB_Bull': 0.50}, False),

    ('C: FVG+OB (V45 baseline)',
     {'FVG_Bull', 'OB_Bull'}, {'FVG_Bull', 'OB_Bull'},
     {'FVG_Bull': 0.55, 'OB_Bull': 0.50}, False),

    ('D: FVG+OB+Sweep',
     {'FVG_Bull', 'OB_Bull', 'SweepUp', 'SweepDown'}, {'FVG_Bull', 'OB_Bull'},
     {'FVG_Bull': 0.55, 'OB_Bull': 0.50}, False),

    ('E: FVG+OB+CHOCH',
     {'FVG_Bull', 'OB_Bull', 'CHOCH_Bull', 'CHOCH_Bear'}, {'FVG_Bull', 'OB_Bull', 'CHOCH_Bull'},
     {'FVG_Bull': 0.55, 'OB_Bull': 0.50, 'CHOCH_Bull': 0.50}, False),

    ('F: All 4 (FVG+OB+Sweep+CHOCH)',
     {'FVG_Bull', 'OB_Bull', 'SweepUp', 'SweepDown', 'CHOCH_Bull', 'CHOCH_Bear'},
     {'FVG_Bull', 'OB_Bull', 'CHOCH_Bull'},
     {'FVG_Bull': 0.55, 'OB_Bull': 0.50, 'CHOCH_Bull': 0.50}, False),

    ('G: All 14 (no Bear)',
     {'FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear',
      'SweepUp', 'SweepDown', 'CHOCH_Bull', 'CHOCH_Bear',
      'MSS_Bull', 'MSS_Bear', 'OTE_Bull', 'OTE_Bear',
      'EQL_High', 'EQL_Low', 'PO3_Acc', 'PO3_Man', 'PO3_DIS',
      'LiquidityVoid', 'Rejection_Resistance', 'Rejection_Support',
      'BreakerBlock_Bull', 'BreakerBlock_Bear',
      'IFVG_Bull', 'IFVG_Bear', 'BPR_Bull', 'BPR_Bear'},
     {'FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear',
      'SweepUp', 'SweepDown', 'CHOCH_Bull', 'CHOCH_Bear',
      'MSS_Bull', 'MSS_Bear', 'OTE_Bull', 'OTE_Bear',
      'EQL_High', 'EQL_Low', 'PO3_Acc', 'PO3_Man', 'PO3_DIS',
      'LiquidityVoid', 'Rejection_Resistance', 'Rejection_Support',
      'BreakerBlock_Bull', 'BreakerBlock_Bear',
      'IFVG_Bull', 'IFVG_Bear', 'BPR_Bull', 'BPR_Bear'},
     {'FVG_Bull': 0.55, 'FVG_Bear': 0.60, 'OB_Bull': 0.50, 'OB_Bear': 0.55,
      'CHOCH_Bull': 0.50, 'CHOCH_Bear': 0.55,
      'MSS_Bull': 0.60, 'MSS_Bear': 0.65, 'OTE_Bull': 0.50, 'OTE_Bear': 0.55,
      'EQL_High': 0.55, 'EQL_Low': 0.55,
      'PO3_Acc': 0.50, 'PO3_Man': 0.50, 'PO3_DIS': 0.50,
      'LiquidityVoid': 0.60,
      'Rejection_Resistance': 0.55, 'Rejection_Support': 0.55,
      'BreakerBlock_Bull': 0.55, 'BreakerBlock_Bear': 0.60,
      'IFVG_Bull': 0.55, 'IFVG_Bear': 0.60, 'BPR_Bull': 0.50, 'BPR_Bear': 0.55},
     False),
]

results = []

for combo_name, trade_types, entry_types, thresholds, enable_bear in COMBOS:
    print(f"\n{'─'*100}")
    print(f"测试组合: {combo_name}")

    # ── Patch engine constants ──
    # Import AFTER setting up combo to avoid stale module state
    # Use import + forced re-read of constants via fresh import
    if 'v45_engine' in sys.modules:
        del sys.modules['v45_engine']

    import v11.v45_engine as eng

    # Apply combo config
    eng.TRADE_SIGNAL_TYPES = trade_types
    eng.ENTRY_SIGNAL_TYPES = entry_types
    eng.QUALITY_THRESHOLDS = thresholds
    eng.ENABLE_BEAR = enable_bear
    eng.ENTRY_AT_ZONE = True
    eng.STOCK_PARAMS_CACHE = {}

    # Now run backtest using fresh config
    t0 = time.time()
    result = eng.run_backtest(symbols, combo_name)
    elapsed = time.time() - t0

    if result and result['summary']['n_trades'] > 0:
        s = result['summary']
        n_tradable = len(result['stock_results'])
        results.append({
            'combo': combo_name,
            'stocks': n_tradable,
            'trades': s['n_trades'],
            'wr': s['win_rate'],
            'rr': s['avg_rr'],
            'pf': s['profit_factor'],
            'pnl': s['avg_pnl'],
            'time': round(elapsed, 1),
        })
        print(f"  → {n_tradable:3d} stocks | {s['n_trades']:5d} trades | "
              f"WR={s['win_rate']:.1f}% | RR={s['avg_rr']:.2f}x | "
              f"PF={s['profit_factor']:.0f} | P&L={s['avg_pnl']:+.2f}% | "
              f"t={elapsed:.0f}s")
    else:
        results.append({
            'combo': combo_name,
            'stocks': 0, 'trades': 0,
            'wr': 0, 'rr': 0, 'pf': 0, 'pnl': 0,
            'time': round(elapsed, 1),
        })
        print(f"  → FAILED (no trades)")

# Print summary table
print(f"\n{'='*100}")
print(f"信号组合测试结果汇总 ({len(symbols)}只股票 × {len(COMBOS)}组合)")
print(f"{'='*100}")
print(f"{'组合':<30s} {'股票':>5s} {'笔数':>6s} {'WR%':>6s} {'RR':>8s} {'PF':>8s} {'P&L':>8s} {'用时':>6s}")
print(f"{'-'*30} {'-'*5} {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")
for r in results:
    print(f"{r['combo']:<30s} {r['stocks']:5d} {r['trades']:6d} "
          f"{r['wr']:6.1f} {r['rr']:8.2f}x {r['pf']:8.0f} "
          f"{r['pnl']:8.2f}% {r['time']:6.1f}s")

# Winners
best_rr = max(results, key=lambda r: r['rr'])
best_wr = max(results, key=lambda r: r['wr'])
best_pf = max(results, key=lambda r: r['pf'])
print(f"\n{'='*100}")
print(f"最佳RR:  {best_rr['combo']} → RR={best_rr['rr']:.2f}x WR={best_rr['wr']:.1f}%")
print(f"最佳WR:  {best_wr['combo']} → WR={best_wr['wr']:.1f}% RR={best_wr['rr']:.2f}x")
print(f"最佳PF:  {best_pf['combo']} → PF={best_pf['pf']:.0f} WR={best_pf['wr']:.1f}%")

# Save
out = OUTPUT_DIR / 'v45_combo_test_results.json'
json.dump(results, open(str(out), 'w'), indent=2)
print(f"\n结果已保存: {out}")
