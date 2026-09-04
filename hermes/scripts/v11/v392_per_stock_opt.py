#!/usr/bin/env python3
"""
V39.2: 自定义每股SL参数优化
为每只股票找到最优SL_multiplier

方法:
1. 对每只股票运行完整backtest_stock_v38，保存每笔交易的上下文
2. 对每只股票，在sl_mult网格上重算SL和trailing
3. 选择最优sl_mult (最高WR，若WR相同则选最高RR)

sl_mult网格: [0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
测试范围: 100只股票
"""

import json, sys, time, math, traceback
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.weekly_trend import synthesize_weekly, weekly_trend
from v11.structure_tree_v38 import StructureTree, calc_atr_v38, calc_stock_atr_profile
from v11.wyckoff_phases_v38 import detect_wyckoff_phases, get_phase_params

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v38')
OUTPUT_DIR.mkdir(exist_ok=True)

MIN_BARS = 120
MAX_HOLD = 60
MIN_VOL_RATIO = 0.6
MIN_TRADES_PER_STOCK = 2

SL_MULT_GRID = [0.15, 0.20, 0.25, 0.30, 0.40, 0.50]


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


def calc_v38_sl(ohlcv, entry_idx, entry_price, signal, entry_type,
                structure_tree, wyckoff_result, atr_params, direction, params,
                custom_sl_mult=None):
    """
    V38结构SL计算 (3层优先级)
    支持custom_sl_mult覆盖自适应阶段参数
    """
    # ── 1. 结构树SL (最高优先级) ──
    tree_sl = structure_tree.get_sl_level(entry_idx, entry_price)
    if tree_sl:
        sl_price, sl_name, sl_pct = tree_sl
        if direction == 'bear':
            sl_pct = (sl_price - entry_price) / entry_price * 100
        if 0.08 <= abs(sl_pct) <= 2.0:
            return sl_price, sl_name, abs(sl_pct)

    # ── 2. 信号结构SL ──
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

    # ── 3. ATR自适应SL (保底，支持custom_sl_mult) ──
    atr_pct = calc_atr_v38(ohlcv, entry_idx)
    phase = wyckoff_result.get('primary_phase', 'unknown')
    phase_params = get_phase_params(phase)

    sl_mult = custom_sl_mult if custom_sl_mult is not None else phase_params['sl_mult']
    base_sl = max(0.15, min(1.5, atr_pct * sl_mult * 0.3))

    if direction == 'bull':
        return round(entry_price * (1 - base_sl / 100), 4), 'adaptive', round(base_sl, 2)
    else:
        return round(entry_price * (1 + base_sl / 100), 4), 'adaptive', round(base_sl, 2)


def calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl,
                      structural_tp, n, max_hold, direction):
    """
    V38.4 差异化trailing (与原始版本完全一致)
    """
    sl = initial_sl
    extreme = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None

    is_bear = (direction == 'bear')
    has_tp = tp_price is not None

    if not has_tp:
        profile = 'tight'
    elif is_bear:
        profile = 'bear'
    else:
        profile = 'loose'

    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]

        if is_bear:
            if bar['l'] < extreme:
                extreme = bar['l']
            gain_pct = (entry_price - extreme) / entry_price * 100

            if tp_price and extreme <= tp_price * 1.05:
                sl = min(sl, entry_price * (1 - max(0.8, tp_pct * 0.5) / 100))
                if extreme <= tp_price * 1.02:
                    return j, tp_price, True
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
                exit_price = min(sl, bar['h'])
                return j, round(exit_price, 2), exit_price < entry_price

        else:
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100

            if tp_price and extreme >= tp_price * 0.90:
                sl = max(sl, entry_price * (1 + max(0.8, tp_pct * 0.5) / 100))
                if extreme >= tp_price * 0.98:
                    return j, tp_price, True
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
                exit_price = max(sl, bar['l'])
                return j, round(exit_price, 2), exit_price > entry_price

    exit_idx = min(entry_idx + max_hold, n - 1)
    exit_price = ohlcv[exit_idx]['c']
    won = exit_price > entry_price if not is_bear else exit_price < entry_price
    return exit_idx, round(exit_price, 2), won


def evaluate_v38_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n,
                       structure_tree, wyckoff_result, direction, params,
                       custom_sl_mult=None):
    """
    V38统一入场评估 (支持custom_sl_mult)
    与原始版本相同，但使用自定义calc_v38_sl
    """
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

    sweep_fvg_found = False
    choch_retest_found = False

    SWEEP_LOOKBACK = 5
    if (is_fvg or is_ob) and sig_idx > SWEEP_LOOKBACK:
        for ps in all_sigs_up_to_idx:
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

    RETEST_THRESHOLD = 0.5
    if (is_fvg or is_ob) and sig_idx > 5:
        sig_lower = sig.get('lower', 0)
        sig_upper = sig.get('upper', 0)
        for ps in all_sigs_up_to_idx:
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

    if is_fvg and quality >= 0.55:
        if sweep_fvg_found:
            entry_type = 'Sweep->FVG'
            signal_type = 'Sweep->FVG'
        elif choch_retest_found:
            entry_type = 'CHOCH->retest'
            signal_type = 'CHOCH->retest'
        else:
            entry_type = 'FVG'
            signal_type = 'FVG'
    elif is_ob and quality >= 0.50:
        if sweep_fvg_found:
            entry_type = 'Sweep->FVG'
            signal_type = 'Sweep->FVG'
        elif choch_retest_found:
            entry_type = 'CHOCH->retest'
            signal_type = 'CHOCH->retest'
        else:
            entry_type = 'OB'
            signal_type = 'OB'
    elif is_bb:
        bb_meta = sig.get('metadata', {})
        if bb_meta.get('has_fvg_overlap', False):
            entry_type = 'BreakerBlock'
            signal_type = 'BreakerBlock'
        else:
            return None
    else:
        return None

    # 成交量过滤
    if sig_idx > 30 and sig_idx < n:
        try:
            bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
            avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                         for j in range(max(0, sig_idx - 30), sig_idx)) / 30
            if bv < avg_vol * MIN_VOL_RATIO:
                return None
        except:
            pass

    # 趋势过滤
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

    # 序列+共振
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None

    window = ohlcv[:entry_bar + 1]
    tf_seq = {'daily': seq_r}
    res = evaluate_full_resonance_v11(
        all_signals=all_sigs_up_to_idx,
        tf_sequences=tf_seq,
        ohlcv=window)

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

    dec = make_entry_decision_v11(res, seq_r, params, tf_sequences=tf_seq)
    if dec['action'] != 'enter':
        return None

    # ATR自适应参数
    atr_pct = calc_atr_v38(ohlcv, entry_bar)
    atr_params = calc_stock_atr_profile(ohlcv)

    # 结构SL (使用custom_sl_mult)
    init_sl, sl_type_name, sl_pct_val = calc_v38_sl(
        ohlcv, entry_bar, entry_price, sig, entry_type,
        structure_tree, wyckoff_result, atr_params, direction, params,
        custom_sl_mult=custom_sl_mult)
    if init_sl is None:
        return None

    # 结构TP
    tp_price, tp_type, tp_pct, tp_idx = calc_v38_tp(
        ohlcv, entry_bar, entry_price, sig, entry_type,
        structure_tree, wyckoff_result, direction, all_signals)

    # Trailing (使用新的SL)
    exit_idx, exit_price, won = calc_v38_trailing(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, MAX_HOLD, direction)

    pnl = (exit_price - entry_price) / entry_price * 100
    if direction == 'bear':
        pnl = -pnl

    actual_sl_pct = abs(entry_price - init_sl) / entry_price * 100
    actual_rr = abs(pnl) / actual_sl_pct if actual_sl_pct > 0 else 10

    return {
        'entry_idx': entry_bar,
        'sig_idx': sig_idx,
        'confirmed_at': confirmed_at,
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
        'signal_type': signal_type,
        'entry_type': entry_type,
        'direction': direction,
        'exit_method': 'tp_hit' if tp_type and tp_price and (
            (direction == 'bull' and exit_price >= tp_price) or
            (direction == 'bear' and exit_price <= tp_price)
        ) else 'trailing',
        'phase': phase,
        'wyckoff_conf': round(wyckoff_conf, 2),
        'atr_pct': round(atr_pct, 2),
    }


def calc_v38_tp(ohlcv, entry_idx, entry_price, signal, entry_type,
                structure_tree, wyckoff_result, direction, all_signals):
    """V38结构TP计算 (与原始版本完全一致)"""
    tree_tp = structure_tree.get_tp_level(entry_idx, entry_price, direction)
    if tree_tp:
        tp_price, tp_name, tp_pct, tp_idx = tree_tp
        return tp_price, tp_name, tp_pct, tp_idx

    if direction == 'bull':
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bull' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 60]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('upper', 0))
            if tp_price > entry_price:
                tp_pct = (tp_price - entry_price) / entry_price * 100
                if tp_pct >= 0.3:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']
    else:
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bear' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 60]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('lower', 0))
            if tp_price > 0 and tp_price < entry_price:
                tp_pct = (entry_price - tp_price) / entry_price * 100
                if tp_pct >= 0.3:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']

    return None, None, None, None


def backtest_stock_v38(ohlcv, symbol, custom_sl_mult=None):
    """单股票V38回测 (支持custom_sl_mult)"""
    n = len(ohlcv)
    if n < MIN_BARS:
        return None

    structure_tree = StructureTree(ohlcv)
    wyckoff_result = detect_wyckoff_phases(ohlcv, structure_tree)
    phase = wyckoff_result.get('primary_phase', 'unknown')

    base_params = {
        'fvg_min_consecutive': 2,
        'sweep_lookback': 20,
        'max_fvg_gap_pct': 5.0,
        'min_fvg_gap_pct': 0.15,
        'swing_window': 5,
        'enable_bear': True,
    }
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_sigs = all_signals.get('all', [])

    if not all_sigs or len(all_sigs) < 3:
        return None

    all_trades = []
    used_long_bars = set()
    used_short_bars = set()

    for sig in all_sigs:
        sig_idx = sig.get('idx', 0)
        if sig_idx < 40 or sig_idx >= n - 10:
            continue

        sigs_up_to = [s for s in all_sigs if s.get('idx', 0) <= sig_idx]

        sig_type = sig.get('type', '')
        if 'Bull' in sig_type:
            result = evaluate_v38_entry(
                all_sigs, sigs_up_to, sig, ohlcv, n,
                structure_tree, wyckoff_result, 'bull', base_params,
                custom_sl_mult=custom_sl_mult)
            if result and result['entry_idx'] not in used_long_bars:
                used_long_bars.add(result['entry_idx'])
                all_trades.append(result)

        elif 'Bear' in sig_type:
            result = evaluate_v38_entry(
                all_sigs, sigs_up_to, sig, ohlcv, n,
                structure_tree, wyckoff_result, 'bear', base_params,
                custom_sl_mult=custom_sl_mult)
            if result and result['entry_idx'] not in used_short_bars:
                used_short_bars.add(result['entry_idx'])
                all_trades.append(result)

    if len(all_trades) < MIN_TRADES_PER_STOCK:
        return None

    wins = sum(1 for t in all_trades if t['won'])
    wr = wins / len(all_trades) * 100
    wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    avg_pnl = sum(t['pnl_pct'] for t in all_trades) / len(all_trades)
    avg_rr = sum(t['rr'] for t in all_trades) / len(all_trades)

    sl_types = Counter(t.get('sl_type', 'unknown') for t in all_trades)
    entry_types = Counter(t.get('entry_type', 'unknown') for t in all_trades)
    directions = Counter(t.get('direction', 'bull') for t in all_trades)

    return {
        'trades': all_trades,
        'perf': {
            'n_trades': len(all_trades),
            'wins': wins,
            'losses': len(all_trades) - wins,
            'win_rate': round(wr, 1),
            'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2),
            'sl_types': dict(sl_types),
            'entry_types': dict(entry_types),
            'directions': dict(directions),
            'phase': phase,
            'wyckoff_conf': wyckoff_result.get('confidence', 0),
        }
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])

    print("=" * 80)
    print("V39.2: 自定义每股SL参数优化")
    print(f"  SL_mult网格: {SL_MULT_GRID}")
    print(f"  测试范围: {len(symbols[:100])}只股票 (前100只)")
    print("=" * 80)

    t_start = time.time()
    results = {}
    stock_count = 0

    for idx, sym in enumerate(symbols[:100]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            continue

        # 先使用默认参数跑一次基准回测
        base_result = backtest_stock_v38(ohlcv, sym, custom_sl_mult=None)
        if not base_result:
            print(f"  [{idx + 1:3d}/100] {sym:12s} SKIP (no trades with default)")
            continue

        base_perf = base_result['perf']
        print(f"  [{idx + 1:3d}/100] {sym:12s} 基准: n={base_perf['n_trades']:2d} "
              f"WR={base_perf['win_rate']:.0f}% RR={base_perf['avg_rr']:.1f}x "
              f"adaptive={base_perf['sl_types'].get('adaptive', 0)}",
              end='')

        # 对每个sl_mult重跑
        grid_results = {}
        for sm in SL_MULT_GRID:
            # 重跑完整backtest
            opt_result = backtest_stock_v38(ohlcv, sym, custom_sl_mult=sm)
            if not opt_result:
                grid_results[str(sm)] = None
                continue

            p = opt_result['perf']
            grid_results[str(sm)] = {
                'win_rate': p['win_rate'],
                'avg_rr': p['avg_rr'],
                'n_trades': p['n_trades'],
                'profit_factor': p['profit_factor'],
                'avg_pnl': p['avg_pnl'],
                'sl_types': p['sl_types'],
            }

        # 选择最优sl_mult (最高WR，若WR相同则选最高RR)
        valid = {k: v for k, v in grid_results.items() if v is not None}
        if not valid:
            print(" → 无可用grid结果")
            continue

        best_sl_mult = max(valid.keys(), key=lambda k: (
            valid[k]['win_rate'],
            valid[k]['avg_rr']
        ))

        results[sym] = {
            'base': {
                'win_rate': base_perf['win_rate'],
                'avg_rr': base_perf['avg_rr'],
                'n_trades': base_perf['n_trades'],
                'adaptive_count': base_perf['sl_types'].get('adaptive', 0),
            },
            'grid': grid_results,
            'optimal_sl_mult': float(best_sl_mult),
            'optimal': valid[best_sl_mult],
        }

        print(f" → 最优: sl_mult={best_sl_mult} "
              f"WR={valid[best_sl_mult]['win_rate']:.0f}% "
              f"RR={valid[best_sl_mult]['avg_rr']:.1f}x")

        stock_count += 1

        if (idx + 1) % 30 == 0:
            time.sleep(0.1)

    total_time = time.time() - t_start

    # 汇总统计
    summary = {
        'config': 'V39.2 每股SL_mult优化',
        'sl_mult_grid': SL_MULT_GRID,
        'n_stocks_tested': 100,
        'n_stocks_tradable': stock_count,
        'total_time_seconds': round(total_time, 1),
        'per_stock': results,
    }

    # 整体统计: sl_mult分布
    sl_mult_dist = Counter()
    for sym, r in results.items():
        sl_mult_dist[str(r['optimal_sl_mult'])] += 1

    summary['sl_mult_distribution'] = dict(sl_mult_dist)

    # 改进统计
    improvements = []
    for sym, r in results.items():
        base_wr = r['base']['win_rate']
        base_rr = r['base']['avg_rr']
        opt_wr = r['optimal']['win_rate']
        opt_rr = r['optimal']['avg_rr']
        improvements.append({
            'symbol': sym,
            'base_wr': base_wr,
            'opt_wr': opt_wr,
            'wr_delta': round(opt_wr - base_wr, 1),
            'base_rr': base_rr,
            'opt_rr': opt_rr,
            'rr_delta': round(opt_rr - base_rr, 2),
        })

    summary['improvements'] = improvements

    # 平均改进
    avg_wr_delta = sum(i['wr_delta'] for i in improvements) / len(improvements) if improvements else 0
    avg_rr_delta = sum(i['rr_delta'] for i in improvements) / len(improvements) if improvements else 0
    summary['avg_wr_improvement'] = round(avg_wr_delta, 1)
    summary['avg_rr_improvement'] = round(avg_rr_delta, 2)

    # 输出
    outpath = OUTPUT_DIR / 'v392_per_stock_opt.json'
    outpath.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\n{'=' * 80}")
    print(f"V39.2 完成: {stock_count}/{100} stocks | {total_time:.0f}s")
    print(f"  sl_mult分布: {dict(sl_mult_dist)}")
    print(f"  平均WR改进: {avg_wr_delta:+.1f}%")
    print(f"  平均RR改进: {avg_rr_delta:+.2f}x")
    print(f"  输出: {outpath}")
    print()


if __name__ == '__main__':
    main()
