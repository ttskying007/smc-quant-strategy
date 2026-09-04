#!/usr/bin/env python3
"""
SMC V38.4 — Live Signal Monitor
=================================
每天扫描前2000只可交易股票的最新60根K线,
使用V38.4引擎检测入场信号, 按质量排序输出。

cron: 0 9 * * 1-5

Usage:
  PYTHONUNBUFFERED=1 python3 smc_live_monitor_v38.py
"""
import json, sys, time, math
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.structure_tree_v38 import StructureTree, calc_atr_v38, calc_stock_atr_profile
from v11.wyckoff_phases_v38 import detect_wyckoff_phases, get_phase_params
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
SIGNAL_DIR = Path('/root/.hermes/smc_signals')
SIGNAL_DIR.mkdir(exist_ok=True)

# === V38.4 PARAMS ===
LOOKBACK = 60
MAX_STOCKS = 2000
MIN_BARS = 120
MIN_VOL_RATIO = 0.6
SWEEP_LOOKBACK = 5
RETEST_THRESHOLD = 0.5
MAX_HOLD = 60

# Wyckoff phase SL multipliers (V38.4 config: all SL×0.5)
PHASE_SL_MULT = {
    'accumulation': 0.3,
    'markup': 0.4,
    'distribution': 0.25,
    'reaccumulation': 0.35,
}
BASE_SL_ATR_MULT = 0.3


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS:
        return None
    for bar in data:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    return data


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback:
        return 'neutral', 0
    seg = ohlcv[idx - lookback:idx + 1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e - s) / s * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx - min(5, idx), idx + 1)) / min(6, idx + 1)
    ema_d = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_d > 0:
        return 'up', change
    if change < -0.6 and ema_d < 0:
        return 'down', abs(change)
    return 'neutral', 0


def calc_v38_sl_lite(ohlcv, entry_idx, entry_price, signal, direction, structure_tree, wyckoff_result):
    """V38.4结构SL计算 (轻量版用于实盘监控)"""
    # 1. 结构树SL
    tree_sl = structure_tree.get_sl_level(entry_idx, entry_price)
    if tree_sl:
        sl_price, sl_name, sl_pct = tree_sl
        if direction == 'bear':
            sl_pct = (sl_price - entry_price) / entry_price * 100
        if 0.08 <= abs(sl_pct) <= 2.0:
            return sl_price, sl_name, abs(sl_pct)

    # 2. 信号结构SL
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

    # 3. ATR自适应SL (保底)
    atr_pct = calc_atr_v38(ohlcv, entry_idx)
    phase = wyckoff_result.get('primary_phase', 'unknown')
    sl_mult = PHASE_SL_MULT.get(phase, 0.3)
    base_sl = max(0.15, min(1.5, atr_pct * sl_mult * BASE_SL_ATR_MULT))

    if direction == 'bull':
        return round(entry_price * (1 - base_sl / 100), 4), 'adaptive', round(base_sl, 2)
    else:
        return round(entry_price * (1 + base_sl / 100), 4), 'adaptive', round(base_sl, 2)


def calc_v38_tp_lite(ohlcv, entry_idx, entry_price, all_signals, direction):
    """V38.4结构TP计算 (轻量版)"""
    # 前方CHOCH
    if direction == 'bull':
        forward = [s for s in all_signals
                   if 'CHOCH_Bull' in s.get('type', '')
                   and s.get('idx', 0) > entry_idx
                   and s.get('idx', 0) <= entry_idx + 60]
        if forward:
            nearest = min(forward, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('upper', 0))
            if tp_price > entry_price:
                tp_pct = (tp_price - entry_price) / entry_price * 100
                if tp_pct >= 0.3:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2)
    else:
        forward = [s for s in all_signals
                   if 'CHOCH_Bear' in s.get('type', '')
                   and s.get('idx', 0) > entry_idx
                   and s.get('idx', 0) <= entry_idx + 60]
        if forward:
            nearest = min(forward, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('lower', 0))
            if tp_price > 0 and tp_price < entry_price:
                tp_pct = (entry_price - tp_price) / entry_price * 100
                if tp_pct >= 0.3:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2)
    return None, None, None


def calc_v38_trailing_lite(ohlcv, entry_idx, entry_price, initial_sl, tp_price, n, direction):
    """V38.4 3-profile trailing (轻量版)"""
    sl = initial_sl
    extreme = entry_price
    has_tp = tp_price is not None
    is_bear = direction == 'bear'

    if not has_tp:
        profile = 'tight'
    elif is_bear:
        profile = 'bear'
    else:
        profile = 'loose'

    for j in range(entry_idx + 1, min(entry_idx + MAX_HOLD + 1, n)):
        bar = ohlcv[j]

        if is_bear:
            if bar['l'] < extreme:
                extreme = bar['l']
            gain_pct = (entry_price - extreme) / entry_price * 100

            if tp_price and extreme <= tp_price * 1.05:
                sl = min(sl, entry_price * (1 - 0.8 / 100))
                if extreme <= tp_price * 1.02:
                    return j, tp_price, 'tp_hit'
            else:
                if profile == 'tight':
                    if gain_pct >= 3.0:
                        sl = min(sl, extreme * (1 + 1.0 / 100))
                    elif gain_pct >= 1.5:
                        sl = min(sl, extreme * (1 + 0.5 / 100))
                    elif gain_pct >= 0.7:
                        sl = min(sl, entry_price * (1 + 0.2 / 100))
                    elif gain_pct >= 0.4:
                        sl = min(sl, entry_price * (1 + 0.05 / 100))
                    elif gain_pct >= 0.2:
                        sl = min(sl, entry_price * 1.0)
                elif profile == 'bear':
                    if gain_pct >= 6.0:
                        sl = min(sl, extreme * (1 + 3.0 / 100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, extreme * (1 + 1.5 / 100))
                    elif gain_pct >= 1.5:
                        sl = min(sl, entry_price * (1 + 0.3 / 100))
                    elif gain_pct >= 1.0:
                        sl = min(sl, entry_price * (1 + 0.1 / 100))
                    elif gain_pct >= 0.35:
                        sl = min(sl, entry_price * 1.0)
                else:
                    if gain_pct >= 6.0:
                        sl = min(sl, extreme * (1 + 3.0 / 100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, extreme * (1 + 1.5 / 100))
                    elif gain_pct >= 1.5:
                        sl = min(sl, entry_price * (1 + 0.3 / 100))
                    elif gain_pct >= 1.0:
                        sl = min(sl, entry_price * (1 + 0.1 / 100))
                    elif gain_pct >= 0.5:
                        sl = min(sl, entry_price * 1.0)

            if bar['h'] >= sl:
                return j, round(min(sl, bar['h']), 2), 'trailing'

        else:
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100

            if tp_price and extreme >= tp_price * 0.90:
                sl = max(sl, entry_price * (1 + 0.8 / 100))
                if extreme >= tp_price * 0.98:
                    return j, tp_price, 'tp_hit'
            else:
                if profile == 'tight':
                    if gain_pct >= 3.0:
                        sl = max(sl, extreme * (1 - 1.0 / 100))
                    elif gain_pct >= 1.5:
                        sl = max(sl, extreme * (1 - 0.5 / 100))
                    elif gain_pct >= 0.7:
                        sl = max(sl, entry_price * (1 + 0.2 / 100))
                    elif gain_pct >= 0.4:
                        sl = max(sl, entry_price * (1 + 0.05 / 100))
                    elif gain_pct >= 0.2:
                        sl = max(sl, entry_price * 1.0)
                else:
                    if gain_pct >= 6.0:
                        sl = max(sl, extreme * (1 - 3.0 / 100))
                    elif gain_pct >= 3.0:
                        sl = max(sl, extreme * (1 - 1.5 / 100))
                    elif gain_pct >= 1.5:
                        sl = max(sl, entry_price * (1 + 0.3 / 100))
                    elif gain_pct >= 1.0:
                        sl = max(sl, entry_price * (1 + 0.1 / 100))
                    elif gain_pct >= 0.5:
                        sl = max(sl, entry_price * 1.0)

            if bar['l'] <= sl:
                return j, round(max(sl, bar['l']), 2), 'trailing'

    exit_idx = min(entry_idx + MAX_HOLD, n - 1)
    return exit_idx, round(ohlcv[exit_idx]['c'], 2), 'max_hold'


def check_stock_v38(ohlcv, symbol):
    """V38.4实时信号检测 - 单股票"""
    n = len(ohlcv)
    if n < MIN_BARS:
        return None

    # 初始化V38组件
    structure_tree = StructureTree(ohlcv)
    wyckoff_result = detect_wyckoff_phases(ohlcv, structure_tree)

    base_params = {
        'fvg_min_consecutive': 2,
        'sweep_lookback': 20,
        'max_fvg_gap_pct': 5.0,
        'min_fvg_gap_pct': 0.15,
        'swing_window': 5,
        'enable_bear': True,
    }

    all_sig_result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_signals = all_sig_result.get('all', [])

    if not all_signals or len(all_signals) < 3:
        return None

    signals_found = []
    entered_bar = -999

    # 只扫描最后LOOKBACK根K线
    scan_start = max(n - LOOKBACK, 80)

    for i in range(scan_start, n - 10):
        if i - entered_bar < 15:
            continue

        sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
        if len(sigs_before) < 3:
            continue

        # 序列分析
        seq_result = analyze_sequence_v11(sigs_before, params=base_params)
        best_seq = seq_result.get('best_sequence')
        if not best_seq:
            continue

        seq_name = best_seq.get('name', '')
        if 'SCOUT' not in seq_name:
            continue

        seq_dir = 'bull' if 'LONG' in seq_name else 'bear'

        # 获取入口信号
        from v11.rolling_backtest_v15 import get_entry_signal_info
        sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
        if sig_idx == 0 and not sig_type:
            continue

        # 信号质量
        quality = sig.get('confidence', sig.get('quality', 0.5))

        # 入口类型判定
        sig_type_check = sig.get('type', sig_type)
        is_fvg = 'FVG' in sig_type_check and 'Mitigated' not in sig_type_check and 'IFVG' not in sig_type_check
        is_ob = 'OB' in sig_type_check and 'BreakerBlock' not in sig_type_check
        is_bb = 'BreakerBlock' in sig_type_check

        # Sweep→FVG检测
        sweep_fvg_found = False
        choch_retest_found = False
        if (is_fvg or is_ob) and sig_idx > SWEEP_LOOKBACK:
            for ps in sigs_before[:-1]:
                ps_type = ps.get('type', '')
                ps_idx = ps.get('idx', 0)
                if seq_dir == 'bull' and 'SweepDown' in ps_type:
                    if 0 < sig_idx - ps_idx <= SWEEP_LOOKBACK:
                        sweep_fvg_found = True
                        break
                elif seq_dir == 'bear' and 'SweepUp' in ps_type:
                    if 0 < sig_idx - ps_idx <= SWEEP_LOOKBACK:
                        sweep_fvg_found = True
                        break

        # CHOCH→retest检测
        if (is_fvg or is_ob) and sig_idx > 5:
            for ps in sigs_before:
                ps_type = ps.get('type', '')
                ps_idx = ps.get('idx', 0)
                if 'CHOCH' not in ps_type:
                    continue
                if seq_dir == 'bull' and 'CHOCH_Bull' in ps_type:
                    bl = ps.get('metadata', {}).get('break_level', ps.get('lower', 0))
                    if bl > 0 and abs(ohlcv[i]['c'] - bl) / max(bl, 0.01) * 100 < RETEST_THRESHOLD:
                        if 0 < sig_idx - ps_idx <= 20:
                            choch_retest_found = True
                            break
                elif seq_dir == 'bear' and 'CHOCH_Bear' in ps_type:
                    bl = ps.get('metadata', {}).get('break_level', ps.get('upper', 0))
                    if bl > 0 and abs(ohlcv[i]['c'] - bl) / max(bl, 0.01) * 100 < RETEST_THRESHOLD:
                        if 0 < sig_idx - ps_idx <= 20:
                            choch_retest_found = True
                            break

        # 入口类型确定
        entry_type = None
        if is_fvg and quality >= 0.55:
            entry_type = 'Sweep→FVG' if sweep_fvg_found else ('CHOCH→retest' if choch_retest_found else 'FVG')
        elif is_ob and quality >= 0.50:
            entry_type = 'Sweep→FVG' if sweep_fvg_found else ('CHOCH→retest' if choch_retest_found else 'OB')
        elif is_bb:
            bb_meta = sig.get('metadata', {})
            if bb_meta.get('has_fvg_overlap', False):
                entry_type = 'BreakerBlock'

        if not entry_type:
            continue

        # 成交量检查
        if sig_idx > 30 and sig_idx < n:
            bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
            avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                         for j in range(max(0, sig_idx - 30), sig_idx)) / 30
            if bar_vol < avg_vol * MIN_VOL_RATIO:
                continue

        # 趋势过滤
        td, _ = short_trend(ohlcv, i)
        if seq_dir == 'bull' and td == 'down':
            continue
        if seq_dir == 'bear' and td == 'up':
            continue

        # 多层趋势过滤
        micro = short_trend(ohlcv, i, 8)
        meso = short_trend(ohlcv, i, 20)
        macro = short_trend(ohlcv, i, 40)
        uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
        dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
        if seq_dir == 'bull' and dc >= 2:
            continue
        if seq_dir == 'bear' and uc >= 2:
            continue

        # 共振过滤
        window = ohlcv[:i + 1]
        tf_seq = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(
            all_signals=sigs_before, tf_sequences=tf_seq, ohlcv=window)

        phase = wyckoff_result.get('primary_phase', 'unknown')
        phase_params = get_phase_params(phase)
        mr = phase_params['min_score']
        if seq_dir == 'bull':
            mr = max(mr, 0.50)
        else:
            mr = max(mr, 0.55)

        if resonance.total < mr:
            continue

        dec = make_entry_decision_v11(resonance, seq_result, base_params, tf_sequences=tf_seq)
        if dec['action'] != 'enter':
            continue

        entry_price = dec.get('entry_price', ohlcv[i]['c'])

        # SL/TP计算
        init_sl, sl_type_name, sl_pct_val = calc_v38_sl_lite(
            ohlcv, i, entry_price, sig, seq_dir, structure_tree, wyckoff_result)
        if init_sl is None:
            continue

        tp_price, tp_type, tp_pct = calc_v38_tp_lite(
            ohlcv, i, entry_price, all_signals, seq_dir)

        # Trailing
        exit_idx, exit_price, exit_method = calc_v38_trailing_lite(
            ohlcv, i, entry_price, init_sl, tp_price, n, seq_dir)

        # 预计盈亏
        pnl = (exit_price - entry_price) / entry_price * 100
        if seq_dir == 'bear':
            pnl = -pnl

        actual_sl_pct = abs(entry_price - init_sl) / entry_price * 100
        actual_rr = abs(pnl) / actual_sl_pct if actual_sl_pct > 0 else 10

        # 综合质量评分
        quality_score = resonance.total
        if seq_dir == 'bull':
            quality_score += 0.1
        quality_score += uc / 6.0
        quality_score += min(sweep_fvg_found * 0.15, 0.15)
        quality_score += min(actual_rr / 20, 0.2)
        quality_score = round(min(quality_score, 1.0), 3)

        signals_found.append({
            'symbol': symbol,
            'entry_type': entry_type,
            'direction': seq_dir,
            'entry_price': round(entry_price, 2),
            'sl': round(init_sl, 2),
            'sl_type': sl_type_name,
            'tp': round(tp_price, 2) if tp_price else None,
            'tp_type': tp_type,
            'exit_method': exit_method,
            'expected_pnl': round(pnl, 2),
            'expected_rr': round(actual_rr, 2),
            'quality': quality_score,
            'resonance': round(resonance.total, 3),
            'phase': phase,
            'wyckoff_conf': round(wyckoff_result.get('confidence', 0), 2),
            'bar_idx': i,
            'bar_date': ohlcv[i].get('date', ohlcv[i].get('t', '')),
        })
        entered_bar = i

    return signals_found


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SMC V38.4 Live Signal Monitor')
    parser.add_argument('--top', type=int, default=30, help='Show top N signals')
    parser.add_argument('--quick', action='store_true', help='Scan fewer stocks')
    args = parser.parse_args()

    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])

    if args.quick:
        symbols = symbols[:200]
    else:
        symbols = symbols[:MAX_STOCKS]

    print(f"SMC V38.4 Live Monitor — Scanning {len(symbols)} stocks...", flush=True)
    print(f"  Engine: V38.4 (Wyckoff+Structure+3-profile trailing)", flush=True)
    print(f"  Lookback: {LOOKBACK} bars | Max: {MAX_STOCKS} stocks", flush=True)

    all_signals = []
    t_start = time.time()

    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            continue

        signals = check_stock_v38(ohlcv, sym)
        if signals:
            all_signals.extend(signals)

        if (idx + 1) % 100 == 0:
            elapsed = time.time() - t_start
            print(f"  [{idx + 1}/{len(symbols)}] {len(all_signals)} signals | {elapsed:.0f}s", flush=True)

    total_time = time.time() - t_start
    print(f"\n{'=' * 80}", flush=True)
    print(f"SCAN COMPLETE — {len(symbols)} stocks in {total_time:.0f}s", flush=True)
    print(f"Total Signals: {len(all_signals)}", flush=True)
    print(f"{'=' * 80}", flush=True)

    if not all_signals:
        print("No signals found.", flush=True)
        sys.exit(0)

    # 按质量排序
    all_signals.sort(key=lambda x: -x['quality'])

    # 统计
    et_counts = Counter(s['entry_type'] for s in all_signals)
    dir_counts = Counter(s['direction'] for s in all_signals)
    ph_counts = Counter(s['phase'] for s in all_signals)

    print(f"\nEntry types: {dict(et_counts)}", flush=True)
    print(f"Directions: {dict(dir_counts)}", flush=True)
    print(f"Phases: {dict(ph_counts)}", flush=True)

    print(f"\nTop {args.top} Signals:", flush=True)
    print(f"{'#':<4} {'Symbol':<12} {'Type':<12} {'Dir':<6} {'Entry':<10} {'SL':<10} {'TP':<10} "
          f"{'RR':<6} {'Q':<6} {'Phase':<14} {'Date':<12}", flush=True)
    print("-" * 110, flush=True)

    for i, s in enumerate(all_signals[:args.top]):
        tp_str = f"{s['tp']:.2f}" if s['tp'] else 'NONE'
        print(f"{i + 1:<4} {s['symbol']:<12} {s['entry_type']:<12} {s['direction']:<6} "
              f"{s['entry_price']:<10.2f} {s['sl']:<10.2f} {tp_str:<10} "
              f"{s['expected_rr']:<6.1f}x {s['quality']:<6.3f} {s['phase']:<14} {s['bar_date']:<12}", flush=True)

    # 保存
    outpath = SIGNAL_DIR / f'live_v38_signals_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    json.dump({
        'timestamp': datetime.now().isoformat(),
        'config': {'version': 'V38.4', 'scan_stocks': len(symbols)},
        'summary': {
            'total_signals': len(all_signals),
            'entry_types': dict(et_counts),
            'directions': dict(dir_counts),
        },
        'signals': all_signals[:100],
    }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved: {outpath}", flush=True)

    latest = SIGNAL_DIR / 'latest_v38_signals.json'
    json.dump({'timestamp': datetime.now().isoformat(), 'signals': all_signals[:50]},
              open(latest, 'w'), default=str)
    print(f"Latest: {latest}", flush=True)


if __name__ == '__main__':
    main()
