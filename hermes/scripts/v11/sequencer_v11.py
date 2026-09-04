#!/usr/bin/env python3
# SMC V11 — Enhanced Signal Sequencer with Temporal Precision
"""
V11信号序列引擎 — 信号发生的时间顺序决定质量

核心创新 (vs V10):
1. 时间窗口约束: 信号之间的K线距离必须在窗口内, 超出不计
2. 部分序列匹配: 允许缺失部分步骤, 但根据完整度降权
3. 时间衰减: 信号间隔越长, 置信度越低
4. 多周期序列: 同一序列在不同TF同时出现 → 极强确认
5. 序列竞争: 多个序列同时存在时, 取最优
6. 信号间距离得分: 信号越近, 序列越可靠
7. 入场精确性: 序列的最后一步决定精确入场位置

序列等级:
  Platinum: 多TF Gold序列 + 摆动点对齐 (WR~88%)
  Gold:     Sweep → CHOCH → FVG → OB (WR~80%)
  Silver:   缺Sweep或缺OB (WR~70%)
  Bronze:   Sweep + FVG or CHOCH + FVG (WR~62%)
  Scout:    单一信号 (WR~50%, 不交易)
"""

import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v11.sequencer')


# ═══════════════════════════════════════════════════════════════════════
# Sequence definitions with time windows
# ═══════════════════════════════════════════════════════════════════════

SEQUENCE_DEFS = {
    # ═══ Gold Sequences (4/4 = WR~80%) ═══
    'LONG_GOLD': {
        'steps': ['SweepDown', 'CHOCH_Bull', 'FVG_Bull', 'OB_Bull'],
        'windows': [3, 4, 3],             # [V11.3] 收紧: Sweep→CHOCH 3K线, CHOCH→FVG 4K线, FVG→OB 3K线
        'min_steps': 3,
        'score_multiplier': 1.5,
        'expected_wr': 0.80,
        'description': 'SSL扫荡→看涨CHOCH→FVG→OB确认',
    },
    'SHORT_GOLD': {
        'steps': ['SweepUp', 'CHOCH_Bear', 'FVG_Bear', 'OB_Bear'],
        'windows': [3, 4, 3],
        'min_steps': 3,
        'score_multiplier': 1.5,
        'expected_wr': 0.80,
        'description': 'BSL扫荡→看跌CHOCH→FVG→OB确认',
    },
    
    # ═══ Silver Sequences (3/4 or alternative) [V11.3: 收紧窗口] ═══
    'LONG_SILVER_A': {
        'steps': ['CHOCH_Bull', 'FVG_Bull', 'OB_Bull'],
        'windows': [4, 3],              # [V11.3] 收紧: CHOCH→FVG 4K线, FVG→OB 3K线
        'min_steps': 2,
        'score_multiplier': 1.25,
        'expected_wr': 0.70,
        'description': 'CHOCH→FVG→OB(窗口4K线)',
    },
    'LONG_SILVER_B': {
        'steps': ['SweepDown', 'CHOCH_Bull', 'FVG_Bull'],
        'windows': [3, 4],              # [V11.3] 收紧: Sweep→CHOCH 3K线, CHOCH→FVG 4K线
        'min_steps': 2,
        'score_multiplier': 1.30,
        'expected_wr': 0.72,
        'description': 'SSL扫荡→CHOCH→FVG(窗口3K线)',
    },
    'SHORT_SILVER_A': {
        'steps': ['CHOCH_Bear', 'FVG_Bear', 'OB_Bear'],
        'windows': [4, 3],
        'min_steps': 2,
        'score_multiplier': 1.25,
        'expected_wr': 0.70,
        'description': 'CHOCH→FVG→OB(窗口4K线)',
    },
    'SHORT_SILVER_B': {
        'steps': ['SweepUp', 'CHOCH_Bear', 'FVG_Bear'],
        'windows': [3, 4],
        'min_steps': 2,
        'score_multiplier': 1.30,
        'expected_wr': 0.72,
        'description': 'BSL扫荡→CHOCH→FVG(窗口3K线)',
    },

    # ═══ Bronze Sequences (2-step) [V11.3: 收紧窗口2-3] ═══
    'LONG_BRONZE_A': {
        'steps': ['SweepDown', 'FVG_Bull'],
        'windows': [2],                 # [V11.3] 收紧: 2K线内
        'min_steps': 2,
        'score_multiplier': 1.1,
        'expected_wr': 0.62,
        'description': 'SSL扫荡→FVG(窗口2K线)',
    },
    'LONG_BRONZE_B': {
        'steps': ['CHOCH_Bull', 'FVG_Bull'],
        'windows': [2],                 # [V11.3] 收紧
        'min_steps': 2,
        'score_multiplier': 1.05,
        'expected_wr': 0.60,
        'description': 'CHOCH→FVG(窗口2K线)',
    },
    'SHORT_BRONZE_A': {
        'steps': ['SweepUp', 'FVG_Bear'],
        'windows': [2],
        'min_steps': 2,
        'score_multiplier': 1.1,
        'expected_wr': 0.62,
        'description': 'BSL扫荡→FVG',
    },
    'SHORT_BRONZE_B': {
        'steps': ['CHOCH_Bear', 'FVG_Bear'],
        'windows': [2],                 # [V11.3] 收紧
        'min_steps': 2,
        'score_multiplier': 1.05,
        'expected_wr': 0.60,
        'description': 'CHOCH→FVG(窗口2K线)',
    },

    # ═══ Extended Bronze (FVG→OB, Sweep→OB) [V11.3: 收紧窗口2] ═══
    'LONG_BRONZE_C': {
        'steps': ['FVG_Bull', 'OB_Bull'],
        'windows': [2],                 # [V11.3] 收紧: FVG→OB 2K线内
        'min_steps': 2,
        'score_multiplier': 1.05,
        'expected_wr': 0.60,
        'description': 'FVG→OB(窗口2K线)',
    },
    'SHORT_BRONZE_C': {
        'steps': ['FVG_Bear', 'OB_Bear'],
        'windows': [2],                 # [V11.3] 收紧
        'min_steps': 2,
        'score_multiplier': 1.05,
        'expected_wr': 0.60,
        'description': 'FVG→OB(窗口2K线)',
    },
    'LONG_BRONZE_D': {
        'steps': ['SweepDown', 'OB_Bull'],
        'windows': [2],                 # [V11.3] 收紧
        'min_steps': 2,
        'score_multiplier': 1.05,
        'expected_wr': 0.60,
        'description': 'SSL扫荡→OB(跳过CHOCH/FVG)',
    },
    'SHORT_BRONZE_D': {
        'steps': ['SweepUp', 'OB_Bear'],
        'windows': [2],                 # [V11.3] 收紧
        'min_steps': 2,
        'score_multiplier': 1.05,
        'expected_wr': 0.62,
        'description': 'BSL扫荡→OB(跳过CHOCH/FVG)',
    },
    
    # ═══ Scout Sequences (single signal, dire need only) ═══
    'LONG_SCOUT_FVG': {
        'steps': ['FVG_Bull'],
        'windows': [],
        'min_steps': 1,
        'score_multiplier': 0.80,
        'expected_wr': 0.50,
        'description': '单一FVG(无确认)',
    },
    'SHORT_SCOUT_FVG': {
        'steps': ['FVG_Bear'],
        'windows': [],
        'min_steps': 1,
        'score_multiplier': 0.80,
        'expected_wr': 0.50,
        'description': '单一FVG(无确认)',
    },
    'LONG_SCOUT_OB': {
        'steps': ['OB_Bull'],
        'windows': [],
        'min_steps': 1,
        'score_multiplier': 0.75,
        'expected_wr': 0.48,
        'description': '单一OB(无确认)',
    },
    'SHORT_SCOUT_OB': {
        'steps': ['OB_Bear'],
        'windows': [],
        'min_steps': 1,
        'score_multiplier': 0.75,
        'expected_wr': 0.48,
        'description': '单一OB(无确认)',
    },
}

# 信号规范化映射
NORMALIZE_MAP = {
    'SweepDown': 'SweepDown',
    'SweepUp': 'SweepUp',
    'OB_Bull': 'OB_Bull',
    'OB_Bear': 'OB_Bear',
    'CHOCH_Bull': 'CHOCH_Bull',
    'CHOCH_Bear': 'CHOCH_Bear',
    'MSB_Up': 'CHOCH_Bull',
    'MSB_Down': 'CHOCH_Bear',
    'IFVG_Bull': 'FVG_Bull',
    'IFVG_Bear': 'FVG_Bear',
    'FVG_Bull': 'FVG_Bull',
    'FVG_Bear': 'FVG_Bear',
    'FVG_Mitigated_Bull': 'FVG_Bull',
    'FVG_Mitigated_Bear': 'FVG_Bear',
    'BreakerBlock_Bull': 'OB_Bull',      # 被破坏的OB = 强支撑
    'BreakerBlock_Bear': 'OB_Bear',      # 被破坏的OB = 强阻力
    'Rejection_Support': 'OB_Bull',
    'Rejection_Resistance': 'OB_Bear',
    # BPR is direction='neutral' — exclude from directional sequence matching
    # BreakerBlock is direction='bull'/'bear' but sequence position varies
}


# ═══════════════════════════════════════════════════════════════════════
# Signal normalization
# ═══════════════════════════════════════════════════════════════════════

def normalize_signal(sig: Dict) -> Optional[str]:
    """标准化信号类型为序列匹配可用的token"""
    sig_type = sig.get('type', '')
    
    # Direct matches
    if sig_type in NORMALIZE_MAP:
        return NORMALIZE_MAP[sig_type]
    
    # FVG with direction
    if 'FVG' in sig_type:
        direction = sig.get('direction', '')
        if direction == 'bull':
            return 'FVG_Bull'
        elif direction == 'bear':
            return 'FVG_Bear'
    
    return None


def _find_fvg_entry(best_sequence: Dict, sequences_found: List[Dict]) -> Optional[Dict]:
    """[V11.4] 若序列以OB结尾且前方有FVG, 返回FVG作为提前入场信号
    Silver/Gold序列的OB确认延迟导致错过最佳入场点.
    FVG信号才是真正的入场点, OB只是确认.
    """
    name = best_sequence.get('name', '')
    # 只有LONG/SHORT结尾的序列才需要FVG优先
    if 'SCOUT' in name:
        return None  # Scout单信号, 不需要提前
    
    # 在sequences_found中找FVG信号
    for seq in sequences_found:
        if seq.get('name') != name:
            continue
        first_sig = seq.get('first_signal', {})
        first_type = first_sig.get('type', '')
        if 'FVG' in first_type:
            return first_sig
        # 如果第一个不是FVG, 找第二个
        match_data = seq.get('match', {})
        matched = match_data.get('matched_tokens', [])
        for m in matched:
            orig = m.get('original', {})
            if 'FVG' in orig.get('type', ''):
                return orig
    return None


# ═══════════════════════════════════════════════════════════════════════
# Core: Temporal-weighted sequence matching
# ═══════════════════════════════════════════════════════════════════════

def match_sequence_with_temporal_weight(
    token_list: List[Dict],       # [{'token': str, 'idx': int, 'confidence': float}, ...]
    pattern: List[str],           # ['SweepDown', 'CHOCH_Bull', ...]
    windows: List[int],           # [8, 12, 10]
    min_steps: int,
) -> Optional[Dict]:
    """时间加权的序列匹配
    
    核心创新: 信号间的距离直接影响匹配得分。
    两个信号越近, 越可能是同一波动的连续动作。
    
    Returns:
        {
            'matched_tokens': [token_dicts],
            'indices': [list_idx_in_token_list],
            'count': N,
            'total_steps': N,
            'completeness': float,
            'temporal_score': float,    # 基于信号间距的得分
            'confidence': float,        # 综合置信度
            'avg_distance': float,      # 平均信号间距(K线数)
            'last_signal': Dict,        # 最后一个信号(入场信号)
        }
    """
    if len(token_list) < min_steps:
        return None
    
    pattern_idx = 0
    matched_tokens = []
    matched_indices = []
    prev_idx = -1
    distances = []
    
    for i, entry in enumerate(token_list):
        if pattern_idx >= len(pattern):
            break
        
        token = entry['token']
        expected = pattern[pattern_idx]
        
        # 精确匹配或同族匹配
        if token == expected or _same_family_v11(token, expected):
            current_idx = entry.get('idx', 0)
            
            # 时间窗口检查 (第一个信号无限制)
            if pattern_idx > 0 and prev_idx >= 0 and windows:
                window = windows[pattern_idx - 1]
                dist = current_idx - prev_idx
                if dist > window:
                    # 距离太远, 重试更近的匹配
                    continue
            
            matched_tokens.append(entry)
            matched_indices.append(i)
            if prev_idx >= 0:
                distances.append(current_idx - prev_idx)
            prev_idx = current_idx
            pattern_idx += 1
    
    if len(matched_tokens) < min_steps:
        return None
    
    # 计算距离得分: 信号越近越好
    avg_distance = sum(distances) / len(distances) if distances else 0
    
    # 时间衰减: [V11.4] 快速衰减 - exp(-avg_dist/4), 距离>5完全不计
    temporal_score = math.exp(-avg_distance / 4.0) if distances else 1.0
    
    # 完整度
    completeness = len(matched_tokens) / len(pattern)
    
    # 平均置信度
    avg_confidence = sum(t.get('confidence', 0.5) for t in matched_tokens) / len(matched_tokens)
    
    # [V11.4] 综合置信度: 重时间分(时间距离=信号质量的核心指标)
    confidence = (completeness * 0.25 + temporal_score * 0.55 + avg_confidence * 0.20)
    
    return {
        'matched_tokens': matched_tokens,
        'indices': matched_indices,
        'count': len(matched_tokens),
        'total_steps': len(pattern),
        'completeness': completeness,
        'temporal_score': round(temporal_score, 4),
        'confidence': round(confidence, 4),
        'avg_distance': round(avg_distance, 1),
        'last_signal': matched_tokens[-1],
        'first_signal': matched_tokens[0],
    }


def _same_family_v11(token: str, pattern_step: str) -> bool:
    """检查两个信号是否属于同一族"""
    families = {
        'SweepDown': ['SweepDown'],
        'SweepUp': ['SweepUp'],
        'CHOCH_Bull': ['CHOCH_Bull', 'MSB_Up'],
        'CHOCH_Bear': ['CHOCH_Bear', 'MSB_Down'],
        'FVG_Bull': ['FVG_Bull', 'IFVG_Bull', 'FVG_Mitigated_Bull'],
        'FVG_Bear': ['FVG_Bear', 'IFVG_Bear', 'FVG_Mitigated_Bear'],
        'OB_Bull': ['OB_Bull', 'Rejection_Support'],
        'OB_Bear': ['OB_Bear', 'Rejection_Resistance'],
        # BPR excluded — direction='neutral', doesn't fit directional sequence
        # BreakerBlock excluded — uses CHOCH/OB as sequence ancestors
    }
    family = families.get(pattern_step, [pattern_step])
    return token in family


# ═══════════════════════════════════════════════════════════════════════
# Main sequence analysis
# ═══════════════════════════════════════════════════════════════════════

def analyze_sequence_v11(all_signals: List[Dict], 
                         params: Dict = None) -> Dict:
    """V11序列分析主入口
    
    Args:
        all_signals: detect_all_signals_v11()的all数组
        params: 可选参数 {score_min, ...}
    
    Returns:
        {
            'sequences_found': [匹配到的序列],
            'best_sequence': 最优序列或None,
            'confidence_boost': 1.0-1.5,
            'direction': 'bull'/'bear'/None,
            'entry_signal': 入场信号,
            'entry_price': 入场价格,
            'analysis': 详细分析,
        }
    """
    if params is None:
        params = {}
    
    if not all_signals:
        return {
            'sequences_found': [],
            'best_sequence': None,
            'confidence_boost': 1.0,
            'direction': None,
            'entry_signal': None,
            'entry_price': None,
        }
    
    # 标准化所有信号
    tokens = []
    for sig in all_signals:
        token = normalize_signal(sig)
        if token:
            tokens.append({
                'token': token,
                'idx': sig.get('idx', 0),
                'confidence': sig.get('confidence', 0.5),
                'price': sig.get('price', 0),
                'original': sig,
            })
    
    tokens.sort(key=lambda t: t['idx'])
    
    if len(tokens) < 2:
        return {
            'sequences_found': [],
            'best_sequence': None,
            'confidence_boost': 1.0,
            'direction': None,
            'entry_signal': None,
            'entry_price': None,
            'sequence_trace': [t['token'] for t in tokens],
        }
    
    # 匹配所有序列
    sequences_found = []
    
    for seq_name, seq_def in SEQUENCE_DEFS.items():
        match = match_sequence_with_temporal_weight(
            tokens, seq_def['steps'], seq_def['windows'], seq_def['min_steps']
        )
        if match:
            sequences_found.append({
                'name': seq_name,
                'definition': seq_def,
                'match': match,
            })
    
    if not sequences_found:
        return {
            'sequences_found': [],
            'best_sequence': None,
            'confidence_boost': 1.0,
            'direction': None,
            'entry_signal': None,
            'entry_price': None,
            'sequence_trace': [t['token'] for t in tokens],
        }
    
    # 评分排序: Gold > Silver > Bronze, 然后按置信度
    def seq_score(s):
        tier = 'BRONZE'
        name = s['name']
        if 'GOLD' in name: tier = 'GOLD'
        elif 'SILVER' in name: tier = 'SILVER'
        
        tier_score = {'GOLD': 3, 'SILVER': 2, 'BRONZE': 1}.get(tier, 0)
        return (tier_score, s['match']['confidence'], s['match']['count'])
    
    sequences_found.sort(key=seq_score, reverse=True)
    best = sequences_found[0]
    
    # 确定方向
    direction = None
    if 'LONG' in best['name']:
        direction = 'bull'
    elif 'SHORT' in best['name']:
        direction = 'bear'
    
    # 置信度加成
    base_mult = best['definition']['score_multiplier']
    completeness = best['match']['completeness']
    temporal = best['match']['temporal_score']
    confidence_boost = 1.0 + (base_mult - 1.0) * completeness * (0.7 + 0.3 * temporal)
    
    # 入场信号 = 序列最后一步
    last_match = best['match']['last_signal']
    entry_signal = last_match['original']
    entry_price = last_match['price']
    
    return {
        'sequences_found': [
            {
                'name': s['name'],
                'description': s['definition']['description'],
                'expected_wr': s['definition']['expected_wr'],
                'completeness': s['match']['completeness'],
                'confidence': s['match']['confidence'],
                'temporal_score': s['match']['temporal_score'],
                'avg_distance': s['match']['avg_distance'],
                'matched_count': s['match']['count'],
                'total_steps': s['match']['total_steps'],
                'first_signal': s['match']['first_signal']['original'],
                'last_signal': s['match']['last_signal']['original'],
            }
            for s in sequences_found
        ],
        'best_sequence': {
            'name': best['name'],
            'description': best['definition']['description'],
            'expected_wr': best['definition']['expected_wr'],
            'completeness': best['match']['completeness'],
            'confidence': best['match']['confidence'],
            'temporal_score': best['match']['temporal_score'],
            'avg_distance': best['match']['avg_distance'],
            'matched_count': best['match']['count'],
            'total_steps': best['match']['total_steps'],
            'first_signal': best['match']['first_signal']['original'],   # [V11.4] 修复: 添加first_signal
        },
        'confidence_boost': round(confidence_boost, 4),
        'direction': direction,
        'entry_signal': entry_signal,        # 序列最后一步(OB或FVG)
        'entry_price': entry_price,
        # [V11.4] 新增: FVG入场信号(若序列以OB结尾且FVG在前方, 用FVG作为入场点)
        'fvg_entry': _find_fvg_entry(best, sequences_found),
        'sequence_trace': [t['token'] for t in tokens],
        'total_normalized': len(tokens),
    }


# ═══════════════════════════════════════════════════════════════════════
# Multi-TF sequence analysis
# ═══════════════════════════════════════════════════════════════════════

def multi_tf_sequence_v11(tf_results: Dict[str, Dict]) -> Dict:
    """多周期序列分析
    
    核心: 同一序列模式在不同时间框架上同时出现 → 极强确认
    
    Args:
        tf_results: {'daily': seq_result, '4h': seq_result, '1h': seq_result, ...}
    
    Returns:
        {
            'tf_alignment': 'platinum'/'full'/'partial'/'none',
            'aligned_direction': 'bull'/'bear'/None,
            'aligned_tfs': ['daily', '4h'],
            'resonance_score': 0-1,
            'platinum_bonus': 1.0-1.3,  # 多TF确认的额外加成
            'per_tf': {...}
        }
    """
    per_tf = {}
    directions = []
    
    for tf, result in tf_results.items():
        per_tf[tf] = result
        if result.get('direction'):
            directions.append((tf, result['direction']))
    
    if len(directions) < 2:
        return {
            'tf_alignment': 'none',
            'aligned_direction': None,
            'aligned_tfs': [],
            'resonance_score': 0.0,
            'platinum_bonus': 1.0,
            'per_tf': per_tf,
        }
    
    # 检查方向一致性
    bulls = [tf for tf, d in directions if d == 'bull']
    bears = [tf for tf, d in directions if d == 'bear']
    
    aligned_tfs = []
    aligned_dir = None
    
    if len(bulls) >= 2:
        aligned_tfs = bulls
        aligned_dir = 'bull'
    elif len(bears) >= 2:
        aligned_tfs = bears
        aligned_dir = 'bear'
    
    if not aligned_tfs:
        return {
            'tf_alignment': 'none',
            'aligned_direction': None,
            'aligned_tfs': [],
            'resonance_score': 0.0,
            'platinum_bonus': 1.0,
            'per_tf': per_tf,
        }
    
    # 检查是否有Gold序列的多TF对齐 → Platinum
    has_gold = any(
        'GOLD' in result.get('best_sequence', {}).get('name', '')
        for tf, result in tf_results.items()
        if result.get('best_sequence')
    )
    
    # 共振得分
    tf_weights = {'daily': 0.40, 'weekly': 0.35, '4h': 0.30, '1h': 0.20, '15min': 0.15}
    total_weight = sum(tf_weights.get(tf, 0.2) for tf in aligned_tfs)
    max_weight = sum(tf_weights.get(tf, 0.2) for tf in tf_results.keys())
    resonance_score = total_weight / max_weight if max_weight > 0 else 0
    
    # 对齐级别
    all_aligned = len(aligned_tfs) == len(directions)
    if all_aligned and has_gold:
        tf_alignment = 'platinum'
        platinum_bonus = 1.3
    elif all_aligned:
        tf_alignment = 'full'
        platinum_bonus = 1.2
    else:
        tf_alignment = 'partial'
        platinum_bonus = 1.1
    
    return {
        'tf_alignment': tf_alignment,
        'aligned_direction': aligned_dir,
        'aligned_tfs': aligned_tfs,
        'resonance_score': round(resonance_score, 2),
        'platinum_bonus': platinum_bonus,
        'per_tf': per_tf,
    }


# ═══════════════════════════════════════════════════════════════════════
# Entry scoring
# ═══════════════════════════════════════════════════════════════════════

def score_entry_v11(seq_result: Dict, 
                    resonance_result: Dict = None,
                    base_score: float = 0.5) -> Dict:
    """基于序列分析的入场评分
    
    Args:
        seq_result: analyze_sequence_v11() 的输出
        resonance_result: multi_tf_sequence_v11() 的输出(可选)
        base_score: 基础分
    
    Returns:
        {
            'final_score': 0-1,
            'grade': 'S'/'A'/'B'/'C'/'D',
            'action': 'enter'/'wait'/'skip',
            'reason': str,
            'expected_wr': float,
        }
    """
    best = seq_result.get('best_sequence')
    
    if not best:
        return {
            'final_score': base_score * 0.3,
            'grade': 'D',
            'action': 'skip',
            'reason': '无已知信号序列 — 不交易',
            'expected_wr': 0.40,
        }
    
    completeness = best.get('completeness', 0)
    temporal_score = best.get('temporal_score', 0)
    expected_wr = best.get('expected_wr', 0.60)
    confidence = best.get('confidence', 0.5)
    boost = seq_result.get('confidence_boost', 1.0)
    
    # 基础分
    score = base_score * boost
    
    # 完整度调整
    score *= (0.5 + 0.5 * completeness)
    
    # 时间分调整: 信号越近越好
    score *= (0.7 + 0.3 * temporal_score)
    
    # 多TF加成
    if resonance_result:
        platinum = resonance_result.get('platinum_bonus', 1.0)
        score *= platinum
    
    score = min(1.0, score)
    
    # 评级
    if score >= 0.80:
        grade, action = 'S', 'enter'
        reason = f'{best["name"]} 完整度{completeness:.0%} WR预期{expected_wr:.0%}'
    elif score >= 0.65:
        grade, action = 'A', 'enter'
        reason = f'{best["name"]} 完整度{completeness:.0%} — 可入场'
    elif score >= 0.50:
        grade, action = 'B', 'wait'
        reason = f'{best["name"]} 完整度{completeness:.0%} — 等待确认'
    elif score >= 0.35:
        grade, action = 'C', 'watch'
        reason = f'{best["name"]} 信号不完整 — 观察'
    else:
        grade, action = 'D', 'skip'
        reason = '序列不完整 — 放弃'
    
    return {
        'final_score': round(score, 3),
        'grade': grade,
        'action': action,
        'reason': reason,
        'expected_wr': expected_wr,
        'sequence_name': best.get('name', ''),
        'confidence': best.get('confidence', 0),
    }
