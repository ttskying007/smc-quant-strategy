#!/usr/bin/env python3
"""
V38 — 多自适应共振交易系统
============================
融合:
- 结构树 (micro/meso/macro 层次化摆动点)
- Wyckoff阶段 (accumulation/markup/distribution/reaccumulation)
- 每股ATR特征参数自适应
- 多入口类型 (FVG/OB/Sweep→FVG/CHOCH→retest/BB+FVG)
- 做空交易 (Bear全信号入口)
- 阶段自适应SL/TP乘数
- 周线多层聚合

入场规则:
  Long:
    - FVG_Bull (质量≥0.6)
    - OB_Bull (质量≥0.55)
    - Sweep→FVG_Bull (sweep后3-5bar内FVG)
    - BreakerBlock_Bull+FVG重叠(一击必中)
    - CHOCH_Bull→retest (CHOCH后回测不破入场)
  Short:
    - FVG_Bear (质量≥0.6)
    - OB_Bear (质量≥0.55)
    - Sweep→FVG_Bear (sweep后3-5bar内FVG)
    - BreakerBlock_Bear+FVG重叠
    - CHOCH_Bear→retest
"""

import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict

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

# ── 全局参数 (硬编码→将被自适应替代) ──
MIN_BARS = 120
MAX_HOLD = 60
MIN_VOL_RATIO = 0.6  # 放宽到0.6(比V36的0.7宽松)
MIN_TRADES_PER_STOCK = 2

# ── ATR网格搜索参数 ──
SL_MULT_RANGE = [0.15, 0.25, 0.30, 0.40, 0.50, 0.60, 0.80]
TP_MULT_RANGE = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
# 注意: 实际SL = atr_pct * SL_MULT, TP = sl_pct * TP_MULT


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_daily_300.json"
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
    seg = ohlcv[idx-lookback:idx+1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e - s) / s * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5, idx), idx+1)) / min(6, idx+1)
    ema_d = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_d > 0:
        return 'up', change
    if change < -0.6 and ema_d < 0:
        return 'down', abs(change)
    return 'neutral', 0


def find_entry_signal(all_signals, entry_bar, direction='bull'):
    """
    在entry_bar位置寻找可用入场信号
    返回可用的信号条目
    """
    candidates = []
    for sig in all_signals:
        sig_idx = sig.get('idx', 0)
        sig_type = sig.get('type', '')
        confirmed_at = sig.get('confirmed_at', sig_idx)
        entry_ok = max(sig_idx, confirmed_at) <= entry_bar
        
        if not entry_ok:
            continue
        
        # 根据方向过滤
        if direction == 'bull' and 'Bull' not in sig_type:
            continue
        if direction == 'bear' and 'Bear' not in sig_type:
            continue
        
        # 信号类型
        is_fvg = 'FVG' in sig_type and 'Mitigated' not in sig_type
        is_ob = 'OB' in sig_type and 'BreakerBlock' not in sig_type
        is_bb = 'BreakerBlock' in sig_type
        is_choch = 'CHOCH' in sig_type
        is_sweep = 'Sweep' in sig_type
        
        # 质量评分
        quality = sig.get('confidence', sig.get('quality', 0.5))
        
        if is_fvg and quality >= 0.55:
            candidates.append({'sig': sig, 'entry_type': 'FVG', 'priority': 1, 'quality': quality})
        elif is_ob and quality >= 0.50:
            candidates.append({'sig': sig, 'entry_type': 'OB', 'priority': 2, 'quality': quality})
        elif is_bb:
            bb_meta = sig.get('metadata', {})
            if bb_meta.get('has_fvg_overlap', False):
                candidates.append({'sig': sig, 'entry_type': 'BreakerBlock', 'priority': 3, 'quality': quality + 0.15})
        elif is_choch:
            # CHOCH入场: 需要CHOCH后的回测形态
            # 检查CHOCH后是否有价格回测到CHOCH break_level附近
            retest_found = False
            brk_level = sig.get('break_level', 0)
            if brk_level > 0:
                for j in range(sig_idx + 1, min(sig_idx + 8, entry_bar + 1)):
                    if j < len(ohlcv) if 'ohlcv' in dir() else True:
                        continue  # 简化为较低优先级CHOCH entry
        
        # Sweep单信号不直接入场 (需要配合FVG/OB)
    
    # 按优先级+质量排序
    candidates.sort(key=lambda c: (c['priority'], -c['quality']))
    return candidates[0] if candidates else None


# ── 接下来写核心回测函数 ──

def atr_grid_search(ohlcv, symbol, all_signals, structure_tree, wyckoff_result):
    """
    每股ATR网格搜索: 在SL_MULT×TP_MULT网格上搜索最优参数组合
    返回最优参数的SL/TP
    """
    atr_profile = calc_stock_atr_profile(ohlcv)
    base_atr = atr_profile['atr14']
    vol_class = atr_profile['vol_class']
    phase = wyckoff_result.get('primary_phase', 'unknown')
    phase_params = get_phase_params(phase)
    
    # 基于波动率类别的自适应范围
    if vol_class == 'high':
        sl_range = [m for m in SL_MULT_RANGE if m >= 0.25]
    elif vol_class == 'low':
        sl_range = [m for m in SL_MULT_RANGE if m <= 0.60]
    else:
        sl_range = SL_MULT_RANGE
    
    # 阶段因子
    sl_phase_mult = phase_params['sl_mult']
    tp_phase_mult = phase_params['tp_mult']
    
    # 返回自适应后的sl_pct和tp_factor
    # 实际SL值将在评估时计算
    return {
        'sl_mult': base_atr * sl_phase_mult * 0.3,  # 基准: atr*0.3*阶段
        'tp_mult': tp_phase_mult,
        'vol_class': vol_class,
        'atr_pct': base_atr,
    }


def calc_v38_sl(ohlcv, entry_idx, entry_price, signal, entry_type,
                structure_tree, wyckoff_result, atr_params, direction, params):
    """
    V38结构SL计算 (3层优先级)
    1. 结构树SL (micro/meso/macro优先级)
    2. 信号结构SL (FVG下边界/OB下边界)
    3. ATR自适应SL (保底)
    """
    # ── 1. 结构树SL (最高优先级) ──
    tree_sl = structure_tree.get_sl_level(entry_idx, entry_price)
    if tree_sl:
        sl_price, sl_name, sl_pct = tree_sl
        # 对于bear交易, SL应在上方
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
    else:  # bear
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
    
    # ── 3. ATR自适应SL (保底) ──
    atr_pct = calc_atr_v38(ohlcv, entry_idx)
    phase = wyckoff_result.get('primary_phase', 'unknown')
    phase_params = get_phase_params(phase)
    
    sl_mult = phase_params['sl_mult']
    base_sl = max(0.15, min(1.5, atr_pct * sl_mult * 0.3))
    
    if direction == 'bull':
        return round(entry_price * (1 - base_sl/100), 4), 'adaptive', round(base_sl, 2)
    else:
        return round(entry_price * (1 + base_sl/100), 4), 'adaptive', round(base_sl, 2)


def calc_v38_tp(ohlcv, entry_idx, entry_price, signal, entry_type,
                structure_tree, wyckoff_result, direction, all_signals):
    """
    V38结构TP计算 (3层优先级)
    """
    # ── 1. 结构树TP (micro→meso→macro优先级) ──
    tree_tp = structure_tree.get_tp_level(entry_idx, entry_price, direction)
    if tree_tp:
        tp_price, tp_name, tp_pct, tp_idx = tree_tp
        return tp_price, tp_name, tp_pct, tp_idx
    
    # ── 2. 前方CHOCH (最可靠结构阻力/支撑) ──
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
    
    # ── 3. 无结构TP → trailing ──
    return None, None, None, None


def calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl,
                       structural_tp, n, max_hold, direction):
    """
    V38.4 差异化trailing:
    - 修复: BearTP检测bug(方向无关的0.98乘数 → 方向感知)
    - 新增: 无结构TP交易使用紧trailing(锁利更快)
    - 新增: Bear方向使用更激进trailing
    
    三个profile:
      PROFILE_LOOSE (Bull+hasTP): 当前V38.2 2x放宽基线
      PROFILE_BEAR  (Bear+hasTP): 稍紧(Bear有上升漂移阻力)
      PROFILE_TIGHT (noTP+任意方向): 最紧(尽快逃逸)
    """
    sl = initial_sl
    extreme = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None
    
    is_bear = (direction == 'bear')
    has_tp = tp_price is not None
    
    # 选择profile
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
            
            # ── 有结构TP: 方向感知的TP接近检测 ──
            if tp_price and extreme <= tp_price * 1.05:  # 10%→5%, 更贴近TP实际位置
                sl = min(sl, entry_price * (1 - max(0.8, tp_pct * 0.5) / 100))
                # FIX: bear TP检测用 1.02 (2%高于TP) 而非 0.98 (2%低于TP)
                # 旧: extreme <= tp_price * 0.98 → 需过冲2%才触发
                # 新: extreme <= tp_price * 1.02 → 到达TP上方2%即触发
                if extreme <= tp_price * 1.02:
                    return j, tp_price, True
            else:
                # profile已选的trailing阈值
                if profile == 'tight':
                    if gain_pct >= 3.0:
                        sl = min(sl, extreme * (1 + 1.0/100))
                    elif gain_pct >= 1.5:
                        sl = min(sl, extreme * (1 + 0.5/100))
                    elif gain_pct >= 0.7:
                        sl = min(sl, entry_price * (1 + 0.2/100))
                    elif gain_pct >= 0.4:
                        sl = min(sl, entry_price * (1 + 0.05/100))
                    elif gain_pct >= 0.2:
                        sl = min(sl, entry_price * 1.0)
                elif profile == 'bear':
                    if gain_pct >= 6.0:
                        sl = min(sl, extreme * (1 + 3.0/100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, extreme * (1 + 1.5/100))
                    elif gain_pct >= 1.5:
                        sl = min(sl, entry_price * (1 + 0.3/100))
                    elif gain_pct >= 1.0:
                        sl = min(sl, entry_price * (1 + 0.1/100))
                    elif gain_pct >= 0.35:
                        sl = min(sl, entry_price * 1.0)
                else:  # loose (Bull+hasTP)
                    if gain_pct >= 6.0:
                        sl = min(sl, extreme * (1 + 3.0/100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, extreme * (1 + 1.5/100))
                    elif gain_pct >= 1.5:
                        sl = min(sl, entry_price * (1 + 0.3/100))
                    elif gain_pct >= 1.0:
                        sl = min(sl, entry_price * (1 + 0.1/100))
                    elif gain_pct >= 0.5:
                        sl = min(sl, entry_price * 1.0)

            # 做空退出检查
            if bar['h'] >= sl:
                exit_price = min(sl, bar['h'])
                return j, round(exit_price, 2), exit_price < entry_price

        else:  # bull
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100
            
            # 有结构TP: 强烈hold到接近TP
            if tp_price and extreme >= tp_price * 0.90:
                sl = max(sl, entry_price * (1 + max(0.8, tp_pct * 0.5) / 100))
                if extreme >= tp_price * 0.98:
                    return j, tp_price, True
            else:
                if profile == 'tight':
                    if gain_pct >= 3.0:
                        sl = max(sl, extreme * (1 - 1.0/100))
                    elif gain_pct >= 1.5:
                        sl = max(sl, extreme * (1 - 0.5/100))
                    elif gain_pct >= 0.7:
                        sl = max(sl, entry_price * (1 + 0.2/100))
                    elif gain_pct >= 0.4:
                        sl = max(sl, entry_price * (1 + 0.05/100))
                    elif gain_pct >= 0.2:
                        sl = max(sl, entry_price * 1.0)
                else:  # loose (bull)
                    if gain_pct >= 6.0:
                        sl = max(sl, extreme * (1 - 3.0/100))
                    elif gain_pct >= 3.0:
                        sl = max(sl, extreme * (1 - 1.5/100))
                    elif gain_pct >= 1.5:
                        sl = max(sl, entry_price * (1 + 0.3/100))
                    elif gain_pct >= 1.0:
                        sl = max(sl, entry_price * (1 + 0.1/100))
                    elif gain_pct >= 0.5:
                        sl = max(sl, entry_price * 1.0)

            # 做多退出检查
            if bar['l'] <= sl:
                exit_price = max(sl, bar['l'])
                return j, round(exit_price, 2), exit_price > entry_price
    
    # Max hold
    exit_idx = min(entry_idx + max_hold, n - 1)
    exit_price = ohlcv[exit_idx]['c']
    won = exit_price > entry_price if not is_bear else exit_price < entry_price
    return exit_idx, round(exit_price, 2), won


def evaluate_v38_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n,
                        structure_tree, wyckoff_result, direction, params):
    """
    V38统一入场评估 (多入口类型 + 做空)
    """
    sig_type = sig.get('type', '')
    sig_idx = sig.get('idx', 0)
    confirmed_at = sig.get('confirmed_at', sig_idx)
    entry_bar = max(sig_idx, confirmed_at)
    
    if entry_bar >= n - 2:
        return None
    
    entry_price = ohlcv[entry_bar]['c']
    
    # ── 入口类型判定 ──
    is_fvg = 'FVG' in sig_type and 'Mitigated' not in sig_type and 'IFVG' not in sig_type
    is_ob = 'OB' in sig_type and 'BreakerBlock' not in sig_type
    is_bb = 'BreakerBlock' in sig_type
    is_sweep = 'Sweep' in sig_type
    is_choch = 'CHOCH' in sig_type
    
    quality = sig.get('confidence', sig.get('quality', 0.5))
    
    # 标记: Sweep/FVG是否在附近
    sweep_fvg_found = False
    choch_retest_found = False
    
    # ── Sweep→FVG: 在FVG/OB信号时搜索前方Sweep ──
    SWEEP_LOOKBACK = 5  # sweep后N个bar内的FVG/OB视为Sweep→FVG
    if (is_fvg or is_ob) and sig_idx > SWEEP_LOOKBACK:
        for ps in all_sigs_up_to_idx:
            ps_type = ps.get('type', '')
            ps_idx = ps.get('idx', 0)
            # Bull: SweepDown(SSL猎杀) → FVG/OB_Bull
            if direction == 'bull' and 'SweepDown' in ps_type:
                if 0 < sig_idx - ps_idx <= SWEEP_LOOKBACK:
                    sweep_fvg_found = True
                    break
            # Bear: SweepUp(BSL猎杀) → FVG/OB_Bear
            elif direction == 'bear' and 'SweepUp' in ps_type:
                if 0 < sig_idx - ps_idx <= SWEEP_LOOKBACK:
                    sweep_fvg_found = True
                    break
    
    # ── CHOCH→retest: 在CHOCH break_level附近形成FVG/OB ──
    RETEST_THRESHOLD = 0.5  # retest价格偏差阈值(%)
    if (is_fvg or is_ob) and sig_idx > 5:
        # 获取信号的lower/upper范围
        sig_lower = sig.get('lower', 0)
        sig_upper = sig.get('upper', 0)
        for ps in all_sigs_up_to_idx:
            ps_type = ps.get('type', '')
            ps_idx = ps.get('idx', 0)
            if 'CHOCH' not in ps_type:
                continue
            # Bull: CHOCH_Bull break_level上方回测不破
            if direction == 'bull' and 'CHOCH_Bull' in ps_type:
                bl = ps.get('metadata', {}).get('break_level', ps.get('lower', 0))
                if bl > 0 and abs(entry_price - bl) / max(bl, 0.01) * 100 < RETEST_THRESHOLD:
                    # 确认CHOCH在合理时间内
                    if 0 < sig_idx - ps_idx <= 20:
                        choch_retest_found = True
                        break
            # Bear: CHOCH_Bear break_level下方回测不破
            elif direction == 'bear' and 'CHOCH_Bear' in ps_type:
                bl = ps.get('metadata', {}).get('break_level', ps.get('upper', 0))
                if bl > 0 and abs(entry_price - bl) / max(bl, 0.01) * 100 < RETEST_THRESHOLD:
                    if 0 < sig_idx - ps_idx <= 20:
                        choch_retest_found = True
                        break
    
    # ── 入口优先级: Sweep→FVG > CHOCH→retest > FVG > OB > BreakerBlock ──
    if is_fvg and quality >= 0.55:
        if sweep_fvg_found:
            entry_type = 'Sweep→FVG'
            signal_type = 'Sweep→FVG'
        elif choch_retest_found:
            entry_type = 'CHOCH→retest'
            signal_type = 'CHOCH→retest'
        else:
            entry_type = 'FVG'
            signal_type = 'FVG'
    elif is_ob and quality >= 0.50:
        if sweep_fvg_found:
            entry_type = 'Sweep→FVG'
            signal_type = 'Sweep→FVG'
        elif choch_retest_found:
            entry_type = 'CHOCH→retest'
            signal_type = 'CHOCH→retest'
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
    
    # ── 成交量过滤 ──
    if sig_idx > 30 and sig_idx < n:
        try:
            bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
            avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                         for j in range(max(0, sig_idx-30), sig_idx)) / 30
            if bv < avg_vol * MIN_VOL_RATIO:
                return None
        except:
            pass
    
    # ── 趋势过滤 ──
    td, _ = short_trend(ohlcv, entry_bar)
    if direction == 'bull' and td == 'down':
        return None
    if direction == 'bear' and td == 'up':
        return None
    
    # 周线趋势
    weekly = synthesize_weekly(ohlcv[:entry_bar+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if direction == 'bull' and wt == 'down':
            return None
        if direction == 'bear' and wt == 'up':
            return None
    
    # 三层趋势检查
    micro = short_trend(ohlcv, entry_bar, 8)
    meso = short_trend(ohlcv, entry_bar, 20)
    macro = short_trend(ohlcv, entry_bar, 40)
    
    uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
    
    if direction == 'bull':
        if dc >= 2 or (uc == 1 and dc == 0):
            return None
    else:  # bear
        if uc >= 2 or (dc == 1 and uc == 0):
            return None
    
    # ── 序列+共振过滤 ──
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None
    
    window = ohlcv[:entry_bar+1]
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
        mr = max(mr, 0.55)  # 做空门槛更高
    
    if res.total < mr:
        return None
    
    dec = make_entry_decision_v11(res, seq_r, params, tf_sequences=tf_seq)
    if dec['action'] != 'enter':
        return None
    
    # ── ATR自适应参数 ──
    atr_pct = calc_atr_v38(ohlcv, entry_bar)
    atr_params = calc_stock_atr_profile(ohlcv)
    
    # ── 结构SL ──
    init_sl, sl_type_name, sl_pct_val = calc_v38_sl(
        ohlcv, entry_bar, entry_price, sig, entry_type,
        structure_tree, wyckoff_result, atr_params, direction, params)
    if init_sl is None:
        return None
    
    # ── 结构TP ──
    tp_price, tp_type, tp_pct, tp_idx = calc_v38_tp(
        ohlcv, entry_bar, entry_price, sig, entry_type,
        structure_tree, wyckoff_result, direction, all_signals)
    
    # ── Trailing ──
    exit_idx, exit_price, won = calc_v38_trailing(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, MAX_HOLD, direction)
    
    pnl = (exit_price - entry_price) / entry_price * 100
    if direction == 'bear':
        pnl = -pnl  # 做空PnL逆转
    
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


def backtest_stock_v38(ohlcv, symbol):
    """单股票V38回测"""
    n = len(ohlcv)
    if n < MIN_BARS:
        return None
    
    # ── V38 新组件 ──
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
    
    # ── 双重通道: 同时评估多头和空头信号 ──
    for sig in all_sigs:
        sig_idx = sig.get('idx', 0)
        if sig_idx < 40 or sig_idx >= n - 10:
            continue
        
        sigs_up_to = [s for s in all_sigs if s.get('idx', 0) <= sig_idx]
        
        # Long评估
        sig_type = sig.get('type', '')
        if 'Bull' in sig_type:
            result = evaluate_v38_entry(
                all_sigs, sigs_up_to, sig, ohlcv, n,
                structure_tree, wyckoff_result, 'bull', base_params)
            if result and result['entry_idx'] not in used_long_bars:
                used_long_bars.add(result['entry_idx'])
                all_trades.append(result)
        
        # Short评估 (启用)
        elif 'Bear' in sig_type:
            result = evaluate_v38_entry(
                all_sigs, sigs_up_to, sig, ohlcv, n,
                structure_tree, wyckoff_result, 'bear', base_params)
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
    print("V38 — 多自适应共振交易系统")
    print(f"  多入口: FVG/OB/BreakerBlock")
    print(f"  做空: 启用")
    print(f"  结构树: micro/meso/macro 3层")
    print(f"  Wyckoff阶段: accumulation/markup/distribution/reaccumulation")
    print("=" * 80)
    
    all_trades, stock_results = [], []
    t_start = time.time()
    sl_type_stats = Counter()
    entry_type_stats = Counter()
    direction_stats = Counter()
    phase_stats = Counter()
    
    for idx, sym in enumerate(symbols[:200]):  # 200只测试
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/200] {sym:12s} NO-DATA")
            continue
        
        result = backtest_stock_v38(ohlcv, sym)
        if result:
            p = result['perf']
            for k, v in p.get('sl_types', {}).items():
                sl_type_stats[k] += v
            for k, v in p.get('entry_types', {}).items():
                entry_type_stats[k] += v
            for k, v in p.get('directions', {}).items():
                direction_stats[k] += v
            phase_stats[p.get('phase', 'unknown')] += 1
            
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            print(f"  [{idx+1:3d}/200] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% PF={p['profit_factor']:.0f} "
                  f"dir={dict(p.get('directions',{}))}")
        else:
            print(f"  [{idx+1:3d}/200] {sym:12s} SKIP")
        
        if (idx + 1) % 30 == 0:
            time.sleep(0.1)
    
    total_time = time.time() - t_start
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = wp / lp if lp > 0 else 999
        rr = sum(t['rr'] for t in all_trades) / n
        pnl = sum(t['pnl_pct'] for t in all_trades) / n
        holds = [t['hold_bars'] for t in all_trades]
        
        print(f"\n{'='*80}")
        print(f"V38 — {len(stock_results)}/200 tradable | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars | Max: {max(holds)}")
        print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        
        # Direction breakdown
        print(f"\n  Direction breakdown:")
        total_dir = sum(direction_stats.values())
        for d, cnt in direction_stats.most_common():
            d_trades = [t for t in all_trades if t.get('direction') == d]
            d_wr = sum(1 for t in d_trades if t['won']) / len(d_trades) * 100 if d_trades else 0
            d_avg_rr = sum(t['rr'] for t in d_trades) / len(d_trades) if d_trades else 0
            print(f"    {d:12s}: {cnt:4d} ({cnt/total_dir*100:5.1f}%) | WR={d_wr:.1f}% | avgRR={d_avg_rr:.2f}x")
        
        # Entry type breakdown
        print(f"\n  Entry type breakdown:")
        total_et = sum(entry_type_stats.values())
        for et, cnt in entry_type_stats.most_common():
            et_trades = [t for t in all_trades if t.get('entry_type') == et]
            et_wr = sum(1 for t in et_trades if t['won']) / len(et_trades) * 100 if et_trades else 0
            et_avg_rr = sum(t['rr'] for t in et_trades) / len(et_trades) if et_trades else 0
            print(f"    {et:15s}: {cnt:4d} ({cnt/total_et*100:5.1f}%) | WR={et_wr:.1f}% | avgRR={et_avg_rr:.2f}x")
        
        # Phase breakdown
        print(f"\n  Wyckoff phase distribution:")
        for ph, cnt in phase_stats.most_common():
            ph_trades = [t for t in all_trades if t.get('phase') == ph]
            ph_wr = sum(1 for t in ph_trades if t['won']) / len(ph_trades) * 100 if ph_trades else 0
            ph_avg_rr = sum(t['rr'] for t in ph_trades) / len(ph_trades) if ph_trades else 0
            print(f"    {ph:18s}: {cnt:3d} stocks | WR={ph_wr:.1f}% | avgRR={ph_avg_rr:.2f}x")
        
        # SL type breakdown
        print(f"\n  SL Type breakdown:")
        for st, cnt in sl_type_stats.most_common():
            st_trades = [t for t in all_trades if t.get('sl_type') == st]
            st_wr = sum(1 for t in st_trades if t['won']) / len(st_trades) * 100 if st_trades else 0
            st_avg = sum(t['pnl_pct'] for t in st_trades) / len(st_trades) if st_trades else 0
            print(f"    {st:20s}: {cnt:4d} ({cnt/n*100:5.1f}%) | WR={st_wr:.1f}% | avgP&L={st_avg:+.2f}%")
        
        # Save
        output = {
            'config': f'V38 {len(symbols)} stocks multi-entry+short+structure_tree+wyckoff',
            'summary': {
                'n_stocks': len(stock_results),
                'n_trades': n,
                'win_rate': round(wr, 1),
                'avg_rr': round(rr, 2),
                'profit_factor': round(pf, 2),
                'avg_pnl': round(pnl, 2),
                'direction_breakdown': dict(direction_stats),
                'entry_type_breakdown': dict(entry_type_stats),
                'phase_breakdown': dict(phase_stats),
            },
            'stock_results': stock_results,
            'trades': all_trades,
        }
        outpath = OUTPUT_DIR / 'backtest_v38.json'
        outpath.write_text(json.dumps(output, ensure_ascii=False, indent=1))
        print(f"\n  Saved: {outpath}")
    
    print()


if __name__ == '__main__':
    main()
