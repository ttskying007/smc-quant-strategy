#!/usr/bin/env python3
"""V20.1 全量回测 + 详细报告"""
import json, sys, time, math
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, detect_signal_sequences, _calc_atr
from v11.v19_backtest_engine import backtest_v19

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v20')
OUT_DIR.mkdir(exist_ok=True)

files = sorted(KLINE_DIR.glob('*_daily_300.json'))
print(f'Files: {len(files)}')

# Results accumulators
baseline = {
    'stocks': 0, 'trades': 0, 'wins': 0, 'losses': 0,
    'total_pnl': 0.0, 'total_hold': 0, 'total_rr': 0.0,
    'exit_methods': defaultdict(int),
    'pnl_dist': [], 'hold_dist': [],
    'per_stock': [],
}

sequence = {
    'stocks': 0, 'trades': 0, 'wins': 0, 'losses': 0,
    'total_pnl': 0.0, 'total_hold': 0, 'total_rr': 0.0,
    'exit_methods': defaultdict(int),
    'pnl_dist': [], 'hold_dist': [],
    'seq_stocks': 0, 'total_seqs': 0,
    'per_stock': [],
}

signal_stats = defaultdict(int)

t0 = time.time()
for i, fp in enumerate(files):
    sym = fp.stem.replace('_daily_300', '')
    try:
        ohlcv = json.loads(fp.read_bytes())
        if len(ohlcv) < 50: continue
    except: continue
    
    # Detect V20.1 signals
    sigs, st, _, swings_dict = detect_all_signals_v20(ohlcv)
    for t, c in st['type_counts'].items():
        signal_stats[t] += c
    
    # Baseline backtest (all FVG_Bull + OB_Bull)
    trades_bl = backtest_v19(sym, ohlcv, sigs, swings_dict)
    if not isinstance(trades_bl, list):
        trades_bl = trades_bl[0]  # Handle tuple return from sequence-filtered mode
    
    if trades_bl:
        baseline['stocks'] += 1
        baseline['trades'] += len(trades_bl)
        stock_pnl = 0
        for t in trades_bl:
            pnl = t.pnl_pct
            baseline['total_pnl'] += pnl
            baseline['total_hold'] += t.hold_bars
            stock_pnl += pnl
            if pnl > 0:
                baseline['wins'] += 1
            else:
                baseline['losses'] += 1
            baseline['exit_methods'][t.exit_method] += 1
            baseline['pnl_dist'].append(pnl)
            baseline['hold_dist'].append(t.hold_bars)
            # RR: positive pnl vs negative pnl ratio
            if pnl > 0:
                baseline['total_rr'] += pnl
            else:
                baseline['total_rr'] += abs(pnl)
        baseline['per_stock'].append({
            'symbol': sym, 'trades': len(trades_bl),
            'pnl_sum': round(stock_pnl, 2),
            'wr': round(sum(1 for t in trades_bl if t.pnl_pct > 0) / len(trades_bl) * 100, 1),
        })
    
    # Sequence detection
    atr = _calc_atr(ohlcv, 14)
    avg_p = sum(b['c'] for b in ohlcv[-50:])/min(50, len(ohlcv))
    atr_pct = atr/avg_p if avg_p > 0 else 0.02
    seqs = detect_signal_sequences(sigs, atr_pct=atr_pct)
    
    if not seqs:
        continue
    
    sequence['seq_stocks'] += 1
    sequence['total_seqs'] += len(seqs)
    
    # Sequence-filtered backtest
    trades_seq, filt = backtest_v19(sym, ohlcv, sigs, swings_dict, sequences=seqs)
    
    if trades_seq:
        sequence['stocks'] += 1
        sequence['trades'] += len(trades_seq)
        stock_pnl = 0
        for t in trades_seq:
            pnl = t.pnl_pct
            sequence['total_pnl'] += pnl
            sequence['total_hold'] += t.hold_bars
            stock_pnl += pnl
            if pnl > 0:
                sequence['wins'] += 1
            else:
                sequence['losses'] += 1
            sequence['exit_methods'][t.exit_method] += 1
            sequence['pnl_dist'].append(pnl)
            sequence['hold_dist'].append(t.hold_bars)
            if pnl > 0:
                sequence['total_rr'] += pnl
            else:
                sequence['total_rr'] += abs(pnl)
        sequence['per_stock'].append({
            'symbol': sym, 'trades': len(trades_seq),
            'pnl_sum': round(stock_pnl, 2),
            'wr': round(sum(1 for t in trades_seq if t.pnl_pct > 0) / len(trades_seq) * 100, 1),
            'seqs': len(seqs),
        })
    
    if (i+1) % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [{i+1}/{len(files)}] {elapsed:.0f}s bl={baseline['trades']} seq={sequence['trades']}")

elapsed = time.time() - t0

# Compute final stats
def compute_stats(data):
    if not data['trades']:
        return {}
    wins = data['wins']
    total = data['trades']
    wr = wins / total * 100
    avg_pnl = data['total_pnl'] / total
    avg_hold = data['total_hold'] / total
    
    # Avg win / avg loss
    win_pnls = [p for p in data['pnl_dist'] if p > 0]
    loss_pnls = [abs(p) for p in data['pnl_dist'] if p <= 0]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
    rr = avg_win / avg_loss if avg_loss > 0 else 999
    
    # Profit Factor
    gross_profit = sum(win_pnls)
    gross_loss = sum(loss_pnls)
    pf = gross_profit / gross_loss if gross_loss > 0 else 999
    
    # PnL distribution
    pnl_buckets = {'<-2%': 0, '-2~-1%': 0, '-1~0%': 0, '0~1%': 0, '1~2%': 0, '2~3%': 0, '3~5%': 0, '>5%': 0}
    for p in data['pnl_dist']:
        if p < -2: pnl_buckets['<-2%'] += 1
        elif p < -1: pnl_buckets['-2~-1%'] += 1
        elif p < 0: pnl_buckets['-1~0%'] += 1
        elif p < 1: pnl_buckets['0~1%'] += 1
        elif p < 2: pnl_buckets['1~2%'] += 1
        elif p < 3: pnl_buckets['2~3%'] += 1
        elif p <= 5: pnl_buckets['3~5%'] += 1
        else: pnl_buckets['>5%'] += 1
    
    # Hold distribution
    hold_buckets = {'1': 0, '2': 0, '3': 0, '4-5': 0, '6-10': 0, '>10': 0}
    for h in data['hold_dist']:
        if h <= 1: hold_buckets['1'] += 1
        elif h == 2: hold_buckets['2'] += 1
        elif h == 3: hold_buckets['3'] += 1
        elif h <= 5: hold_buckets['4-5'] += 1
        elif h <= 10: hold_buckets['6-10'] += 1
        else: hold_buckets['>10'] += 1
    
    return {
        'trades': total, 'stocks': data['stocks'],
        'wr': round(wr, 1), 'avg_pnl': round(avg_pnl, 2),
        'total_pnl': round(data['total_pnl'], 1),
        'avg_rr': round(rr, 1), 'pf': round(pf, 1),
        'avg_win': round(avg_win, 2), 'avg_loss': round(avg_loss, 2),
        'avg_hold': round(avg_hold, 1),
        'exit_methods': dict(data['exit_methods']),
        'pnl_buckets': pnl_buckets,
        'hold_buckets': hold_buckets,
    }

bl_stats = compute_stats(baseline)
sq_stats = compute_stats(sequence)

# Top/bottom stocks
bl_top = sorted(baseline['per_stock'], key=lambda x: x['pnl_sum'], reverse=True)[:20]
sq_top = sorted(sequence['per_stock'], key=lambda x: x['pnl_sum'], reverse=True)[:20]

# Signal count summary
sig_summary = {k: v for k, v in sorted(signal_stats.items())}

report = {
    'engine': 'V20.1',
    'runtime_sec': round(elapsed, 1),
    'signal_summary': sig_summary,
    'baseline': bl_stats,
    'sequence': sq_stats,
    'comparison': {
        'wr_delta': round(sq_stats.get('wr', 0) - bl_stats.get('wr', 0), 1),
        'pnl_delta': round(sq_stats.get('avg_pnl', 0) - bl_stats.get('avg_pnl', 0), 2),
        'trade_reduction': round((1 - sq_stats.get('trades', 0) / max(bl_stats.get('trades', 1), 1)) * 100, 0),
    },
    'baseline_top20': bl_top,
    'sequence_top20': sq_top,
    'sequence_stats': {
        'seq_stocks': sequence['seq_stocks'],
        'total_seqs': sequence['total_seqs'],
    },
}

# Print report
print(f"\n{'='*70}")
print(f"  V20.1 全量回测报告 ({elapsed:.0f}s)")
print(f"{'='*70}")

print(f"\n  信号总览:")
print(f"    CHOCH: {sig_summary.get('CHOCH_Bull',0)+sig_summary.get('CHOCH_Bear',0):,d}")
print(f"    BOS:   {sig_summary.get('BOS_Bull',0)+sig_summary.get('BOS_Bear',0):,d}")
print(f"    Sweep: {sig_summary.get('Sweep_BSL',0)+sig_summary.get('Sweep_SSL',0):,d}")
print(f"    FVG:   {sig_summary.get('FVG_Bull',0)+sig_summary.get('FVG_Bear',0):,d}")
print(f"    OB:    {sig_summary.get('OB_Bull',0)+sig_summary.get('OB_Bear',0):,d}")
print(f"    MSS:   {sig_summary.get('MSS_Bull',0)+sig_summary.get('MSS_Bear',0):,d}")
print(f"    总信号: {sum(sig_summary.values()):,d}")

print(f"\n  ═══════════ 回测对比 ═══════════")
print(f"  {'指标':20s} {'Baseline':>12s} {'Sequence':>12s} {'变化':>10s}")
print(f"  {'─'*20} {'─'*12} {'─'*12} {'─'*10}")
for label, key, fmt, unit in [
    ('交易股票', 'stocks', 'd', ''), ('交易笔数', 'trades', 'd', ''),
    ('胜率 WR', 'wr', '.1f', '%'), ('平均盈亏', 'avg_pnl', '.2f', '%'),
    ('盈亏比 RR', 'avg_rr', '.1f', ''), ('Profit Factor', 'pf', '.1f', ''),
    ('平均盈利', 'avg_win', '.2f', '%'), ('平均亏损', 'avg_loss', '.2f', '%'),
    ('平均持仓(bar)', 'avg_hold', '.1f', ''),
]:
    bv = bl_stats.get(key, 0)
    sv = sq_stats.get(key, 0)
    if key in ('stocks', 'trades'):
        delta = f'{sv - bv:+d}'
    elif isinstance(bv, (int, float)):
        delta = f'{sv - bv:+.1f}'
    else:
        delta = '--'
    bv_str = f'{bv:{fmt}}{unit}' if isinstance(bv, (int, float)) else str(bv)
    sv_str = f'{sv:{fmt}}{unit}' if isinstance(sv, (int, float)) else str(sv)
    print(f'  {label:20s} {bv_str:>12s} {sv_str:>12s} {delta:>10s}')

print(f"\n  退出方式:")
for em in ['tp_hit', 'sl_hit', 'eod']:
    bc = bl_stats['exit_methods'].get(em, 0)
    sc = sq_stats['exit_methods'].get(em, 0)
    bpct = bc/bl_stats['trades']*100 if bl_stats['trades'] else 0
    spct = sc/sq_stats['trades']*100 if sq_stats['trades'] else 0
    print(f"    {em}: baseline={bc}({bpct:.0f}%)  sequence={sc}({spct:.0f}%)")

print(f"\n  PnL分布:")
for bkt in ['<-2%', '-2~-1%', '-1~0%', '0~1%', '1~2%', '2~3%', '3~5%', '>5%']:
    bc = bl_stats['pnl_buckets'][bkt]
    sc = sq_stats['pnl_buckets'][bkt]
    print(f"    {bkt:8s}: bl={bc:>5d}({bc/bl_stats['trades']*100:4.1f}%)  seq={sc:>5d}({sc/sq_stats['trades']*100:4.1f}%)")

print(f"\n  持仓分布:")
for bkt in ['1', '2', '3', '4-5', '6-10', '>10']:
    bc = bl_stats['hold_buckets'][bkt]
    sc = sq_stats['hold_buckets'][bkt]
    print(f"    {bkt:>5s}bar: bl={bc:>5d}({bc/bl_stats['trades']*100:4.1f}%)  seq={sc:>5d}({sc/sq_stats['trades']*100:4.1f}%)")

print(f"\n  序列统计:")
print(f"    有序列股票: {sequence['seq_stocks']} ({sequence['seq_stocks']/4800*100:.1f}%)")
print(f"    总序列数: {sequence['total_seqs']:,d}")
print(f"    序列→交易转化: {sq_stats['trades']}/{sequence['total_seqs']} = {sq_stats['trades']/max(sequence['total_seqs'],1)*100:.0f}%")

print(f"\n  Top 10 Baseline:")
for r in bl_top[:10]:
    print(f"    {r['symbol']:12s} {r['trades']:>3d}笔 WR={r['wr']:>5.1f}% PnL={r['pnl_sum']:>+8.1f}%")

print(f"\n  Top 10 Sequence:")
for r in sq_top[:10]:
    print(f"    {r['symbol']:12s} {r['trades']:>3d}笔 WR={r['wr']:>5.1f}% PnL={r['pnl_sum']:>+8.1f}% seqs={r.get('seqs',0)}")

# Save
json.dump(report, open(OUT_DIR / 'v20_backtest_report.json', 'w'), indent=2, ensure_ascii=False)
print(f"\nReport saved to {OUT_DIR / 'v20_backtest_report.json'}")
