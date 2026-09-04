#!/usr/bin/env python3
"""V44引擎小规模回测 (200只股票)"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')

from pathlib import Path
from collections import Counter

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v44')
OUTPUT_DIR.mkdir(exist_ok=True)

# 选择200只活跃股票
symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_daily_300.json')])[:200]

print(f"Testing V44 on {len(symbols)} stocks...")

from v44_engine import (
    load_ohlcv, detect_market_phase, calc_stock_params,
    detect_all_signals_v11, detect_retest_entries,
    evaluate_signal_entry_v44, _evaluate_retest_entry,
    backtest_stock_v44
)

t_start = time.time()
all_trades, stock_results = [], []

for idx, sym in enumerate(symbols):
    ohlcv = load_ohlcv(sym)
    if not ohlcv or len(ohlcv) < 150:
        if (idx + 1) % 20 == 0:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} SKIP (no data)")
        continue

    result = backtest_stock_v44(ohlcv, sym)
    if result:
        p = result['perf']
        all_trades.extend(result['trades'])
        stock_results.append({'symbol': sym, **p})
        if (idx + 1) % 20 == 0 or p['n_trades'] > 0:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x PF={p['profit_factor']:.0f} "
                  f"retest={p['retest_entries']}")
    else:
        if (idx + 1) % 50 == 0:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} SKIP")

total_time = time.time() - t_start

if all_trades:
    n = len(all_trades)
    wins = sum(1 for t in all_trades if t['won'])
    wr = wins / n * 100
    wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    rr = sum(t['rr'] for t in all_trades) / n
    pnl = sum(t['pnl_pct'] for t in all_trades) / n
    holds = [t['hold_bars'] for t in all_trades]

    # TP vs Trailing
    tp_hits = [t for t in all_trades if t.get('exit_method') == 'tp_hit']
    trailing_trades = [t for t in all_trades if t.get('exit_method') == 'trailing']
    n_tp = len(tp_hits)
    n_trail = len(trailing_trades)
    wr_tp = sum(1 for t in tp_hits if t['won']) / n_tp * 100 if n_tp > 0 else 0
    wr_trail = sum(1 for t in trailing_trades if t['won']) / n_trail * 100 if n_trail > 0 else 0
    rr_tp = sum(t['rr'] for t in tp_hits) / n_tp if n_tp > 0 else 0
    rr_trail = sum(t['rr'] for t in trailing_trades) / n_trail if n_trail > 0 else 0

    # 方向分析
    bull_trades = [t for t in all_trades if t.get('direction') == 'bull']
    bear_trades = [t for t in all_trades if t.get('direction') == 'bear']
    n_bull = len(bull_trades)
    n_bear = len(bear_trades)
    wr_bull = sum(1 for t in bull_trades if t['won']) / n_bull * 100 if n_bull > 0 else 0
    wr_bear = sum(1 for t in bear_trades if t['won']) / n_bear * 100 if n_bear > 0 else 0
    rr_bull = sum(t['rr'] for t in bull_trades) / n_bull if n_bull > 0 else 0
    rr_bear = sum(t['rr'] for t in bear_trades) / n_bear if n_bear > 0 else 0

    # W/L不对称性
    avg_win = sum(t['pnl_pct'] for t in all_trades if t['won']) / wins if wins > 0 else 0
    avg_loss = abs(sum(t['pnl_pct'] for t in all_trades if not t['won'])) / (n - wins) if n > wins else 0

    # 早期退出问题
    early_exit = [t for t in all_trades if t['hold_bars'] <= 3 and t.get('tp_pct', 0) and t['tp_pct'] > 2.0]

    # 等级分析
    print("\n  === Grade Analysis ===")
    for grade in ['S', 'A', 'B', 'C', 'D']:
        grade_trades = [t for t in all_trades if t.get('quality_grade') == grade]
        ng = len(grade_trades)
        if ng > 0:
            wg = sum(1 for t in grade_trades if t['won']) / ng * 100
            rg = sum(t['rr'] for t in grade_trades) / ng
            print(f"    Grade {grade}: n={ng:4d} WR={wg:.1f}% RR={rg:.2f}x")

    print(f"\n  === V44 RESULTS ===")
    print(f"  Time: {total_time:.0f}s | Stocks: {len(stock_results)}/{len(symbols)}")
    print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
    print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars | Max: {max(holds)}")
    print(f"  Retest entries: {sum(s.get('retest_entries', 0) for s in stock_results)}")

    print(f"\n  TP vs Trailing:")
    print(f"    TP hit:  n={n_tp:5d} WR={wr_tp:.1f}% RR={rr_tp:.2f}x")
    print(f"    Trailing: n={n_trail:5d} WR={wr_trail:.1f}% RR={rr_trail:.2f}x")

    print(f"\n  Direction:")
    print(f"    Bull: n={n_bull:5d} WR={wr_bull:.1f}% RR={rr_bull:.2f}x")
    print(f"    Bear: n={n_bear:5d} WR={wr_bear:.1f}% RR={rr_bear:.2f}x")
    print(f"    W/L ratio: avgWin={avg_win:.3f}% avgLoss=-{avg_loss:.3f}% ratio={avg_win/avg_loss:.1f}x")
    print(f"    Early exit (hold<=3, tp>2%): {len(early_exit)} trades")

    # SL/TP类型分析
    sl_type_stats = Counter(t.get('sl_type', 'unknown') for t in all_trades)
    tp_type_stats = Counter(t.get('tp_type', 'none') for t in all_trades)
    grade_stats = Counter(t.get('quality_grade', 'D') for t in all_trades)

    print(f"\n  SL Type breakdown:")
    for st, cnt in sl_type_stats.most_common():
        st_trades = [t for t in all_trades if t.get('sl_type') == st]
        st_wr = sum(1 for t in st_trades if t['won']) / len(st_trades) * 100 if st_trades else 0
        st_avg_pnl = sum(t['pnl_pct'] for t in st_trades) / len(st_trades) if st_trades else 0
        print(f"    {st:20s}: {cnt:4d} ({cnt/n*100:5.1f}%) | WR={st_wr:.1f}% | avgP&L={st_avg_pnl:+.2f}%")

    print(f"\n  TP Type breakdown:")
    for tt, cnt in tp_type_stats.most_common():
        if tt in ('none',) or tt == 'None':
            tt_trades = [t for t in all_trades if t.get('tp_type') is None]
        else:
            tt_trades = [t for t in all_trades if t.get('tp_type') == tt]
        if not tt_trades:
            continue
        tt_wr = sum(1 for t in tt_trades if t['won']) / len(tt_trades) * 100
        tt_avg_rr = sum(t['rr'] for t in tt_trades) / len(tt_trades)
        print(f"    {str(tt):20s}: {len(tt_trades):4d} | WR={tt_wr:.1f}% | avgRR={tt_avg_rr:.2f}x")

    print(f"\n  Grade distribution: {dict(grade_stats)}")

    # 保存结果
    outpath = OUTPUT_DIR / 'v44_system_test.json'
    json.dump({
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'V44-TEST',
        'config': {
            'ob_v14': True, 'retest_entry': True,
            'dynamic_trailing': True, 'quality_grades': True,
            'bear_enhanced': True,
        },
        'summary': {
            'total_trades': n, 'tradable': len(stock_results),
            'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(pnl, 2),
            'tp_wr': round(wr_tp, 1), 'tp_rr': round(rr_tp, 2),
            'trail_wr': round(wr_trail, 1), 'trail_rr': round(rr_trail, 2),
            'bull_wr': round(wr_bull, 1), 'bull_rr': round(rr_bull, 2),
            'bear_wr': round(wr_bear, 1), 'bear_rr': round(rr_bear, 2),
            'avg_win_pct': round(avg_win, 3),
            'avg_loss_pct': round(avg_loss, 3),
            'wl_ratio': round(avg_win/avg_loss, 1) if avg_loss > 0 else 999,
            'sl_types': dict(sl_type_stats),
            'tp_types': dict(tp_type_stats),
            'grade_dist': dict(grade_stats),
            'early_exit_count': len(early_exit),
        },
        'stocks': stock_results,
        'all_trades': all_trades,
    }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\n  Saved: {outpath}")