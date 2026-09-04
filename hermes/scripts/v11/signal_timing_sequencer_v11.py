#!/usr/bin/env python3
"""
V33 Comprehensive Signal Time-Sequence System
============================================
核心原则: 信号发生的 TIME-ORDER = 市场"剧本"的结构编码

A股日线SMC信号 = 市场做市商的"剧本"
每个信号是剧本中的一句对白, 顺序决定剧情走向

三层时序分析:
  Layer 1: SIGNAL PAIRS — 最近2个信号的类型+距离 (目前V32只做这个)
  Layer 2: SIGNAL CHAINS — 3-5个信号的完整序列模式
  Layer 3: MARKET PATTERN — 已知高胜率模式的匹配

时序评分不是简单的"有→加分", 而是:
  1. ORDER MATTERS: CHOCH→FVG 与 FVG→CHOCH 完全不同
  2. TIMING MATTERS: 3K线内的确认 vs 20K线外的"过期"确认
  3. COMBINATION MATTERS: 3个弱信号≠1个强信号
  4. STRENGTH MATTERS: 高confidence信号权重更高
  5. PHASE MATTERS: 相同序列在breakout vs ranging中意义不同
"""

from typing import List, Dict, Tuple, Optional
from collections import defaultdict

# ============================================================
# Layer 1: SIGNAL TYPE CODES
# ============================================================
# Each signal type gets a short prefix code for pattern building
SIGNAL_CODES = {
    'FVG_Bull': 'F',
    'FVG_Bear': 'f',
    'OB_Bull': 'O',
    'OB_Bear': 'o',
    'SweepDown': 'S',  # SSL扫荡(下方)
    'SweepUp': 's',    # BSL扫荡(上方)
    'CHOCH_Bull': 'C',  # 结构转为上升
    'CHOCH_Bear': 'c',  # 结构转为下降
    'BPR': 'B',
    'LiquidityVoid_Bull': 'L',
    'LiquidityVoid_Bear': 'l',
    'RejectionBlock_Bull': 'R',
    'RejectionBlock_Bear': 'r',
}

# ============================================================
# Layer 2: PATTERN DEFINITIONS (相同方向)
# ============================================================
# 已知高胜率信号序列模式
# 格式: code_sequence -> description, score_bonus, min_match
PATTERN_DB = {
    # ═══ GOLD: 结构转换确认 ═══
    'CF':     {'desc': 'CHOCH→FVG(最经典)', 'bonus': 0.35, 'min': 2, 'wr': 0.85},
    'FO':     {'desc': 'FVG→OB(双确认)', 'bonus': 0.30, 'min': 2, 'wr': 0.82},
    'SF':     {'desc': 'SSL扫荡→FVG(流动性抓取)', 'bonus': 0.30, 'min': 2, 'wr': 0.80},
    
    # ═══ SILVER: 好序列 ═══
    'FF':     {'desc': 'FVG→FVG(连续gap)', 'bonus': 0.20, 'min': 2, 'wr': 0.72},
    'SO':     {'desc': '扫荡→OB', 'bonus': 0.18, 'min': 2, 'wr': 0.68},
    'OF':     {'desc': 'OB→FVG', 'bonus': 0.18, 'min': 2, 'wr': 0.65},
    'CSF':    {'desc': 'CHOCH→Sweep→FVG(三级确认)', 'bonus': 0.50, 'min': 3, 'wr': 0.90},
    'SCF':    {'desc': 'Sweep→CHOCH→FVG', 'bonus': 0.45, 'min': 3, 'wr': 0.88},
    'CCF':    {'desc': '双重CHOCH→FVG', 'bonus': 0.40, 'min': 3, 'wr': 0.85},
    'COF':    {'desc': 'CHOCH→OB→FVG', 'bonus': 0.40, 'min': 3, 'wr': 0.83},
    'FOF':    {'desc': 'FVG→OB→FVG', 'bonus': 0.35, 'min': 3, 'wr': 0.80},
    'FFO':    {'desc': 'FVG→FVG→OB', 'bonus': 0.30, 'min': 3, 'wr': 0.78},
    
    # ═══ BRONZE: 一般信号 ═══
    'CO':     {'desc': 'CHOCH→OB', 'bonus': 0.15, 'min': 2, 'wr': 0.60},
    'OO':     {'desc': 'OB→OB', 'bonus': 0.05, 'min': 2, 'wr': 0.45},
    'SS':     {'desc': '扫荡→扫荡(双流)', 'bonus': -0.10, 'min': 2, 'wr': 0.35},
    
    # ═══ 3-信号链 ═══
    'SFF':    {'desc': '扫荡→FVG→FVG', 'bonus': 0.40, 'min': 3, 'wr': 0.85},
    'OFF':    {'desc': 'OB→FVG→FVG', 'bonus': 0.35, 'min': 3, 'wr': 0.82},
    'FCF':    {'desc': 'FVG→CHOCH→FVG', 'bonus': 0.35, 'min': 3, 'wr': 0.80},
    'OFC':    {'desc': 'OB→FVG→CHOCH', 'bonus': 0.45, 'min': 3, 'wr': 0.88},
}


def classify_signal_code(signal: Dict) -> str:
    """Convert a signal dict to its 1-char type code"""
    stype = signal.get('type', '')
    # Match against known signal codes
    for pattern, code in SIGNAL_CODES.items():
        if pattern in stype:
            return code
    # If nothing matches, try the first char of type
    if stype:
        return stype[0].upper()
    return '?'


# Core signal types only — filter out auxiliary signals (BPR, LiquidityVoid, RejectionBlock)
# These are noise, not useful for timing confirmation
CORE_SIGNAL_TYPES = {'FVG', 'OB', 'Sweep', 'CHOCH'}

def _is_core_signal(signal: Dict) -> bool:
    """Check if this is a core SMC signal (not auxiliary)"""
    stype = signal.get('type', '')
    return any(core in stype for core in CORE_SIGNAL_TYPES)

def extract_signal_chain(all_signals: List[Dict], target_bar: int, 
                          lookback: int = 30, max_signals: int = 6,
                          direction: str = 'bull',
                          exclude_idx: int = -1) -> Tuple[str, List[Dict]]:
    """
    提取目标bar之前, 特定方向的信号链
    Only core signals (FVG/OB/Sweep/CHOCH) are included — aux signals filtered out.
    
    Args:
        exclude_idx: If >= 0, exclude this signal idx from chain (the target signal)
    """
    # Get all core same-direction signals within lookback window
    preceding = [s for s in all_signals 
                 if s.get('idx', 0) <= target_bar
                 and s.get('idx', 0) >= target_bar - lookback
                 and s.get('direction') == direction
                 and _is_core_signal(s)
                 and s.get('idx', 0) != exclude_idx]  # Exclude target
    
    # Sort by time ascending (oldest first)
    preceding.sort(key=lambda s: s.get('idx', 0))
    
    # Take the last N signals (most recent)
    recent = preceding[-max_signals:]
    
    if not recent:
        return '', []
    
    # Build code string
    codes = ''.join(classify_signal_code(s) for s in recent)
    return codes, recent


def score_chain_by_pattern(code_string: str, direction: str = 'bull') -> Dict:
    """
    Layer 2: 信号链模式评分
    
    Check all sub-strings of code_string against PATTERN_DB.
    Longer matches get priority.
    """
    best_match = {
        'pattern': 'isolated',
        'desc': '孤立信号(无前序确认)',
        'bonus': 0.0,
        'matched_length': 0,
        'complexity': 1,
    }
    
    # Check all pattern lengths (2 to full length)
    max_len = len(code_string)
    for length in range(min(5, max_len), 1, -1):  # longest first = priority
        for start in range(max_len - length + 1):
            sub = code_string[start:start+length]
            if sub in PATTERN_DB:
                p = PATTERN_DB[sub]
                # Direction check: only match same direction patterns
                # (codes are case-sensitive: capital = bull, lowercase = bear)
                if direction == 'bull' and not sub[0].isupper():
                    continue
                match = {
                    'pattern': sub,
                    'desc': p['desc'],
                    'bonus': p['bonus'],
                    'matched_length': length,
                    'complexity': length,
                    'expected_wr': p.get('wr', 0.5),
                }
                # Longer match always beats shorter
                if length > best_match.get('matched_length', 0):
                    best_match = match
                elif length == best_match.get('matched_length', 0):
                    # Same length, pick higher bonus
                    if p['bonus'] > best_match.get('bonus', 0):
                        best_match = match
                break  # Found best for this start position
            if best_match.get('matched_length', 0) >= length:
                break  # Can't beat this
    
    # If chain has no recognized pattern but has at least 2 signals
    if best_match['pattern'] == 'isolated':
        # Check if there are ANY preceding signals
        n_signals = len(code_string)
        if n_signals >= 2:
            best_match['pattern'] = 'unrecognized'
            best_match['desc'] = f'未识别序列({code_string[-3:]})'
            best_match['bonus'] = 0.0
    
    return best_match


def analyze_signal_cluster(all_signals: List[Dict], target_signal: Dict,
                           direction: str = 'bull') -> Dict:
    """
    分析目标信号周围的信号"集群" — 不仅仅是最近1个信号
    
    Returns:
    {
        'chain_code': 'S_C_F',      # 完整信号链code
        'matched_pattern': 'C_S_F',  # 匹配到的已知模式
        'pattern_desc': '结构转多→扫荡→FVG',
        'bonus': 0.50,              # 时序加成
        'n_preceding': 3,           # 前序信号数
        'n_total': 4,               # 总信号数
        'signal_density': 0.10,     # 信号密度(信号数/回看窗口)
        'avg_separation': 5.3,      # 平均间距(K线)
        'last_distance': 2,         # 最近信号间距
        'complexity': 3,            # 链长度
    }
    """
    target_idx = target_signal.get('idx', 0)
    lookback = 30
    
    # Extract chain
    raw_code, preceding = extract_signal_chain(
        all_signals, target_idx, lookback=lookback, max_signals=6,
        direction=direction, exclude_idx=target_idx
    )
    
    n_preceding = len([s for s in preceding if s.get('idx', 0) < target_idx])
    n_total = len(preceding)
    
    # Score against known patterns
    match = score_chain_by_pattern(raw_code, direction)
    
    # Calculate cluster stats
    separations = []
    for i in range(1, len(preceding)):
        sep = preceding[i].get('idx', 0) - preceding[i-1].get('idx', 0)
        if 0 < sep <= lookback:
            separations.append(sep)
    
    last_distance = 999
    if preceding and len(preceding) >= 2:
        last = preceding[-2].get('idx', 0)  # second-to-last = closest preceding
        last_distance = target_idx - last if last < target_idx else 999
    
    avg_sep = sum(separations) / len(separations) if separations else lookback
    signal_density = n_total / lookback if lookback > 0 else 0
    
    return {
        'chain_code': raw_code,
        'matched_pattern': match['pattern'],
        'pattern_desc': match['desc'],
        'bonus': match['bonus'],
        'n_preceding': n_preceding,
        'n_total': n_total,
        'signal_density': round(signal_density, 3),
        'avg_separation': round(avg_sep, 1),
        'last_distance': last_distance,
        'complexity': match.get('complexity', 1),
        'expected_wr': match.get('expected_wr', 0.5),
    }


def score_signal_timing(all_signals: List[Dict], target_signal: Dict,
                         params: Dict = None) -> Dict:
    """
    综合信号时序评分 — V33核心
    
    三合一评分:
      1. 信号链模式匹配 (最强权)
      2. 信号间距分析 (时间有效性)
      3. 信号集群密度 (噪声vs确认)
    
    Returns:
    {
        'score': 0.0-1.0,           # 综合评分
        'grade': 'A/B/C/D/F',       # 等级
        'chain': 'C_S_F',           # 完整链
        'desc': '结构转多→扫荡→FVG', # 描述
        'bonus': 0.50,              # 模式加成
        'timing_penalty': 0.0,      # 时间衰减
        'cluster_bonus': 0.05,      # 集群密度加成
        'action': 'enter/wait/skip',
        'entry_mult': 1.0,          # 入场信心乘数(0=不要入场, >1=提高置信度)
    }
    """
    if params is None:
        params = {}
    
    target_idx = target_signal.get('idx', 0)
    target_type = target_signal.get('type', '')
    direction = target_signal.get('direction', 'bull')
    
    # Only score for FVG signals (our entry signals)
    if 'FVG' not in target_type:
        return _default_result('no_fvg', 0.50)
    
    # Get cluster analysis
    cluster = analyze_signal_cluster(all_signals, target_signal, direction)
    
    # ============================================================
    # COMPOSITE SCORE
    # ============================================================
    score = 0.50  # Base: 50% confidence (any signal gets 0.50)
    
    # Component 1: Pattern bonus (最高权重)
    if cluster['bonus'] != 0:
        score += cluster['bonus']
    
    # Component 2: Timing penalty (信号越新越有效)
    timing_penalty = 0.0
    if cluster['last_distance'] < 999:
        if cluster['last_distance'] <= 3:
            timing_penalty = 0.05       # 3K线内 — 紧密确认
        elif cluster['last_distance'] <= 8:
            timing_penalty = 0.0        # 4-8K线 — 可接受
        elif cluster['last_distance'] <= 15:
            timing_penalty = -0.05      # 9-15K线 — 衰减
        else:
            timing_penalty = -0.15      # >15K线 — 过期
    
    score += timing_penalty
    
    # Component 3: Cluster density bonus
    cluster_bonus = 0.0
    density = cluster['signal_density']
    n_prec = cluster['n_preceding']
    if n_prec == 0:
        # Isolated signal — no preceding core signals
        # But still scoreable if other conditions are good
        if not timing_penalty < 0:  # If timing is fresh
            pass  # Keep base 0.50
        else:
            score -= 0.10  # Old isolated signal
    elif 1 <= n_prec <= 3:
        cluster_bonus = 0.05   # Some confirmation
    elif 4 <= n_prec <= 6:
        cluster_bonus = 0.00   # Moderate
    else:
        cluster_bonus = -0.10  # Too many signals = noise
    
    score += cluster_bonus
    
    # Component 4: Separation bonus — tightly packed signals are stronger
    if cluster['avg_separation'] < 5 and n_prec >= 2:
        score += 0.05  # Signals packed close together = confirmation
    
    # ============================================================
    # GRADING
    # ============================================================
    grade = 'F'
    action = 'skip'
    entry_mult = 0.0  # Never enter without some score
    
    if score >= 0.75:
        grade = 'A'
        action = 'enter'
        entry_mult = 1.3  # 高置信度 — 允许降低共振门槛
    elif score >= 0.60:
        grade = 'B'
        action = 'enter'
        entry_mult = 1.0  # 正常入场
    elif score >= 0.50:
        grade = 'C'
        action = 'enter'    # 仅当共振极高时才入场
        entry_mult = 0.6    # 降低共振门槛15%
    elif score >= 0.35:
        grade = 'D'
        action = 'wait'
        entry_mult = 0.0
    else:
        grade = 'F'
        action = 'skip'
        entry_mult = 0.0
    
    # Override for isolated signals with no preceding signals
    if cluster['n_preceding'] == 0:
        # Isolated FVG: still allow if fresh (not old)
        if timing_penalty < -0.10:  # Old isolated signal
            grade = 'D'
            action = 'wait'
            entry_mult = 0.0
            cluster['pattern_desc'] = '孤立过期信号 — 跳过'
        else:
            # Fresh isolated FVG is scoreable at base 0.50 = Grade C
            if score < 0.50:
                grade = 'D'
                action = 'wait'
                entry_mult = 0.0
                cluster['pattern_desc'] = '孤立弱信号 — 跳过'
    
    score = max(0.0, min(1.0, score))
    
    return {
        'score': round(score, 3),
        'grade': grade,
        'action': action,
        'entry_mult': entry_mult,
        'chain': cluster['chain_code'],
        'desc': cluster['pattern_desc'],
        'bonus': cluster['bonus'],
        'timing_penalty': timing_penalty,
        'cluster_bonus': cluster_bonus,
        'complexity': cluster['complexity'],
        'n_preceding': cluster['n_preceding'],
        'last_distance': cluster['last_distance'],
        'avg_separation': cluster['avg_separation'],
        'signal_density': cluster['signal_density'],
        'expected_wr': cluster['expected_wr'],
    }


def _default_result(reason: str, score: float = 0.5):
    return {
        'score': score, 'grade': 'D', 'action': 'wait',
        'entry_mult': 0.5,
        'chain': '', 'desc': reason, 'bonus': 0,
        'timing_penalty': 0, 'cluster_bonus': 0,
        'complexity': 0, 'n_preceding': 0, 'last_distance': 999,
        'avg_separation': 999, 'signal_density': 0, 'expected_wr': 0.5,
    }
