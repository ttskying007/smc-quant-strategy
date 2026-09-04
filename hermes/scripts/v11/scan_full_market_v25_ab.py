#!/usr/bin/env python3
"""V25 Full Market Scan — A/B Quality Tier Filtered + Multi-Cycle Filter"""
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v25 import *

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/scripts')
QUALITY_PATH = Path('/root/.hermes/smc_signals/stock_quality_ratings.json')
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Load quality ratings ──
quality_data = json.loads(QUALITY_PATH.read_text())
ab_symbols = set()
for s in quality_data['stocks']:
    if s['tier'] in ('A', 'B'):
        ab_symbols.add(s['symbol'])
print(f"Quality ratings loaded: {quality_data['total_stocks']} stocks, {len(ab_symbols)} A/B tier")

# ── Build symbol list from cache, filtered by A/B ──
all_cached = sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
symbols = sorted([s for s in all_cached if s in ab_symbols])
print(f"V25 Full Market (A/B only) — {len(symbols)} stocks (filtered from {len(all_cached)} cached)")

# ── Override simulate_trades to add 1UP2NEUTRAL skip ──
_original_simulate = simulate_trades

def simulate_trades_v25_ab(ohlcv, all_signals, params, phase):
    """V25 with extra multi-cycle filter: skip BEARISH & 1UP2NEUTRAL"""
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    phase_params = PHASE_PARAMS.get(phase, {'sl': 0.3, 'tp': 3.0})
    sl_fixed = phase_params['sl']
    swing_count = 0
    fixed_count = 0
    skipped_bearish = 0
    skipped_1up2neutral = 0

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
        sn = best.get('name', '')
        sc = 'SCOUT' in sn
        sd = 'bull' if 'LONG' in sn else 'bear'
        if sd != 'bull' or not sc:
            continue

        sig_idx, sig_type, sig = get_entry_signal_info(seq_r)
        if sig_idx == 0:
            sig_idx = i

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
            skipped_bearish += 1
            continue

        weekly = synthesize_weekly(ohlcv[:i + 1])
        if len(weekly) >= 3 and weekly_trend(weekly, lookback=min(5, len(weekly))) == 'down':
            skipped_bearish += 1
            continue

        signal_type = 'FVG' if 'FVG' in st else 'OB'

        micro = short_trend(ohlcv, i, 8)
        meso = short_trend(ohlcv, i, 20)
        macro = short_trend(ohlcv, i, 40)
        uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
        dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')

        # Multi-cycle filter: skip BEARISH
        if dc >= 2:
            skipped_bearish += 1
            continue

        # Multi-cycle filter: skip 1UP2NEUTRAL (uc >= 2 but not ALL-UP, i.e., uc == 2)
        if uc == 2:
            skipped_1up2neutral += 1
            continue

        # Also skip (uc==1 and dc==0) — from original
        if uc == 1 and dc == 0:
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
            'cycle': cd
        })
        entered_bar = i

    total = swing_count + fixed_count
    swing_pct = swing_count / total * 100 if total else 0
    if skipped_bearish > 0 or skipped_1up2neutral > 0:
        print(f"    Multi-cycle filter: skipped {skipped_bearish} BEARISH, {skipped_1up2neutral} 1UP2NEUTRAL")
    return trades, swing_pct


# ── Main scan loop ──
all_stocks = []
all_trades = []
t_start = time.time()

for idx, sym in enumerate(symbols):
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        continue
    phase = detect_market_phase(ohlcv)
    base = calc_stock_params(ohlcv, sym, phase=phase, tf='daily')
    sigs = detect_all_signals_v11(ohlcv, params=base, tf='daily')['all']
    if not sigs or len(sigs) < 5:
        continue
    trades, sp = simulate_trades_v25_ab(ohlcv, sigs, {**base}, phase)
    if sp < MIN_SWING_COVERAGE or len(trades) < 2:
        continue

    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    all_stocks.append({
        'symbol': sym, 'n_trades': len(trades), 'win_rate': round(wr, 1),
        'avg_rr': round(sum(t['rr'] for t in trades) / len(trades), 2),
        'profit_factor': round(pf, 1), 'swing_sl_pct': round(sp, 1),
        'avg_pnl': round(sum(t['pnl_pct'] for t in trades) / len(trades), 2),
        'phase': phase
    })
    all_trades.extend(trades)

    if (idx + 1) % 500 == 0:
        print(f"  [{idx + 1}/{len(symbols)}] {len(all_stocks)} tradable | {(time.time() - t_start):.0f}s")
        json.dump({'stocks': all_stocks, 'trades': all_trades[:10000], 'processed': idx + 1},
                  open(OUTPUT_DIR / 'checkpoint.json', 'w'), default=str)

total_time = time.time() - t_start
n = len(all_trades)
wins = sum(1 for t in all_trades if t['won'])
wr = wins / n * 100 if n else 0
wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
pf = wp / lp if lp > 0 else 999
rr = sum(t['rr'] for t in all_trades) / n if n else 0
pnl = sum(t['pnl_pct'] for t in all_trades) / n if n else 0

print(f"\n{'=' * 70}")
print(f"V25 FULL MARKET (A/B ONLY) — {len(all_stocks)}/{len(symbols)} | {total_time:.0f}s")
print(f"{'=' * 70}")
print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
print(f"  WR>=80%: {sum(1 for s in all_stocks if s['win_rate'] >= 80)}")
swing_trades = [t for t in all_trades if t.get('sl_type') == 'swing']
print(f"  Swing SL: {len(swing_trades)}/{n}")

# ── Top 10 by quality score (from ratings) ──
quality_map = {}
for s in quality_data['stocks']:
    quality_map[s['symbol']] = s

top10 = sorted(all_stocks, key=lambda x: quality_map.get(x['symbol'], {}).get('score', 0), reverse=True)[:10]
print(f"\n{'─' * 70}")
print(f"  TOP 10 SIGNALS BY QUALITY SCORE")
print(f"{'─' * 70}")
print(f"  {'Symbol':12s} {'Score':>6s} {'Tier':>5s} {'Trades':>7s} {'WR%':>5s} {'RR':>5s} {'PF':>5s} {'Phase':12s}")
for s in top10:
    q = quality_map.get(s['symbol'], {})
    print(f"  {s['symbol']:12s} {q.get('score', 0):>5.1f} {q.get('tier', '?'):>5s} {s['n_trades']:>5d}  {s['win_rate']:>4.1f} {s['avg_rr']:>5.2f} {s['profit_factor']:>5.1f} {s['phase']:12s}")

# ── Ranking by composite score ──
print(f"\n{'─' * 70}")
print(f"  TOP 10 BY COMPOSITE STRATEGY SCORE (WR × PF × RR)")
print(f"{'─' * 70}")
ranked = sorted(all_stocks, key=lambda x: x['win_rate'] * x['profit_factor'] * x['avg_rr'], reverse=True)[:10]
print(f"  {'Symbol':12s} {'WR%':>5s} {'RR':>5s} {'PF':>5s} {'P&L':>7s} {'Swing%':>7s} {'Phase':12s}")
for s in ranked:
    print(f"  {s['symbol']:12s} {s['win_rate']:>4.1f} {s['avg_rr']:>5.2f} {s['profit_factor']:>5.1f} {s['avg_pnl']:>+6.2f}% {s['swing_sl_pct']:>6.1f}% {s['phase']:12s}")

# ── Save ──
outpath = OUTPUT_DIR / 'latest_signals.json'
json.dump({
    'timestamp': time.time(),
    'config': {
        'version': 'V25',
        'trailing': True,
        'quality_filter': 'A/B only',
        'swing_coverage_min': MIN_SWING_COVERAGE,
        'phase_params': PHASE_PARAMS,
        'cycle_filter': 'skip BEARISH/1UP2NEUTRAL'
    },
    'summary': {
        'total_ab_stocks': len(symbols),
        'tradable': len(all_stocks),
        'total_trades': n,
        'win_rate': round(wr, 1),
        'avg_rr': round(rr, 2),
        'profit_factor': round(pf, 2),
        'avg_pnl': round(pnl, 2)
    },
    'stocks': all_stocks,
    'all_trades': all_trades,
    'top10_by_quality': [
        {
            'symbol': s['symbol'],
            'quality_score': quality_map.get(s['symbol'], {}).get('score', 0),
            'tier': quality_map.get(s['symbol'], {}).get('tier', '?'),
            'n_trades': s['n_trades'],
            'win_rate': s['win_rate'],
            'avg_rr': s['avg_rr'],
            'profit_factor': s['profit_factor'],
            'phase': s['phase']
        }
        for s in top10
    ]
}, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
print(f"\n✅ Saved: {outpath} ({os.path.getsize(outpath) // 1024} KB)")
