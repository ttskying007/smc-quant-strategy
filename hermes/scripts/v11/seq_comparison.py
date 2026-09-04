#!/usr/bin/env python3
"""V19 Sequence Filter Comparison: baseline vs sequence-only entries"""
import json, sys, os, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v19 import detect_all_signals_v19, detect_signal_sequences
from v11.v19_backtest_engine import backtest_v19

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v19')
OUT_DIR.mkdir(exist_ok=True)

# Get all daily cache files
files = sorted(KLINE_DIR.glob('*_daily_300.json'))
print(f"Found {len(files)} kline cache files")

results = {'baseline': [], 'sequence': [], 'no_seq': 0}

t0 = time.time()
for i, fpath in enumerate(files):
    symbol_raw = fpath.stem.replace('_daily_300', '')
    symbol = symbol_raw.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
    
    try:
        ohlcv = json.loads(fpath.read_bytes())
        if len(ohlcv) < 50:
            continue
    except:
        continue
    
    # Detect signals
    signals, stats, swings, swings_dict = detect_all_signals_v19(ohlcv)
    
    # Baseline: no sequence filter
    trades_bl = backtest_v19(symbol, ohlcv, signals, swings_dict)
    
    # Sequence filter
    sequences = detect_signal_sequences(signals)
    if not sequences:
        results['no_seq'] += 1
        continue
    
    trades_seq, filt_stats = backtest_v19(symbol, ohlcv, signals, swings_dict, sequences=sequences)
    
    # Record baseline stats
    if trades_bl:
        wins_bl = sum(1 for t in trades_bl if t.pnl_pct > 0)
        results['baseline'].append({
            'symbol': symbol,
            'trades': len(trades_bl),
            'wr': wins_bl / len(trades_bl) * 100,
            'avg_pnl': sum(t.pnl_pct for t in trades_bl) / len(trades_bl),
            'total_pnl': sum(t.pnl_pct for t in trades_bl),
            'avg_hold': sum(t.hold_bars for t in trades_bl) / len(trades_bl),
        })
    
    # Record sequence stats
    if trades_seq:
        wins_seq = sum(1 for t in trades_seq if t.pnl_pct > 0)
        results['sequence'].append({
            'symbol': symbol,
            'trades': len(trades_seq),
            'wr': wins_seq / len(trades_seq) * 100,
            'avg_pnl': sum(t.pnl_pct for t in trades_seq) / len(trades_seq),
            'total_pnl': sum(t.pnl_pct for t in trades_seq),
            'avg_hold': sum(t.hold_bars for t in trades_seq) / len(trades_seq),
            'unfiltered': filt_stats['unfiltered_entries'],
            'filtered': filt_stats['filtered_entries'],
            'sequences': filt_stats['sequences_found'],
        })
    
    if (i+1) % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [{i+1}/{len(files)}] {elapsed:.0f}s | baseline_trades={sum(r['trades'] for r in results['baseline'])} | seq_trades={sum(r['trades'] for r in results['sequence'])}")

elapsed = time.time() - t0
print(f"\n=== Completed in {elapsed:.0f}s ===")

# Summary
baseline_trades = sum(r['trades'] for r in results['baseline'])
baseline_pnl = sum(r['total_pnl'] for r in results['baseline'])
baseline_wr = sum(r['wr'] * r['trades'] for r in results['baseline']) / baseline_trades if baseline_trades else 0

seq_trades = sum(r['trades'] for r in results['sequence'])
seq_pnl = sum(r['total_pnl'] for r in results['sequence'])
seq_wr = sum(r['wr'] * r['trades'] for r in results['sequence']) / seq_trades if seq_trades else 0

seq_stocks = len(results['sequence'])
avg_unfiltered = sum(r['unfiltered'] for r in results['sequence']) / seq_stocks if seq_stocks else 0
avg_filtered = sum(r['filtered'] for r in results['sequence']) / seq_stocks if seq_stocks else 0

print(f"""
{'='*60}
  V19 序列过滤对比 (Sequence Filter Comparison)
{'='*60}

  BASELINE (无过滤, 所有FVG/OB入场):
    股票数: {len(results['baseline'])}
    交易数: {baseline_trades}
    胜率WR: {baseline_wr:.1f}%
    平均盈亏: {sum(r['avg_pnl'] for r in results['baseline'])/len(results['baseline']):+.2f}%
    累计盈亏: {baseline_pnl:+.1f}%
    TP命中率: (需要逐笔统计)

  SEQUENCE (仅序列终端信号入场):
    股票数: {seq_stocks}
    无序列股票: {results['no_seq']}
    交易数: {seq_trades}
    胜率WR: {seq_wr:.1f}%
    平均盈亏: {sum(r['avg_pnl'] for r in results['sequence'])/seq_stocks:+.2f}%
    累计盈亏: {seq_pnl:+.1f}%
    平均未过滤入场: {avg_unfiltered:.1f}
    平均过滤后入场: {avg_filtered:.1f}
    过滤比例: {avg_filtered/avg_unfiltered*100:.1f}%

  WR变化: {baseline_wr:.1f}% → {seq_wr:.1f}% ({seq_wr-baseline_wr:+.1f}pp)
  交易减少: {baseline_trades} → {seq_trades} ({(1-seq_trades/baseline_trades)*100:.0f}%)

{'='*60}
""")

# Save
json.dump(results, open(OUT_DIR / 'v19_seq_comparison.json', 'w'), indent=2, ensure_ascii=False)
print(f"Saved to {OUT_DIR / 'v19_seq_comparison.json'}")
