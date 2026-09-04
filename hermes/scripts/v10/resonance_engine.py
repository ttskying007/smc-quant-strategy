#!/usr/bin/env python3
# SMC V10 — Multi-TF + Multi-Indicator Resonance Engine
"""
核心创新: 共振 = 胜率放大器。

共振维度:
1. 时间框架共振 (TF Resonance): Daily↑ + 4H↑ + 1H↑ → 三重共振
2. 指标共振 (Indicator Resonance): Sweep + CHOCH + FVG + OB → 四重共振
3. 摆动点共振 (Swing Resonance): Micro↑ + Meso↑ + Macro↑ → 三重共振
4. 信号顺序共振 (Sequence Resonance): Gold Sequence pattern match

共振层次:
  单层共振: base WR ~60%
  双层共振: base WR ~70%
  三层共振: base WR ~80%
  四层全共振: base WR ~88%+
  
每种共振贡献独立的一维得分，最终得分为各维度的加权乘积。
"""

import math, logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v10.resonance')


# ═══════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ResonanceScore:
    """Multi-dimensional resonance score."""
    tf_resonance: float = 0.0        # 0-1: timeframe alignment
    indicator_resonance: float = 0.0  # 0-1: indicator confluence
    swing_resonance: float = 0.0      # 0-1: swing point alignment
    sequence_resonance: float = 0.0   # 0-1: sequence pattern match
    
    @property
    def total(self) -> float:
        """Weighted total resonance score."""
        return (
            self.tf_resonance * 0.30 +
            self.indicator_resonance * 0.30 +
            self.swing_resonance * 0.25 +
            self.sequence_resonance * 0.15
        )
    
    @property
    def layers(self) -> int:
        """Count how many resonance layers are active (>0.5)."""
        return sum(1 for x in [
            self.tf_resonance, self.indicator_resonance,
            self.swing_resonance, self.sequence_resonance
        ] if x >= 0.5)
    
    @property
    def expected_wr(self) -> float:
        """Estimated win rate based on resonance layers."""
        base = {0: 0.40, 1: 0.55, 2: 0.68, 3: 0.78, 4: 0.86}
        return base.get(self.layers, 0.86)
    
    def to_dict(self) -> Dict:
        return {
            'tf': round(self.tf_resonance, 3),
            'indicator': round(self.indicator_resonance, 3),
            'swing': round(self.swing_resonance, 3),
            'sequence': round(self.sequence_resonance, 3),
            'total': round(self.total, 3),
            'layers': self.layers,
            'expected_wr': self.expected_wr,
        }


# ═══════════════════════════════════════════════════════════════════════
# 1. Timeframe Resonance
# ═══════════════════════════════════════════════════════════════════════

def calc_tf_resonance(tf_directions: Dict[str, Optional[str]], 
                      tf_strengths: Dict[str, float] = None) -> float:
    """Calculate timeframe resonance: do higher TFs agree with target?
    
    Args:
        tf_directions: {'weekly': 'bull', 'daily': 'bull', '4h': 'bear', ...}
        tf_strengths: optional signal strength per TF
    
    Returns: 0-1 resonance score
    """
    if not tf_directions:
        return 0.0
    
    # Timeframe weight: higher TF = more weight
    tf_weights = {
        'monthly': 1.0, 'weekly': 0.9, 'daily': 0.8,
        '4h': 0.6, '2h': 0.5, '1h': 0.4, '30min': 0.3,
        '15min': 0.25, '5min': 0.2, '1min': 0.1,
    }
    
    # Count aligned vs opposed directions
    bulls = []
    bears = []
    
    for tf, direction in tf_directions.items():
        if direction is None:
            continue
        weight = tf_weights.get(tf, 0.3)
        
        # Adjust by signal strength if provided
        if tf_strengths and tf in tf_strengths:
            weight *= min(1.0, tf_strengths[tf])
        
        if direction == 'bull':
            bulls.append(weight)
        elif direction == 'bear':
            bears.append(weight)
        elif direction == 'neutral':
            bulls.append(weight * 0.3)
            bears.append(weight * 0.3)
    
    total_bull = sum(bulls)
    total_bear = sum(bears)
    total = total_bull + total_bear
    
    if total == 0:
        return 0.0
    
    # Dominant direction / total = resonance
    dominant = max(total_bull, total_bear)
    
    # Bonus: if all TFs agree
    if total_bull == 0 or total_bear == 0:
        return min(1.0, dominant / total * 1.2)  # 20% bonus for unanimous
    
    return dominant / total


# ═══════════════════════════════════════════════════════════════════════
# 2. Indicator Resonance
# ═══════════════════════════════════════════════════════════════════════

def calc_indicator_resonance(signals: List[Dict], lookback_idx: int = None) -> float:
    """Calculate indicator confluence within a local window.
    
    Indicators: FVG, Sweep, OB, CHOCH, BPR, MSB
    Each contributes independently, but direction consistency multiplies.
    
    Args:
        signals: all detected signals
        lookback_idx: focus on signals near this index (None = all)
    
    Returns: 0-1 resonance score
    """
    if not signals:
        return 0.0
    
    # Filter to recent signals if lookback specified
    if lookback_idx is not None:
        window = max(1, min(20, lookback_idx // 10))
        signals = [s for s in signals if abs(s.get('idx', 0) - lookback_idx) <= window]
    
    if not signals:
        return 0.0
    
    # Count indicators present
    indicator_flags = {
        'FVG': False, 'Sweep': False, 'OB': False,
        'CHOCH': False, 'BPR': False, 'MSB': False,
    }
    
    directions = []
    
    for s in signals:
        sig_type = s.get('type', '')
        direction = s.get('direction', '')
        
        if 'FVG' in sig_type or 'IFVG' in sig_type:
            indicator_flags['FVG'] = True
        elif 'Sweep' in sig_type:
            indicator_flags['Sweep'] = True
        elif 'OB' in sig_type:
            indicator_flags['OB'] = True
        elif 'CHOCH' in sig_type or sig_type.startswith('Swing_CHOCH'):
            indicator_flags['CHOCH'] = True
        elif 'BPR' in sig_type:
            indicator_flags['BPR'] = True
        elif 'MSB' in sig_type:
            indicator_flags['MSB'] = True
        
        if direction in ('bull', 'bear'):
            directions.append(direction)
    
    # Score: how many indicators present
    present = sum(1 for v in indicator_flags.values() if v)
    indicator_count_score = present / 6.0  # 0-1 based on presence
    
    # Direction consistency
    if directions:
        bulls = sum(1 for d in directions if d == 'bull')
        bears = sum(1 for d in directions if d == 'bear')
        consistency = max(bulls, bears) / len(directions)
    else:
        consistency = 0.5
    
    # Weighted combination
    # The "perfect" combo: Sweep + CHOCH + FVG = all 3 weight most
    key_indicators = indicator_flags['Sweep'] + indicator_flags['CHOCH'] + indicator_flags['FVG']
    key_score = key_indicators / 3.0
    
    resonance = (
        indicator_count_score * 0.3 +
        consistency * 0.35 +
        key_score * 0.35
    )
    
    # Bonus for the golden trio
    if indicator_flags['Sweep'] and indicator_flags['CHOCH'] and indicator_flags['FVG']:
        resonance = min(1.0, resonance * 1.25)
    
    return resonance


# ═══════════════════════════════════════════════════════════════════════
# 3. Swing Point Resonance
# ═══════════════════════════════════════════════════════════════════════

def calc_swing_resonance(swing_tree: Dict) -> float:
    """Calculate swing point resonance from hierarchy tree.
    
    Input: tree from swing_points._build_hierarchy_tree()
    
    Returns: 0-1 resonance score
    """
    if not swing_tree:
        return 0.0
    
    if swing_tree.get('all_aligned', False):
        return swing_tree.get('strength', 1.0)
    
    # Partial alignment
    confirmed = len(swing_tree.get('levels_confirmed', []))
    if confirmed >= 2:
        return 0.6
    elif confirmed == 1:
        return 0.35
    
    return 0.1


# ═══════════════════════════════════════════════════════════════════════
# 4. Sequence Resonance  
# ═══════════════════════════════════════════════════════════════════════

def calc_sequence_resonance(seq_result: Dict) -> float:
    """Calculate sequence resonance from signal sequencer output.
    
    Args:
        seq_result: output from signal_sequencer.analyze_signal_sequence()
    
    Returns: 0-1 resonance score
    """
    best = seq_result.get('best_sequence')
    if not best:
        return 0.0
    
    completeness = best['completeness']
    
    # Tier multiplier
    if 'GOLD' in best['name']:
        tier_mult = 1.0
    elif 'SILVER' in best['name']:
        tier_mult = 0.7
    else:
        tier_mult = 0.4
    
    return min(1.0, completeness * tier_mult * 1.2)


# ═══════════════════════════════════════════════════════════════════════
# Full resonance engine
# ═══════════════════════════════════════════════════════════════════════

def evaluate_full_resonance(
    tf_directions: Dict[str, Optional[str]],
    signals: List[Dict],
    swing_tree: Dict,
    seq_result: Dict,
    symbol: str = '',
    lookback_idx: int = None,
) -> ResonanceScore:
    """Evaluate all four resonance dimensions and produce final score.
    
    This is THE function to call for trade entry validation.
    
    Args:
        tf_directions: {'daily': 'bull', '4h': 'bear', ...}
        signals: all detected signals from SMC detectors
        swing_tree: tree from swing_points module
        seq_result: sequence analysis from signal_sequencer module
        symbol: stock symbol for logging
        lookback_idx: focus index for indicator resonance
    
    Returns: ResonanceScore with all dimensions
    """
    score = ResonanceScore()
    
    score.tf_resonance = calc_tf_resonance(tf_directions)
    score.indicator_resonance = calc_indicator_resonance(signals, lookback_idx)
    score.swing_resonance = calc_swing_resonance(swing_tree)
    score.sequence_resonance = calc_sequence_resonance(seq_result)
    
    log.debug(f"[{symbol}] Resonance: TF={score.tf_resonance:.2f} "
              f"Ind={score.indicator_resonance:.2f} "
              f"Swing={score.swing_resonance:.2f} "
              f"Seq={score.sequence_resonance:.2f} "
              f"Total={score.total:.2f} Layers={score.layers}")
    
    return score


def get_resonance_grade(score: ResonanceScore) -> Dict:
    """Get human-readable grade and action from resonance score."""
    total = score.total
    layers = score.layers
    
    if total >= 0.75 and layers >= 3:
        grade, action = 'S', 'STRONG_ENTER'
        advice = f'{layers}层共振满分 — 高置信度入场'
    elif total >= 0.60 and layers >= 2:
        grade, action = 'A', 'ENTER'
        advice = f'{layers}层共振 — 可入场'
    elif total >= 0.45 and layers >= 1:
        grade, action = 'B', 'CAUTIOUS'
        advice = f'{layers}层共振 — 谨慎入场,需紧止损'
    elif total >= 0.30:
        grade, action = 'C', 'WAIT'
        advice = '共振不足 — 等待更多确认'
    else:
        grade, action = 'D', 'SKIP'
        advice = '无共振 — 不交易'
    
    return {
        'grade': grade,
        'action': action,
        'advice': advice,
        'total': round(total, 3),
        'layers': layers,
        'expected_wr': score.expected_wr,
        'details': score.to_dict(),
    }


# ═══════════════════════════════════════════════════════════════════════
# Phase-aware parameter adjustment
# ═══════════════════════════════════════════════════════════════════════

PHASE_PARAMS = {
    'trending_up': {
        # Long-only in uptrend
        'direction_filter': 'long',
        'sl_mult': 0.8,      # tighter stops in trend
        'tp_mult': 1.2,      # wider targets
        'score_min_mult': 1.0,
        'max_trades_add': 2, # more trades allowed
    },
    'trending_down': {
        'direction_filter': 'short',
        'sl_mult': 0.8,
        'tp_mult': 1.2,
        'score_min_mult': 1.0,
        'max_trades_add': 2,
    },
    'ranging': {
        'direction_filter': 'both',
        'sl_mult': 1.3,      # wider stops (choppy)
        'tp_mult': 0.7,      # smaller targets
        'score_min_mult': 1.3, # higher quality threshold
        'max_trades_add': -1,  # fewer trades
    },
    'volatile': {
        'direction_filter': 'both',
        'sl_mult': 1.5,      # much wider stops
        'tp_mult': 0.6,      # conservative targets
        'score_min_mult': 1.5, # very strict
        'max_trades_add': -2,
    },
    'breakout': {
        'direction_filter': 'both',
        'sl_mult': 0.7,      # tight (momentum)
        'tp_mult': 1.5,      # ride the trend
        'score_min_mult': 0.8, # easier to enter
        'max_trades_add': 1,
    },
}


def adjust_params_for_phase(base_params: Dict, market_phase: str) -> Dict:
    """Adjust trading parameters based on market phase.
    
    Different phases require different parameter settings:
    - Trending: tighter stops, wider targets, more trades
    - Ranging: wider stops, smaller targets, fewer trades, higher quality
    - Volatile: widest stops, smallest targets, very strict quality
    - Breakout: momentum setup, tight stops, ride the trend
    
    Args:
        base_params: default parameter dict
        market_phase: one of trending_up/down/ranging/volatile/breakout
    
    Returns: adjusted parameter dict
    """
    phase_cfg = PHASE_PARAMS.get(market_phase, PHASE_PARAMS['ranging'])
    
    adjusted = dict(base_params)
    
    # Adjust SL/TP
    if 'sl_pct' in adjusted:
        adjusted['sl_pct'] = round(adjusted['sl_pct'] * phase_cfg['sl_mult'], 1)
    if 'tp_pct' in adjusted:
        adjusted['tp_pct'] = round(adjusted['tp_pct'] * phase_cfg['tp_mult'], 1)
    
    # Adjust score threshold
    if 'score_min' in adjusted:
        adjusted['score_min'] = round(adjusted['score_min'] * phase_cfg['score_min_mult'], 2)
    
    # Adjust max trades
    if 'max_trades' in adjusted:
        adjusted['max_trades'] = max(1, adjusted['max_trades'] + phase_cfg['max_trades_add'])
    
    # Direction filter
    adjusted['_phase'] = market_phase
    adjusted['_direction_filter'] = phase_cfg['direction_filter']
    
    # Ensure TP/SL ratio stays >= 1.5
    if 'sl_pct' in adjusted and 'tp_pct' in adjusted:
        if adjusted['tp_pct'] / adjusted['sl_pct'] < 1.5:
            adjusted['tp_pct'] = round(adjusted['sl_pct'] * 1.5, 1)
    
    return adjusted


# ═══════════════════════════════════════════════════════════════════════
# Resonance report generator
# ═══════════════════════════════════════════════════════════════════════

def build_resonance_report(
    symbol: str,
    resonance: ResonanceScore,
    phase: str,
    seq_result: Dict = None,
    swing_result: Dict = None,
) -> str:
    """Generate a human-readable resonance report."""
    
    def bar(label, value, max_val=1.0):
        filled = int(value * 20)
        bar_str = '█' * filled + '░' * (20 - filled)
        return f"  {label:12s} [{bar_str}] {value:.2f}"
    
    lines = [
        f"",
        f"╔══════════════════════════════════════════════╗",
        f"║  V10 共振分析报告 — {symbol:12s}        ║",
        f"╚══════════════════════════════════════════════╝",
        f"",
        f"  市场阶段: {phase.upper()}  |  共振层级: {resonance.layers}/4",
        f"  预期胜率: {resonance.expected_wr:.0%}",
        f"",
        f"  共振维度分解:",
        bar('TF共振', resonance.tf_resonance),
        bar('指标共振', resonance.indicator_resonance),
        bar('摆动共振', resonance.swing_resonance),
        bar('序列共振', resonance.sequence_resonance),
        f"",
        f"  综合得分: {resonance.total:.3f}",
    ]
    
    if seq_result:
        best = seq_result.get('best_sequence')
        if best:
            lines.append(f"")
            lines.append(f"  信号序列: {best['name']} "
                        f"({best['match_count']}/{best['total_steps']}步)")
            lines.append(f"  序列: {' → '.join(best['matched_steps'])}")
    
    if swing_result:
        tree = swing_result.get('tree', {})
        if tree.get('all_aligned'):
            lines.append(f"  摆动点: 全层级对齐 ({tree.get('direction', 'N/A')})")
    
    grade = get_resonance_grade(resonance)
    lines.append(f"")
    lines.append(f"  评级: {grade['grade']}  |  建议: {grade['action']}")
    lines.append(f"  {grade['advice']}")
    lines.append(f"")
    
    return '\n'.join(lines)
