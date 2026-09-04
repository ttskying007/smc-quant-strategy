#!/usr/bin/env python3
"""
SMC V469 — 多信号共振引擎 + 分级Trailing + 参数网格搜索
============================================================

V468基础上4大改进 (A+B+C+D):

A) 多信号共振评分: 检测信号集群(5-8bar内FVG+OB+CHOCH+Sweep数量), 量化信号强度
B) 分级Trailing: 信号强度A/B/C级 → 不同宽松度的trailing
C) 可达TP目标: 替换不可达的swing_high TP, 改用阶梯SL收紧 (2.5x/5.0x/8.0x SL)
D) 参数搜索: swing_skip, POI_WINDOW, SL_MIN, TRAIL_BE 网格扫描

核心哲学: 不要交易量, 要每次交易高质量信号 + 高盈亏比。
信号组合(多信号共振) = 用时间顺序找信号组合过滤噪声。
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v469')
OUTPUT_DIR.mkdir(exist_ok=True)

MIN_BARS = 60
MAX_HOLD = 100

# ── V469 参数 (可被grid_search重写) ──
SWING_SKIP = 3           # 跳过bar数 (Swing TP向前找)
POI_RETRACE_WINDOW = 50  # POI回调扫描长度
SL_MIN = 0.30            # SL最小百分比
TRAIL_BE = 8.0           # Trailing 保本触发(%)
TRAIL_LK = 12.0          # Trailing 锁利触发(%)
MIN_PROJECTED_RR = 8.0   # 最小预期RR

# ── V469 信号强度评分: 多信号集群检测 ──
# 扫描信号前5-8bar, 计算共存的信号数量和类型
SIGNAL_CLUSTER_WINDOW = 8  # 扫描前8根bar的信号

# ── 交易信号类型白名单 ──
TRADE_SIGNAL_TYPES = {'FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear',
                      'SweepUp', 'SweepDown', 'CHOCH_Bull', 'CHOCH_Bear'}

# ── 入口信号类型 ──
ENTRY_SIGNAL_TYPES = {'FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear'}

# ── 质量门限 ──
QUALITY_THRESHOLDS = {
    'FVG_Bull': 0.70,
    'FVG_Bear': 0.70,
    'OB_Bull': 0.50,
    'OB_Bear': 0.55,
}

# ── 共振门限 ──
RESONANCE_THRESHOLDS = {
    'bull': 0.50,
    'bear': 0.60,
}

ENABLE_BEAR = False
ENTRY_AT_ZONE = True

# ═══════════════════════════════════════════════════════════════════
# A) 信号强度评分 — 多信号共振检测
# ═══════════════════════════════════════════════════════════════════

def calc_signal_strength(sig, all_sigs_up_to_idx, ohlcv):
    """计算入场信号的强度等级 (A/B/C)
    
    核心: 在sig前后SIGNAL_CLUSTER_WINDOW内检测共存的信号数量和类型。
    信号组合越完整, 强度越高。
    
    cluster_score:
      1+ signal types = C级 (基础)
      2+ signal types = B级 (一般确认)
      3+ signal types = A级 (强确认)
      4 signal types  = S级 (超强)
    
    Returns: {'grade': 'A'|'B'|'C', 'score': float, 'clusters': set, 'n_signals': int}
    """
    sig_idx = sig.get('idx', 0)
    sig_type = sig.get('type', '')
    sig_dir = sig.get('direction', '')
    
    # 检测sig附近SIGNAL_CLUSTER_WINDOW内的其他信号
    start = max(0, sig_idx - SIGNAL_CLUSTER_WINDOW)
    end = sig_idx
    
    types_found = set()
    sigs_found = []
    for s in all_sigs_up_to_idx:
        s_idx = s.get('idx', 0)
        if s_idx < start or s_idx > end:
            continue
        s_type = s.get('type', '')
        s_dir = s.get('direction', '')
        if s_dir != sig_dir:
            continue
        # 标准化信号类型
        if 'FVG' in s_type and 'Mitigated' not in s_type and 'IFVG' not in s_type:
            types_found.add('FVG')
        elif 'OB' in s_type and 'BreakerBlock' not in s_type:
            types_found.add('OB')
        elif 'Sweep' in s_type:
            types_found.add('Sweep')
        elif 'CHOCH' in s_type or 'MSS' in s_type:
            types_found.add('CHOCH')
        elif 'BPR' in s_type:
            types_found.add('BPR')
        sigs_found.append(s_type)
    
    n_found = len(types_found)
    
    # ── 趋势叠加评分 ──
    trend_score = 0.0
    if sig_idx >= 20:
        c20 = (ohlcv[sig_idx]['c'] - ohlcv[sig_idx-20]['c']) / ohlcv[sig_idx-20]['c'] * 100
        if sig_dir == 'bull':
            if c20 < -1.0: trend_score = 0.15  # 下跌后反转 → 加分
            elif c20 > 3.0: trend_score = 0.05  # 已大幅上涨 → 谨慎
            else: trend_score = 0.10
        else:
            if c20 > 1.0: trend_score = 0.15
            elif c20 < -3.0: trend_score = 0.05
            else: trend_score = 0.10
    
    # ── 质量等级 ──
    quality = sig.get('quality', sig.get('confidence', 0.5))
    quality_score = quality * 0.20  # 0-0.20
    
    # ── 综合强度分 (0-1) ──
    # n_found: 1 type=0.25, 2=0.50, 3=0.75, 4+=0.85
    type_score = min(0.85, (n_found - 1) * 0.25 + 0.25) if n_found >= 1 else 0.25
    
    final_score = type_score + trend_score + quality_score
    
    # ── 等级判定 ──
    if final_score >= 0.80 and n_found >= 3:
        grade = 'A'
    elif final_score >= 0.50 and n_found >= 2:
        grade = 'B'
    else:
        grade = 'C'
    
    return {
        'grade': grade,
        'score': round(final_score, 3),
        'clusters': types_found,
        'n_clusters': n_found,
        'n_total': len(sigs_found),
    }


# ═══════════════════════════════════════════════════════════════════
# B) 分级Trailing — 信号质量决定退出宽松度
# ═══════════════════════════════════════════════════════════════════

def calc_v469_trailing(ohlcv, entry_idx, entry_price, initial_sl,
                        structural_tp, n, max_hold, direction,
                        be_lock=2.0, look_lock=4.0, signal_grade='C'):
    """
    V469 分级Trailing — 信号质量决定退出策略的宽松度。
    
    A级(强共振):   超宽trailing, 等价格跑远再锁利, 目标RR>10x
    B级(一般确认): 中宽trailing, 适度锁利, 目标RR>6x
    C级(基础):     标准trailing, 保守锁利, 目标RR>4x
    
    核心改动: 不再使用不可达的swing_high TP目标。
    改为阶梯式SL收紧 (收益越高, SL锁越多, 但不是绝对TP)。
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

    be_gain = be_lock
    lk_gain = look_lock

    # ── 分级宽松度系数 ──
    # A级: 系数1.5 (所有阈值x1.5) — 给利润更多空间
    # B级: 系数1.2
    # C级: 系数1.0 (基线)
    G = {'A': 1.5, 'B': 1.2, 'C': 1.0}.get(signal_grade, 1.0)

    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]

        if is_bear:
            if bar['l'] < extreme:
                extreme = bar['l']
            gain_pct = (entry_price - extreme) / entry_price * 100

            # Bear trailing (不常用, 保持V468风格)
            if profile == 'tight':
                if gain_pct >= 12.0:
                    sl = min(sl, extreme * (1 + 5.0/100))
                elif gain_pct >= 6.0:
                    sl = min(sl, extreme * (1 + 2.5/100))
                elif gain_pct >= 3.5:
                    sl = min(sl, entry_price * (1 + 1.0/100))
                elif gain_pct >= lk_gain:
                    sl = min(sl, entry_price * (1 + 0.3/100))
                elif gain_pct >= be_gain:
                    sl = min(sl, entry_price * 1.0)
            else:
                if gain_pct >= 20.0:
                    sl = min(sl, extreme * (1 + 10.0/100))
                elif gain_pct >= 10.0:
                    sl = min(sl, extreme * (1 + 5.0/100))
                elif gain_pct >= 5.0:
                    sl = min(sl, entry_price * (1 + 1.5/100))
                elif gain_pct >= 3.0:
                    sl = min(sl, entry_price * (1 + 0.5/100))
                elif gain_pct >= be_gain:
                    sl = min(sl, entry_price * 1.0)

            if bar['h'] >= sl:
                exit_price = min(sl, bar['h'])
                return j, round(exit_price, 2), exit_price > entry_price

        else:  # bull — 主要使用的方向
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100

            # ── 阶梯式SL收紧 (替代不可达的TP目标) ──
            # 第一阶: 2.5x SL时锁部分利润 (最低目标)
            # 第二阶: 5.0x SL时锁更多
            # 第三阶: 8.0x SL时几乎全锁
            sl_initial_pct = (entry_price - initial_sl) / entry_price * 100 if not is_bear else 0
            
            if sl_initial_pct > 0:
                # 第1阶: 2.5x SL (可靠的微小利润)
                tier1 = sl_initial_pct * 2.5 * G
                # 第2阶: 5.0x SL  
                tier2 = sl_initial_pct * 5.0 * G
                # 第3阶: 8.0x SL
                tier3 = sl_initial_pct * 8.0 * G
                # 第4阶: 12.0x SL (超跑)
                tier4 = sl_initial_pct * 12.0 * G
                
                if gain_pct >= tier4:
                    # 超跑阶段: 锁极端-5%
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= tier3:
                    # 第三阶: 锁极端-2%
                    sl = max(sl, extreme * (1 - 2.0/100))
                elif gain_pct >= tier2:
                    # 第二阶: 锁极端-1%
                    sl = max(sl, extreme * (1 - 1.0/100))
                elif gain_pct >= tier1:
                    # 第一阶: 锁BE
                    sl = max(sl, entry_price)
            
            # ── V467 渐进式BE锁 (备用, 防止价格回撤) ──
            # A级: 给更多时间
            # B级: 标准
            # C级: 收紧
            progressive_be = {
                'A': [(8, 0.0), (15, 0.5), (25, 1.0), (40, 2.0)],
                'B': [(5, 0.0), (10, 0.3), (18, 0.8), (30, 1.5)],
                'C': [(3, 0.0), (6, 0.3), (12, 0.5), (20, 1.0)],
            }.get(signal_grade, PROGRESSIVE_BE)
            
            for min_hold, min_gain in progressive_be:
                if j >= entry_idx + min_hold and gain_pct < min_gain:
                    sl = max(sl, entry_price)
                    break

            # 常规trailing阈值 (带分级系数)
            if profile == 'loose':
                t30 = 30.0 / G
                t20 = 20.0 / G
                t12 = 12.0 / G
                t8 = TRAIL_BE * G / 8.0
                
                if gain_pct >= t30:
                    sl = max(sl, extreme * (1 - 10.0/100))
                elif gain_pct >= t20:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= t12:
                    sl = max(sl, entry_price * (1 - 2.0/100))
                elif gain_pct >= TRAIL_BE * G:
                    sl = max(sl, entry_price)

            elif profile == 'tight':
                if gain_pct >= 12.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 8.0:
                    sl = max(sl, extreme * (1 - 2.5/100))
                elif gain_pct >= 5.0:
                    sl = max(sl, entry_price * (1 - 1.0/100))
                elif gain_pct >= be_gain:
                    sl = max(sl, entry_price)

            if bar['l'] <= sl:
                exit_price = max(sl, bar['l'])
                return j, round(exit_price, 2), exit_price > entry_price

    # 达到max_hold未exit
    if sl is not None:
        return min(entry_idx + max_hold, n-1), sl, sl > entry_price
    return min(entry_idx + max_hold, n-1), entry_price * 0.95, False


# ── V467渐进BE (默认) ──
PROGRESSIVE_BE = [(5, 0.0), (8, 0.3), (12, 0.5), (20, 1.0)]
TP_DISTANCE_AWARE = True
TP_RELIABLE_MAX = 12.0

# ═══════════════════════════════════════════════════════════════════
# 辅助函数 (沿用V468, 无改动)
# ═══════════════════════════════════════════════════════════════════

def is_reversal_ob(ohlcv, sig, all_signals):
    """反转OB检测 (同V468)"""
    idx = sig.get('idx', 0)
    sig_dir = sig.get('direction', '')
    sig_type = sig.get('type', '')
    
    if 'OB' not in sig_type:
        return True, 'not_ob'
    
    if sig_dir == 'bull':
        trend20 = (ohlcv[idx]['c'] - ohlcv[idx-20]['c']) / ohlcv[idx-20]['c'] * 100 if idx >= 20 else 0
        has_sweep = any('SweepDown' in s.get('type','') and abs(s.get('idx',0)-idx)<=10 for s in all_signals)
        has_rev_choch = any('CHOCH_Bull' in s.get('type','') and s.get('idx',0)<=idx and idx-s.get('idx',0)<=15 for s in all_signals)
        at_swing = sig.get('metadata', {}).get('at_structure', False)
        
        if trend20 > 1.0:
            if has_sweep and has_rev_choch:
                return True, f'rev_swp_choc_{trend20:+.0f}%'
            return False, f'uptrend_pull_{trend20:+.0f}%'
        
        score = sum([has_sweep, has_rev_choch, at_swing, trend20 < -1.0])
        if score >= 1:
            return True, f'rev_score{score}'
        return True, f'weak_rev_{trend20:+.0f}%'
    else:
        trend20 = (ohlcv[idx]['c'] - ohlcv[idx-20]['c']) / ohlcv[idx-20]['c'] * 100 if idx >= 20 else 0
        has_sweep = any('SweepUp' in s.get('type','') and abs(s.get('idx',0)-idx)<=10 for s in all_signals)
        has_rev_choch = any('CHOCH_Bear' in s.get('type','') and s.get('idx',0)<=idx and idx-s.get('idx',0)<=15 for s in all_signals)
        if trend20 < -1.0:
            if has_sweep and has_rev_choch:
                return True, 'bear_rev'
            return False, 'downtrend_pull'
        return True, 'bear_reversal'


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_60min_200.json"
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


def calc_atr_v45(ohlcv, idx, period=14):
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100 if ohlcv[idx]['l'] > 0 else 0.5
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100 if ohlcv[idx]['l'] > 0 else 0.5


def find_swing_high_forward(ohlcv, entry_idx, lookahead=200):
    """60min: 跳过SWING_SKIP bar, 找前方摆动高"""
    n = len(ohlcv)
    best = None
    start = max(entry_idx + SWING_SKIP, 0)
    for i in range(start, min(start + lookahead, n - 2)):
        is_high = all(ohlcv[i]['h'] >= ohlcv[j]['h']
                      for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_high:
            pct = (ohlcv[i]['h'] - ohlcv[entry_idx]['c']) / ohlcv[entry_idx]['c'] * 100
            if best is None or pct > best['pct']:
                best = {'idx': i, 'price': ohlcv[i]['h'], 'pct': pct}
            if pct >= 4.0:
                return {'idx': i, 'price': ohlcv[i]['h'], 'pct': pct}
    return best


def find_swing_low_forward(ohlcv, entry_idx, lookahead=200):
    n = len(ohlcv)
    best = None
    start = max(entry_idx + SWING_SKIP, 0)
    for i in range(start, min(start + lookahead, n - 2)):
        is_low = all(ohlcv[i]['l'] <= ohlcv[j]['l']
                     for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_low:
            pct = (ohlcv[entry_idx]['c'] - ohlcv[i]['l']) / ohlcv[entry_idx]['c'] * 100
            if best is None or pct > best['pct']:
                best = {'idx': i, 'price': ohlcv[i]['l'], 'pct': pct}
            if pct >= 4.0:
                return {'idx': i, 'price': ohlcv[i]['l'], 'pct': pct}
    return best


def check_poi_activation(ohlcv, sig, entry_bar, direction):
    lower = sig.get('lower', 0)
    upper = sig.get('upper', 0)
    if lower <= 0 or upper <= 0 or upper <= lower:
        return False, None, None, None
    bar = ohlcv[entry_bar]
    if direction == 'bull':
        if bar['l'] <= upper and bar['h'] >= lower:
            sl_price = lower * 0.998
            return True, bar['c'], sl_price, 'poi_lower'
    else:
        if bar['h'] >= lower and bar['l'] <= upper:
            sl_price = upper * 1.002
            return True, bar['c'], sl_price, 'poi_upper'
    return False, None, None, None


# ═══════════════════════════════════════════════════════════════════
# SL/TP计算
# ═══════════════════════════════════════════════════════════════════

def calc_v469_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction, params, all_signals):
    """V469 SL: 信号边界 > 摆动点 > ATR自适应 (放宽边界范围)"""
    sig_type = signal.get('type', '')

    if direction == 'bull':
        if 'FVG' in sig_type:
            lower = signal.get('lower', 0)
            if lower > 0 and lower < entry_price:
                pct = (entry_price - lower) / entry_price * 100
                if SL_MIN <= pct <= 5.0:  # 放宽到5.0% (V468是3.0%)
                    return lower, 'fvg_lower', round(pct, 2)
        if 'OB' in sig_type:
            lower = signal.get('lower', 0)
            if lower > 0 and lower < entry_price:
                pct = (entry_price - lower) / entry_price * 100
                if SL_MIN <= pct <= 5.0:
                    return lower, 'ob_lower', round(pct, 2)
    else:
        if 'FVG' in sig_type:
            upper = signal.get('upper', 0)
            if upper > 0 and upper > entry_price:
                pct = (upper - entry_price) / entry_price * 100
                if SL_MIN <= pct <= 5.0:
                    return upper, 'fvg_upper', round(pct, 2)
        if 'OB' in sig_type:
            upper = signal.get('upper', 0)
            if upper > 0 and upper > entry_price:
                pct = (upper - entry_price) / entry_price * 100
                if SL_MIN <= pct <= 5.0:
                    return upper, 'ob_upper', round(pct, 2)

    # 2. 摆动点SL
    swing_lookback = 20
    if direction == 'bull':
        n = len(ohlcv)
        start = max(10, entry_idx - swing_lookback)
        best_sl = None
        best_pct = 0
        for i in range(start, entry_idx - 2):
            if i < 4 or i > n - 4:
                continue
            is_low = all(ohlcv[j]['l'] >= ohlcv[i]['l'] for j in range(i-3, i+4) if j != i)
            if is_low:
                pct = (entry_price - ohlcv[i]['l']) / entry_price * 100
                if SL_MIN <= pct <= 5.0:
                    if best_sl is None or pct < best_pct:
                        best_sl = (ohlcv[i]['l'], 'swing_low', round(pct, 2))
                        best_pct = pct
        if best_sl:
            return best_sl

    # 3. ATR自适应SL (保底)
    atr = calc_atr_v45(ohlcv, entry_idx)
    sl_mult = params.get('sl_mult', 0.3)
    base_sl = max(SL_MIN, min(3.0, atr * sl_mult * 0.5))
    if direction == 'bull':
        return round(entry_price * (1 - base_sl/100), 4), 'adaptive', round(base_sl, 2)
    else:
        return round(entry_price * (1 + base_sl/100), 4), 'adaptive', round(base_sl, 2)


def calc_v469_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals, entry_type='FVG'):
    """V469 TP — 保持结构TP作为trailing参考, 不再依赖其到达
    
    主要用途: 为trailing提供reference point
    如果swing_high/swing_low TP合理, 用其作为阶梯收窄的锚点
    """
    if direction == 'bull':
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bull' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 200]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('upper', 0))
            if tp_price > entry_price:
                tp_pct = (tp_price - entry_price) / entry_price * 100
                if tp_pct >= 2.0:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']

        swing = find_swing_high_forward(ohlcv, entry_idx, 200)
        if swing and swing['price'] > entry_price:
            tp_pct = (swing['price'] - entry_price) / entry_price * 100
            if tp_pct >= 2.0:
                return round(swing['price'], 4), 'swing_high', round(tp_pct, 2), swing['idx']

    return None, None, None, None


def _calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir):
    """同V468: 真实可成交入场价, 无虚假折扣"""
    entry_price = ohlcv[entry_bar]['c']
    if not ENTRY_AT_ZONE or sig_dir != 'bull':
        return entry_price
    lower = sig.get('lower', 0)
    upper = sig.get('upper', 0)
    if lower <= 0 or upper <= 0 or upper <= lower:
        return entry_price
    if lower < entry_price < upper:
        return round(lower, 2)
    return round(entry_price, 2)


def calc_stock_params_v469(ohlcv, symbol):
    """同V468参数"""
    n = len(ohlcv)
    if n < 30:
        return {'sl_mult': 0.3, 'atr_pct': 2.0, 'be_lock': 0.20,
                'look_lock': 0.50, 'max_hold': 30, 'vol_class': 'medium'}
    atr_list = []
    for i in range(14, min(50, n)):
        atr = calc_atr_v45(ohlcv, i)
        atr_list.append(atr)
    avg_atr = sum(atr_list) / len(atr_list) if atr_list else 1.0
    if avg_atr < 1.0:
        vol_class = 'low'
        sl_mult = 0.50
        be_lock = 2.0
        look_lock = 3.0
        max_hold = 100
    elif avg_atr < 3.0:
        vol_class = 'medium'
        sl_mult = 0.50
        be_lock = 2.5
        look_lock = 4.5
        max_hold = 100
    else:
        vol_class = 'high'
        sl_mult = 0.50
        be_lock = 3.5
        look_lock = 5.5
        max_hold = 80
    return {'sl_mult': sl_mult, 'atr_pct': round(avg_atr, 3),
            'be_lock': be_lock, 'look_lock': look_lock,
            'max_hold': max_hold, 'vol_class': vol_class}


# ═══════════════════════════════════════════════════════════════════
# 主入场评估
# ═══════════════════════════════════════════════════════════════════

def evaluate_v469_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n,
                         direction, params, stock_params):
    """V469统一入场评估 — 多信号共振 + 分级trailing"""
    sig_type = sig.get('type', '')
    sig_idx = sig.get('idx', 0)
    confirmed_at = sig.get('confirmed_at', sig_idx)
    entry_bar = max(sig_idx, confirmed_at)

    if entry_bar >= n - 3:
        return None

    is_fvg = 'FVG' in sig_type and 'Mitigated' not in sig_type and 'IFVG' not in sig_type
    is_ob = 'OB' in sig_type and 'BreakerBlock' not in sig_type
    is_sweep = 'Sweep' in sig_type
    is_choch = 'CHOCH' in sig_type

    quality = sig.get('confidence', sig.get('quality', 0.5))
    sig_dir = sig.get('direction', '')

    # ── 策略C: OB-only入口 ──
    if not is_ob:
        if not (is_fvg and quality >= 0.80):
            return None

    if sig_dir == 'bear' and not ENABLE_BEAR:
        return None
    if sig_dir == 'bear' and not is_ob:
        return None

    # 质量门限
    q_threshold = QUALITY_THRESHOLDS.get(sig_type, 0.50)
    if quality < q_threshold:
        return None

    # 反转OB过滤
    is_rev, rev_reason = is_reversal_ob(ohlcv, sig, all_sigs_up_to_idx)
    if not is_rev:
        return None

    # Sweep→FVG/OB检测
    sweep_fvg_found = False
    if sig_idx > 5:
        for ps in all_sigs_up_to_idx:
            ps_type = ps.get('type', '')
            ps_idx = ps.get('idx', 0)
            if sig_dir == 'bull' and 'SweepDown' in ps_type:
                if 0 < sig_idx - ps_idx <= 5:
                    sweep_fvg_found = True
                    break
            elif sig_dir == 'bear' and 'SweepUp' in ps_type:
                if 0 < sig_idx - ps_idx <= 5:
                    sweep_fvg_found = True
                    break

    # ── 信号强度评分 (仅用于分级trailing, 不作为硬过滤) ──
    strength_info = calc_signal_strength(sig, all_sigs_up_to_idx, ohlcv)
    signal_grade = strength_info['grade']  # 'A'|'B'|'C'
    
    # 序列分析 (方向匹配)
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    seq_dir = best_seq.get('direction', '')
    
    if seq_dir and seq_dir != sig_dir:
        all_seqs = seq_r.get('sequences_found', [])
        matching_seqs = [s for s in all_seqs if s.get('direction') == sig_dir]
        if not matching_seqs:
            return None
        best_seq = matching_seqs[0]
        seq_name = best_seq.get('name', '')
    
    # 序列质量用于信号等级增强
    seq_quality = best_seq.get('expected_wr', 0.5)
    if 'SCOUT' in seq_name:
        seq_grade_bonus = 0
    elif 'BRONZE' in seq_name:
        seq_grade_bonus = 1
    elif 'SILVER' in seq_name:
        seq_grade_bonus = 2
    else:  # GOLD / PLATINUM
        seq_grade_bonus = 3

    # ═══ POI回调入场扫描 ──
    entry_bar = max(sig_idx, confirmed_at)
    poi_activated = False
    poiretrace_bars = 0
    
    if sig_dir == 'bull':
        lower = sig.get('lower', 0)
        upper = sig.get('upper', 0)
        if lower > 0 and upper > lower:
            for candidate in range(entry_bar + 1, min(entry_bar + POI_RETRACE_WINDOW, n - 2)):
                bar = ohlcv[candidate]
                if bar['l'] <= upper and bar['h'] >= lower:
                    entry_bar = candidate
                    poi_activated = True
                    poiretrace_bars = candidate - max(sig_idx, confirmed_at)
                    break

    # 入场价
    entry_price = _calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)

    # 入口类型
    if is_ob and quality >= 0.50:
        if sweep_fvg_found:
            entry_type = 'Sweep→OB'
        else:
            entry_type = 'OB_Rev'
    elif is_fvg and quality >= 0.80:
        if sweep_fvg_found:
            entry_type = 'Sweep→FVG'
        else:
            entry_type = 'FVG_HQ'
    else:
        return None

    # 成交量过滤
    if sig_idx > 30 and sig_idx < n:
        bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                     for j in range(max(0, sig_idx-30), sig_idx)) / 30
        if bv < avg_vol * 0.6:
            return None

    # 趋势过滤
    td, _ = short_trend(ohlcv, entry_bar)
    if sig_dir == 'bull' and td == 'down':
        return None

    micro = short_trend(ohlcv, entry_bar, 8)
    meso = short_trend(ohlcv, entry_bar, 20)
    macro = short_trend(ohlcv, entry_bar, 40)
    uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
    if sig_dir == 'bull':
        if dc >= 2:
            return None
    else:
        if uc >= 2:
            return None

    # ── 共振过滤 (基于已在前面分析的序列) ──
    window = ohlcv[:entry_bar+1]
    tf_seq = {'daily': seq_r}
    res = evaluate_full_resonance_v11(
        all_signals=all_sigs_up_to_idx,
        tf_sequences=tf_seq,
        ohlcv=window)

    mr = RESONANCE_THRESHOLDS.get(sig_dir, 0.50)
    if res.total < mr:
        return None

    dec = make_entry_decision_v11(res, seq_r, params, tf_sequences=tf_seq)
    if dec['action'] != 'enter':
        return None

    # ── SL/TP/Trailing ──
    init_sl, sl_type_name, sl_pct_val = calc_v469_sl(
        ohlcv, entry_bar, entry_price, sig, entry_type, sig_dir, params, all_signals)

    if init_sl is None:
        return None

    # TP (作为trailing参考)
    tp_price, tp_type, tp_pct, tp_idx = calc_v469_tp(
        ohlcv, entry_bar, entry_price, sig, sig_dir, all_signals, entry_type)

    # MIN_PROJECTED_RR过滤
    if tp_type is None:
        return None
    if sl_pct_val and tp_pct:
        projected_rr = tp_pct / sl_pct_val
        if projected_rr < MIN_PROJECTED_RR:
            return None

    # 每只股票BE/LK参数
    be_lock = stock_params.get('be_lock', 0.20)
    look_lock = stock_params.get('look_lock', 0.50)
    max_hold = stock_params.get('max_hold', 30)

    # ═══ 序列等级提升信号等级 ═══
    # Gold/Silver序列 → 升级Grade, Bronze → 保持, SCOUT→不降级
    if seq_grade_bonus >= 2 and signal_grade == 'C':
        signal_grade = 'B'  # 序列确认提升到B
    elif seq_grade_bonus >= 3 and signal_grade == 'B':
        signal_grade = 'A'  # Gold序列提升到A

    # ═══ B) 分级Trailing ──
    exit_idx, exit_price, won = calc_v469_trailing(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, max_hold, sig_dir,
        be_lock=be_lock, look_lock=look_lock,
        signal_grade=signal_grade)

    pnl = (exit_price - entry_price) / entry_price * 100
    actual_rr = abs(exit_price - entry_price) / abs(entry_price - init_sl) if entry_price != init_sl else 10

    is_bear = sig_dir == 'bear'

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
        'sl_pct': round(sl_pct_val, 2),
        'tp_type': tp_type,
        'tp_pct': round(tp_pct, 2) if tp_pct else None,
        'signal_type': sig_type,
        'direction': sig_dir,
        'entry_type': entry_type,
        'exit_method': 'tp_hit' if tp_type and tp_price and (
            (not is_bear and exit_price >= tp_price) or
            (is_bear and exit_price <= tp_price)
        ) else 'trailing',
        'resonance_total': round(res.total, 3),
        'poi_activated': poi_activated,
        'poiretrace_bars': poiretrace_bars,
        'is_retest': poi_activated,
        'sweep_fvg': sweep_fvg_found,
        'signal_grade': signal_grade,
        'signal_strength': strength_info['score'],
        'n_clusters': strength_info['n_clusters'],
    }


# ═══════════════════════════════════════════════════════════════════
# 回测运行器
# ═══════════════════════════════════════════════════════════════════

def backtest_stock_v469(ohlcv, symbol):
    """V469单股票回测"""
    n = len(ohlcv)
    stock_params = calc_stock_params_v469(ohlcv, symbol)
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}

    signals_result = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
    all_signals = signals_result.get('all', [])

    if not all_signals or len(all_signals) < 3:
        return None

    trades = []
    used_bars = set()

    for sig in all_signals:
        sig_idx = sig.get('idx', 0)
        sig_type = sig.get('type', '')
        direction = sig.get('direction', '')

        if sig_type not in TRADE_SIGNAL_TYPES:
            continue
        if 'OB' not in sig_type:
            continue
        if sig_idx < 40 or sig_idx >= n - 10:
            continue

        sigs_up_to = [s for s in all_signals if s.get('idx', 0) <= sig_idx]

        result = evaluate_v469_entry(
            all_signals, sigs_up_to, sig, ohlcv, n, direction,
            base_params, stock_params)

        if result:
            if result['entry_idx'] in used_bars:
                continue
            used_bars.add(result['entry_idx'])
            trades.append(result)

    if len(trades) < 2:
        return None

    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)

    sl_types = Counter(t.get('sl_type', 'unknown') for t in trades)
    tp_types = Counter(t.get('tp_type', 'none') for t in trades)
    exit_methods = Counter(t.get('exit_method', 'unknown') for t in trades)
    directions = Counter(t.get('direction', 'unknown') for t in trades)
    entry_types = Counter(t.get('entry_type', 'unknown') for t in trades)
    poi_count = sum(1 for t in trades if t.get('poi_activated', False))
    
    # 信号等级分布
    grades = Counter(t.get('signal_grade', 'C') for t in trades)

    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades),
            'wins': wins,
            'losses': len(trades) - wins,
            'win_rate': round(wr, 1),
            'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2),
            'sl_types': dict(sl_types),
            'tp_types': dict(tp_types),
            'exit_methods': dict(exit_methods),
            'directions': dict(directions),
            'entry_types': dict(entry_types),
            'poi_activated': poi_count,
            'grades': dict(grades),
            'vol_class': stock_params.get('vol_class', 'medium'),
            'stock_params': {k: v for k, v in stock_params.items()},
        }
    }


def run_backtest(symbols, label="V469"):
    """通用回测运行器"""
    all_trades, stock_results = [], []
    t_start = time.time()
    sl_type_stats = Counter()
    tp_type_stats = Counter()
    direction_stats = Counter()
    grade_stats = Counter()

    print(f"{'='*80}")
    print(f"V469 — 多信号共振引擎 + 分级Trailing")
    print(f"  {len(symbols)} 只股票 | 信号: OB-only | 过滤: 序列+共振+趋势+信号强度")
    print(f"  SwingSkip={SWING_SKIP} POI={POI_RETRACE_WINDOW} SL_MIN={SL_MIN}% BE={TRAIL_BE}%")
    print(f"{'='*80}")

    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} NO-DATA")
            continue

        result = backtest_stock_v469(ohlcv, sym)
        if result:
            p = result['perf']
            for st, cnt in p['sl_types'].items():
                sl_type_stats[st] += cnt
            for tt, cnt in p['tp_types'].items():
                tp_type_stats[tt] += cnt
            for d, cnt in p['directions'].items():
                direction_stats[d] += cnt
            for g, cnt in p['grades'].items():
                grade_stats[g] += cnt
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x "
                  f"Grade={dict(p['grades'])}")
        else:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} SKIP")

        if (idx + 1) % 50 == 0:
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

        tp_hits = [t for t in all_trades if t.get('exit_method') == 'tp_hit']
        trailing_trades = [t for t in all_trades if t.get('exit_method') == 'trailing']
        
        # 按等级分组
        grade_a = [t for t in all_trades if t.get('signal_grade') == 'A']
        grade_b = [t for t in all_trades if t.get('signal_grade') == 'B']
        grade_c = [t for t in all_trades if t.get('signal_grade') == 'C']

        print(f"\n  === {label} RESULTS ===")
        print(f"  Time: {total_time:.0f}s | Stocks: {len(stock_results)}/{len(symbols)}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars | Max: {max(holds)}")
        print(f"  TP hit: {len(tp_hits)}/{n} ({len(tp_hits)/n*100:.1f}%)")

        print(f"\n  Grade breakdown (signal strength):")
        for g in ['A', 'B', 'C']:
            gt = [t for t in all_trades if t.get('signal_grade') == g]
            if gt:
                gw = sum(1 for t in gt if t['won'])/len(gt)*100
                gr = sum(t['rr'] for t in gt)/len(gt)
                gp = sum(t['pnl_pct'] for t in gt)/len(gt)
                gh = sum(t['hold_bars'] for t in gt)/len(gt)
                print(f"    Grade {g}: n={len(gt):3d} WR={gw:.1f}% RR={gr:.2f}x "
                      f"P&L={gp:+.2f}% hold={gh:.1f}b")

        wn = sum(t['pnl_pct'] for t in all_trades if t['won']) / wins if wins > 0 else 0
        ls = abs(sum(t['pnl_pct'] for t in all_trades if not t['won'])) / (n - wins) if n > wins else 0
        wl = wn / ls if ls > 0 else 0
        print(f"\n  W/L: avgWin={wn:.3f}% avgLoss={ls:.3f}% ratio={wl:.1f}x")

    return {
        'stock_results': stock_results,
        'all_trades': all_trades,
        'summary': {
            'n_stocks': len(stock_results),
            'n_trades': len(all_trades),
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(rr, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
            'avg_pnl': round(pnl, 2) if all_trades else 0,
        }
    }


# ═══════════════════════════════════════════════════════════════════
# C) 参数网格搜索
# ═══════════════════════════════════════════════════════════════════

def run_grid_search(symbols, param_grid):
    """网格搜索 — 扫描参数组合"""
    results = []
    
    for params in param_grid:
        # 设置全局参数
        global SWING_SKIP, POI_RETRACE_WINDOW, SL_MIN, TRAIL_BE, MIN_PROJECTED_RR
        
        ss = params.get('swing_skip', SWING_SKIP)
        pw = params.get('poi_window', POI_RETRACE_WINDOW)
        sm = params.get('sl_min', SL_MIN)
        tb = params.get('trail_be', TRAIL_BE)
        mp = params.get('min_rr', MIN_PROJECTED_RR)
        
        SWING_SKIP = ss
        POI_RETRACE_WINDOW = pw
        SL_MIN = sm
        TRAIL_BE = tb
        MIN_PROJECTED_RR = mp
        
        label = f"V469 SS={ss} POI={pw} SL={sm} BE={tb} RRmin={mp}"
        print(f"\n{'#'*80}")
        print(f"# Running: {label}")
        print(f"{'#'*80}\n")
        
        result = run_backtest(symbols, label)
        
        if result and result.get('all_trades'):
            results.append({
                'params': params,
                'summary': result['summary'],
                'stocks': len(result['stock_results']),
            })
    
    return results


if __name__ == '__main__':
    symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                     for f in CACHE_DIR.glob('*_60min_200.json')])
    
    # 20只小规模测试
    test_symbols = symbols[:20]
    
    # 或全量
    # result = run_backtest(symbols, "V469")
    
    # 网格搜索
    param_grid = [
        # 基线 (V468)
        {'swing_skip': 3, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
        # 更紧skip
        {'swing_skip': 2, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
        # 更松skip
        {'swing_skip': 4, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
        # 更宽POI
        {'swing_skip': 3, 'poi_window': 80, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
        # 更紧POI
        {'swing_skip': 3, 'poi_window': 30, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
        # 更紧SL (更严格止损)
        {'swing_skip': 3, 'poi_window': 50, 'sl_min': 0.50, 'trail_be': 8.0, 'min_rr': 8.0},
        # 更高RR门槛
        {'swing_skip': 3, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 6.0},
        # 更宽松trailing
        {'swing_skip': 3, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 10.0, 'min_rr': 8.0},
        # 最宽松组合
        {'swing_skip': 2, 'poi_window': 80, 'sl_min': 0.50, 'trail_be': 10.0, 'min_rr': 6.0},
        # 最保守组合
        {'swing_skip': 4, 'poi_window': 30, 'sl_min': 0.30, 'trail_be': 6.0, 'min_rr': 10.0},
    ]
    
    result = run_grid_search(test_symbols, param_grid)
    
    print(f"\n{'='*80}")
    print(f"GRID SEARCH RESULTS — {len(result)} combinations")
    print(f"{'='*80}")
    for r in result:
        s = r['summary']
        p = r['params']
        print(f"  SS={p['swing_skip']} POI={p['poi_window']} "
              f"SL={p['sl_min']} BE={p['trail_be']} RRmin={p['min_rr']}  "
              f"→ {s['n_trades']}t {s['n_stocks']}st WR={s['win_rate']:.1f}% "
              f"RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.0f} P&L={s['avg_pnl']:+.2f}%")
    
    # Save grid results
    out_path = OUTPUT_DIR / 'grid_search_results.json'
    json.dump(result, open(str(out_path), 'w'))
    print(f"\n  Saved: {out_path}")
