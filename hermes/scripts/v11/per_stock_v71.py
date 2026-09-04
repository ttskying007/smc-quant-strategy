#!/usr/bin/env python3
"""
SMC V7.1 — Per-Stock + Time-Window + Multi-TF Analysis
======================================================
从detailed_trades_v63.json读取交易数据，分析:
  1. Per-stock: 每只股票的最优信号类型、WR、avgPnL
  2. Time-window: 不同月份/季度的信号表现
  3. FVG vs OB SL率对比
  4. Multi-TF: 周线趋势对日线入场的影响(需要周线数据)
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

TRADES_FILE = Path('/root/.hermes/smc_opt_v21/detailed_trades_v63.json')
KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

print("=" * 80)
print("  SMC V7.1 — Per-Stock + Time-Window + Multi-TF Analysis")
print("=" * 80)

data = json.loads(TRADES_FILE.read_bytes())
all_trades = data.get('all_trades', [])
stocks = data.get('stocks', {})

print(f"  Loaded {len(all_trades)} trades from {len(stocks)} stocks")

# ═══ 1. Per-Stock Analysis ═══
print(f"\n{'=' * 80}")
print(f"  1. PER-STOCK ANALYSIS")
print(f"{'=' * 80}")

stock_stats = {}
for sym, info in stocks.items():
    trades = info['trades']
    if len(trades) < 3:
        continue
    
    # Per-pattern breakdown
    patterns = defaultdict(list)
    for t in trades:
        patterns[t['pattern']].append(t)
    
    best_pattern = max(patterns.items(), key=lambda x: (len(x[1]) >= 3, sum(t['pnl_pct'] for t in x[1]) / len(x[1])))
    best_pat_name = best_pattern[0]
    best_pat_trades = best_pattern[1]
    best_pat_wr = sum(1 for t in best_pat_trades if t['won']) / len(best_pat_trades) * 100
    best_pat_avg = sum(t['pnl_pct'] for t in best_pat_trades) / len(best_pat_trades)
    
    all_wr = sum(1 for t in trades if t['won']) / len(trades) * 100
    all_avg = sum(t['pnl_pct'] for t in trades) / len(trades)
    all_cum = sum(t['pnl_pct'] for t in trades)
    
    # SL rate
    sl_count = sum(1 for t in trades if t['exit_reason'] == 'sl_hit')
    sl_rate = sl_count / len(trades) * 100
    
    stock_stats[sym] = {
        'total': len(trades),
        'wr': round(all_wr, 1),
        'avg': round(all_avg, 2),
        'cum': round(all_cum, 2),
        'sl_rate': round(sl_rate, 1),
        'best_pat': best_pat_name,
        'best_n': len(best_pat_trades),
        'best_wr': round(best_pat_wr, 1),
        'best_avg': round(best_pat_avg, 2),
    }

# Top/Bottom stocks
ranked = sorted(stock_stats.items(), key=lambda x: (x[1]['total'] >= 5, x[1]['cum']), reverse=True)
print(f"\n  Top 20 stocks (by cumPnL, ≥5 trades):")
print(f"  {'Symbol':<15s} {'n':>4s} {'WR':>7s} {'avg':>7s} {'cum':>8s} {'SL%':>5s} {'BestPat':<30s} {'bWR':>6s}")
print(f"  {'-'*90}")
for sym, s in ranked[:20]:
    print(f"  {sym:<15s} {s['total']:>4d} {s['wr']:>6.1f}% {s['avg']:>+6.2f}% {s['cum']:>+7.1f}% {s['sl_rate']:>4.1f}% {s['best_pat']:<30s} {s['best_wr']:>5.1f}%")

print(f"\n  Bottom 10 stocks (by cumPnL):")
for sym, s in ranked[-10:]:
    print(f"  {sym:<15s} {s['total']:>4d} {s['wr']:>6.1f}% {s['avg']:>+6.2f}% {s['cum']:>+7.1f}% {s['sl_rate']:>4.1f}% {s['best_pat']:<30s} {s['best_wr']:>5.1f}%")

# ═══ 2. Time-Window Analysis ═══
print(f"\n{'=' * 80}")
print(f"  2. TIME-WINDOW ANALYSIS (by month)")
print(f"{'=' * 80}")

monthly = defaultdict(lambda: {'trades': [], 'patterns': defaultdict(list)})
for t in all_trades:
    month = t.get('entry_date', '')[:6]  # YYYYMM
    if not month:
        continue
    monthly[month]['trades'].append(t)
    monthly[month]['patterns'][t['pattern']].append(t)

print(f"\n  {'Month':<8s} {'n':>5s} {'WR':>7s} {'avg':>7s} {'cum':>8s} {'TopPat':<30s} {'pWR':>6s}")
print(f"  {'-'*80}")
for month in sorted(monthly.keys()):
    m = monthly[month]
    trades = m['trades']
    n = len(trades)
    wr = sum(1 for t in trades if t['won']) / n * 100
    avg = sum(t['pnl_pct'] for t in trades) / n
    cum = sum(t['pnl_pct'] for t in trades)
    
    # Top pattern this month
    pats = m['patterns']
    if pats:
        top_pat = max(pats.items(), key=lambda x: len(x[1]))
        top_name = top_pat[0]
        top_wr = sum(1 for t in top_pat[1] if t['won']) / len(top_pat[1]) * 100
    else:
        top_name, top_wr = '-', 0
    
    sig = '★' if avg > 0 else ' '
    print(f"  {sig}{month:<7s} {n:>5d} {wr:>6.1f}% {avg:>+6.2f}% {cum:>+7.1f}% {top_name:<30s} {top_wr:>5.1f}%")

# Quarterly
print(f"\n  By Quarter:")
quarterly = defaultdict(list)
for t in all_trades:
    month = t.get('entry_date', '')[:6]
    if not month:
        continue
    q = f"{month[:4]}Q{(int(month[4:6])-1)//3+1}"
    quarterly[q].append(t)

for q in sorted(quarterly.keys()):
    trades = quarterly[q]
    n = len(trades)
    if n == 0:
        continue
    wr = sum(1 for t in trades if t['won']) / n * 100
    avg = sum(t['pnl_pct'] for t in trades) / n
    cum = sum(t['pnl_pct'] for t in trades)
    print(f"    {q}: n={n} WR={wr:.1f}% avg={avg:+.2f}% cum={cum:+.1f}%")

# ═══ 3. FVG vs OB SL Rate ═══
print(f"\n{'=' * 80}")
print(f"  3. FVG vs OB SL RATE COMPARISON")
print(f"{'=' * 80}")

fvg_trades = [t for t in all_trades if 'FVG' in t.get('entry_signal', '')]
ob_trades = [t for t in all_trades if 'OB' in t.get('entry_signal', '')]
pinbar_trades = [t for t in all_trades if 'Pinbar' in t.get('entry_signal', '')]

for name, trades in [('FVG_Bull', fvg_trades), ('OB_Bull', ob_trades), ('Pinbar_Bull', pinbar_trades)]:
    if not trades:
        continue
    n = len(trades)
    wr = sum(1 for t in trades if t['won']) / n * 100
    avg = sum(t['pnl_pct'] for t in trades) / n
    sl = sum(1 for t in trades if t['exit_reason'] == 'sl_hit')
    tp = sum(1 for t in trades if t['exit_reason'] == 'tp_hit')
    eod = sum(1 for t in trades if t['exit_reason'] == 'eod')
    sl_rate = sl / n * 100
    tp_rate = tp / n * 100
    avg_sl_loss = sum(t['pnl_pct'] for t in trades if not t['won']) / max(1, n - sum(1 for t in trades if t['won']))
    
    print(f"\n  {name}: n={n} WR={wr:.1f}% avg={avg:+.2f}%")
    print(f"    TP={tp}({tp_rate:.1f}%) SL={sl}({sl_rate:.1f}%) EOD={eod}")
    print(f"    Avg loss: {avg_sl_loss:+.2f}%")

# FVG breakdown by entry mode
fvg_imm = [t for t in fvg_trades if t.get('entry_mode') == 'immediate']
if fvg_imm:
    wr_i = sum(1 for t in fvg_imm if t['won']) / len(fvg_imm) * 100
    avg_i = sum(t['pnl_pct'] for t in fvg_imm) / len(fvg_imm)
    sl_i = sum(1 for t in fvg_imm if t['exit_reason'] == 'sl_hit')
    print(f"\n  FVG immediate: n={len(fvg_imm)} WR={wr_i:.1f}% avg={avg_i:+.2f}% SL={sl_i}({sl_i/len(fvg_imm)*100:.1f}%)")

# ═══ 4. Multi-TF: Weekly trend resonance ═══
print(f"\n{'=' * 80}")
print(f"  4. MULTI-TF RESONANCE (weekly trend + daily entry)")
print(f"{'=' * 80}")

# Quick weekly trend check using daily data
def weekly_trend_simple(daily):
    """简化周线趋势: 最近20日MA vs 50日MA"""
    if len(daily) < 50:
        return 'unknown'
    ma20 = sum(b['c'] for b in daily[-20:]) / 20
    ma50 = sum(b['c'] for b in daily[-50:]) / 50
    if ma20 > ma50 * 1.02:
        return 'bullish'
    elif ma20 < ma50 * 0.98:
        return 'bearish'
    return 'neutral'

# Load weekly trends for stocks with trades
tf_stats = defaultdict(lambda: {'trades': [], 'won': 0, 'pnl': 0})
for sym, info in stocks.items():
    # Load daily data
    fname = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ') + '_daily_300.json'
    fp = KLINE / fname
    if not fp.exists():
        continue
    try:
        daily = json.loads(fp.read_bytes())
    except:
        continue
    
    trend = weekly_trend_simple(daily)
    
    for t in info['trades']:
        tf_stats[trend]['trades'].append(t)
        if t['won']:
            tf_stats[trend]['won'] += 1
        tf_stats[trend]['pnl'] += t['pnl_pct']

print(f"\n  {'Trend':<12s} {'n':>5s} {'WR':>7s} {'avgPnL':>8s} {'cumPnL':>9s}")
print(f"  {'-'*50}")
for trend in ['bullish', 'neutral', 'bearish', 'unknown']:
    ts = tf_stats[trend]
    n = len(ts['trades'])
    if n == 0:
        continue
    wr = ts['won'] / n * 100
    avg = ts['pnl'] / n
    print(f"  {trend:<12s} {n:>5d} {wr:>6.1f}% {avg:>+7.2f}% {ts['pnl']:>+8.1f}%")

# ═══ 5. Signal combo time-window sensitivity ═══
print(f"\n{'=' * 80}")
print(f"  5. SIGNAL TIME-WINDOW SENSITIVITY (gap analysis)")
print(f"{'=' * 80}")

gap_stats = defaultdict(lambda: {'trades': [], 'won': 0})
for t in all_trades:
    gap = t.get('gap', 0)
    gap_stats[gap]['trades'].append(t)
    if t['won']:
        gap_stats[gap]['won'] += 1

print(f"\n  {'Gap':>5s} {'n':>5s} {'WR':>7s} {'avgPnL':>8s} {'bestPat':>30s}")
print(f"  {'-'*60}")
for gap in sorted(gap_stats.keys()):
    gs = gap_stats[gap]
    n = len(gs['trades'])
    if n < 3:
        continue
    wr = gs['won'] / n * 100
    avg = sum(t['pnl_pct'] for t in gs['trades']) / n
    pats = Counter(t['pattern'] for t in gs['trades'])
    top_pat = pats.most_common(1)[0][0] if pats else '-'
    print(f"  {gap:>5d} {n:>5d} {wr:>6.1f}% {avg:>+7.2f}% {top_pat:<30s}")

# ═══ Save results ═══
output = {
    'meta': {
        'version': 'V7.1 Per-Stock Analysis',
        'date': time.strftime('%Y-%m-%d %H:%M'),
        'total_stocks': len(stocks),
        'total_trades': len(all_trades),
    },
    'stock_stats': stock_stats,
    'monthly': {m: {
        'n': len(v['trades']),
        'wr': round(sum(1 for t in v['trades'] if t['won']) / len(v['trades']) * 100, 1),
        'avg': round(sum(t['pnl_pct'] for t in v['trades']) / len(v['trades']), 2),
        'cum': round(sum(t['pnl_pct'] for t in v['trades']), 2),
    } for m, v in monthly.items()},
    'tf_stats': {t: {
        'n': len(v['trades']),
        'wr': round(v['won'] / len(v['trades']) * 100, 1) if v['trades'] else 0,
        'avg': round(v['pnl'] / len(v['trades']), 2) if v['trades'] else 0,
        'cum': round(v['pnl'], 2),
    } for t, v in tf_stats.items()},
}

out_file = OUT / 'per_stock_v71.json'
json.dump(output, open(out_file, 'w'), ensure_ascii=False)
print(f"\n  Saved: {out_file} ({out_file.stat().st_size//1024}KB)")

print(f"\n{'=' * 80}")
print(f"  DONE — {len(stock_stats)} stocks analyzed")
print(f"{'=' * 80}")
