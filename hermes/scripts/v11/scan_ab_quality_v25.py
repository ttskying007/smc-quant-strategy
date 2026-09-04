#!/usr/bin/env python3
"""
V25 A/B Quality Filtered Full Market Scan
===========================================
Loads quality ratings, filters A/B tier only, runs V25 trailing stop strategy.
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v25 import (
    CACHE_DIR as _CACHE_DIR_V25, OUTPUT_DIR as _OUTPUT_DIR_V25,
    SWING_MAX_DISTANCE, SWING_SL_CAP, MIN_VOL_RATIO, MIN_FVG_GAP,
    MIN_SWING_COVERAGE, MAX_STOCKS, MIN_BARS, ROLL_START,
    ROLL_END_OFFSET, MAX_HOLD, COOLDOWN, CYCLE_SL_MULT,
    load_ohlcv, short_trend, find_all_swing_lows, find_all_swing_highs,
    find_best_swing_sl, calc_initial_sl, calc_trailing_exit,
    get_entry_signal_info, simulate_trades,
    detect_all_signals_v11, analyze_sequence_v11,
    evaluate_full_resonance_v11, make_entry_decision_v11,
    calc_stock_params, detect_market_phase,
    synthesize_weekly,
)
from v11.weekly_trend import weekly_trend as weekly_trend_func

# Paths
CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v25')
OUTPUT_DIR.mkdir(exist_ok=True)
QUALITY_FILE = Path('/root/.hermes/smc_signals/stock_quality_ratings.json')
OUTPUT_FILE = Path('/root/.hermes/scripts/latest_signals.json')

# Load quality ratings
print("=" * 80)
print("V25 — A/B Quality Filtered Full Market Scan (Trailing Stop)")
print("=" * 80)

quality_data = json.loads(QUALITY_FILE.read_text())
quality_map = {}  # symbol -> {score, tier, phase, weekly_trend}
for s in quality_data.get('stocks', []):
    quality_map[s['symbol']] = {
        'score': s.get('score', 0),
        'tier': s.get('tier', 'C'),
        'phase': s.get('phase', ''),
        'weekly_trend': s.get('weekly_trend', ''),
    }

# Filter A/B symbols
ab_symbols = sorted([sym for sym, q in quality_map.items() if q['tier'] in ('A', 'B')])
print(f"Quality ratings loaded: {quality_data.get('total_stocks', '?')} total")
print(f"A tier: {quality_data.get('tier_distribution', {}).get('A', 0)}")
print(f"B tier: {quality_data.get('tier_distribution', {}).get('B', 0)}")
print(f"Total A/B to scan: {len(ab_symbols)}")

# Map to available cache files
cache_files = set(f.stem for f in CACHE_DIR.glob('*_daily_300.json'))
available_ab = []
for sym in ab_symbols:
    cache_name = f"{sym.replace('.', '_')}_daily_300"
    if cache_name in cache_files:
        available_ab.append(sym)
    else:
        pass  # silently skip missing caches

print(f"With kline cache: {len(available_ab)}")
print(f"{'='*80}\n")

# Custom V25 parameters as specified
PHASE_PARAMS_V25 = {
    'breakout': {'sl': 0.3, 'tp': 3.0},
    'volatile': {'sl': 0.5, 'tp': 5.0},
    'ranging': {'sl': 0.7, 'tp': 3.0},
    'trending_up': {'sl': 0.3, 'tp': 5.0},
    'trending_down': {'sl': 0.5, 'tp': 5.0},
}

# Multi-cycle filter: skip BEARISH / 1UP2NEUTRAL sequences
def cycle_filter_passes(seq_result):
    """Multi-cycle filter: only allow sequences that are not BEARISH or 1UP2NEUTRAL"""
    best = seq_result.get('best_sequence', {})
    name = best.get('name', '')
    # Skip bearish sequences
    if 'BEAR' in name or 'bear' in name or 'SELL' in name or 'short' in name.lower():
        return False
    # Skip 1UP2NEUTRAL = weak directional
    if '1UP2NEUTRAL' in name:
        return False
    return True


def simulate_trades_v25(ohlcv, all_signals, params, phase, quality):
    """V25 simulation with phase-adaptive SL/TP, multi-cycle filter, trailing stop exit."""
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999

    phase_params = PHASE_PARAMS_V25.get(phase, {'sl': 0.3, 'tp': 3.0})
    sl_fixed = phase_params['sl']
    swing_count = 0
    fixed_count = 0

    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN:
            continue

        sigs = [s for s in all_signals if s.get('idx', 0) <= i]
        if len(sigs) < 3:
            continue

        seq_r = analyze_sequence_v11(sigs, params=params)
        best = seq_r.get('best_sequence')
        if not best:
            continue

        # Multi-cycle filter
        if not cycle_filter_passes(seq_r):
            continue

        sn = best.get('name', '')
        sc = 'SCOUT' in sn
        sd = 'bull' if 'LONG' in sn else 'bear'
        if sd != 'bull' or not sc:
            continue

        sig_idx, sig_type, sig = get_entry_signal_info(seq_r)
        if sig_idx == 0:
            sig_idx = i

        # Volume check
        if sig_idx < n - 1 and sig_idx > 30:
            bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
            av = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0)) for j in range(max(0, sig_idx - 30), sig_idx)) / 30
            if bv < av * MIN_VOL_RATIO:
                continue

        st = sig.get('type', sig_type)
        if 'FVG' in st and sig_idx > 0 and sig_idx < n:
            bar = ohlcv[sig_idx]
            if bar['c'] <= bar['o']:
                continue
            up = sig.get('upper', 0)
            lo = sig.get('lower', 0)
            if up > 0 and lo > 0 and (up - lo) / lo * 100 < MIN_FVG_GAP:
                continue

        if len(sigs) < 8:
            continue

        td, _ = short_trend(ohlcv, i)
        if td == 'down':
            continue

        weekly = synthesize_weekly(ohlcv[:i + 1])
        if len(weekly) >= 3 and weekly_trend_func(weekly, lookback=min(5, len(weekly))) == 'down':
            continue

        signal_type = 'FVG' if 'FVG' in st else 'OB'

        # Multi-cycle trend analysis
        micro = short_trend(ohlcv, i, 8)
        meso = short_trend(ohlcv, i, 20)
        macro = short_trend(ohlcv, i, 40)
        uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
        dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
        if dc >= 2 or (uc == 1 and dc == 0):
            continue

        cd = 'ALL-UP' if uc == 3 else ('2UP-1NEUTRAL' if uc >= 2 else 'NEUTRAL')
        cm = CYCLE_SL_MULT.get(cd, 1.0)

        window = ohlcv[:i + 1]
        tf_seq = {'daily': seq_r}
        res = evaluate_full_resonance_v11(all_signals=sigs, tf_sequences=tf_seq, ohlcv=window)
        mr = 0.55 if uc >= 2 else 0.65
        if signal_type == 'OB':
            mr = max(mr, 0.70)
        if res.total < mr:
            continue

        dec = make_entry_decision_v11(res, seq_r, params, tf_sequences=tf_seq)
        if dec['action'] != 'enter':
            continue

        entry_price = dec.get('entry_price')
        if not entry_price:
            continue

        actual_sl_val = sl_fixed * cm
        init_sl, sl_pct_val, sl_type = calc_initial_sl(ohlcv, i, entry_price, signal_type, actual_sl_val)
        if init_sl is None:
            continue

        if sl_type == 'swing':
            swing_count += 1
        else:
            fixed_count += 1

        # V25: Trailing exit (no fixed TP)
        exit_idx, exit_price, won = calc_trailing_exit(ohlcv, i, entry_price, init_sl, n, MAX_HOLD)

        pnl = (exit_price - entry_price) / entry_price * 100
        actual_rr = abs(exit_price - entry_price) / abs(entry_price - init_sl) if entry_price != init_sl else 10

        trades.append({
            'entry_idx': i, 'exit_idx': exit_idx,
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'sl': round(init_sl, 2),
            'pnl_pct': round(pnl, 2), 'won': won,
            'rr': round(actual_rr, 2),
            'hold_bars': exit_idx - i,
            'sl_type': sl_type, 'sl_pct': round(sl_pct_val, 2),
            'signal_type': signal_type,
            'exit_method': 'trailing',
            'used_sl': actual_sl_val,
        })
        entered_bar = i

    total = swing_count + fixed_count
    swing_pct = swing_count / total * 100 if total else 0
    return trades, swing_pct


# Main scan loop
all_stocks = []
all_trades = []
t_start = time.time()
skipped_no_cache = 0
skipped_no_ohlcv = 0
skipped_few_signals = 0
skipped_coverage = 0

for idx, sym in enumerate(available_ab):
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        skipped_no_ohlcv += 1
        continue

    phase = detect_market_phase(ohlcv)
    # Override phase from quality data if available
    q_phase = quality_map.get(sym, {}).get('phase', '')
    if q_phase and q_phase in PHASE_PARAMS_V25:
        phase = q_phase

    base = calc_stock_params(ohlcv, sym, phase=phase, tf='daily')
    sigs = detect_all_signals_v11(ohlcv, params=base, tf='daily')['all']

    if not sigs or len(sigs) < 5:
        skipped_few_signals += 1
        continue

    quality_info = quality_map.get(sym, {})
    trades, sp = simulate_trades_v25(ohlcv, sigs, {**base}, phase, quality_info)

    if sp < MIN_SWING_COVERAGE or len(trades) < 2:
        skipped_coverage += 1
        continue

    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999

    score = quality_info.get('score', 0)
    tier = quality_info.get('tier', 'B')
    weekly_trend = quality_info.get('weekly_trend', '')

    stock_entry = {
        'symbol': sym,
        'tier': tier,
        'quality_score': score,
        'n_trades': len(trades),
        'win_rate': round(wr, 1),
        'avg_rr': round(sum(t['rr'] for t in trades) / len(trades), 2),
        'profit_factor': round(pf, 1),
        'swing_sl_pct': round(sp, 1),
        'avg_pnl': round(sum(t['pnl_pct'] for t in trades) / len(trades), 2),
        'phase': phase,
        'weekly_trend': weekly_trend,
    }
    all_stocks.append(stock_entry)
    all_trades.extend(trades)

    if (idx + 1) % 500 == 0:
        print(f"  [{idx + 1}/{len(available_ab)}] {len(all_stocks)} qualified | {(time.time() - t_start):.0f}s")
        # Checkpoint
        json.dump({
            'stocks': all_stocks,
            'trades': all_trades[:10000],
            'processed': idx + 1,
        }, open(OUTPUT_DIR / 'checkpoint_ab_v25.json', 'w'), default=str)

total_time = time.time() - t_start

# Sort by quality score descending for top N
all_stocks_sorted = sorted(all_stocks, key=lambda x: x['quality_score'], reverse=True)
top_10 = all_stocks_sorted[:10]

# Aggregate stats
n = len(all_trades)
if n > 0:
    wins = sum(1 for t in all_trades if t['won'])
    wr = wins / n * 100
    wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    rr = sum(t['rr'] for t in all_trades) / n
    pnl = sum(t['pnl_pct'] for t in all_trades) / n
    swing_trades = [t for t in all_trades if t.get('sl_type') == 'swing']
else:
    wr = pf = rr = pnl = 0

print(f"\n{'=' * 80}")
print(f"V25 A/B QUALITY SCAN — COMPLETE")
print(f"{'=' * 80}")
print(f"  Total A/B symbols in ratings:     {len(ab_symbols)}")
print(f"  With kline cache:                 {len(available_ab)}")
print(f"  No OHLCV data:                    {skipped_no_ohlcv}")
print(f"  Few signals (<5):                 {skipped_few_signals}")
print(f"  Below swing coverage (<30%):       {skipped_coverage}")
print(f"  Qualified stocks:                 {len(all_stocks)}")
print(f"  Total trades:                     {n}")
print(f"  Scan time:                        {total_time:.0f}s")
print()
print(f"  {'Win Rate':<20} {wr:.1f}%")
print(f"  {'Avg RR':<20} {rr:.2f}x")
print(f"  {'Profit Factor':<20} {pf:.0f}")
print(f"  {'Avg P&L':<20} {pnl:+.2f}%")
print(f"  {'Swing SL ratio':<20} {len(swing_trades)}/{n} ({len(swing_trades) / n * 100:.0f}%)" if swing_trades else "")
print(f"  {'WR >= 80%':<20} {sum(1 for s in all_stocks if s['win_rate'] >= 80)}")

print(f"\n{'─' * 80}")
print(f"TOP 10 BY QUALITY SCORE")
print(f"{'─' * 80}")
print(f"{'Rank':<5} {'Symbol':<12} {'Tier':<5} {'Score':<7} {'Trades':<7} {'WR':<7} {'RR':<7} {'PF':<7} {'Phase':<15}")
print(f"{'─' * 80}")
for rank, s in enumerate(top_10, 1):
    print(f"{rank:<5} {s['symbol']:<12} {s['tier']:<5} {s['quality_score']:<7} {s['n_trades']:<7} {s['win_rate']:<7} {s['avg_rr']:<7} {s['profit_factor']:<7} {s['phase']:<15}")

# Save results
output_data = {
    'timestamp': time.time(),
    'config': {
        'version': 'V25',
        'trailing': True,
        'quality_filter': 'A/B only',
        'swing_coverage_min': MIN_SWING_COVERAGE,
        'phase_params': PHASE_PARAMS_V25,
        'cycle_filter': 'skip BEARISH/1UP2NEUTRAL',
        'exit': 'trailing_stop (no fixed TP)',
    },
    'summary': {
        'total_ab_rated': len(ab_symbols),
        'scanned': len(available_ab),
        'qualified_stocks': len(all_stocks),
        'total_trades': n,
        'win_rate': round(wr, 1),
        'avg_rr': round(rr, 2),
        'profit_factor': round(pf, 2),
        'avg_pnl': round(pnl, 2),
        'scan_time_s': round(total_time, 1),
        'wr_ge_80': sum(1 for s in all_stocks if s['win_rate'] >= 80),
    },
    'top_10': top_10,
    'stocks': all_stocks,
}

OUTPUT_FILE.write_text(json.dumps(output_data, ensure_ascii=False, indent=2, default=str))
print(f"\n{'─' * 80}")
print(f"Saved: {OUTPUT_FILE}")

# Also save to the standard output dir
json.dump(output_data, open(OUTPUT_DIR / 'v25_ab_quality_scan.json', 'w'),
          ensure_ascii=False, indent=2, default=str)
print(f"Saved: {OUTPUT_DIR / 'v25_ab_quality_scan.json'}")

if n > 0:
    # P&L distribution
    print(f"\n  P&L Distribution:")
    for bucket in [(-5, 0), (0, 2), (2, 5), (5, 10), (10, 20), (20, 50)]:
        subset = [t for t in all_trades if bucket[0] <= t['pnl_pct'] < bucket[1]]
        if subset:
            avg = sum(t['pnl_pct'] for t in subset) / len(subset)
            print(f"    {bucket[0]:+}% to {bucket[1]:+}%: {len(subset):3d} trades (avg {avg:+.2f}%)")
