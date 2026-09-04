#!/usr/bin/env python3
"""
V38 — ATR SL/TP Multiplier Grid Search Optimizer
==================================================
Phase 1: Global grid search — best fixed SL_MULT × TP_MULT (50 stocks)
Phase 2: Per-stock optimal parameters (50 stocks)

Strategy: pre-compute signals/tree/Wyckoff once per stock, then iterate
SL/TP combos with patched SL/TP evaluation only (no re-detection).
"""
import sys, json, time, math
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v38 import (
    CACHE_DIR, OUTPUT_DIR, MIN_BARS, MIN_TRADES_PER_STOCK, MAX_HOLD,
    MIN_VOL_RATIO, SL_MULT_RANGE, TP_MULT_RANGE,
    load_ohlcv, calc_atr_v38, calc_stock_atr_profile,
    calc_v38_sl as _orig_calc_sl,
    calc_v38_tp as _orig_calc_tp,
    calc_v38_trailing, evaluate_v38_entry,
    short_trend, find_entry_signal,
)
from v11.structure_tree_v38 import StructureTree
from v11.wyckoff_phases_v38 import detect_wyckoff_phases, get_phase_params
from v11.signals_v11 import detect_all_signals_v11

# ── Grid Search Space ──
SL_GRID = [0.15, 0.25, 0.30, 0.40, 0.50, 0.60, 0.80]
TP_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]

# ── Global Multiplier State ──
CUSTOM_SL_MULT = 0.30
CUSTOM_TP_MULT = 2.0

OUT_DIR = Path('/root/.hermes/smc_opt_v38')
OUT_DIR.mkdir(exist_ok=True)


# ═════════════════════════════════════════════════════════════════════
#  Patched SL/TP (same signature as originals)
# ═════════════════════════════════════════════════════════════════════

def patched_calc_sl(ohlcv, entry_idx, entry_price, signal, entry_type,
                    structure_tree, wyckoff_result, atr_params, direction, params):
    """ATR adaptive SL using CUSTOM_SL_MULT. Structural SL still takes priority."""
    # 1. Structural tree SL
    tree_sl = structure_tree.get_sl_level(entry_idx, entry_price)
    if tree_sl:
        sl_price, sl_name, sl_pct = tree_sl
        if direction == 'bear':
            sl_pct = (sl_price - entry_price) / entry_price * 100
        if 0.08 <= abs(sl_pct) <= 2.0:
            return sl_price, sl_name, abs(sl_pct)

    # 2. Signal structure SL (FVG/OB boundaries)
    sig_type = signal.get('type', '')
    if direction == 'bull':
        if 'FVG' in sig_type and 'Mitigated' not in sig_type:
            lower = signal.get('lower', 0)
            if lower > 0 and lower < entry_price:
                pct = (entry_price - lower) / entry_price * 100
                if 0.08 <= pct <= 1.0:
                    return lower, 'fvg_lower', pct
        if 'OB' in sig_type:
            lower = signal.get('lower', 0)
            if lower > 0 and lower < entry_price:
                pct = (entry_price - lower) / entry_price * 100
                if 0.08 <= pct <= 1.5:
                    return lower, 'ob_lower', pct
    else:
        if 'FVG' in sig_type and 'Mitigated' not in sig_type:
            upper = signal.get('upper', 0)
            if upper > 0 and upper > entry_price:
                pct = (upper - entry_price) / entry_price * 100
                if 0.08 <= pct <= 1.0:
                    return upper, 'fvg_upper', pct
        if 'OB' in sig_type:
            upper = signal.get('upper', 0)
            if upper > 0 and upper > entry_price:
                pct = (upper - entry_price) / entry_price * 100
                if 0.08 <= pct <= 1.5:
                    return upper, 'ob_upper', pct

    # 3. ATR adaptive: use CUSTOM_SL_MULT directly (not phase_params)
    atr_pct = calc_atr_v38(ohlcv, entry_idx)
    base_sl_pct = atr_pct * CUSTOM_SL_MULT
    base_sl_pct = max(0.08, min(2.0, base_sl_pct))

    if direction == 'bull':
        return (round(entry_price * (1 - base_sl_pct / 100), 4),
                'adaptive', round(base_sl_pct, 2))
    else:
        return (round(entry_price * (1 + base_sl_pct / 100), 4),
                'adaptive', round(base_sl_pct, 2))


def patched_calc_tp(ohlcv, entry_idx, entry_price, signal, entry_type,
                    structure_tree, wyckoff_result, direction, all_signals):
    """TP using CUSTOM_TP_MULT scaling. Falls back to ATR-based TP."""
    # 1. Structure tree TP (scaled)
    tree_tp = structure_tree.get_tp_level(entry_idx, entry_price, direction)
    if tree_tp:
        tp_price, tp_name, tp_pct, tp_idx = tree_tp
        scaled_pct = tp_pct * CUSTOM_TP_MULT
        if direction == 'bull':
            new_tp = entry_price * (1 + scaled_pct / 100)
        else:
            new_tp = entry_price * (1 - scaled_pct / 100)
        return (round(new_tp, 4), 'tree_tp', round(scaled_pct, 2), tp_idx)

    # 2. Forward CHOCH (scaled)
    if direction == 'bull':
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bull' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 60]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp = nearest.get('break_level', nearest.get('upper', 0))
            if tp > entry_price:
                pct = (tp - entry_price) / entry_price * 100
                if pct >= 0.3:
                    sp = pct * CUSTOM_TP_MULT
                    nt = entry_price * (1 + sp / 100)
                    return (round(nt, 4), 'choch_tp', round(sp, 2), nearest['idx'])
    else:
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bear' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 60]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp = nearest.get('break_level', nearest.get('lower', 0))
            if tp > 0 and tp < entry_price:
                pct = (entry_price - tp) / entry_price * 100
                if pct >= 0.3:
                    sp = pct * CUSTOM_TP_MULT
                    nt = entry_price * (1 - sp / 100)
                    return (round(nt, 4), 'choch_tp', round(sp, 2), nearest['idx'])

    # 3. ATR TP fallback: SL% × TP_MULT
    atr_pct = calc_atr_v38(ohlcv, entry_idx)
    sl_pct = atr_pct * CUSTOM_SL_MULT
    tp_pct = sl_pct * CUSTOM_TP_MULT
    tp_pct = max(0.3, min(10.0, tp_pct))

    if direction == 'bull':
        tp_price = entry_price * (1 + tp_pct / 100)
    else:
        tp_price = entry_price * (1 - tp_pct / 100)
    return (round(tp_price, 4), 'grid_tp', round(tp_pct, 2), entry_idx + 10)


# ═════════════════════════════════════════════════════════════════════
#  Pre-computed stock cache
# ═════════════════════════════════════════════════════════════════════

class StockCache:
    """Pre-computed signals/tree/wyckoff for one stock."""
    __slots__ = ('symbol', 'ohlcv', 'n', 'structure_tree', 'wyckoff_result',
                 'all_signals', 'all_sigs')

    def __init__(self, symbol, ohlcv):
        self.symbol = symbol
        self.ohlcv = ohlcv
        self.n = len(ohlcv)
        self.structure_tree = StructureTree(ohlcv)
        self.wyckoff_result = detect_wyckoff_phases(ohlcv, self.structure_tree)
        base_params = {
            'fvg_min_consecutive': 2,
            'sweep_lookback': 20,
            'max_fvg_gap_pct': 5.0,
            'min_fvg_gap_pct': 0.15,
            'swing_window': 5,
            'enable_bear': True,
        }
        all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
        self.all_signals = all_signals
        self.all_sigs = all_signals.get('all', [])


def evaluate_entry_with_params(cache, sig, direction):
    """Evaluate a single entry with current CUSTOM_SL_MULT / CUSTOM_TP_MULT.
    Mirrors evaluate_v38_entry logic but uses patched SL/TP."""
    from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
    from v11.sequencer_v11 import analyze_sequence_v11
    from v11.weekly_trend import synthesize_weekly, weekly_trend

    ohlcv = cache.ohlcv
    n = cache.n
    structure_tree = cache.structure_tree
    wyckoff_result = cache.wyckoff_result
    all_sigs = cache.all_sigs
    all_signals = cache.all_signals

    sig_type = sig.get('type', '')
    sig_idx = sig.get('idx', 0)
    confirmed_at = sig.get('confirmed_at', sig_idx)
    entry_bar = max(sig_idx, confirmed_at)

    if entry_bar >= n - 2:
        return None

    entry_price = ohlcv[entry_bar]['c']

    is_fvg = 'FVG' in sig_type and 'Mitigated' not in sig_type and 'IFVG' not in sig_type
    is_ob = 'OB' in sig_type and 'BreakerBlock' not in sig_type
    is_bb = 'BreakerBlock' in sig_type
    is_sweep = 'Sweep' in sig_type
    is_choch = 'CHOCH' in sig_type
    quality = sig.get('confidence', sig.get('quality', 0.5))

    # Sweep→FVG check
    sweep_fvg_found = False
    choch_retest_found = False
    SWEEP_LOOKBACK = 5
    if (is_fvg or is_ob) and sig_idx > SWEEP_LOOKBACK:
        for ps in all_sigs:
            ps_type = ps.get('type', '')
            ps_idx = ps.get('idx', 0)
            if direction == 'bull' and 'SweepDown' in ps_type:
                if 0 < sig_idx - ps_idx <= SWEEP_LOOKBACK:
                    sweep_fvg_found = True
                    break
            elif direction == 'bear' and 'SweepUp' in ps_type:
                if 0 < sig_idx - ps_idx <= SWEEP_LOOKBACK:
                    sweep_fvg_found = True
                    break

    # CHOCH→retest check
    RETEST_THRESHOLD = 0.5
    if (is_fvg or is_ob) and sig_idx > 5:
        for ps in all_sigs:
            ps_type = ps.get('type', '')
            ps_idx = ps.get('idx', 0)
            if 'CHOCH' not in ps_type:
                continue
            if direction == 'bull' and 'CHOCH_Bull' in ps_type:
                bl = ps.get('metadata', {}).get('break_level', ps.get('lower', 0))
                if bl > 0 and abs(entry_price - bl) / max(bl, 0.01) * 100 < RETEST_THRESHOLD:
                    if 0 < sig_idx - ps_idx <= 20:
                        choch_retest_found = True
                        break
            elif direction == 'bear' and 'CHOCH_Bear' in ps_type:
                bl = ps.get('metadata', {}).get('break_level', ps.get('upper', 0))
                if bl > 0 and abs(entry_price - bl) / max(bl, 0.01) * 100 < RETEST_THRESHOLD:
                    if 0 < sig_idx - ps_idx <= 20:
                        choch_retest_found = True
                        break

    # Entry type
    if is_fvg and quality >= 0.55:
        entry_type = 'Sweep→FVG' if sweep_fvg_found else ('CHOCH→retest' if choch_retest_found else 'FVG')
    elif is_ob and quality >= 0.50:
        entry_type = 'Sweep→FVG' if sweep_fvg_found else ('CHOCH→retest' if choch_retest_found else 'OB')
    elif is_bb:
        bb_meta = sig.get('metadata', {})
        if bb_meta.get('has_fvg_overlap', False):
            entry_type = 'BreakerBlock'
        else:
            return None
    else:
        return None

    # Volume filter
    if sig_idx > 30 and sig_idx < n:
        try:
            bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
            avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                         for j in range(max(0, sig_idx - 30), sig_idx)) / 30
            if bv < avg_vol * MIN_VOL_RATIO:
                return None
        except:
            pass

    # Trend filters
    td, _ = short_trend(ohlcv, entry_bar)
    if direction == 'bull' and td == 'down':
        return None
    if direction == 'bear' and td == 'up':
        return None

    weekly = synthesize_weekly(ohlcv[:entry_bar + 1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if direction == 'bull' and wt == 'down':
            return None
        if direction == 'bear' and wt == 'up':
            return None

    micro = short_trend(ohlcv, entry_bar, 8)
    meso = short_trend(ohlcv, entry_bar, 20)
    macro = short_trend(ohlcv, entry_bar, 40)
    uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
    if direction == 'bull':
        if dc >= 2 or (uc == 1 and dc == 0):
            return None
    else:
        if uc >= 2 or (dc == 1 and uc == 0):
            return None

    # Sequence + resonance
    seq_r = analyze_sequence_v11(all_sigs, params={'enable_bear': True})
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None

    window = ohlcv[:entry_bar + 1]
    tf_seq = {'daily': seq_r}
    res = evaluate_full_resonance_v11(
        all_signals=all_sigs, tf_sequences=tf_seq, ohlcv=window)

    wyckoff_conf = wyckoff_result.get('confidence', 0.0)
    phase = wyckoff_result.get('primary_phase', 'unknown')
    phase_params = get_phase_params(phase)
    mr = phase_params['min_score']
    if direction == 'bull':
        mr = max(mr, 0.50)
    else:
        mr = max(mr, 0.55)
    if res.total < mr:
        return None

    dec = make_entry_decision_v11(res, seq_r, {'enable_bear': True}, tf_sequences=tf_seq)
    if dec['action'] != 'enter':
        return None

    atr_pct = calc_atr_v38(ohlcv, entry_bar)
    atr_params = calc_stock_atr_profile(ohlcv)

    # SL (patched)
    init_sl, sl_type_name, sl_pct_val = patched_calc_sl(
        ohlcv, entry_bar, entry_price, sig, entry_type,
        structure_tree, wyckoff_result, atr_params, direction, {})

    # TP (patched)
    tp_price, tp_type, tp_pct, tp_idx = patched_calc_tp(
        ohlcv, entry_bar, entry_price, sig, entry_type,
        structure_tree, wyckoff_result, direction, all_sigs)

    # Trailing
    exit_idx, exit_price, won = calc_v38_trailing(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx) if tp_price else (None, None, None, None),
        n, MAX_HOLD, direction)

    pnl = (exit_price - entry_price) / entry_price * 100
    if direction == 'bear':
        pnl = -pnl

    actual_sl_pct = abs(entry_price - init_sl) / entry_price * 100
    actual_rr = abs(pnl) / actual_sl_pct if actual_sl_pct > 0 else 10

    return {
        'entry_idx': entry_bar,
        'exit_idx': exit_idx,
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'sl': round(init_sl, 2),
        'pnl_pct': round(pnl, 2),
        'won': won,
        'rr': round(actual_rr, 2),
        'hold_bars': exit_idx - entry_bar,
        'sl_type': sl_type_name,
        'sl_pct': round(actual_sl_pct, 2),
        'tp_type': tp_type,
        'tp_pct': round(tp_pct, 2) if tp_pct else None,
        'entry_type': entry_type,
        'direction': direction,
        'phase': phase,
        'atr_pct': round(atr_pct, 2),
    }


def run_cached_backtest(cache):
    """Run full backtest on cached stock data with current multipliers."""
    ohlcv = cache.ohlcv
    n = cache.n
    all_sigs = cache.all_sigs

    if n < MIN_BARS or not all_sigs or len(all_sigs) < 3:
        return None

    trades = []
    used_long = set()
    used_short = set()

    for sig in all_sigs:
        sig_idx = sig.get('idx', 0)
        if sig_idx < 40 or sig_idx >= n - 10:
            continue

        sig_type = sig.get('type', '')
        if 'Bull' in sig_type:
            result = evaluate_entry_with_params(cache, sig, 'bull')
            if result and result['entry_idx'] not in used_long:
                used_long.add(result['entry_idx'])
                trades.append(result)
        elif 'Bear' in sig_type:
            result = evaluate_entry_with_params(cache, sig, 'bear')
            if result and result['entry_idx'] not in used_short:
                used_short.add(result['entry_idx'])
                trades.append(result)

    if len(trades) < MIN_TRADES_PER_STOCK:
        return None

    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)

    return {
        'trades': trades,
        'n_trades': len(trades),
        'wins': wins,
        'losses': len(trades) - wins,
        'win_rate': round(wr, 1),
        'avg_rr': round(avg_rr, 2),
        'profit_factor': round(pf, 2) if pf < 999 else 999,
        'avg_pnl': round(avg_pnl, 2),
    }


def build_cache(symbol, ohlcv):
    """Build cache for one stock, return None if invalid."""
    try:
        cache = StockCache(symbol, ohlcv)
        if not cache.all_sigs or len(cache.all_sigs) < 3:
            return None
        return cache
    except Exception as e:
        return None


# ═════════════════════════════════════════════════════════════════════
#  Grid search runners
# ═════════════════════════════════════════════════════════════════════

def run_config_on_caches(caches, sl_mult, tp_mult):
    """Run backtest with given multipliers on pre-built caches."""
    global CUSTOM_SL_MULT, CUSTOM_TP_MULT
    CUSTOM_SL_MULT = sl_mult
    CUSTOM_TP_MULT = tp_mult

    all_trades = []
    stock_results = []

    for cache in caches:
        result = run_cached_backtest(cache)
        if result:
            all_trades.extend(result['trades'])
            stock_results.append({
                'symbol': cache.symbol,
                'n_trades': result['n_trades'],
                'win_rate': result['win_rate'],
                'avg_rr': result['avg_rr'],
                'profit_factor': result['profit_factor'],
                'avg_pnl': result['avg_pnl'],
            })

    if not all_trades:
        return None

    n = len(all_trades)
    wins = sum(1 for t in all_trades if t['won'])
    wr = wins / n * 100
    wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    pf = wp / lp if lp > 0 else 999.0
    rr = sum(t['rr'] for t in all_trades) / n
    pnl = sum(t['pnl_pct'] for t in all_trades) / n
    capped_pf = min(pf, 50.0)
    composite = wr * rr * capped_pf

    return {
        'sl': sl_mult, 'tp': tp_mult,
        'n_stocks': len(stock_results),
        'n_trades': n, 'wins': wins,
        'wr': round(wr, 1), 'rr': round(rr, 2),
        'pf': round(pf, 2), 'pnl': round(pnl, 2),
        'composite': round(composite, 1),
        'wr80plus': sum(1 for s in stock_results if s['win_rate'] >= 80),
        'stock_results': stock_results,
        'trades': all_trades,
    }


def prebuild_caches(symbols, max_stocks):
    """Build caches for all symbols (signals/tree/Wyckoff once)."""
    print(f"\n  Pre-building caches for {min(max_stocks, len(symbols))} stocks...")
    caches = []
    t0 = time.time()
    for idx, sym in enumerate(symbols[:max_stocks]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            continue
        cache = build_cache(sym, ohlcv)
        if cache:
            caches.append(cache)
        if (idx + 1) % 50 == 0:
            print(f"    [{idx+1}/{max_stocks}] {len(caches)} cached, {time.time()-t0:.0f}s")
    print(f"  Cached {len(caches)}/{max_stocks} tradable stocks in {time.time()-t0:.0f}s")
    return caches


# ═════════════════════════════════════════════════════════════════════
#  Phase 1: Global Grid Search
# ═════════════════════════════════════════════════════════════════════

def phase1_grid(caches):
    """Grid search: iterate SL_GRID × TP_GRID, find best global combo."""
    total = len(SL_GRID) * len(TP_GRID)
    print(f"\n{'='*70}")
    print(f"PHASE 1: Global Grid Search ({total} combos)")
    print(f"{'='*70}")

    results = []
    t0 = time.time()
    ci = 0

    for sl in SL_GRID:
        for tp in TP_GRID:
            ci += 1
            tc = time.time()
            r = run_config_on_caches(caches, sl, tp)
            if r is None:
                print(f"  [{ci:2d}/{total}] SL={sl:.2f} TP={tp:.1f} → NO TRADES  [{time.time()-tc:.0f}s]")
                continue
            results.append(r)
            print(f"  [{ci:2d}/{total}] SL={sl:.2f} TP={tp:.1f} | "
                  f"{r['n_stocks']:3d}st {r['n_trades']:4d}tr | "
                  f"WR={r['wr']:.1f}% RR={r['rr']:.2f}x PF={r['pf']:.1f} "
                  f"P&L={r['pnl']:+.2f}% C={r['composite']:.0f} [{time.time()-tc:.1f}s]")

    total_elapsed = time.time() - t0
    print(f"\n  Grid search done: {total_elapsed:.0f}s ({total_elapsed/total:.1f}s/combo)")

    if not results:
        print("  No valid configurations!")
        return []

    results.sort(key=lambda r: r['composite'], reverse=True)

    print(f"\n{'='*70}")
    print(f"TOP-10 GLOBAL CONFIGURATIONS")
    print(f"{'='*70}")
    print(f"  {'Rank':>4s} {'SL':>5s} {'TP':>5s} {'Stk':>4s} {'Trd':>5s} "
          f"{'WR%':>5s} {'RR':>5s} {'PF':>6s} {'P&L%':>6s} {'W80+':>4s} {'Comp':>5s}")
    for i, r in enumerate(results[:10]):
        print(f"  {i+1:4d} {r['sl']:5.2f} {r['tp']:5.1f} "
              f"{r['n_stocks']:4d} {r['n_trades']:5d} "
              f"{r['wr']:5.1f} {r['rr']:5.2f} {r['pf']:6.1f} "
              f"{r['pnl']:6.2f} {r['wr80plus']:4d} {r['composite']:5.0f}")

    save = {
        'phase': '1_global',
        'sl_grid': SL_GRID,
        'tp_grid': TP_GRID,
        'top10': [{'rank': i+1, **r} for i, r in enumerate(results[:10])],
        'all': results,
    }
    path = OUT_DIR / 'opt_phase1.json'
    path.write_text(json.dumps(save, ensure_ascii=False, indent=1))
    print(f"\n  Saved: {path}")
    return results


# ═════════════════════════════════════════════════════════════════════
#  Phase 2: Per-Stock Optimization
# ═════════════════════════════════════════════════════════════════════

def phase2_per_stock(caches):
    """Find optimal SL/TP per stock."""
    total = len(SL_GRID) * len(TP_GRID)
    print(f"\n{'='*70}")
    print(f"PHASE 2: Per-Stock Optimization ({len(caches)} stocks × {total} combos)")
    print(f"{'='*70}")

    stock_optima = []
    t0 = time.time()

    for idx, cache in enumerate(caches):
        best = None
        best_score = -1
        best_results = []

        for sl in SL_GRID:
            for tp in TP_GRID:
                CUSTOM_SL_MULT = sl
                CUSTOM_TP_MULT = tp
                r = run_cached_backtest(cache)
                if r:
                    comp = r['win_rate'] * r['avg_rr'] * min(r['profit_factor'], 50.0)
                    best_results.append({
                        'sl': sl, 'tp': tp,
                        'n': r['n_trades'], 'wr': r['win_rate'],
                        'rr': r['avg_rr'], 'pf': r['profit_factor'],
                        'comp': round(comp, 1),
                    })
                    if comp > best_score:
                        best_score = comp
                        best = best_results[-1]

        if best and best['n'] >= MIN_TRADES_PER_STOCK:
            stock_optima.append({
                'symbol': cache.symbol,
                'opt_sl': best['sl'],
                'opt_tp': best['tp'],
                'n': best['n'],
                'wr': best['wr'],
                'rr': best['rr'],
                'pf': best['pf'],
                'comp': best['comp'],
            })

        if (idx + 1) % 5 == 0 or idx == len(caches) - 1:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed if elapsed > 0 else 0
            print(f"  [{idx+1:3d}/{len(caches)}] {cache.symbol:12s} → "
                  f"opt SL={best['sl']:.2f} TP={best['tp']:.1f} "
                  f"n={best['n']:2d} C={best['comp']:.0f} "
                  f"[{elapsed:.0f}s, {rate:.1f}stk/s]" if best else
                  f"  [{idx+1:3d}/{len(caches)}] {cache.symbol:12s} → NO TRADES")

    total_elapsed = time.time() - t0
    print(f"\n  Per-stock done: {len(stock_optima)}/{len(caches)} tradable | {total_elapsed:.0f}s")

    if not stock_optima:
        return []

    sl_counts = Counter(o['opt_sl'] for o in stock_optima)
    tp_counts = Counter(o['opt_tp'] for o in stock_optima)
    combo_counts = Counter((o['opt_sl'], o['opt_tp']) for o in stock_optima)

    print(f"\n  Optimal SL distribution:")
    for sl_val, cnt in sl_counts.most_common():
        print(f"    SL={sl_val:.2f}: {cnt:3d} stocks ({cnt/len(stock_optima)*100:.0f}%)")
    print(f"  Optimal TP distribution:")
    for tp_val, cnt in tp_counts.most_common():
        print(f"    TP={tp_val:.1f}: {cnt:3d} stocks ({cnt/len(stock_optima)*100:.0f}%)")
    print(f"  Top-10 SL×TP combos:")
    for (sl, tp), cnt in combo_counts.most_common(10):
        print(f"    SL={sl:.2f}×TP={tp:.1f}: {cnt:3d} ({cnt/len(stock_optima)*100:.0f}%)")

    agg_wr = sum(o['wr'] for o in stock_optima) / len(stock_optima)
    agg_rr = sum(o['rr'] for o in stock_optima) / len(stock_optima)
    agg_pf = sum(o['pf'] for o in stock_optima) / len(stock_optima)
    agg_c = sum(o['comp'] for o in stock_optima) / len(stock_optima)

    print(f"\n  Per-stock optimal aggregate:")
    print(f"    Avg WR={agg_wr:.1f}% RR={agg_rr:.2f}x PF={agg_pf:.1f} Composite={agg_c:.0f}")

    save = {
        'phase': '2_per_stock',
        'sl_grid': SL_GRID,
        'tp_grid': TP_GRID,
        'summary': {
            'n_optimized': len(stock_optima),
            'avg_wr': round(agg_wr, 1),
            'avg_rr': round(agg_rr, 2),
            'avg_pf': round(agg_pf, 1),
            'avg_composite': round(agg_c, 0),
            'top_sl': [[v, c] for v, c in sl_counts.most_common(5)],
            'top_tp': [[v, c] for v, c in tp_counts.most_common(5)],
            'top_combos': [[s, t, c] for (s, t), c in combo_counts.most_common(10)],
        },
        'results': stock_optima,
    }
    path = OUT_DIR / 'opt_phase2.json'
    path.write_text(json.dumps(save, ensure_ascii=False, indent=1))
    print(f"\n  Saved: {path}")
    return stock_optima


# ═════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════

def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    print(f"{'='*70}")
    print(f"V38 Parameter Optimizer — {len(symbols)} symbols in cache")
    print(f"{'='*70}")

    # Pre-build caches (signals/tree/Wyckoff — done ONCE)
    caches = prebuild_caches(symbols, max_stocks=50)
    if not caches:
        print("No tradable stocks found!")
        return

    # ── Baseline (default: SL=0.30, TP=2.0) ──
    print(f"\n{'─'*70}")
    print("BASELINE (SL=0.30, TP=2.0)")
    print(f"{'─'*70}")
    base = run_config_on_caches(caches, 0.30, 2.0)
    if base:
        print(f"  Stocks={base['n_stocks']} Trades={base['n_trades']} | "
              f"WR={base['wr']:.1f}% RR={base['rr']:.2f}x PF={base['pf']:.1f} "
              f"P&L={base['pnl']:+.2f}% WR80+={base['wr80plus']}")

    # ── Phase 1: Global grid ──
    p1 = phase1_grid(caches)
    if not p1:
        return

    # ── Phase 2: Per-stock ──
    p2 = phase2_per_stock(caches)

    # ── Report ──
    best_global = p1[0]
    print(f"\n{'='*70}")
    print("FINAL OPTIMIZATION REPORT (50 stocks)")
    print(f"{'='*70}")

    if base:
        print(f"\n  Baseline (SL=0.30, TP=2.0):")
        print(f"    WR={base['wr']:.1f}%  RR={base['rr']:.2f}x  PF={base['pf']:.1f}  "
              f"P&L={base['pnl']:+.2f}%")
        print(f"    WR80+={base['wr80plus']}/{base['n_stocks']} stocks  "
              f"n={base['n_trades']} trades")

    print(f"\n  Best global (SL={best_global['sl']:.2f}, TP={best_global['tp']:.1f}):")
    print(f"    WR={best_global['wr']:.1f}%  RR={best_global['rr']:.2f}x  "
          f"PF={best_global['pf']:.1f}  P&L={best_global['pnl']:+.2f}%")
    print(f"    WR80+={best_global['wr80plus']}/{best_global['n_stocks']} stocks  "
          f"n={best_global['n_trades']} trades")

    if base:
        wr_d = best_global['wr'] - base['wr']
        rr_d = best_global['rr'] - base['rr']
        pf_d = best_global['pf'] - base['pf']
        pnl_d = best_global['pnl'] - base['pnl']
        print(f"\n  Improvement vs baseline:")
        print(f"    WR:  {base['wr']:.1f}% → {best_global['wr']:.1f}% ({wr_d:+.1f}pp)")
        print(f"    RR:  {base['rr']:.2f}x → {best_global['rr']:.2f}x ({rr_d:+.2f}x)")
        print(f"    PF:  {base['pf']:.1f} → {best_global['pf']:.1f} ({pf_d:+.1f})")
        print(f"    P&L: {base['pnl']:+.2f}% → {best_global['pnl']:+.2f}% ({pnl_d:+.2f}pp)")

    if p2:
        avg_wr_p2 = sum(o['wr'] for o in p2) / len(p2)
        avg_rr_p2 = sum(o['rr'] for o in p2) / len(p2)
        avg_pf_p2 = sum(o['pf'] for o in p2) / len(p2)
        print(f"\n  Per-stock optimal (avg of {len(p2)} stocks):")
        print(f"    WR={avg_wr_p2:.1f}%  RR={avg_rr_p2:.2f}x  PF={avg_pf_p2:.1f}")

    print(f"\n  Results saved:")
    print(f"    {OUT_DIR / 'opt_phase1.json'}")
    print(f"    {OUT_DIR / 'opt_phase2.json'}")
    print()


if __name__ == '__main__':
    main()
