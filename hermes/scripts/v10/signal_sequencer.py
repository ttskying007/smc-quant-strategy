#!/usr/bin/env python3
# SMC V10 — Signal Sequencer: Order Matters
"""
核心创新: 信号发生顺序直接影响胜率。

ICT/SMC 理论中，信号出现的顺序决定信号质量:
  Gold Sequence (做多): SSL Sweep → Bullish CHOCH → FVG Retest → OB Confirmation
  Gold Sequence (做空): BSL Sweep → Bearish CHOCH → FVG Retest → OB Confirmation
  
降级序列:
  Silver: CHOCH → FVG Retest (缺少 Sweep，信号弱一档)
  Bronze: FVG + OB alone (无结构转换)
  Noise: Isolated FVG/Sweep (噪音，不可交易)

检测逻辑:
1. 扫描所有原始信号 (FVG, Sweep, OB, CHOCH, BPR, MSB)
2. 按时间顺序排列
3. 匹配已知的高胜率序列模式
4. 对匹配到的序列计算"顺序得分"(sequence score)
5. 根据序列完整度给予加成倍率
"""

import logging
from collections import defaultdict
from typing import List, Dict, Optional, Tuple, Set

log = logging.getLogger('smc_v10.sequencer')

# ═══════════════════════════════════════════════════════════════════════
# Sequence pattern definitions
# ═══════════════════════════════════════════════════════════════════════

# Each pattern is: (step1_type, step2_type, step3_type, step4_type) + metadata
# The score_multiplier is applied to the base confidence score

GOLD_SEQUENCES = {
    'LONG_GOLD': {
        'steps': ['SweepDown', 'CHOCH_Bull', 'FVG_Bull_Retest', 'OB_Bull_Confirm'],
        'min_steps': 3,           # need at least 3/4 steps
        'score_multiplier': 1.5,  # 50% bonus
        'description': 'SSL扫荡→看涨CHOCH→FVG回测→OB确认',
        'expected_wr': 0.80,      # expected win rate for this sequence
    },
    'SHORT_GOLD': {
        'steps': ['SweepUp', 'CHOCH_Bear', 'FVG_Bear_Retest', 'OB_Bear_Confirm'],
        'min_steps': 3,
        'score_multiplier': 1.5,
        'description': 'BSL扫荡→看跌CHOCH→FVG回测→OB确认',
        'expected_wr': 0.80,
    },
}

SILVER_SEQUENCES = {
    'LONG_SILVER_A': {
        'steps': ['CHOCH_Bull', 'FVG_Bull_Retest', 'OB_Bull_Confirm'],
        'min_steps': 2,
        'score_multiplier': 1.25,
        'description': '看涨CHOCH→FVG回测→OB确认(无Sweep)',
        'expected_wr': 0.70,
    },
    'LONG_SILVER_B': {
        'steps': ['SweepDown', 'CHOCH_Bull', 'FVG_Bull_Retest'],
        'min_steps': 2,
        'score_multiplier': 1.30,
        'description': 'SSL扫荡→看涨CHOCH→FVG回测(无OB)',
        'expected_wr': 0.72,
    },
    'SHORT_SILVER_A': {
        'steps': ['CHOCH_Bear', 'FVG_Bear_Retest', 'OB_Bear_Confirm'],
        'min_steps': 2,
        'score_multiplier': 1.25,
        'description': '看跌CHOCH→FVG回测→OB确认(无Sweep)',
        'expected_wr': 0.70,
    },
    'SHORT_SILVER_B': {
        'steps': ['SweepUp', 'CHOCH_Bear', 'FVG_Bear_Retest'],
        'min_steps': 2,
        'score_multiplier': 1.30,
        'description': 'BSL扫荡→看跌CHOCH→FVG回测(无OB)',
        'expected_wr': 0.72,
    },
}

BRONZE_SEQUENCES = {
    'LONG_BRONZE': {
        'steps': ['SweepDown', 'FVG_Bull_Retest'],
        'min_steps': 2,
        'score_multiplier': 1.1,
        'description': 'SSL扫荡→FVG回测',
        'expected_wr': 0.62,
    },
    'SHORT_BRONZE': {
        'steps': ['SweepUp', 'FVG_Bear_Retest'],
        'min_steps': 2,
        'score_multiplier': 1.1,
        'description': 'BSL扫荡→FVG回测',
        'expected_wr': 0.62,
    },
}

ALL_SEQUENCES = {**GOLD_SEQUENCES, **SILVER_SEQUENCES, **BRONZE_SEQUENCES}


# ═══════════════════════════════════════════════════════════════════════
# Signal normalization — convert raw signals to sequence tokens
# ═══════════════════════════════════════════════════════════════════════

def _normalize_signal(signal: Dict) -> Optional[str]:
    """Convert a raw signal dict to a sequence token for pattern matching.
    
    Maps:
      SweepDown → 'SweepDown'
      SweepUp → 'SweepUp'  
      OB_Bull → 'OB_Bull_Confirm' (if near a FVG retest)
      FVG with direction=bull → 'FVG_Bull' → needs context for 'Retest'
      CHOCH detected → 'CHOCH_Bull' or 'CHOCH_Bear'
      MSB_Up → 'CHOCH_Bull' (same meaning)
      BPR_Bull → 'FVG_Bull_Retest' (balanced price range = retest)
    """
    sig_type = signal.get('type', '')
    direction = signal.get('direction', '')
    
    # Sweep
    if sig_type == 'SweepDown':
        return 'SweepDown'
    if sig_type == 'SweepUp':
        return 'SweepUp'
    
    # OB
    if sig_type == 'OB_Bull':
        return 'OB_Bull_Confirm'
    if sig_type == 'OB_Bear':
        return 'OB_Bear_Confirm'
    
    # CHOCH / MSB
    if sig_type in ('CHOCH_Bull', 'MSB_Up'):
        return 'CHOCH_Bull'
    if sig_type in ('CHOCH_Bear', 'MSB_Down'):
        return 'CHOCH_Bear'
    
    # BPR = FVG retest
    if sig_type == 'BPR_Bull':
        return 'FVG_Bull_Retest'
    if sig_type == 'BPR_Bear':
        return 'FVG_Bear_Retest'
    
    # FVG — check if it's been retested
    if sig_type == 'FVG':
        is_mitigated = signal.get('mitigated', False)
        if is_mitigated:
            return 'FVG_Bull_Retest' if direction == 'bull' else 'FVG_Bear_Retest'
        else:
            return 'FVG_Bull' if direction == 'bull' else 'FVG_Bear'
    
    # IFVG
    if sig_type == 'IFVG':
        return 'FVG_Bull_Retest' if direction == 'bull' else 'FVG_Bear_Retest'
    
    return None


# ═══════════════════════════════════════════════════════════════════════
# Core sequencing algorithm
# ═══════════════════════════════════════════════════════════════════════

def analyze_signal_sequence(raw_signals: List[Dict]) -> Dict:
    """Analyze signal sequence and identify high-quality patterns.
    
    The key insight: signals in isolation are weak. Signals forming a
    known high-probability sequence are strong.
    
    Args:
        raw_signals: list of signal dicts from detect_all_signals()
    
    Returns:
        {
            'sequences_found': [matched sequence patterns],
            'best_sequence': best_match or None,
            'confidence_boost': 1.0-2.0 multiplier,
            'entry_signal': recommended entry signal,
            'sequence_trace': chronological order of normalized signals,
            'direction': 'bull'/'bear'/None (overall direction),
        }
    """
    # Normalize all signals
    tokens = []
    for sig in raw_signals:
        token = _normalize_signal(sig)
        if token:
            tokens.append({
                'token': token,
                'idx': sig.get('idx', 0),
                'original': sig,
            })
    
    # Sort by index (chronological order)
    tokens.sort(key=lambda t: t['idx'])
    
    if len(tokens) < 2:
        return {
            'sequences_found': [],
            'best_sequence': None,
            'confidence_boost': 1.0,
            'entry_signal': None,
            'sequence_trace': [t['token'] for t in tokens],
            'direction': None,
        }
    
    # Build chronological token list
    token_list = [t['token'] for t in tokens]
    
    # Match against all known sequences
    matches = []
    
    for seq_name, seq_def in ALL_SEQUENCES.items():
        steps = seq_def['steps']
        min_steps = seq_def['min_steps']
        
        # Try to match subsequence in chronological order
        match_result = _match_subsequence(token_list, steps, min_steps)
        
        if match_result:
            matches.append({
                'name': seq_name,
                'definition': seq_def,
                'matched_steps': match_result['matched'],
                'match_count': match_result['count'],
                'total_steps': len(steps),
                'completeness': match_result['count'] / len(steps),
                'indices': match_result['indices'],
            })
    
    # Sort by: tier priority (gold > silver > bronze), then completeness
    tier_priority = {
        'LONG_GOLD': 3, 'SHORT_GOLD': 3,
        'LONG_SILVER_A': 2, 'LONG_SILVER_B': 2,
        'SHORT_SILVER_A': 2, 'SHORT_SILVER_B': 2,
        'LONG_BRONZE': 1, 'SHORT_BRONZE': 1,
    }
    
    matches.sort(key=lambda m: (
        tier_priority.get(m['name'], 0),
        m['completeness'],
        m['match_count'],
    ), reverse=True)
    
    # Determine best sequence and direction
    best = matches[0] if matches else None
    
    direction = None
    if best:
        if 'LONG' in best['name']:
            direction = 'bull'
        elif 'SHORT' in best['name']:
            direction = 'bear'
    
    # Confidence boost from sequence
    confidence_boost = 1.0
    if best:
        base_boost = best['definition']['score_multiplier']
        completeness = best['completeness']
        confidence_boost = 1.0 + (base_boost - 1.0) * completeness
    
    # Entry signal: the last signal in the best sequence
    entry_signal = None
    if best and best['indices']:
        last_idx = best['indices'][-1]
        if last_idx < len(tokens):
            entry_signal = tokens[last_idx]['original']
    
    return {
        'sequences_found': matches,
        'best_sequence': best,
        'confidence_boost': round(confidence_boost, 2),
        'entry_signal': entry_signal,
        'sequence_trace': token_list,
        'direction': direction,
        'total_signals': len(raw_signals),
        'normalized_signals': len(tokens),
    }


def _match_subsequence(token_list: List[str], pattern: List[str], min_steps: int) -> Optional[Dict]:
    """Check if pattern appears as a subsequence in token_list.
    
    Uses greedy matching: find pattern elements in order.
    
    Returns: {'matched': [...], 'count': N, 'indices': [...]} or None
    """
    if len(token_list) < min_steps:
        return None
    
    pattern_idx = 0
    matched = []
    indices = []
    
    for i, token in enumerate(token_list):
        if pattern_idx >= len(pattern):
            break
        
        # Try exact match first
        if token == pattern[pattern_idx]:
            matched.append(token)
            indices.append(i)
            pattern_idx += 1
        # Fuzzy match: same family
        elif _same_family(token, pattern[pattern_idx]):
            matched.append(pattern[pattern_idx])  # use canonical name
            indices.append(i)
            pattern_idx += 1
    
    if len(matched) >= min_steps:
        return {'matched': matched, 'count': len(matched), 'indices': indices}
    
    return None


def _same_family(token: str, pattern_step: str) -> bool:
    """Check if token belongs to the same signal family as pattern_step."""
    families = {
        'SweepDown': ['SweepDown'],
        'SweepUp': ['SweepUp'],
        'CHOCH_Bull': ['CHOCH_Bull', 'MSB_Up'],
        'CHOCH_Bear': ['CHOCH_Bear', 'MSB_Down'],
        'FVG_Bull_Retest': ['FVG_Bull_Retest', 'BPR_Bull', 'IFVG'],
        'FVG_Bear_Retest': ['FVG_Bear_Retest', 'BPR_Bear', 'IFVG'],
        'OB_Bull_Confirm': ['OB_Bull_Confirm', 'OB_Bull'],
        'OB_Bear_Confirm': ['OB_Bear_Confirm', 'OB_Bear'],
    }
    
    family = families.get(pattern_step, [pattern_step])
    return token in family


# ═══════════════════════════════════════════════════════════════════════
# Sequence-based entry scoring
# ═══════════════════════════════════════════════════════════════════════

def score_entry_from_sequence(seq_result: Dict, base_score: float = 0.5) -> Dict:
    """Calculate entry quality score based on sequence analysis.
    
    This is the critical function: it takes the sequence result
    and produces a final confidence score for the trade entry.
    
    Args:
        seq_result: output from analyze_signal_sequence()
        base_score: starting score (default 0.5 on 0-1 scale)
    
    Returns:
        {
            'final_score': 0.0-1.0,
            'grade': 'S'/'A'/'B'/'C'/'D',
            'action': 'enter'/'wait'/'skip',
            'reason': explanation string,
        }
    """
    best = seq_result.get('best_sequence')
    
    if not best:
        return {
            'final_score': base_score * 0.3,
            'grade': 'D',
            'action': 'skip',
            'reason': '无已知信号序列 — 单独信号不可交易',
        }
    
    # Score components
    completeness = best['completeness']  # 0-1
    tier = 'Gold' if 'GOLD' in best['name'] else ('Silver' if 'SILVER' in best['name'] else 'Bronze')
    boost = best['definition']['score_multiplier']
    expected_wr = best['definition']['expected_wr']
    
    # Base score × sequence boost × completeness
    score = base_score * boost * completeness
    
    # Cap at 1.0
    score = min(1.0, score)
    
    # Grade and action
    if score >= 0.8:
        grade, action = 'S', 'enter'
        reason = f'{tier}序列({best["name"]}), 完整度{completeness:.0%}, 预期WR={expected_wr:.0%}'
    elif score >= 0.65:
        grade, action = 'A', 'enter'
        reason = f'{tier}序列({best["name"]}), 完整度{completeness:.0%} — 可入场,紧止损'
    elif score >= 0.5:
        grade, action = 'B', 'wait'
        reason = f'{tier}序列({best["name"]}), 完整度{completeness:.0%} — 等待更多确认'
    elif score >= 0.35:
        grade, action = 'C', 'wait'
        reason = f'{tier}序列({best["name"]}), 信号不完整 — 观察'
    else:
        grade, action = 'D', 'skip'
        reason = f'信号序列不完整 — 放弃'
    
    return {
        'final_score': round(score, 3),
        'grade': grade,
        'action': action,
        'reason': reason,
        'expected_wr': expected_wr,
        'sequence_name': best['name'],
        'matched_steps': best['matched_steps'],
    }


# ═══════════════════════════════════════════════════════════════════════
# Multi-timeframe sequence analysis
# ═══════════════════════════════════════════════════════════════════════

def multi_tf_sequence_analyze(tf_signals: Dict[str, List[Dict]]) -> Dict:
    """Analyze signal sequences across multiple timeframes.
    
    The holy grail: same sequence pattern appearing across timeframes.
    E.g., Gold sequence on Daily AND Gold sequence on 4H → very strong.
    
    Args:
        tf_signals: {'daily': [signals], '4h': [signals], '1h': [signals], ...}
    
    Returns:
        {
            'tf_alignment': 'full'/'partial'/'none',
            'aligned_direction': 'bull'/'bear'/None,
            'aligned_tfs': ['daily', '4h'],
            'resonance_score': 0-1,
            'per_tf': {tf: sequence_result}
        }
    """
    per_tf = {}
    directions = []
    
    for tf, signals in tf_signals.items():
        result = analyze_signal_sequence(signals)
        per_tf[tf] = result
        if result['direction']:
            directions.append((tf, result['direction']))
    
    if len(directions) < 2:
        return {
            'tf_alignment': 'none',
            'aligned_direction': None,
            'aligned_tfs': [],
            'resonance_score': 0.0,
            'per_tf': per_tf,
        }
    
    # Check direction alignment
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
            'per_tf': per_tf,
        }
    
    # Calculate resonance score
    tf_weights = {'daily': 0.4, 'weekly': 0.5, '4h': 0.3, '1h': 0.2, '15min': 0.15, '5min': 0.1}
    
    total_weight = sum(tf_weights.get(tf, 0.2) for tf in aligned_tfs)
    max_weight = sum(tf_weights.get(tf, 0.2) for tf in tf_signals.keys())
    resonance_score = total_weight / max_weight if max_weight > 0 else 0
    
    # Full alignment: all TFs agree
    tf_alignment = 'full' if len(aligned_tfs) == len(directions) else 'partial'
    
    return {
        'tf_alignment': tf_alignment,
        'aligned_direction': aligned_dir,
        'aligned_tfs': aligned_tfs,
        'resonance_score': round(resonance_score, 2),
        'per_tf': per_tf,
    }


# ═══════════════════════════════════════════════════════════════════════
# Quick API
# ═══════════════════════════════════════════════════════════════════════

def quick_sequence_check(raw_signals: List[Dict]) -> Dict:
    """One-call sequence analysis and entry scoring."""
    seq_result = analyze_signal_sequence(raw_signals)
    entry_score = score_entry_from_sequence(seq_result)
    return {
        **seq_result,
        'entry_score': entry_score,
    }
