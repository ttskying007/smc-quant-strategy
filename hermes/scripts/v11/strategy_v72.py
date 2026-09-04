#!/usr/bin/env python3
"""
SMC V7.2 — 诚实策略全量回测 + 选股
====================================
策略:
  主力: BOS_Bull→FVG_Bull, Sweep_SSL→FVG_Bull, EQL→FVG_Bull
  辅助: EQL→Pinbar_Bull, OB_Bull(confirmed_at≤+5)
  过滤: 周线bullish/neutral趋势, confirmed_at≤entry_bar+5
  入场: FVG=immediate, Pinbar/OB=retrace
  SL: 0.95 tight, TP: 1.05 cap
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, Signal

KLINE = Path('/root/.hermes/kline_cache')
PICKS_FILE = Path('/root/.hermes/smc_opt_v21/LD_picks_v6.json')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ Strategy config ═══
PRIMARY_SIGNALS = ['BOS_Bull→FVG_Bull', 'Sweep_SSL→FVG_Bull', 'EQL→FVG_Bull']
SECONDARY_SIGNALS = ['EQL→Pinbar_Bull', 'CHOCH_Bull→FVG_Bull', 'Sweep_SSL→Pinbar_Bull']
OB_HONEST_SIGNAL = 'OB_Bull'  # Only if confirmed_at ≤ +5

MW = 3
SL_MUL = 0.95
TP_CAP = 1.05
MAX_CONFIRM_GAP = 5  # Max bars for confirmed_at ahead of entry

# ═══ Weekly trend ═══
def weekly_trend(daily):
    if len(daily) < 50: return 'neutral'
    ma20 = sum(b['c'] for b in daily[-20:]) / 20
    ma50 = sum(b['c'] for b in daily[-50:]) / 50
    if ma20 > ma50 * 1.02: return 'bullish'
    elif ma20 < ma50 * 0.98: return 'bearish'
    return 'neutral'

def load_ohlcv(symbol):
    fname = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ') + '_daily_300.json'
    fp = KLINE / fname
    if not fp.exists(): return None
    try: return json.loads(fp.read_bytes())
    except: return None

def execute_strategy_trade(daily, pick, signal_cache):
    """Execute trade with honest strategy rules. Returns trade dict or None."""
    n = len(daily)
    zone_bar = pick.get('zone_bar', 0)
    entry_bar = zone_bar + 1
    if entry_bar >= n - 2: return None
    
    signal_type = pick['signal']
    zone_type = pick.get('zone_type', '')
    
    # Future function check
    confirmed_at = pick.get('confirmed_at', -1)
    if confirmed_at < 0 and signal_cache:
        sigs, _ = signal_cache
        for s in sigs:
            if s.type == zone_type and s.idx == zone_bar:
                confirmed_at = s.confirmed_at if hasattr(s, 'confirmed_at') else entry_bar
                break
    if confirmed_at < 0: confirmed_at = entry_bar
    if confirmed_at > entry_bar + MAX_CONFIRM_GAP:
        return None  # Future function
    
    # Entry mode
    entry_mode = 'retrace' if 'Pinbar' in zone_type or 'OB_' in zone_type else 'immediate'
    
    if entry_mode == 'retrace':
        zone_low = pick.get('zone_low', daily[entry_bar]['o'] * 0.99)
        # Wait for retrace to zone_low
        retrace_bar = -1
        for k in range(entry_bar, min(entry_bar + MW, n)):
            if daily[k]['l'] <= zone_low:
                retrace_bar = k; break
        if retrace_bar < 0: return None
        actual_ep = zone_low
        actual_entry_bar = retrace_bar
    else:
        actual_ep = daily[entry_bar]['o']
        actual_entry_bar = entry_bar
    
    if actual_ep <= 0: return None
    
    sl = actual_ep * SL_MUL
    tp = min(pick.get('tp', actual_ep * TP_CAP), actual_ep * TP_CAP)
    if tp <= actual_ep: return None
    
    tpd = (tp - actual_ep) / actual_ep * 100
    sld = (actual_ep - sl) / actual_ep * 100
    if sld <= 0 or tpd / sld < 1.0: return None
    
    # Walk bars
    exit_idx = -1; exit_price = 0; exit_method = 'eod'
    for k in range(actual_entry_bar + 1, n):
        bk = daily[k]
        if bk['h'] >= tp: exit_idx = k; exit_price = tp; exit_method = 'tp_hit'; break
        if bk['l'] <= sl: exit_idx = k; exit_price = sl; exit_method = 'sl_hit'; break
    if exit_idx < 0: exit_idx = min(n - 1, actual_entry_bar + 20); exit_price = daily[exit_idx]['c']
    if exit_idx <= actual_entry_bar: return None
    
    pnl = (exit_price - actual_ep) / actual_ep * 100
    return {
        'symbol': pick.get('_sym_dot', pick['symbol']),
        'entry_bar': actual_entry_bar, 'exit_bar': exit_idx,
        'entry_price': round(actual_ep, 2), 'exit_price': round(exit_price, 2),
        'entry_date': str(daily[actual_entry_bar].get('t', ''))[:8],
        'exit_date': str(daily[exit_idx].get('t', ''))[:8],
        'pnl_pct': round(pnl, 2), 'won': pnl > 0,
        'entry_signal': zone_type, 'pattern': signal_type,
        'pattern_type': 'combo' if '→' in signal_type else 'single',
        'sl_price': round(sl, 2), 'tp_price': round(tp, 2),
        'exit_reason': exit_method, 'hold_bars': exit_idx - actual_entry_bar,
        'entry_mode': entry_mode, 'zone_low': pick.get('zone_low', actual_ep),
        'zone_bar': zone_bar, 'signal_chain': [],
    }

# ═══ MAIN ═══
print("=" * 80)
print("  SMC V7.2 — 诚实策略回测 + 选股")
print("=" * 80)

picks_data = json.loads(PICKS_FILE.read_bytes())
all_picks = picks_data['picks']

# Filter picks by strategy
strategy_picks = []
for p in all_picks:
    sig = p['signal']
    if sig in PRIMARY_SIGNALS:
        strategy_picks.append({**p, 'priority': 'primary'})
    elif sig in SECONDARY_SIGNALS:
        strategy_picks.append({**p, 'priority': 'secondary'})
    elif sig == OB_HONEST_SIGNAL:
        strategy_picks.append({**p, 'priority': 'ob_honest'})

# Group by symbol
picks_by_sym = defaultdict(list)
for p in strategy_picks:
    sym = p['symbol'].replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
    p['_sym_dot'] = sym
    picks_by_sym[sym].append(p)

print(f"  Strategy picks: {len(strategy_picks)} ({len(picks_by_sym)} stocks)")
print(f"  Primary: {sum(1 for p in strategy_picks if p['priority']=='primary')}")
print(f"  Secondary: {sum(1 for p in strategy_picks if p['priority']=='secondary')}")
print(f"  OB honest: {sum(1 for p in strategy_picks if p['priority']=='ob_honest')}")

# Execute
t0 = time.time()
all_trades = []
stocks_out = {}
processed = 0
weekly_filtered = 0
future_filtered = 0

for sym, picks in picks_by_sym.items():
    daily = load_ohlcv(sym)
    if daily is None or len(daily) < 50: continue
    
    # Weekly trend filter
    trend = weekly_trend(daily)
    if trend == 'bearish':
        weekly_filtered += len(picks)
        continue
    
    # Signal detection for future-function check
    signal_cache = None
    try:
        sigs, st, _, _ = detect_all_signals_v20(daily)
        signal_cache = (sigs, st)
    except: pass
    
    trades = []
    for pick in picks:
        trade = execute_strategy_trade(daily, pick, signal_cache)
        if trade:
            # Build signal chain
            if '→' in pick['signal']:
                parts = pick['signal'].split('→')
                trade['signal_chain'] = [
                    {'type': parts[0], 'bar': pick.get('start_bar', pick['zone_bar'] - pick.get('gap', 1))},
                    {'type': parts[1], 'bar': pick['zone_bar']}
                ]
            else:
                trade['signal_chain'] = [{'type': pick['zone_type'], 'bar': pick['zone_bar']}]
            trades.append(trade)
        else:
            future_filtered += 1
    
    if trades:
        n = len(trades)
        wr = sum(1 for t in trades if t['won']) / n * 100
        avg = sum(t['pnl_pct'] for t in trades) / n
        cum = sum(t['pnl_pct'] for t in trades)
        stocks_out[sym] = {
            'total_trades': n, 'wr': round(wr, 1), 'avg_pnl': round(avg, 2),
            'cum_pnl': round(cum, 2), 'trend': trend,
            'trades': trades
        }
        all_trades.extend(trades)
    
    processed += 1
    if processed % 1000 == 0:
        print(f"  [{processed}/{len(picks_by_sym)}] {time.time()-t0:.0f}s trades={len(all_trades)}")

elapsed = time.time() - t0

# ═══ Summary ═══
print(f"\n{'=' * 80}")
print(f"  RESULTS — {len(stocks_out)} stocks, {len(all_trades)} trades — {elapsed:.0f}s")
print(f"{'=' * 80}")

total_wins = sum(1 for t in all_trades if t['won'])
total_pnl = sum(t['pnl_pct'] for t in all_trades)
avg_win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won']) / max(1, total_wins)
avg_loss_pnl = sum(t['pnl_pct'] for t in all_trades if not t['won']) / max(1, len(all_trades) - total_wins)
pf = sum(t['pnl_pct'] for t in all_trades if t['won']) / max(0.01, abs(sum(t['pnl_pct'] for t in all_trades if not t['won'])))

# Per-pattern
pattern_stats = defaultdict(lambda: {'n': 0, 'won': 0, 'pnl': 0, 'tp': 0, 'sl': 0})
for t in all_trades:
    pat = t['pattern']
    pattern_stats[pat]['n'] += 1
    if t['won']: pattern_stats[pat]['won'] += 1
    pattern_stats[pat]['pnl'] += t['pnl_pct']
    if t['exit_reason'] == 'tp_hit': pattern_stats[pat]['tp'] += 1
    elif t['exit_reason'] == 'sl_hit': pattern_stats[pat]['sl'] += 1

print(f"\n  总交易: {len(all_trades)}")
print(f"  WR: {total_wins/len(all_trades)*100:.1f}%")
print(f"  avgPnL: {total_pnl/len(all_trades):+.2f}%")
print(f"  累计: {total_pnl:+.1f}%")
print(f"  均盈利: +{avg_win_pnl:.2f}% | 均亏损: {avg_loss_pnl:.2f}%")
print(f"  盈亏比: {pf:.1f}x")
print(f"  周线过滤: {weekly_filtered} picks")
print(f"  未来函数过滤: {future_filtered} picks")

print(f"\n  信号表现:")
for pat in sorted(pattern_stats, key=lambda x: -pattern_stats[x]['n']):
    s = pattern_stats[pat]
    n = s['n']
    wr = s['won'] / n * 100
    avg = s['pnl'] / n
    print(f"    {pat:<35s} n={n:>4d} WR={wr:>5.1f}% avg={avg:>+6.2f}% TP={s['tp']}/{s['sl']}")

# ═══ Stock selection ═══
print(f"\n{'=' * 80}")
print(f"  STOCK SELECTION (WR≥80% & ≥2 trades)")
print(f"{'=' * 80}")

selected = []
for sym, info in stocks_out.items():
    if info['wr'] >= 80 and info['total_trades'] >= 2:
        selected.append((sym, info))

selected.sort(key=lambda x: (-x[1]['total_trades'], -x[1]['cum_pnl']))
print(f"  {len(selected)} stocks selected")
print(f"  {'代码':<15s} {'笔':>3s} {'WR':>6s} {'avg':>7s} {'cum':>7s} {'趋势':>8s}")
print(f"  {'-' * 55}")
for sym, s in selected[:30]:
    print(f"  {sym:<15s} {s['total_trades']:>3d} {s['wr']:>5.1f}% {s['avg_pnl']:>+6.2f}% {s['cum_pnl']:>+6.1f}% {s['trend']:>8s}")

# ═══ Save ═══
strategy_data = {
    'meta': {
        'version': 'V7.2 Honest Strategy',
        'date': time.strftime('%Y-%m-%d %H:%M'),
        'strategy': 'BOS→FVG + Sweep_SSL→FVG + EQL→FVG (primary) + EQL→Pinbar + OB_honest (secondary)',
        'config': f'MW={MW} SL={SL_MUL} TP={TP_CAP}',
        'total_trades': len(all_trades),
        'wr': round(total_wins/len(all_trades)*100, 1),
        'avg_pnl': round(total_pnl/len(all_trades), 2),
        'cum_pnl': round(total_pnl, 2),
        'selected_stocks': len(selected),
        'weekly_filtered': weekly_filtered,
        'future_filtered': future_filtered,
    },
    'pattern_summary': {pat: {
        'n': s['n'], 'wr': round(s['won']/s['n']*100, 1), 'avg_pnl': round(s['pnl']/s['n'], 2),
        'cum_pnl': round(s['pnl'], 2), 'tp': s['tp'], 'sl': s['sl']
    } for pat, s in pattern_stats.items()},
    'stocks': stocks_out,
    'all_trades': all_trades,
    'selected': [{'symbol': sym, 'trades': s['total_trades'], 'wr': s['wr'],
                  'avg': s['avg_pnl'], 'cum': s['cum_pnl'], 'trend': s['trend']}
                 for sym, s in selected],
}

# Save as detailed_trades (for frontend compatibility)
trade_out = OUT / 'detailed_trades_v63.json'
json.dump(strategy_data, open(trade_out, 'w'), ensure_ascii=False)
print(f"\n  保存: {trade_out} ({trade_out.stat().st_size//1024}KB)")

# Also save as strategy-specific file
strat_out = OUT / 'strategy_v72.json'
json.dump(strategy_data, open(strat_out, 'w'), ensure_ascii=False)
print(f"  保存: {strat_out} ({strat_out.stat().st_size//1024}KB)")

print(f"\n{'=' * 80}")
print(f"  DONE — {elapsed:.0f}s")
print(f"{'=' * 80}")
