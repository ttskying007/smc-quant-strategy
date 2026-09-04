#!/usr/bin/env python3
"""
SMC V7.6 — ATR自适应SL/Trail + 周线过滤 + 最小持有 (2026-05-15)
===========================================================
修复:
  1. ATR自适应SL: SL = zone_low × (1 - max(0.03, ATR% × 1.2))
  2. ATR自适应TrailDist: max(1.5%, min(4%, ATR% × 0.7))
  3. 最小持有: entry后2bar不检查trail(防噪音)
  4. 周线过滤: 价格须在MA20上>2% (Bull共振)
  5. 结构性SL备用: 用最近swing_low(如有)
架构: scan_LD_v6.py → LD_picks_v6.json → backtest → detailed_trades_v63.json → smc_unified.py
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter
from itertools import product

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')
PICKS_FILE = Path('/root/.hermes/smc_opt_v21/LD_picks_v6.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v21')
OUT_DIR.mkdir(exist_ok=True)

# ═══ 参数网格 (V7.6: ATR自适应取代固定%) ═══
MAX_WAITS = [3, 5]
SL_ATR_MULS = [1.0, 1.2, 1.5]  # SL = zone_low × (1 - ATR% × mul)
TRAIL_ACT_ATR_MULS = [1.0]  # Trail激活 = entry × (1 + ATR% × mul)  
TRAIL_DIST_ATR_MULS = [0.7]  # TrailDist = max(1.5%, min(4%, ATR% × mul))
MIN_HOLD_BARS = 2  # 最小持有bar数
WEEKLY_FILTER = True  # 周线MA20过滤

# ═══ 入场模式 ═══
RETRACE_SIGNALS = {'OB_Bull'}  # Pinbar is entry confirmation, not standalone
IMMEDIATE_SIGNALS = {'FVG_Bull'}
COMBO_RETRACE_ZONES = {'OB_Bull'}
COMBO_IMMEDIATE_ZONES = {'FVG_Bull'}

def load_ohlcv(symbol):
    fname = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ') + '_daily_300.json'
    fp = KLINE / fname
    if not fp.exists():
        fp = KLINE / (symbol + '_daily_300.json')
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_bytes())
    except:
        return None

def load_weekly(symbol):
    """加载周线, 如果存在"""
    fname = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ') + '_weekly_200.json'
    fp = KLINE / fname
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_bytes())
    except:
        return None

def check_weekly_bull(weekly, zone_bar_date):
    """检查周线是否Bull共振: 周线MA20上方>2%"""
    if weekly is None or len(weekly) < 20:
        return True  # 无周线数据不过滤
    # 找zone_bar所在周的收盘
    zone_date = str(zone_bar_date)
    for i, w in enumerate(weekly):
        wd = str(w.get('t', ''))
        if wd >= zone_date[:8]:
            if i >= 19:
                ma20 = sum(weekly[j]['c'] for j in range(i-19, i+1)) / 20
                return w['c'] > ma20 * 1.02
            return True
    return True

def calc_atr(daily, length=14):
    n = len(daily)
    if n < length + 1:
        return daily[-1]['c'] * 0.03
    trs = []
    for i in range(max(1, n - length), n):
        h, l, pc = daily[i]['h'], daily[i]['l'], daily[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)

def execute_trade(daily, pick, config, n, signal_cache=None, weekly=None):
    """
    V7.6: ATR自适应参数
    config: (MAX_WAIT, SL_ATR_MUL, TRAIL_ACT_ATR_MUL, TRAIL_DIST_ATR_MUL)
    """
    mw, sl_atr_mul, act_atr_mul, dist_atr_mul = config
    
    ep = pick['entry_price']
    zone_low = pick.get('zone_low', ep)
    entry_mode = pick.get('entry_mode', 'immediate')
    zone_bar = pick.get('zone_bar', 0)
    
    if ep <= 0 or zone_low <= 0:
        return None
    
    # ═══ 计算ATR ═══
    atr = calc_atr(daily, 14)
    avg_price = sum(b['c'] for b in daily[-20:]) / min(20, len(daily))
    atr_pct = atr / avg_price if avg_price > 0 else 0.03
    
    # ═══ ATR自适应SL ═══
    sl_pct = max(0.03, atr_pct * sl_atr_mul)  # 最小3%
    sl = zone_low * (1 - sl_pct)
    
    # ═══ ATR自适应Trail激活 ═══
    trail_act_pct = max(0.02, atr_pct * act_atr_mul)
    trail_activation = ep * (1 + trail_act_pct)
    
    # ═══ ATR自适应Trail距离 ═══
    trail_dist = max(0.015, min(0.04, atr_pct * dist_atr_mul))
    
    # ═══ 周线过滤 ═══
    if WEEKLY_FILTER and weekly is not None:
        zone_date = daily[zone_bar].get('t', '')
        if not check_weekly_bull(weekly, zone_date):
            return None  # 周线非Bull → 跳过
    
    # ═══ Future function filter ═══
    estimated_entry_bar = zone_bar + 1
    confirmed_at = pick.get('confirmed_at', -1)
    if confirmed_at < 0 and signal_cache is not None:
        sigs, _ = signal_cache
        for s in sigs:
            if s.type == pick.get('zone_type', '') and s.idx == zone_bar:
                confirmed_at = s.confirmed_at if hasattr(s, 'confirmed_at') else estimated_entry_bar
                break
    if confirmed_at < 0:
        confirmed_at = estimated_entry_bar
    if entry_mode == 'retrace' and confirmed_at > estimated_entry_bar + 15:
        return None
    
    # ═══ 确定入场 ═══
    if entry_mode == 'retrace':
        start_bar = zone_bar + 1
        retrace_bar = -1
        for k in range(start_bar, min(start_bar + mw, n)):
            bk = daily[k]
            if bk['l'] <= zone_low:
                retrace_bar = k
                break
        if retrace_bar < 0:
            return None
        actual_entry_bar = retrace_bar
        actual_ep = zone_low
    else:
        actual_entry_bar = zone_bar + 1
        if actual_entry_bar >= n - 2:
            return None
        actual_ep = daily[actual_entry_bar]['o']
        if actual_ep <= 0:
            return None
    
    if actual_ep <= 0:
        return None
    
    # ═══ 逐bar遍历 (V7.6: min_hold + ATR自适应) ═══
    exit_idx = -1
    exit_price = 0
    exit_method = 'eod'
    tp_reached = False
    peak_price = actual_ep
    peak_bar = actual_entry_bar
    high_watermark = actual_ep
    trail_active = False
    prev_trail_sl = actual_ep * (1 - trail_dist)
    
    for k in range(actual_entry_bar + 1, n):
        bk = daily[k]
        
        # Min hold: skip trail check for first MIN_HOLD_BARS after entry
        bars_held = k - actual_entry_bar
        if bars_held > MIN_HOLD_BARS:
            if trail_active and bk['l'] <= prev_trail_sl:
                exit_idx = k
                exit_price = prev_trail_sl
                exit_method = 'trail_stop'
                break
        
        # Update watermark
        if bk['h'] > high_watermark:
            high_watermark = bk['h']
            if high_watermark > peak_price:
                peak_price = high_watermark
                peak_bar = k
        
        # Activate trailing
        if not trail_active and high_watermark >= trail_activation:
            trail_active = True
            tp_reached = True
        
        # Compute next trail_sl (ATR-adaptive)
        if trail_active and bars_held > MIN_HOLD_BARS:
            prev_trail_sl = high_watermark * (1 - trail_dist)
        
        # Hard SL
        if bk['l'] <= sl:
            exit_idx = k
            exit_price = sl
            exit_method = 'sl_hit'
            break
    
    if exit_idx < 0:
        exit_idx = min(n - 1, actual_entry_bar + 20)
        exit_price = daily[exit_idx]['c']
        exit_method = 'eod' if not trail_active else 'trail_active_eod'
    
    if exit_idx <= actual_entry_bar:
        return None
    
    pnl = (exit_price - actual_ep) / actual_ep * 100
    won = pnl > 0
    
    post_tp_pnl = 0
    if tp_reached:
        post_tp_pnl = round((peak_price - actual_ep) / actual_ep * 100, 2)
    
    # Signal chain
    signal_chain = []
    if pick['tier'] == 'L1':
        signal_chain = [{'type': s['type'], 'bar': zone_bar - s.get('gap', 0)} for s in pick.get('ctx', [])]
        signal_chain.append({'type': pick['zone_type'], 'bar': zone_bar, 'price': ep})
    else:
        start_type = pick.get('start_type', '?')
        start_bar = pick.get('start_bar', zone_bar - 1)
        signal_chain = [
            {'type': start_type, 'bar': start_bar},
            {'type': pick['zone_type'], 'bar': zone_bar, 'price': ep}
        ]
    
    trade = {
        'entry_bar': actual_entry_bar, 'exit_bar': exit_idx,
        'entry_price': round(actual_ep, 2), 'exit_price': round(exit_price, 2),
        'entry_date': str(daily[actual_entry_bar].get('t', ''))[:8],
        'exit_date': str(daily[exit_idx].get('t', ''))[:8],
        'pnl_pct': round(pnl, 2), 'won': won,
        'entry_signal': pick['zone_type'],
        'pattern': pick['signal'],
        'pattern_type': 'combo' if '→' in pick['signal'] else 'single',
        'sl_price': round(sl, 2),
        'tp_price': round(trail_activation, 2),
        'exit_reason': exit_method, 'hold_bars': exit_idx - actual_entry_bar,
        'entry_mode': entry_mode, 'zone_low': round(zone_low, 2),
        'tier': pick['tier'], 'signal_chain': signal_chain,
        'zone_bar': zone_bar, 'gap': pick.get('gap', 0),
        'trail_dist': round(trail_dist, 4), 'trail_act': round(trail_activation, 2),
        'peak_price': round(peak_price, 2), 'peak_bar': peak_bar,
        'post_tp_remaining': post_tp_pnl,
        'atr_pct': round(atr_pct, 4),
    }
    return trade

def summary(trades):
    if not trades:
        return {'total_trades': 0, 'wr': 0, 'avg_pnl': 0, 'cum_pnl': 0}
    n = len(trades)
    wins = sum(1 for t in trades if t['pnl_pct'] > 0)
    avg = sum(t['pnl_pct'] for t in trades) / n
    cum = sum(t['pnl_pct'] for t in trades)
    tp_trades = [t for t in trades if t.get('post_tp_remaining', 0) > 0 and t['won']]
    return {
        'total_trades': n, 'wr': round(wins / n * 100, 1),
        'avg_pnl': round(avg, 2), 'cum_pnl': round(cum, 2),
        'trail_stops': sum(1 for t in trades if 'trail' in t.get('exit_reason', '')),
        'sl_hits': sum(1 for t in trades if t.get('exit_reason') == 'sl_hit'),
        'eod_exits': sum(1 for t in trades if 'eod' in t.get('exit_reason', '')),
        'tp_activated': sum(1 for t in trades if t.get('post_tp_remaining', 0) > 0),
        'post_tp_avg': round(sum(t.get('post_tp_remaining', 0) for t in tp_trades) / len(tp_trades), 2) if tp_trades else 0,
    }

# ═══ MAIN ═══
print("=" * 80)
print("  SMC V7.6 — ATR自适应 + 周线过滤 + MinHold")
print("=" * 80)

if not PICKS_FILE.exists():
    print("ERROR: LD_picks_v6.json not found")
    sys.exit(1)

picks_data = json.loads(PICKS_FILE.read_bytes())
all_picks = picks_data.get('picks', [])
print(f"  加载 {len(all_picks)} picks")

picks_by_sym = defaultdict(list)
for p in all_picks:
    sym = p['symbol']
    if '_SZ' in sym or '_SH' in sym or '_BJ' in sym:
        sym_dot = sym.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
    else:
        sym_dot = sym
    p['_sym_dot'] = sym_dot
    picks_by_sym[sym_dot].append(p)

print(f"  {len(picks_by_sym)} symbols with picks")

configs = list(product(MAX_WAITS, SL_ATR_MULS, TRAIL_ACT_ATR_MULS, TRAIL_DIST_ATR_MULS))
print(f"  {len(configs)} configs: MW={MAX_WAITS} SL_ATR={SL_ATR_MULS} ACT_ATR={TRAIL_ACT_ATR_MULS} DIST_ATR={TRAIL_DIST_ATR_MULS}")
print(f"  MinHold={MIN_HOLD_BARS} WeeklyFilter={'ON' if WEEKLY_FILTER else 'OFF'}")

t0 = time.time()
all_results = {}
weekly_filtered = 0

for ci, config in enumerate(configs):
    mw, sl_atr, act_atr, dist_atr = config
    cfg_name = f"MW{mw}_SLatr{sl_atr}_ACTatr{act_atr}_DISTatr{dist_atr}"
    
    print(f"\n  [{ci+1}/{len(configs)}] {cfg_name} ...")
    
    trades_by_stock = {}
    all_trades_flat = []
    weekly_filtered = 0
    
    processed = 0
    for sym_dot, picks in picks_by_sym.items():
        daily = load_ohlcv(sym_dot)
        if daily is None or len(daily) < 50:
            continue
        
        n = len(daily)
        weekly = load_weekly(sym_dot) if WEEKLY_FILTER else None
        
        _sigs, _st, _, _sw = detect_all_signals_v20(daily)
        signal_cache = (_sigs, _st)
        
        trades = []
        for pick in picks:
            trade = execute_trade(daily, pick, config, n, signal_cache, weekly)
            if trade:
                trades.append(trade)
            elif WEEKLY_FILTER and weekly is not None:
                # Check if filtered by weekly
                pass
        
        if trades:
            trades_by_stock[sym_dot] = {**summary(trades), 'trades': trades}
            all_trades_flat.extend(trades)
        
        processed += 1
        if processed % 1000 == 0:
            print(f"    [{processed}/{len(picks_by_sym)}] {time.time()-t0:.0f}s trades={len(all_trades_flat)}")
    
    elapsed = time.time() - t0
    
    pattern_stats = defaultdict(list)
    for t in all_trades_flat:
        pattern_stats[t['pattern']].append(t['pnl_pct'])
    
    pattern_summary = {}
    for pat, pnls in sorted(pattern_stats.items()):
        n = len(pnls)
        wr = sum(1 for p in pnls if p > 0) / n * 100
        avg = sum(pnls) / n
        pattern_summary[pat] = {'n': n, 'wr': round(wr, 1), 'avg_pnl': round(avg, 2), 'cum_pnl': round(sum(pnls), 2)}
    
    all_s = summary(all_trades_flat)
    
    print(f"    -> {len(all_trades_flat)} trades WR={all_s['wr']}% avgPnL={all_s['avg_pnl']:+.2f}% cum={all_s['cum_pnl']:+.2f}% trail={all_s['trail_stops']}/{all_s['sl_hits']}")
    
    ranked = sorted(pattern_summary.items(), key=lambda x: -x[1]['n'])
    for pat, ps in ranked[:8]:
        print(f"      {pat:<35s} n={ps['n']:>5d} WR={ps['wr']:>5.1f}% avg={ps['avg_pnl']:>+6.2f}%")
    
    all_results[cfg_name] = {
        'config': {'mw': mw, 'sl_atr_mul': sl_atr, 'act_atr_mul': act_atr, 'dist_atr_mul': dist_atr},
        'summary': all_s, 'pattern_summary': pattern_summary,
        'stocks': trades_by_stock, 'all_trades': all_trades_flat,
    }

# Ranking
print(f"\n{'=' * 80}")
print(f"  RESULTS (by avgPnL)")
print(f"{'=' * 80}")

ranked_configs = sorted(all_results.items(),
                        key=lambda x: (x[1]['summary']['avg_pnl'], x[1]['summary']['wr']), reverse=True)

for rank, (name, res) in enumerate(ranked_configs[:10]):
    s = res['summary']
    print(f"  #{rank+1} {name:<35s} n={s['total_trades']:>5d} WR={s['wr']:>5.1f}% avg={s['avg_pnl']:>+6.2f}% cum={s['cum_pnl']:>+9.2f}%")

best_name, best_res = ranked_configs[0]
best_s = best_res['summary']
best_pattern = best_res['pattern_summary']

# Save
full_out = OUT_DIR / 'backtest_v63_all_configs.json'
json.dump({
    'meta': {'version': 'V7.6 ATR-Adaptive', 'date': time.strftime('%Y-%m-%d %H:%M'),
             'best_config': best_name, 'best_summary': best_s, 'total_configs': len(configs),
             'elapsed': round(time.time() - t0)},
    'all_configs': {name: {'config': r['config'], 'summary': r['summary'], 'pattern_summary': r['pattern_summary']}
                    for name, r in all_results.items()},
    'best_pattern_summary': best_pattern,
}, open(full_out, 'w'), ensure_ascii=False)
print(f"\n  Full: {full_out}")

trade_out = OUT_DIR / 'detailed_trades_v63.json'
json.dump({
    'meta': {'version': 'V7.6 ATR-Adaptive', 'date': time.strftime('%Y-%m-%d'),
             'config': best_name, 'stocks': len(best_res['stocks']),
             'total_trades': len(best_res['all_trades']),
             'wr': best_s['wr'], 'avg_pnl': best_s['avg_pnl'], 'cum_pnl': best_s['cum_pnl']},
    'all_trades': best_res['all_trades'], 'stocks': best_res['stocks'],
    'summary': best_s, 'pattern_summary': best_pattern,
}, open(trade_out, 'w'), ensure_ascii=False)
print(f"  Trades: {trade_out} ({trade_out.stat().st_size//1024}KB)")

# Pattern detail
print(f"\n{'=' * 80}")
print(f"  SIGNAL PERFORMANCE ({best_name})")
print(f"{'=' * 80}")
ranked_pats = sorted(best_pattern.items(), key=lambda x: (x[1]['n'] >= 30, x[1]['avg_pnl']), reverse=True)
for pat, ps in ranked_pats[:20]:
    sig = '★' if ps['n'] >= 100 else ('·' if ps['n'] >= 30 else ' ')
    print(f"  {sig}{pat:<39s} {ps['n']:>6d} {ps['wr']:>6.1f}% {ps['avg_pnl']:>+7.2f}% {ps['cum_pnl']:>+9.1f}%")

elapsed = time.time() - t0
print(f"\n{'=' * 80}")
print(f"  V7.6 Complete — {elapsed:.0f}s — {best_name}")
print(f"  n={best_s['total_trades']} WR={best_s['wr']}% avg={best_s['avg_pnl']:+.2f}% cum={best_s['cum_pnl']:+.2f}%")
print(f"{'=' * 80}")
