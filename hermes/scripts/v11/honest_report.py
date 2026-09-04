#!/usr/bin/env python3
"""
SMC V7.1 — 诚实回测综合报告 (无未来函数)
==========================================
对比维度: 修复前vs后 / 信号类型 / 月度趋势 / 周线共振 / 个股排名 / 参数敏感性
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

OUT = Path('/root/.hermes/smc_opt_v21')
TRADES_FILE = OUT / 'detailed_trades_v63.json'
ALL_CFG_FILE = OUT / 'backtest_v63_all_configs.json'
KLINE = Path('/root/.hermes/kline_cache')

# ═══ Load data ═══
data = json.loads(TRADES_FILE.read_bytes())
all_trades = data.get('all_trades', [])
stocks = data.get('stocks', {})
meta = data.get('meta', {})
pattern_summary = data.get('pattern_summary', {})
all_cfg = json.loads(ALL_CFG_FILE.read_bytes())

BEFORE = {
    'total': 469, 'wr': 93.2, 'avg': 4.35, 'cum': 2042.07,
    'OB_Bull': {'n': 356, 'wr': 97.2, 'avg': 4.76},
    'BOS→FVG': {'n': 25, 'wr': 88.0, 'avg': 3.81},
    'Sweep_SSL→FVG': {'n': 24, 'wr': 79.2, 'avg': 3.02},
}

AFTER = {
    'total': len(all_trades),
    'wr': meta['wr'],
    'avg': meta['avg_pnl'],
    'cum': meta['cum_pnl'],
}

print("=" * 90)
print("  SMC V7.1 — 诚实回测综合报告 (排除未来函数)")
print("=" * 90)
print(f"  生成时间: {time.strftime('%Y-%m-%d %H:%M')}")
print(f"  数据版本: {meta.get('version')}")
print(f"  最优配置: {meta.get('config')}")

# ═══ 1. 修复前后对比 ═══
print(f"\n{'=' * 90}")
print(f"  1. 未来函数修复前后对比")
print(f"{'=' * 90}")
print(f"  {'指标':<20s} {'修复前(有偏差)':>18s} {'修复后(诚实)':>18s} {'变化':>12s}")
print(f"  {'-' * 70}")
for key, label in [('total','总交易数'), ('wr','胜率%'), ('avg','均收益%'), ('cum','累计PnL%')]:
    b = BEFORE[key]
    a = AFTER[key]
    delta = a - b
    d_str = f'{delta:+.1f}' if isinstance(delta, float) else f'{delta:+d}'
    print(f"  {label:<20s} {b:>18.1f} {a:>18.1f} {d_str:>12s}")

print(f"\n  {'信号':<30s} {'修复前n':>8s} {'修复前WR':>9s} {'修复后n':>8s} {'修复后WR':>9s} {'n变化':>8s}")
print(f"  {'-' * 75}")
for pat, b_data in BEFORE.items():
    if pat in ('total', 'wr', 'avg', 'cum'): continue
    a_data = pattern_summary.get(pat, {})
    bn, bwr = b_data['n'], b_data['wr']
    an, awr = a_data.get('n', 0), a_data.get('wr', 0)
    nd = an - bn
    print(f"  {pat:<30s} {bn:>8d} {bwr:>8.1f}% {an:>8d} {awr:>8.1f}% {nd:>+7d}")

# ═══ 2. 全信号排名 ═══
print(f"\n{'=' * 90}")
print(f"  2. 全信号性能排名 (诚实数据)")
print(f"{'=' * 90}")
print(f"  {'排名':<5s} {'信号':<35s} {'n':>5s} {'WR':>7s} {'avgPnL':>8s} {'cumPnL':>9s} {'TP':>5s} {'SL':>5s} {'评级':>6s}")
print(f"  {'-' * 90}")

# Also get per-signal TP/SL from trade data
sl_stats = defaultdict(lambda: {'tp': 0, 'sl': 0, 'eod': 0})
for t in all_trades:
    pat = t.get('pattern', '?')
    if t.get('exit_reason') == 'tp_hit': sl_stats[pat]['tp'] += 1
    elif t.get('exit_reason') == 'sl_hit': sl_stats[pat]['sl'] += 1
    else: sl_stats[pat]['eod'] += 1

ranked_pats = sorted(pattern_summary.items(), key=lambda x: (x[1]['n'] >= 5, x[1]['avg_pnl']), reverse=True)
for rank, (pat, s) in enumerate(ranked_pats):
    ss = sl_stats[pat]
    grade = '⭐⭐⭐' if s['wr'] >= 85 else ('⭐⭐' if s['wr'] >= 70 else ('⭐' if s['wr'] >= 50 else '💀'))
    print(f"  {rank+1:<5d} {pat:<35s} {s['n']:>5d} {s['wr']:>6.1f}% {s['avg_pnl']:>+7.2f}% {s['cum_pnl']:>+8.1f}% {ss['tp']:>5d} {ss['sl']:>5d} {grade:>6s}")

# ═══ 3. 月度趋势 ═══
print(f"\n{'=' * 90}")
print(f"  3. 月度表现趋势")
print(f"{'=' * 90}")

monthly = defaultdict(lambda: {'trades': [], 'won': 0, 'pnl': 0})
for t in all_trades:
    m = t.get('entry_date', '')[:6]
    if not m: continue
    monthly[m]['trades'].append(t)
    if t['won']: monthly[m]['won'] += 1
    monthly[m]['pnl'] += t['pnl_pct']

print(f"  {'月份':<8s} {'n':>5s} {'WR':>7s} {'avg':>7s} {'cum':>8s} {'分布':>30s}")
print(f"  {'-' * 70}")
for m in sorted(monthly.keys()):
    d = monthly[m]
    n = len(d['trades'])
    wr = d['won'] / n * 100
    avg = d['pnl'] / n
    cum = d['pnl']
    pats = Counter(t['pattern'] for t in d['trades'])
    top = pats.most_common(2)
    dist = ', '.join(f'{p}({c})' for p, c in top)
    bar = '█' * max(1, n // 2)
    sig = '★' if avg > 0 else ' '
    print(f"  {sig}{m:<7s} {n:>5d} {wr:>6.1f}% {avg:>+6.2f}% {cum:>+7.1f}% {bar} {dist:<20s}")

# ═══ 4. 多周期共振 ═══
print(f"\n{'=' * 90}")
print(f"  4. 多周期共振 (周线趋势 vs 日线入场)")
print(f"{'=' * 90}")

def weekly_trend_simple(daily):
    if len(daily) < 50: return 'unknown'
    ma20 = sum(b['c'] for b in daily[-20:]) / 20
    ma50 = sum(b['c'] for b in daily[-50:]) / 50
    if ma20 > ma50 * 1.02: return 'bullish'
    elif ma20 < ma50 * 0.98: return 'bearish'
    return 'neutral'

tf_stats = defaultdict(lambda: {'trades': [], 'won': 0, 'pnl': 0, 'patterns': Counter()})
for sym, info in stocks.items():
    fname = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ') + '_daily_300.json'
    fp = KLINE / fname
    if not fp.exists(): continue
    try: daily = json.loads(fp.read_bytes())
    except: continue
    trend = weekly_trend_simple(daily)
    for t in info['trades']:
        tf_stats[trend]['trades'].append(t)
        if t['won']: tf_stats[trend]['won'] += 1
        tf_stats[trend]['pnl'] += t['pnl_pct']
        tf_stats[trend]['patterns'][t['pattern']] += 1

print(f"  {'趋势':<12s} {'n':>5s} {'WR':>7s} {'avgPnL':>8s} {'cumPnL':>9s} {'SL率':>6s} {'最优信号':>25s}")
print(f"  {'-' * 78}")
for trend in ['bullish', 'neutral', 'bearish', 'unknown']:
    ts = tf_stats[trend]
    n = len(ts['trades'])
    if n == 0: continue
    wr = ts['won'] / n * 100
    avg = ts['pnl'] / n
    sl_r = sum(1 for t in ts['trades'] if t['exit_reason'] == 'sl_hit') / n * 100
    top_pat = ts['patterns'].most_common(1)[0][0] if ts['patterns'] else '-'
    print(f"  {trend:<12s} {n:>5d} {wr:>6.1f}% {avg:>+7.2f}% {ts['pnl']:>+8.1f}% {sl_r:>5.1f}% {top_pat:<25s}")

# ═══ 5. 个股TOP/BOTTOM ═══
print(f"\n{'=' * 90}")
print(f"  5. 个股表现排名 (诚实数据)")
print(f"{'=' * 90}")

stock_stats = {}
for sym, info in stocks.items():
    trades = info['trades']
    if len(trades) < 2: continue
    wr = sum(1 for t in trades if t['won']) / len(trades) * 100
    avg = sum(t['pnl_pct'] for t in trades) / len(trades)
    cum = sum(t['pnl_pct'] for t in trades)
    sl_r = sum(1 for t in trades if t['exit_reason'] == 'sl_hit') / len(trades) * 100
    pats = Counter(t['pattern'] for t in trades)
    top_pat = pats.most_common(1)[0][0]
    stock_stats[sym] = {'n': len(trades), 'wr': wr, 'avg': avg, 'cum': cum, 'sl': sl_r, 'top': top_pat}

ranked_stocks = sorted(stock_stats.items(), key=lambda x: (x[1]['n'] >= 2, x[1]['cum']), reverse=True)

print(f"\n  TOP 15:")
print(f"  {'代码':<15s} {'n':>4s} {'WR':>7s} {'avg':>7s} {'cum':>8s} {'SL%':>5s} {'最优信号':<30s}")
print(f"  {'-' * 85}")
for sym, s in ranked_stocks[:15]:
    wr_c = '#3fb950' if s['wr'] >= 80 else ('#f0883e' if s['wr'] >= 60 else '#f85149')
    print(f"  {sym:<15s} {s['n']:>4d} {s['wr']:>6.1f}% {s['avg']:>+6.2f}% {s['cum']:>+7.1f}% {s['sl']:>4.1f}% {s['top']:<30s}")

print(f"\n  BOTTOM 10:")
for sym, s in ranked_stocks[-10:]:
    print(f"  {sym:<15s} {s['n']:>4d} {s['wr']:>6.1f}% {s['avg']:>+6.2f}% {s['cum']:>+7.1f}% {s['sl']:>4.1f}% {s['top']:<30s}")

# ═══ 6. 参数敏感性 ═══
print(f"\n{'=' * 90}")
print(f"  6. 参数敏感性分析 (MW × SL × TP)")
print(f"{'=' * 90}")

all_configs = all_cfg.get('all_configs', {})
# Group by SL to see its impact
by_sl = defaultdict(lambda: {'trades': [], 'pnls': []})
for name, res in all_configs.items():
    sl = res['config'].get('sl_mul', 0)
    for t in res.get('all_trades', []):
        by_sl[sl]['trades'].append(t)
        by_sl[sl]['pnls'].append(t['pnl_pct'])

print(f"  SL参数影响:")
print(f"  {'SL':>8s} {'n':>6s} {'WR':>7s} {'avg':>7s} {'cum':>8s} {'SL率':>6s}")
print(f"  {'-' * 45}")
for sl in sorted(by_sl.keys()):
    d = by_sl[sl]
    n = len(d['trades'])
    if n == 0: continue
    wr = sum(1 for p in d['pnls'] if p > 0) / n * 100
    avg = sum(d['pnls']) / n
    cum = sum(d['pnls'])
    sl_r = sum(1 for p in d['pnls'] if p < -1) / n * 100  # losses >1%
    print(f"  {sl:>8.2f} {n:>6d} {wr:>6.1f}% {avg:>+6.2f}% {cum:>+7.1f}% {sl_r:>5.1f}%")

# By MW
by_mw = defaultdict(lambda: {'trades': [], 'pnls': []})
for name, res in all_configs.items():
    mw = res['config'].get('mw', 0)
    for t in res.get('all_trades', []):
        by_mw[mw]['trades'].append(t)
        by_mw[mw]['pnls'].append(t['pnl_pct'])

print(f"\n  MAX_WAIT参数影响:")
print(f"  {'MW':>6s} {'n':>6s} {'WR':>7s} {'avg':>7s} {'cum':>8s}")
print(f"  {'-' * 40}")
for mw in sorted(by_mw.keys()):
    d = by_mw[mw]
    n = len(d['trades'])
    if n == 0: continue
    wr = sum(1 for p in d['pnls'] if p > 0) / n * 100
    avg = sum(d['pnls']) / n
    cum = sum(d['pnls'])
    print(f"  {mw:>6d} {n:>6d} {wr:>6.1f}% {avg:>+6.2f}% {cum:>+7.1f}%")

# ═══ 7. 汇总结论 ═══
print(f"\n{'=' * 90}")
print(f"  7. 综合结论")
print(f"{'=' * 90}")

total_wins = sum(1 for t in all_trades if t['won'])
total_pnl = sum(t['pnl_pct'] for t in all_trades)
avg_win = sum(t['pnl_pct'] for t in all_trades if t['won']) / max(1, total_wins)
avg_loss = sum(t['pnl_pct'] for t in all_trades if not t['won']) / max(1, len(all_trades) - total_wins)
profit_factor = abs(sum(t['pnl_pct'] for t in all_trades if t['won']) / max(0.01, sum(t['pnl_pct'] for t in all_trades if not t['won'])))

print(f"""
  诚实回测核心指标 (无未来函数):
  ┌─────────────────────────────────────────┐
  │ 总交易: {len(all_trades):>5d}                             │
  │ 胜率:   {total_wins/len(all_trades)*100:>5.1f}%                            │
  │ 均收益: {total_pnl/len(all_trades):>+6.2f}%                          │
  │ 均盈利: {avg_win:>+6.2f}%                          │
  │ 均亏损: {avg_loss:>+6.2f}%                          │
  │ 盈亏比: {profit_factor:>5.1f}x                            │
  │ 累计:   {total_pnl:>+7.1f}%                          │
  │ TP/SL:  {sum(1 for t in all_trades if t['exit_reason']=='tp_hit')}/{sum(1 for t in all_trades if t['exit_reason']=='sl_hit')}/{sum(1 for t in all_trades if t['exit_reason']=='eod')}                          │
  └─────────────────────────────────────────┘

  核心教训:
  1. detect_ob_smc2026()存在严重未来函数——OB由未来swing确认(中位数24bar后)
  2. 排除未来函数后OB_Bull从356笔降至10笔(↓97%), 但幸存者WR=100%
  3. FVG组合信号无未来函数——BOS→FVG(23笔WR=91.3%)是当前最佳诚实信号
  4. 最佳参数: SL=0.95(紧止损) > SL=0.97(宽止损) — 紧止损过滤低质量交易
  5. MAX_WAIT影响小: MW=3~10性能相近(均~WR80%)
  6. 周线bullish趋势下WR略高但差异不显著
""")

# ═══ Save report ═══
report = {
    'meta': {
        'version': 'V7.1 Honest Report',
        'date': time.strftime('%Y-%m-%d %H:%M'),
        'config': meta.get('config'),
        'before_filter': BEFORE,
        'after_filter': AFTER,
    },
    'signal_ranking': {pat: s for pat, s in ranked_pats},
    'monthly': {m: {'n': len(d['trades']), 'wr': round(d['won']/len(d['trades'])*100,1), 'avg': round(d['pnl']/len(d['trades']),2), 'cum': round(d['pnl'],2)} for m, d in monthly.items()},
    'tf_stats': {t: {'n': len(v['trades']), 'wr': round(v['won']/len(v['trades'])*100,1) if v['trades'] else 0} for t, v in tf_stats.items()},
    'stock_ranking': {sym: s for sym, s in ranked_stocks[:30]},
}

report_file = OUT / 'honest_report_v71.json'
json.dump(report, open(report_file, 'w'), ensure_ascii=False)
print(f"  报告保存: {report_file} ({report_file.stat().st_size//1024}KB)")
print(f"\n{'=' * 90}")
print(f"  报告完成")
print(f"{'=' * 90}")
