#!/usr/bin/env python3
"""V37 — Multi-Dimensional Adaptive Resonance System (MARS)

核心架构:
┌─────────────────────────────────────────────────────────────┐
│  V37 综合决策引擎                                             │
├─────────────────────────────────────────────────────────────┤
│  1. 流动性层: BSL/SSL区域 → 猎杀追踪 → 反转确认                │
│  2. 信号层: V11.2 13种SMC信号 + 流动性上下文增强                │
│  3. 时序层: ATR自适应窗口 + MSS/CHOCH层级桥接                  │
│  4. 多周期层: 周线趋势+摆动点 → 日线共振评分                    │
│  5. 结构SL/TP: ATR自适应SL + 摆动点TP + 结构感知trailing       │
└─────────────────────────────────────────────────────────────┘

关键改进 vs V36:
- 不是找"信号", 而是找"流动性被猎杀后的反转" 
- 信号序列窗口根据波动率自适应
- MSS→MSS-meso→CHOCH三级结构
- 周线上下文: 支撑/阻力/趋势方向
"""

import json, sys, math, time
from pathlib import Path
from collections import Counter
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.liquidity_v37 import (
    detect_liquidity_zones, calc_adaptive_windows_v37,
    enhance_signals_with_liquidity,
)
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v37')
OUTPUT_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
# 全局参数
# ═══════════════════════════════════════════════════════════════════════

SWING_MAX_DISTANCE = 30
SWING_SL_CAP = 0.5
MIN_VOL_RATIO = 0.7
MIN_FVG_GAP = 0.2
MAX_STOCKS = 200
MIN_BARS = 120
MAX_HOLD = 60

PHASE_PARAMS = {
    'breakout':    {'sl': 0.3, 'window_mult': 0.8},
    'volatile':    {'sl': 0.5, 'window_mult': 1.0},
    'ranging':     {'sl': 0.8, 'window_mult': 1.3},
    'trending_up': {'sl': 0.3, 'window_mult': 0.9},
    'trending_down':{'sl': 0.5, 'window_mult': 0.9},
}
CYCLE_SL_MULT = {'ALL-UP': 0.8, '2UP-1NEUTRAL': 1.0, 'NEUTRAL': 1.2}


# ═══════════════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════════════

def load_ohlcv(symbol: str) -> Optional[List[Dict]]:
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


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

def calc_atr(ohlcv, idx, period=14):
    """Simple ATR for volatility reference"""
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100


def find_swing_highs(ohlcv, lookback=8):
    """找摆动高点"""
    highs = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        is_high = all(ohlcv[i]['h'] >= ohlcv[j]['h'] for j in range(i - lookback, i + lookback + 1))
        if is_high:
            highs.append((i, ohlcv[i]['h']))
    return highs


def find_swing_lows(ohlcv, lookback=8):
    """找摆动低点"""
    lows = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        is_low = all(ohlcv[i]['l'] <= ohlcv[j]['l'] for j in range(i - lookback, i + lookback + 1))
        if is_low:
            lows.append((i, ohlcv[i]['l']))
    return lows


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback:
        return 'neutral', 0
    seg = ohlcv[idx-lookback:idx+1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e - s) / s * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ema_d = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_d > 0:
        return 'up', change
    if change < -0.6 and ema_d < 0:
        return 'down', abs(change)
    return 'neutral', 0


# ═══════════════════════════════════════════════════════════════════════
# 模块2: 周线多周期共振
# ═══════════════════════════════════════════════════════════════════════

def calc_weekly_resonance(ohlcv: List[Dict], idx: int) -> Dict:
    """计算周线上下文对日线信号的共振得分
    
    由于60min不可用, 用周线作为更高时间框架:
    - 周线趋势方向
    - 周线摆动点作为关键支撑/阻力
    - 日线信号是否与周线趋势对齐
    
    Returns:
        {'tf_score': 0-1, 'weekly_trend': str, 'at_level': str}
    """
    if idx < 20:
        return {'tf_score': 0.5, 'weekly_trend': 'neutral', 'at_level': 'none'}
    
    # 合成周线
    weekly_close = []
    for i in range(max(0, idx - 60), idx + 1, 5):
        if i < len(ohlcv):
            weekly_close.append(ohlcv[i]['c'])
    
    if len(weekly_close) < 4:
        return {'tf_score': 0.5, 'weekly_trend': 'neutral', 'at_level': 'none'}
    
    # 周线趋势
    w_trend = 'up' if weekly_close[-1] > weekly_close[0] * 1.02 else \
              'down' if weekly_close[-1] < weekly_close[0] * 0.98 else 'neutral'
    
    # 周线摆动点 (作为关键水平)
    weekly_high = max(ohlcv[i]['h'] for i in range(max(0, idx-30), idx+1))
    weekly_low = min(ohlcv[i]['l'] for i in range(max(0, idx-30), idx+1))
    current = ohlcv[idx]['c']
    
    # 当前价格在周线中的位置
    weekly_range = weekly_high - weekly_low
    if weekly_range == 0:
        return {'tf_score': 0.5, 'weekly_trend': w_trend, 'at_level': 'middle'}
    
    pos = (current - weekly_low) / weekly_range
    
    # 判断是否在周线关键水平
    if pos < 0.15:
        at_level = 'support_low'  # 近周线低点 = 支撑区
    elif pos > 0.85:
        at_level = 'resistance_high'  # 近周线高点 = 阻力区
    else:
        at_level = 'middle'
    
    # 共振得分
    tf_score = 0.5  # 基础
    if w_trend == 'up' and at_level == 'support_low':
        tf_score = 0.75  # 周线上涨 + 价格在支撑区 = 做多好位置
    elif w_trend == 'down' and at_level == 'resistance_high':
        tf_score = 0.75  # 周线下跌 + 价格在阻力区 = 做空好位置
    elif w_trend == 'up' and at_level == 'middle':
        tf_score = 0.60
    elif w_trend == 'down' and at_level == 'middle':
        tf_score = 0.50
    
    return {
        'tf_score': round(tf_score, 3),
        'weekly_trend': w_trend,
        'at_level': at_level,
        'weekly_high': round(weekly_high, 4),
        'weekly_low': round(weekly_low, 4),
    }


# ═══════════════════════════════════════════════════════════════════════
# 模块3: MSS→CHOCH层级桥接
# ═══════════════════════════════════════════════════════════════════════

def classify_structure_shift(mss_signals: List[Dict], 
                              choch_signals: List[Dict],
                              idx: int, direction: str) -> Dict:
    """对当前K线附近的结构变化做层级分类
    
    MSS(微观) → MSS-meso(中观) → CHOCH(宏观)
    
    Returns:
        {'level': 'micro'|'meso'|'macro', 'score': 0-1, 'count': int}
    """
    # 附近的结构信号
    nearby_mss = [s for s in mss_signals 
                  if abs(s.get('idx', 0) - idx) <= 3 
                  and s.get('direction', '') == direction]
    nearby_choch = [s for s in choch_signals 
                    if abs(s.get('idx', 0) - idx) <= 8 
                    and s.get('direction', '') == direction]
    
    mss_count = len(nearby_mss)
    choch_count = len(nearby_choch)
    
    if choch_count >= 1:
        return {'level': 'macro', 'score': 0.95, 'count': choch_count}
    elif mss_count >= 3:
        return {'level': 'meso', 'score': 0.80, 'count': mss_count}
    elif mss_count >= 1:
        return {'level': 'micro', 'score': 0.55, 'count': mss_count}
    else:
        return {'level': 'none', 'score': 0.0, 'count': 0}


# ═══════════════════════════════════════════════════════════════════════
# 模块4: 综合评分 — V37决策引擎
# ═══════════════════════════════════════════════════════════════════════

def score_v37_entry(all_signals: List[Dict], 
                    liquidity_result: Dict,
                    weekly_res: Dict,
                    structure_shift: Dict,
                    adaptive_windows: Dict,
                    ohlcv: List[Dict],
                    idx: int, direction: str) -> Dict:
    """V37综合入场评分 (v2 — 收紧版)
    
    五维评分:
    A. 流动性猎杀+信号共振(35%): 流动性被猎杀 + 多信号共振
    B. 多信号类型覆盖(30%): 至少2种不同信号类型同时出现
    C. 结构层级(20%): MSS/CHOCH级别
    D. 周线对齐(15%): 方向是否与周线趋势一致?
    
    硬过滤 (任何条件不满足 → grade D):
    1. 必须至少有2种不同信号类型 (FVG+OB, FVG+Sweep等)
    2. 结构层级必须>=micro
    3. 周线方向不能相反 (trend_up vs bear = pass; trend_down vs bull = pass)
    
    Returns:
        {'score': 0-1, 'grade': str, 'details': {...}}
    """
    # ─── 硬过滤 #1: 至少2种信号类型 ───
    recent_signals = [s for s in all_signals 
                      if 0 < s.get('idx', 0) - idx <= 8 
                      and s.get('direction', '') == direction]
    types_present = set()
    for s in recent_signals:
        t = s.get('type', '')
        if 'FVG' in t: types_present.add('FVG')
        if 'OB' in t: types_present.add('OB')
        if 'Sweep' in t: types_present.add('Sweep')
    
    # 必须有FVG (baseline)
    has_fvg = 'FVG' in types_present
    # 必须有至少另一个类型
    has_secondary = len(types_present) >= 2
    
    # ─── 硬过滤 #2: 结构层级必须>=micro ───
    struct_level = structure_shift.get('level', 'none')
    has_structure = struct_level != 'none'
    
    # ─── 硬过滤 #3: 周线方向 ───
    weekly_trend = weekly_res.get('weekly_trend', 'neutral')
    weekly_ok = True
    if weekly_trend != 'neutral':
        if direction == 'bull' and weekly_trend == 'down':
            weekly_ok = False  # 做多但周线下跌 → 过滤
        elif direction == 'bear' and weekly_trend == 'up':
            weekly_ok = False  # 做空但周线上涨 → 过滤
    
    if not (has_fvg and has_secondary and has_structure and weekly_ok):
        return {
            'score': 0.0, 'grade': 'D',
            'details': {
                'has_fvg': has_fvg, 'has_secondary': has_secondary,
                'has_structure': has_structure, 'weekly_ok': weekly_ok,
                'types': list(types_present),
            }
        }
    
    # ─── 评分 ───
    score = 0.0
    
    # A. 流动性猎杀 + 信号强度 (35%)
    liq_score = 0.0
    sweep_sigs = liquidity_result.get('sweep_signals', [])
    
    # 检查是否有同向猎杀
    recent_sweep = None
    for ss in sweep_sigs:
        if ss.get('direction', '') == direction and ss.get('idx', 0) >= idx - 10:
            recent_sweep = ss
            break
    
    if recent_sweep:
        # 流动性被猎杀+反转 = 最强入口 (ICT核心)
        cluster_size = recent_sweep.get('zone_cluster_size', 2)
        zone_density = recent_sweep.get('zone_density', 0.5)
        liq_score = min(1.0, 0.6 + cluster_size * 0.05 + zone_density * 0.2)
    else:
        # 没有猎杀: 仅靠信号自身
        signal_strengths = [s.get('strength', 3.0) for s in recent_signals]
        avg_strength = sum(signal_strengths) / max(1, len(signal_strengths))
        liq_score = min(0.6, avg_strength / 12.0 + 0.2)
    
    score += liq_score * 0.35
    
    # B. 多信号类型覆盖 (30%)
    coverage = len(types_present) / 3.0
    sig_count = min(5, len(recent_signals)) / 5.0
    sig_score = min(1.0, coverage * 0.7 + sig_count * 0.3)
    score += sig_score * 0.30
    
    # C. 结构层级 (20%)
    struct_score = structure_shift.get('score', 0.5)
    score += struct_score * 0.20
    
    # D. 周线对齐 (15%)
    if weekly_trend != 'neutral':
        if direction == 'bull' and weekly_trend == 'up':
            weekly_score = 0.85  # 完美对齐
        elif direction == 'bear' and weekly_trend == 'down':
            weekly_score = 0.85
        else:
            weekly_score = 0.60
    else:
        weekly_score = 0.50
    score += weekly_score * 0.15
    
    score = min(1.0, max(0.0, score))
    
    # 等级
    if score >= 0.75:
        grade = 'S'
    elif score >= 0.60:
        grade = 'A'
    elif score >= 0.45:
        grade = 'B'
    elif score >= 0.30:
        grade = 'C'
    else:
        grade = 'D'
    
    return {
        'score': round(score, 4),
        'grade': grade,
        'details': {
            'liq_score': round(liq_score, 4),
            'sig_score': round(sig_score, 4),
            'struct_score': round(struct_score, 4),
            'weekly_score': round(weekly_score, 4),
            'has_fvg': has_fvg,
            'has_secondary': has_secondary,
            'types': list(types_present),
            'recent_sweep': recent_sweep.get('type', 'none') if recent_sweep else 'none',
        }
    }


# ═══════════════════════════════════════════════════════════════════════
# 模块5: 结构性SL/TP (从V36移植并增强)
# ═══════════════════════════════════════════════════════════════════════

def calc_structural_sl_v37(ohlcv: List[Dict], all_signals: List[Dict],
                            entry_idx: int, entry_price: float,
                            direction: str) -> Tuple[float, str]:
    """V37增强结构SL
    
    优先级:
    1. 流动性猎杀反转点 (新!)
    2. 摆动低点/高点
    3. FVG下边界/OB下边界
    4. ATR自适应保底
    
    Returns: (sl_price, sl_type)
    """
    n = len(ohlcv)
    if n == 0:
        return entry_price * 0.997, 'fallback'
    
    atr = calc_atr(ohlcv, min(entry_idx, n-1))
    candidates = []
    
    # 1. 检查流动性猎杀信号
    liq_signals = [s for s in all_signals if 'Sweep' in s.get('type', '') 
                   and s.get('direction', '') == direction
                   and s.get('idx', 0) <= entry_idx]
    if liq_signals:
        last_liq = max(liq_signals, key=lambda s: s.get('strength', 0))
        # 猎杀的反转点 = 区域的另一侧
        if direction == 'bull':
            sl_candidate = last_liq.get('lower', 0) or last_liq.get('upper', 0) * 0.99
            pct = abs(entry_price - sl_candidate) / entry_price * 100
            if 0.1 <= pct <= 1.0:
                candidates.append((sl_candidate, 'liquidity_sweep'))
        else:
            sl_candidate = last_liq.get('upper', 0) or last_liq.get('lower', 0) * 1.01
            pct = abs(entry_price - sl_candidate) / entry_price * 100
            if 0.1 <= pct <= 1.0:
                candidates.append((sl_candidate, 'liquidity_sweep'))
    
    # 2. 摆动点SL
    if direction == 'bull':
        swing_lows = find_swing_lows(ohlcv, lookback=12)
        recent_lows = [(i, p) for i, p in swing_lows 
                       if 0 < entry_idx - i <= SWING_MAX_DISTANCE]
        for i, p in recent_lows:
            pct = abs(entry_price - p) / entry_price * 100
            if 0.10 <= pct <= 0.70:
                candidates.append((p, 'swing_low'))
    else:
        swing_highs = find_swing_highs(ohlcv, lookback=12)
        recent_highs = [(i, p) for i, p in swing_highs 
                        if 0 < entry_idx - i <= SWING_MAX_DISTANCE]
        for i, p in recent_highs:
            pct = abs(entry_price - p) / entry_price * 100
            if 0.10 <= pct <= 0.70:
                candidates.append((p, 'swing_high'))
    
    # 3. ATR自适应保底
    atr_sl_pct = max(0.1, min(0.8, atr * 0.20))
    atr_sl = entry_price * (1 - atr_sl_pct / 100) if direction == 'bull' \
             else entry_price * (1 + atr_sl_pct / 100)
    candidates.append((atr_sl, 'adaptive_atr'))
    
    if not candidates:
        return entry_price * 0.997, 'fallback'
    
    # 选择最短的SL (最紧)
    if direction == 'bull':
        best = max(candidates, key=lambda c: c[0])
    else:
        best = min(candidates, key=lambda c: c[0])
    
    return best


def calc_structural_tp_v37(ohlcv: List[Dict], all_signals: List[Dict],
                            entry_idx: int, entry_price: float,
                            direction: str) -> Tuple[float, str]:
    """V37结构TP
    
    优先级:
    1. 前方CHOCH break_level
    2. 前方摆动高点/低点
    3. ATR * 8 虚拟TP (退出用trailing)
    
    Returns: (tp_price, tp_type)
    """
    n = len(ohlcv)
    
    # 1. CHOCH break_level作为TP
    choch_signals = [s for s in all_signals 
                     if 'CHOCH' in s.get('type', '')
                     and s.get('direction', '') == direction
                     and s.get('idx', 0) > entry_idx]
    if choch_signals:
        nearest = min(choch_signals, key=lambda s: abs(s.get('idx', 0) - entry_idx))
        break_level = nearest.get('metadata', {}).get('break_level', 0)
        if break_level > 0:
            return break_level, 'choch_break'
    
    # 2. 摆动点
    if direction == 'bull':
        swing_highs = find_swing_highs(ohlcv, lookback=8)
        ahead_highs = [(i, p) for i, p in swing_highs if i > entry_idx and p > entry_price]
        if ahead_highs:
            nearest = min(ahead_highs, key=lambda x: x[1] - entry_price)
            return nearest[1], 'swing_high'
    else:
        swing_lows = find_swing_lows(ohlcv, lookback=8)
        ahead_lows = [(i, p) for i, p in swing_lows if i > entry_idx and p < entry_price]
        if ahead_lows:
            nearest = max(ahead_lows, key=lambda x: entry_price - x[1])
            return nearest[1], 'swing_low'
    
    # 3. 无结构TP
    atr = calc_atr(ohlcv, min(entry_idx, n-1))
    atr_tp = entry_price * (1 + atr * 6 / 100) if direction == 'bull' \
             else entry_price * (1 - atr * 6 / 100)
    return atr_tp, 'atr_projection'


def calc_trailing_v37(entry_price: float, current_price: float,
                       sl_price: float, direction: str) -> float:
    """V37增强trailing
    
    结合价格行为和结构:
    - 移动止损至保本 (盈亏平衡)
    - 然后每上涨一个ATR就收紧
    """
    if direction == 'bull':
        gain_pct = (current_price - entry_price) / entry_price * 100
        
        if gain_pct < 0.3:
            return sl_price  # 还没到保本
        if gain_pct < 0.8:
            return entry_price  # 保本
        if gain_pct < 2.0:
            return entry_price * 1.002  # 微利
        if gain_pct < 4.0:
            return entry_price * 1.005  # 锁定部分利润
        return entry_price * 1.01  # 大幅盈利后收紧
    else:
        # Short (bear)
        loss_pct = (entry_price - current_price) / entry_price * 100
        
        if loss_pct < 0.3:
            return sl_price
        if loss_pct < 0.8:
            return entry_price
        if loss_pct < 2.0:
            return entry_price * 0.998
        if loss_pct < 4.0:
            return entry_price * 0.995
        return entry_price * 0.99


# ═══════════════════════════════════════════════════════════════════════
# 核心: 信号入场评估
# ═══════════════════════════════════════════════════════════════════════

def evaluate_signal_entry_v37(ohlcv: List[Dict], idx: int, 
                               all_signals: List[Dict],
                               liquidity_result: Dict,
                               direction: str) -> Optional[Dict]:
    """V37 — ICT Liquidity Sweep + FVG 入场
    
    核心逻辑:
    1. 检查近期是否有流动性猎杀 (Sweep信号)
    2. 猎杀后是否有FVG形成 (反转确认)
    3. 入场 = FVG confirmed_at bar
    
    这是ICT最核心的形态: 流动性被猎杀 → 反转 → FVG确认
    """
    n = len(ohlcv)
    if idx < 10 or idx >= n - 2:
        return None
    
    current_price = ohlcv[idx]['c']
    
    # 1. 检查近期流动性猎杀 (Sweep)
    sweep_sigs = liquidity_result.get('sweep_signals', [])
    recent_sweep = None
    for ss in sweep_sigs:
        if ss.get('direction', '') == direction and ss.get('idx', 0) >= idx - 15:
            recent_sweep = ss
            break
    
    # 2. 必须有同向FVG在猎杀后
    fvg_after = [s for s in all_signals 
                 if 'FVG' in s.get('type', '')
                 and s.get('direction', '') == direction
                 and (recent_sweep is None or s.get('idx', 0) >= recent_sweep.get('idx', 0))
                 and idx >= s.get('confirmed_at', s.get('idx', 0))
                 and 0 < idx - s.get('confirmed_at', s.get('idx', 0)) <= 6]
    
    if not fvg_after:
        return None
    
    best_fvg = max(fvg_after, key=lambda s: s.get('strength', 0))
    
    # 3. 如果没猎杀但有CHOCH+FVG (次优)
    has_sweep = recent_sweep is not None
    if not has_sweep:
        choch_after = [s for s in all_signals 
                       if 'CHOCH' in s.get('type', '')
                       and s.get('direction', '') == direction
                       and 0 < idx - s.get('idx', 0) <= 12]
        if not choch_after:
            return None  # 既没猎杀也没CHOCH → 不交易
    
    # 4. 周线对齐
    weekly_res = calc_weekly_resonance(ohlcv, idx)
    weekly_trend = weekly_res.get('weekly_trend', 'neutral')
    if weekly_trend == 'down' and direction == 'bull':
        # 周线下跌时做多 → 必须要有猎杀
        if not has_sweep:
            return None
    
    # 5. SL: 猎杀区域外 + 摆动低点
    if direction == 'bull':
        swing_lows_list = find_swing_lows(ohlcv, lookback=12)
        best_sl = None
        best_sl_dist = 999
        
        # 优先: 猎杀区域下方不超过1.0%
        if has_sweep:
            sweep_price = recent_sweep.get('price', 0)
            sweep_lower = recent_sweep.get('zone_lower', 0)
            if sweep_lower > 0:
                sl_pct = (current_price - sweep_lower) / current_price * 100
                if sl_pct <= 1.5:  # 最多1.5%止损
                    best_sl = (sweep_lower, 'liquidity_sweep')
        
        # 次选: 摆动低点SL
        if best_sl is None:
            for sw_i, sw_p in swing_lows_list:
                if sw_i < idx and idx - sw_i <= SWING_MAX_DISTANCE:
                    sl_pct = (current_price - sw_p) / current_price * 100
                    if 0.15 <= sl_pct <= 0.80:
                        quality = (idx - sw_i) / SWING_MAX_DISTANCE  # 越近越好
                        if quality < best_sl_dist:
                            best_sl_dist = quality
                            best_sl = (sw_p, 'swing_low')
        
        # 保底
        if best_sl is None:
            atr = calc_atr(ohlcv, min(idx, n-1))
            sl_pct = max(0.20, min(0.60, atr * 0.3))
            best_sl = (current_price * (1 - sl_pct / 100), 'adaptive_atr')
        
        sl_price = best_sl[0]
        sl_type = best_sl[1]
        
        # TP: 前方摆动高点
        swing_highs_list = find_swing_highs(ohlcv, lookback=8)
        tp_price = None
        tp_type = 'none'
        for sw_i, sw_p in swing_highs_list:
            if sw_i > idx and sw_p > current_price and (sw_p - current_price) / current_price * 100 > 0.5:
                tp_price = sw_p
                tp_type = 'swing_high'
                break
        if tp_price is None:
            atr = calc_atr(ohlcv, min(idx, n-1))
            tp_price = current_price * (1 + atr * 5 / 100)
            tp_type = 'atr_projection'
    else:
        atr = calc_atr(ohlcv, min(idx, n-1))
        sl_price = current_price * (1 + max(0.20, atr * 0.3) / 100)
        sl_type = 'adaptive_atr'
        tp_price = current_price * (1 - atr * 5 / 100)
        tp_type = 'atr_projection'
    
    # 综合评分
    score = 0.50  # base
    if has_sweep:
        cluster_size = recent_sweep.get('zone_cluster_size', 0)
        score += min(0.30, cluster_size * 0.05)  # 浮动池加分
    if weekly_trend == 'up' and direction == 'bull':
        score += 0.10  # 周线+日线一致
    if best_fvg.get('trend_aligned', False):
        score += 0.05
    if has_sweep:
        score += 0.05  # 猎杀加分
    
    score = min(1.0, score)
    grade = 'S' if score >= 0.75 else 'A' if score >= 0.65 else 'B' if score >= 0.55 else 'C'
    
    return {
        'entry_idx': idx,
        'entry_price': round(current_price, 4),
        'direction': direction,
        'sl_price': round(sl_price, 4),
        'sl_type': sl_type,
        'tp_price': round(tp_price, 4),
        'tp_type': tp_type,
        'has_liquidity_sweep': has_sweep,
        'weekly_trend': weekly_trend,
        'v37_score': round(score, 4),
        'v37_grade': grade,
    }


# ═══════════════════════════════════════════════════════════════════════
# V37主回测循环
# ═══════════════════════════════════════════════════════════════════════

def backtest_stock_v37(symbol: str, ohlcv: List[Dict]) -> Dict:
    """对单只股票运行V37回测"""
    n = len(ohlcv)
    
    # 1. 检测所有信号
    sig_result = detect_all_signals_v11(ohlcv)
    all_signals = sig_result['all']
    
    if not all_signals:
        return {'symbol': symbol, 'trades': [], 'tradable': False, 'reason': 'no_signals'}
    
    # 2. 流动性分析 (一次性)
    liquidity_result = detect_liquidity_zones(ohlcv)
    
    # 3. 增强信号
    enhanced_signals = enhance_signals_with_liquidity(all_signals, ohlcv)
    
    # 4. 回测交易
    trades = []
    in_position = False
    position = {}
    
    for i in range(120, n - 1):  # 从120根K线后开始
        bar = ohlcv[i]
        
        if not in_position:
            # 只在Bull方向交易 (V36结论)
            entry = evaluate_signal_entry_v37(ohlcv, i, enhanced_signals, liquidity_result, 'bull')
            if entry:
                in_position = True
                position = {
                    'entry_idx': i,
                    'entry_price': entry['entry_price'],
                    'direction': 'bull',
                    'sl_price': entry['sl_price'],
                    'sl_type': entry['sl_type'],
                    'tp_price': entry['tp_price'],
                    'tp_type': entry['tp_type'],
                    'v37_score': entry['v37_score'],
                    'v37_grade': entry['v37_grade'],
                    'has_liquidity_sweep': entry.get('has_liquidity_sweep', False),
                    'weekly_trend': entry['weekly_trend'],
                    'best_hold': 0,
                    'trailing_sl': entry['sl_price'],
                }
        else:
            # 持仓管理
            hold = i - position['entry_idx']
            current_price = ohlcv[i]['c']
            high = ohlcv[i]['h']
            low = ohlcv[i]['l']
            
            # Trailing
            new_sl = calc_trailing_v37(
                position['entry_price'], current_price,
                position['trailing_sl'], 'bull'
            )
            position['trailing_sl'] = new_sl
            
            # 检查止损/止盈
            exit_reason = None
            exit_price = None
            
            if low <= position['trailing_sl']:
                exit_reason = 'stop_loss'
                exit_price = position['trailing_sl']
            elif high >= position['tp_price']:
                exit_reason = 'take_profit' 
                exit_price = position['tp_price']
            elif hold >= MAX_HOLD:
                exit_reason = 'max_hold'
                exit_price = current_price
            
            if exit_reason:
                pnl_pct = (exit_price - position['entry_price']) / position['entry_price'] * 100
                rr = abs(pnl_pct) / max(0.01, abs(position['trailing_sl'] - position['entry_price']) / position['entry_price'] * 100)
                
                trades.append({
                    'entry_idx': position['entry_idx'],
                    'exit_idx': i,
                    'hold_bars': hold,
                    'direction': 'bull',
                    'entry_price': position['entry_price'],
                    'exit_price': round(exit_price, 4),
                    'sl_price': position['trailing_sl'],
                    'sl_type': position['sl_type'],
                    'tp_price': position['tp_price'],
                    'tp_type': position['tp_type'],
                    'exit_reason': exit_reason,
                    'pnl_pct': round(pnl_pct, 2),
                    'rr': round(rr, 2),
                    'v37_score': position['v37_score'],
                    'v37_grade': position['v37_grade'],
                    'has_liquidity_sweep': position.get('has_liquidity_sweep', False),
                    'weekly_trend': position['weekly_trend'],
                })
                in_position = False
                position = {}
    
    if not trades:
        return {'symbol': symbol, 'trades': [], 'tradable': False, 'reason': 'no_trades'}
    
    # 统计
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(abs(t['pnl_pct']) for t in losses) / len(losses) if losses else 0.01
    rr = avg_win / avg_loss if avg_loss > 0 else 0
    pf = sum(t['pnl_pct'] for t in wins) / max(0.01, sum(abs(t['pnl_pct']) for t in losses))
    total_pnl = sum(t['pnl_pct'] for t in trades)
    avg_hold = sum(t['hold_bars'] for t in trades) / len(trades)
    
    return {
        'symbol': symbol,
        'trades': trades,
        'tradable': True,
        'stats': {
            'total_trades': len(trades),
            'win_rate': round(wr, 1),
            'avg_rr': round(rr, 2),
            'profit_factor': round(pf, 1),
            'total_pnl_pct': round(total_pnl, 2),
            'avg_hold_bars': round(avg_hold, 1),
            'avg_win_pct': round(avg_win, 2),
            'avg_loss_pct': round(avg_loss, 2),
            'wins': len(wins),
            'losses': len(losses),
        },
        'v37_scores': {
            'S': sum(1 for t in trades if t['v37_grade'] == 'S'),
            'A': sum(1 for t in trades if t['v37_grade'] == 'A'),
            'B': sum(1 for t in trades if t['v37_grade'] == 'B'),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# 批量运行
# ═══════════════════════════════════════════════════════════════════════

def run_v37_batch(stock_list: List[str], limit: int = 200):
    """批量运行V37回测"""
    results = {'stocks': {}, 'all_trades': [], 'total': 0, 'tradable': 0}
    
    for idx, symbol in enumerate(stock_list[:limit]):
        ohlcv = load_ohlcv(symbol)
        if not ohlcv:
            continue
        
        result = backtest_stock_v37(symbol, ohlcv)
        results['stocks'][symbol] = result
        results['all_trades'].extend(result.get('trades', []))
        results['total'] += 1
        if result.get('tradable'):
            results['tradable'] += 1
        
        if (idx + 1) % 25 == 0:
            done = idx + 1
            stats = result.get('stats', {})
            print(f"  [{done}/{len(stock_list[:limit])}] {symbol:>10} "
                  f"n={stats.get('total_trades',0):>4} "
                  f"WR={stats.get('win_rate',0):>4}% "
                  f"PF={stats.get('profit_factor',0):>4}")
    
    # 汇总统计
    tradable_results = [r for r in results['stocks'].values() if r.get('tradable')]
    
    if tradable_results:
        total_trades = sum(r['stats']['total_trades'] for r in tradable_results)
        all_wins = sum(r['stats']['wins'] for r in tradable_results)
        all_losses = sum(r['stats']['losses'] for r in tradable_results)
        all_wr = all_wins / total_trades * 100 if total_trades > 0 else 0
        all_pnl = sum(r['stats']['total_pnl_pct'] for r in tradable_results)
        
        # 加权平均RR
        w_avg_rr = sum(r['stats']['avg_rr'] * r['stats']['total_trades'] for r in tradable_results) / total_trades if total_trades > 0 else 0
        
        wr_ge_80 = sum(1 for r in tradable_results if r['stats']['win_rate'] >= 80)
        
        print(f"\n{'='*70}")
        print(f"V37 — {results['tradable']}/{results['total']} tradable | {len(stock_list[:limit])} stocks scanned")
        print(f"{'='*70}")
        print(f"  Trades: {total_trades} | WR: {all_wr:.1f}% | RR: {w_avg_rr:.2f}x")
        print(f"  Total P&L: {all_pnl:+.2f}% | WR>=80%: {wr_ge_80}")
        
        # Grade breakdown
        s_count = sum(r['v37_scores']['S'] for r in tradable_results)
        a_count = sum(r['v37_scores']['A'] for r in tradable_results)
        b_count = sum(r['v37_scores']['B'] for r in tradable_results)
        print(f"  V37 Grade: S={s_count} A={a_count} B={b_count}")
        print(f"  Liquidity Sweep trades: {sum(1 for t in results['all_trades'] if t.get('has_liquidity_sweep', False))}")
        
        # 保存结果
        output_path = OUTPUT_DIR / 'backtest_v37.json'
        with open(output_path, 'w') as f:
            json.dump({
                'summary': {
                    'total_scanned': len(stock_list[:limit]),
                    'total_data': results['total'],
                    'tradable': results['tradable'],
                    'total_trades': total_trades,
                    'win_rate': round(all_wr, 1),
                    'avg_rr': round(w_avg_rr, 2),
                    'total_pnl': round(all_pnl, 2),
                    'wr_ge_80': wr_ge_80,
                    's_trades': s_count,
                    'a_trades': a_count,
                    'b_trades': b_count,
                },
                'stocks': {k: v for k, v in results['stocks'].items()},
            }, f, indent=1)
        print(f"\n  Saved: {output_path}")
    
    return results


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import random
    
    cache_files = list(CACHE_DIR.glob('*_daily_300.json'))
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.') for f in cache_files])
    random.seed(42)
    test_symbols = random.sample(symbols, min(MAX_STOCKS, len(symbols)))
    
    print(f"V37 Multi-Dimensional Adaptive Resonance System")
    print(f"Stocks: {len(test_symbols)} | Bars min: {MIN_BARS}")
    print(f"{'='*70}")
    
    t0 = time.time()
    results = run_v37_batch(test_symbols, limit=MAX_STOCKS)
    elapsed = time.time() - t0
    print(f"\nTime: {elapsed:.0f}s ({elapsed/60:.1f}min)")
