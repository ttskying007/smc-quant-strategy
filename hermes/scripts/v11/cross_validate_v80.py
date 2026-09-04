#!/usr/bin/env python3
"""
SMC V8.0 — 全量交叉验证引擎
============================
目标: 找出每只股票/每个时段/每种信号的最优组合
输出矩阵:
  1. per_stock_best: 每只股票的最优信号类型
  2. per_month_best: 每月的全局最优信号
  3. per_stock_month: 每只股票×每月的信号表现
  4. signal_time_decay: 信号类型的时间衰减曲线

方法论: 
  - 将16个月数据分4个季度窗口
  - 每窗口内独立回测所有信号类型
  - 输出全矩阵: stock × quarter × signal × WR/avgPnL/n
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter
from itertools import product

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v21')
OUT_DIR.mkdir(exist_ok=True)

# ═══ Config ═══
MAX_WAIT = 3
SL_ATR_MUL = 1.5
TRAIL_ACT_ATR_MUL = 1.0
TRAIL_DIST_ATR_MUL = 0.7
MIN_HOLD = 2

# ═══ Time windows (overlapping quarters) ═══
# Each stock has ~300 bars covering ~16 months
# Split into: Q1=bars 0-75, Q2=bars 50-125, Q3=bars 100-175, Q4=bars 150-225, Q5=bars 200-275
WINDOWS = [
    ('2025Q1', 0, 75),
    ('2025Q2', 50, 125),
    ('2025Q3', 100, 175),
    ('2025Q4', 150, 225),
    ('2026Q1', 200, 275),
]

SIGNAL_TYPES = ['OB_Bull', 'BOS_Bull→FVG_Bull', 'CHOCH_Bull→FVG_Bull',
                'Sweep_SSL→FVG_Bull', 'EQL→FVG_Bull', 'MSS_Bull→FVG_Bull',
                'Sweep_SSL→Pinbar_Bull', 'EQL→Pinbar_Bull']

def load_ohlcv(symbol):
    for fmt in [symbol.replace('.','_')+'_daily_300.json', symbol+'_daily_300.json']:
        fp = KLINE / fmt
        if fp.exists():
            return json.loads(fp.read_bytes())
    return None

def calc_atr(daily, length=14):
    n = len(daily)
    if n < length+1: return daily[-1]['c'] * 0.03
    trs = []
    for i in range(max(1,n-length), n):
        h,l,pc = daily[i]['h'],daily[i]['l'],daily[i-1]['c']
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs)

def sim_trade(daily, entry_bar, zone_low, entry_mode):
    """单笔快速模拟"""
    n = len(daily)
    atr = calc_atr(daily, 14)
    avg_p = sum(b['c'] for b in daily[-20:]) / min(20, n)
    atr_pct = atr/avg_p if avg_p>0 else 0.03
    sl_pct = max(0.03, atr_pct*SL_ATR_MUL)
    trail_dist = max(0.015, min(0.04, atr_pct*TRAIL_DIST_ATR_MUL))
    act_pct = max(0.02, atr_pct*TRAIL_ACT_ATR_MUL)
    
    if entry_mode == 'retrace':
        retrace_bar = -1
        for k in range(entry_bar+1, min(entry_bar+MAX_WAIT+1, n)):
            if daily[k]['l'] <= zone_low:
                retrace_bar = k; break
        if retrace_bar < 0: return None
        actual_entry = retrace_bar; ep = zone_low
    else:
        actual_entry = entry_bar+1
        if actual_entry >= n-2: return None
        ep = daily[actual_entry]['o']
    
    sl = zone_low * (1-sl_pct)
    trail_act = ep * (1+act_pct)
    high_watermark = ep; trail_active = False
    prev_trail_sl = ep * (1-trail_dist)
    
    for k in range(actual_entry+1, min(actual_entry+25, n)):
        bk = daily[k]
        bars_held = k - actual_entry
        if bars_held > MIN_HOLD and trail_active and bk['l'] <= prev_trail_sl:
            return (prev_trail_sl-ep)/ep*100, True, k-actual_entry
        if bk['h'] > high_watermark:
            high_watermark = bk['h']
            if not trail_active and high_watermark >= trail_act:
                trail_active = True
        if trail_active and bars_held > MIN_HOLD:
            prev_trail_sl = high_watermark*(1-trail_dist)
        if bk['l'] <= sl:
            return (sl-ep)/ep*100, False, k-actual_entry
    
    exit_k = min(actual_entry+20, n-1)
    return (daily[exit_k]['c']-ep)/ep*100, daily[exit_k]['c']>ep, exit_k-actual_entry

# ═══ MAIN ═══
print("="*80)
print("  SMC V8.0 — 全量交叉验证: Stock×Quarter×Signal")
print("="*80)

# Load all pick data
picks_data = json.loads((OUT_DIR/'LD_picks_v6.json').read_bytes())
all_picks = picks_data.get('picks', [])
picks_by_sym = defaultdict(list)
for p in all_picks:
    sym = p['symbol'].replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    picks_by_sym[sym].append(p)

stock_count = len(picks_by_sym)
print(f"  {stock_count} stocks with picks, {len(all_picks)} total picks")
print(f"  {len(WINDOWS)} time windows, {len(SIGNAL_TYPES)} signal types")
print(f"  Total tests: {stock_count}×{len(WINDOWS)}×{len(SIGNAL_TYPES)} ≈ {stock_count*len(WINDOWS)*len(SIGNAL_TYPES):,}")

# Results storage
per_stock_signal = defaultdict(lambda: defaultdict(list))  # stock→signal→[(pnl, won, hold)]
per_window_signal = defaultdict(lambda: defaultdict(list))  # window→signal→[(pnl, won, hold)]
per_stock_window = defaultdict(lambda: defaultdict(list))   # stock→window→[(pnl, won, hold, signal)]

t0 = time.time()
processed = 0; total_trades = 0

for sym, picks in picks_by_sym.items():
    daily = load_ohlcv(sym)
    if daily is None or len(daily) < 100: continue
    
    n = len(daily)
    
    # Group picks by signal type and bar
    signals_by_type = defaultdict(list)
    for p in picks:
        sig = p.get('signal', '?')
        zone_bar = p.get('zone_bar', 0)
        zone_low = p.get('zone_low', p.get('entry_price', 0))
        entry_mode = p.get('entry_mode', 'immediate')
        if zone_low > 0 and zone_bar < n:
            signals_by_type[sig].append((zone_bar, zone_low, entry_mode))
    
    for sig_type, sig_list in signals_by_type.items():
        for zone_bar, zone_low, entry_mode in sig_list:
            # Determine which windows this signal falls into
            for wname, wstart, wend in WINDOWS:
                if wstart <= zone_bar <= wend:
                    # Only test if we have enough bars after entry
                    result = sim_trade(daily, zone_bar, zone_low, entry_mode)
                    if result:
                        pnl, won, hold = result
                        per_stock_signal[sym][sig_type].append((pnl, won, hold))
                        per_window_signal[wname][sig_type].append((pnl, won, hold))
                        per_stock_window[sym][wname].append((pnl, won, hold, sig_type))
                        total_trades += 1
    
    processed += 1
    if processed % 500 == 0:
        elapsed = time.time()-t0
        print(f"  [{processed}/{stock_count}] {elapsed:.0f}s trades={total_trades:,}")

# ═══ Aggregate Results ═══
def agg(pnls):
    if not pnls: return {'n':0,'wr':0,'avg':0,'cum':0}
    n = len(pnls)
    wins = sum(1 for p in pnls if p[1])
    return {'n':n, 'wr':round(wins/n*100,1), 'avg':round(sum(p[0] for p in pnls)/n,2), 'cum':round(sum(p[0] for p in pnls),2)}

# 1. Per-stock best signal
stock_best = {}
for sym, sigs in per_stock_signal.items():
    best_sig, best_score = None, -999
    for sig, pnls in sigs.items():
        a = agg(pnls)
        if a['n'] >= 2 and a['wr'] >= 50:
            score = a['avg'] * a['wr']/100 * min(a['n'], 10)
            if score > best_score:
                best_score = score; best_sig = sig
    if best_sig:
        a = agg(sigs[best_sig])
        stock_best[sym] = {'best_signal': best_sig, **a}

# 2. Per-window best signal
window_best = {}
for wname, sigs in per_window_signal.items():
    best_sig, best_score = None, -999
    for sig, pnls in sigs.items():
        a = agg(pnls)
        if a['n'] >= 5:
            score = a['avg'] * a['wr']/100 * a['n']
            if score > best_score:
                best_score = score; best_sig = sig
    if best_sig:
        a = agg(sigs[best_sig])
        window_best[wname] = {'best_signal': best_sig, **a}

# 3. Per-window per-signal full matrix
window_signal_matrix = {}
for wname, sigs in per_window_signal.items():
    window_signal_matrix[wname] = {sig: agg(pnls) for sig, pnls in sigs.items()}

# 4. Signal time decay (average performance trend across windows)
signal_time_trend = defaultdict(list)
for wname in [w[0] for w in WINDOWS]:
    ws = window_signal_matrix.get(wname, {})
    for sig in SIGNAL_TYPES:
        a = ws.get(sig, {'n':0,'wr':0,'avg':0})
        signal_time_trend[sig].append((wname, a['n'], a['wr'], a['avg']))

# ═══ Output ═══
output = {
    'meta': {'version': 'V8.0 Cross-Validation', 'date': time.strftime('%Y-%m-%d %H:%M'),
             'stocks': stock_count, 'total_trades': total_trades, 
             'elapsed': round(time.time()-t0),
             'config': {'mw': MAX_WAIT, 'sl_atr': SL_ATR_MUL, 'act_atr': TRAIL_ACT_ATR_MUL, 'dist_atr': TRAIL_DIST_ATR_MUL}},
    'stock_best': stock_best,  # {sym: {best_signal, n, wr, avg, cum}}
    'window_best': window_best,  # {window: {best_signal, n, wr, avg, cum}}
    'window_signal_matrix': window_signal_matrix,  # {window: {signal: {n, wr, avg, cum}}}
    'signal_time_trend': {sig: [(w,n,wr,avg) for w,n,wr,avg in trend] for sig, trend in signal_time_trend.items()},
}

out_file = OUT_DIR / 'cross_validation_v80.json'
json.dump(output, open(out_file, 'w'), ensure_ascii=False)
print(f"\n  Output: {out_file} ({out_file.stat().st_size//1024}KB)")

# ═══ Summary Report ═══
print(f"\n{'='*80}")
print(f"  PER-WINDOW BEST SIGNALS")
print(f"{'='*80}")
for wname, wb in sorted(window_best.items()):
    print(f"  {wname}: {wb['best_signal']:<30s} n={wb['n']:>5d} WR={wb['wr']:>5.1f}% avg={wb['avg']:>+6.2f}%")

print(f"\n{'='*80}")
print(f"  SIGNAL TIME TREND (avgPnL% across quarters)")
print(f"{'='*80}")
print(f"  {'Signal':<32s} {'Q1':>7s} {'Q2':>7s} {'Q3':>7s} {'Q4':>7s} {'Q5':>7s} {'Trend':>8s}")
for sig, trend in signal_time_trend.items():
    vals = [f"{t[3]:+6.2f}%" if t[1]>=3 else "    N/A" for t in trend]
    first_valid = next((t[3] for t in trend if t[1]>=3), 0)
    last_valid = next((t[3] for t in reversed(trend) if t[1]>=3), 0)
    trend_str = "↗改善" if last_valid>first_valid else ("↘衰减" if last_valid<first_valid else "→稳定")
    print(f"  {sig:<32s} {vals[0]:>7s} {vals[1]:>7s} {vals[2]:>7s} {vals[3]:>7s} {vals[4]:>7s} {trend_str:>8s}")

# Top stocks by best signal
print(f"\n{'='*80}")
print(f"  TOP STOCKS BY BEST SIGNAL (top 30)")
print(f"{'='*80}")
ranked = sorted(stock_best.items(), key=lambda x: -(x[1]['avg']*x[1]['wr']/100*x[1]['n']))
for sym, sb in ranked[:30]:
    print(f"  {sym:<12s} {sb['best_signal']:<30s} n={sb['n']:>3d} WR={sb['wr']:>5.1f}% avg={sb['avg']:>+6.2f}%")

# Signal distribution across stocks
print(f"\n{'='*80}")
print(f"  PER-STOCK SIGNAL DISTRIBUTION")
print(f"{'='*80}")
sig_dist = Counter(sb['best_signal'] for sb in stock_best.values())
for sig, cnt in sig_dist.most_common():
    print(f"  {sig}: {cnt} stocks ({cnt/len(stock_best)*100:.1f}%)")

elapsed = time.time()-t0
print(f"\n{'='*80}")
print(f"  V8.0 Complete — {elapsed:.0f}s — {processed} stocks × {len(WINDOWS)} windows × {len(SIGNAL_TYPES)} signals")
print(f"  Total trades simulated: {total_trades:,}")
print(f"{'='*80}")
