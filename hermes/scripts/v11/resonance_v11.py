#!/usr/bin/env python3
# SMC V11 — Unified Resonance Engine
"""
V11 共振引擎 — 四维综合评分

核心创新 (vs V10):
1. TF共振: 多周期方向对齐 + 每个TF的信号质量加权
2. 指标共振: 信号间重叠区域检测 + 信号时间顺序
3. 摆动共振: 多层摆动点对齐 + 结构树完整性
4. 时间共振: 信号间K线距离 + 时间衰减
5. 综合评分: 四维加权 → 0-1的终极置信度

共振级别:
  S (0.85+): 四维全对齐 → WR~88%
  A (0.70+): 三维对齐 → WR~78%  
  B (0.55+): 二维对齐 → WR~68%
  C (0.40+): 一维对齐 → WR~55%
  D (<0.40): 无共振 → 跳过
"""

import math, logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

log = logging.getLogger('smc_v11.resonance')


@dataclass
class ResonanceResult:
    """四维共振结果"""
    tf_score: float = 0.0          # 0-1 多周期对齐
    indicator_score: float = 0.0   # 0-1 指标共振
    swing_score: float = 0.0       # 0-1 摆动对齐
    temporal_score: float = 0.0    # 0-1 时间距离
    
    @property
    def total(self) -> float:
        """加权总分"""
        return (
            self.tf_score * 0.25 +
            self.indicator_score * 0.30 +
            self.swing_score * 0.15 +
            self.temporal_score * 0.30
        )
    
    @property
    def layers_active(self) -> int:
        """活跃层数 (>0.5)"""
        return sum(1 for x in [
            self.tf_score, self.indicator_score,
            self.swing_score, self.temporal_score
        ] if x >= 0.5)
    
    def grade(self) -> str:
        total = self.total
        if total >= 0.85: return 'S'
        elif total >= 0.70: return 'A'
        elif total >= 0.55: return 'B'
        elif total >= 0.40: return 'C'
        else: return 'D'
    
    def expected_wr(self) -> float:
        return {0: 0.40, 1: 0.55, 2: 0.68, 3: 0.78, 4: 0.86}.get(self.layers_active, 0.86)
    
    def to_dict(self) -> Dict:
        return {
            'tf_score': round(self.tf_score, 3),
            'indicator_score': round(self.indicator_score, 3),
            'swing_score': round(self.swing_score, 3),
            'temporal_score': round(self.temporal_score, 3),
            'total': round(self.total, 3),
            'grade': self.grade(),
            'layers_active': self.layers_active,
            'expected_wr': self.expected_wr(),
        }


# ═══════════════════════════════════════════════════════════════════════
# 1. TF Resonance — Multi-Timeframe Direction Alignment
# ═══════════════════════════════════════════════════════════════════════

def calc_tf_resonance(tf_sequences: Dict[str, Dict],
                      tf_data: Dict[str, List[Dict]]) -> float:
    """计算TF共振得分
    
    核心: 每个TF的信号序列方向是否一致
    高TF权重更大 (daily > 4h > 1h > 15min)
    
    Returns: 0-1
    """
    if not tf_sequences or len(tf_sequences) < 2:
        # Single TF: default to moderate value based on signal quality
        if tf_sequences and len(tf_sequences) == 1:
            tf_name = list(tf_sequences.keys())[0]
            seq = tf_sequences[tf_name]
            if seq.get('best_sequence') and seq.get('direction'):
                return 0.40  # Gold/Silver sequence on single TF
            elif seq.get('direction'):
                return 0.20  # Directional bias on single TF
        return 0.0
    
    tf_weights = {'daily': 0.40, 'weekly': 0.35, '4h': 0.28, '1h': 0.18, '15min': 0.12}
    
    directions = {}
    for tf, seq_result in tf_sequences.items():
        direction = seq_result.get('direction')
        if direction:
            directions[tf] = direction
    
    if len(directions) < 2:
        return 0.0
    
    # 按方向分组
    bulls = [tf for tf, d in directions.items() if d == 'bull']
    bears = [tf for tf, d in directions.items() if d == 'bear']
    
    main_group = bulls if len(bulls) >= len(bears) else bears
    main_direction = 'bull' if len(bulls) >= len(bears) else 'bear'
    
    if len(main_group) < 2:
        return 0.0
    
    # 加权和
    total_weight = 0
    matched_weight = 0
    
    for tf in directions:
        w = tf_weights.get(tf, 0.15)
        total_weight += w
        if tf in main_group:
            matched_weight += w
    
    # 方向一致性得分
    ratio = matched_weight / total_weight if total_weight > 0 else 0
    
    # TF层次加分: 高TF一致 = 更强
    high_tf_aligned = all(tf in main_group for tf in ['daily', '4h'] if tf in directions)
    high_tf_bonus = 0.15 if high_tf_aligned else 0
    
    return min(1.0, ratio * 0.85 + high_tf_bonus)


# ═══════════════════════════════════════════════════════════════════════
# 2. Indicator Resonance — Signal Overlap & Confluence
# ═══════════════════════════════════════════════════════════════════════

def calc_indicator_resonance(all_signals: List[Dict], 
                             last_n: int = 20) -> float:
    """计算指标共振得分
    
    核心: 不同类型的信号在相近的K线区域内同时出现
    FVG+Sweep+OB+CHOCH同时出现 → 四重共振
    
    Returns: 0-1
    """
    if not all_signals:
        return 0.0
    
    # 只看最近的信号
    if len(all_signals) > last_n:
        recent = all_signals[-last_n:]
    else:
        recent = all_signals
    
    # 按方向分组
    bull_signals = []
    bear_signals = []
    
    for s in recent:
        direction = s.get('direction', '')
        sig_type = s.get('type', '')
        if direction == 'bull':
            bull_signals.append(sig_type)
        elif direction == 'bear':
            bear_signals.append(sig_type)
    
    # 计算各方向的信号类型覆盖度
    signal_types_needed = {'FVG', 'Sweep', 'OB', 'CHOCH'}
    
    def coverage(signals):
        types_present = set()
        for s in signals:
            if 'FVG' in s: types_present.add('FVG')
            if 'Sweep' in s: types_present.add('Sweep')
            if 'OB' in s or 'Rejection' in s: types_present.add('OB')
            if 'CHOCH' in s or 'MSB' in s: types_present.add('CHOCH')
        return len(types_present & signal_types_needed) / len(signal_types_needed)
    
    bull_cov = coverage(bull_signals)
    bear_cov = coverage(bear_signals)
    
    # 取较高方向
    max_cov = max(bull_cov, bear_cov)
    
    # 信号数量奖励
    dominant_signals = bull_signals if bull_cov >= bear_cov else bear_signals
    count_bonus = min(0.2, len(dominant_signals) * 0.05)
    
    return min(1.0, max_cov * 0.8 + count_bonus)


# ═══════════════════════════════════════════════════════════════════════
# 3. Swing Resonance — Multi-Layer Pivot Alignment
# ═══════════════════════════════════════════════════════════════════════

def _find_last_swing(ohlcv: List[Dict], left: int, right: int, name: str) -> Tuple[Optional[str], float]:
    """找最近的一个完整摆动点 — 从右向左扫描
    
    Returns: (direction_str, strength_0to1) or (None, 0)
    """
    n = len(ohlcv)
    if n < left + right + 1:
        return None, 0
    
    # 从倒数第right-1根开始向左扫描
    scan_end = n - max(1, right // 2)
    scan_start = max(left, scan_end - max(60, left * 3))
    
    for center in range(scan_end, scan_start, -1):
        if center - left < 0 or center + right >= n:
            continue
        
        # 检查摆动高点
        is_high = True
        for j in range(center - left, center + right + 1):
            if j == center:
                continue
            if ohlcv[center]['h'] < ohlcv[j]['h']:
                is_high = False
                break
        
        # 检查摆动低点
        is_low = True
        for j in range(center - left, center + right + 1):
            if j == center:
                continue
            if ohlcv[center]['l'] > ohlcv[j]['l']:
                is_low = False
                break
        
        if is_high or is_low:
            # 确定方向: 摆动点之后的价格行为
            after = ohlcv[center+1:min(center+6, n)]
            if len(after) >= 3:
                trend = 'up' if after[-1]['c'] > after[0]['c'] else 'down'
                return trend, 0.9 if is_high else 0.8
            elif len(after) >= 1:
                trend = 'up' if after[-1]['c'] > after[0]['c'] else 'down'
                return trend, 0.5
    return None, 0


def calc_swing_resonance(ohlcv: List[Dict]) -> float:
    """计算摆动点共振得分
    
    核心: 多层级摆动点的对齐程度
    micro + meso + macro 同方向 → 三重共振
    
    V11.1修复: 从右向左扫描, 找每个层级最近的有效摆动点
    
    Returns: 0-1
    """
    if not ohlcv or len(ohlcv) < 30:
        return 0.0
    
    # 4层摆动点检测 — 从右向左扫描
    scales = [
        (3, 3, 'micro'),      # ~6根K线
        (8, 5, 'meso'),       # ~13根
        (20, 8, 'macro'),     # ~28根
        (50, 15, 'mega'),     # ~65根
    ]
    
    directions = {}
    
    for left, right, name in scales:
        direction, strength = _find_last_swing(ohlcv, left, right, name)
        if direction:
            directions[name] = direction
    
    if len(directions) < 2:
        return 0.0
    
    # 检查方向一致性
    dirs_list = list(directions.values())
    aligned = all(d == dirs_list[0] for d in dirs_list)
    
    if not aligned:
        return 0.2  # 部分对齐 — 仍给少量分
    
    # 层数奖励
    n_layers = len(directions)
    if n_layers >= 4:
        return 0.95
    elif n_layers >= 3:
        return 0.80
    else:
        return 0.60


# ═══════════════════════════════════════════════════════════════════════
# 4. Temporal Resonance — Signal Proximity Score
# ═══════════════════════════════════════════════════════════════════════

def calc_temporal_resonance(all_signals: List[Dict], 
                            last_n: int = 15) -> float:
    """计算时间共振得分
    
    核心: 信号间的K线距离越近, 共振越强
    
    Returns: 0-1
    """
    if not all_signals or len(all_signals) < 2:
        return 0.0
    
    # 取最近的信号
    recent = all_signals[-min(last_n, len(all_signals)):]
    indices = [s.get('idx', 0) for s in recent]
    
    if len(indices) < 2:
        return 0.0
    
    # 计算间距
    distances = [indices[i+1] - indices[i] for i in range(len(indices) - 1)]
    avg_dist = sum(distances) / len(distances) if distances else 0
    
    # 最近间距 (越小越好)
    last_dist = distances[-1] if distances else 10
    
    # 评分: 越近越高
    avg_score = math.exp(-avg_dist / 15.0)  # 平均间距15K线内为佳
    last_score = math.exp(-last_dist / 8.0)  # 最后间距8K线内为佳
    
    # 信号密度: 在短时间内出现多个信号
    time_span = (indices[-1] - indices[0]) if len(indices) > 1 else 1
    density = min(1.0, len(recent) / max(1, time_span) * 5)
    
    return min(1.0, avg_score * 0.4 + last_score * 0.3 + density * 0.3)


# ═══════════════════════════════════════════════════════════════════════
# 5. Full Resonance Evaluation
# ═══════════════════════════════════════════════════════════════════════

def evaluate_full_resonance_v11(
    all_signals: List[Dict],
    tf_sequences: Dict[str, Dict] = None,
    tf_data: Dict[str, List[Dict]] = None,
    ohlcv: List[Dict] = None,
) -> ResonanceResult:
    """V11完整共振评估
    
    Args:
        all_signals: 当前TF的所有信号
        tf_sequences: 各TF的序列分析结果 {tf: seq_result}
        tf_data: 各TF的OHLCV数据 {tf: [OHLCV]}
        ohlcv: 当前TF的OHLCV数据(用于摆动分析)
    
    Returns:
        ResonanceResult 对象
    """
    result = ResonanceResult()
    
    # 1. TF共振
    if tf_sequences and tf_data:
        result.tf_score = calc_tf_resonance(tf_sequences, tf_data)
    
    # 2. 指标共振
    result.indicator_score = calc_indicator_resonance(all_signals)
    
    # 3. 摆动共振
    if ohlcv:
        result.swing_score = calc_swing_resonance(ohlcv)
    
    # 4. 时间共振
    result.temporal_score = calc_temporal_resonance(all_signals)
    
    # 5. 单TF Fallback: 如果没传tf_data但有tf_sequences, 用序列本身评分
    if tf_sequences and not tf_data:
        # 只用一个TF: 序列方向一致给基础分
        for tf_name, seq in tf_sequences.items():
            if seq.get('best_sequence') and seq.get('direction'):
                result.tf_score = max(result.tf_score, 0.40)
            elif seq.get('direction'):
                result.tf_score = max(result.tf_score, 0.20)
    
    return result


# ═══════════════════════════════════════════════════════════════════════
# 6. Combined Entry Decision
# ═══════════════════════════════════════════════════════════════════════

def make_entry_decision_v11(
    resonance: ResonanceResult,
    seq_result: Dict,
    params: Dict = None,
    tf_sequences: Dict[str, Dict] = None,
) -> Dict:
    """基于共振+序列的综合入场决策
    
    Args:
        resonance: ResonanceResult
        seq_result: analyze_sequence_v11() 的结果
        params: 交易参数
    
    Returns:
        {
            'action': 'enter'/'wait'/'skip',
            'grade': 'S'/'A'/'B'/'C'/'D',
            'confidence': 0-1,
            'reason': str,
            'expected_wr': float,
            'entry_price': float or None,
            'sl': float or None,
            'tp': float or None,
            'rr': float or None,
        }
    """
    if params is None:
        params = {}
    
    # 基础置信度 = 共振总分
    base_confidence = resonance.total
    
    # 序列加成
    sequence_boost = seq_result.get('confidence_boost', 1.0)
    has_sequence = seq_result.get('best_sequence') is not None
    
    # 最终置信度
    if has_sequence:
        confidence = base_confidence * sequence_boost
    else:
        confidence = base_confidence * 0.5  # 无序列则减半
    
    confidence = min(1.0, confidence)
    
    # 单TF模式: 降低入场门槛
    is_single_tf = tf_sequences is None or len(tf_sequences) <= 1
    
    # 入场/止盈/止损
    entry_signal = seq_result.get('entry_signal')
    entry_price = seq_result.get('entry_price')
    direction = seq_result.get('direction')
    
    sl_price = None
    tp_price = None
    rr = None
    
    if entry_price and direction:
        sl_pct = params.get('sl_pct', 1.0)
        tp_pct = params.get('tp_pct', 2.5)
        
        if direction == 'bull':
            sl_price = entry_price * (1 - sl_pct / 100)
            tp_price = entry_price * (1 + tp_pct / 100)
        else:
            sl_price = entry_price * (1 + sl_pct / 100)
            tp_price = entry_price * (1 - tp_pct / 100)
        
        if sl_price and entry_price:
            if direction == 'bull':
                rr = abs(tp_price - entry_price) / abs(entry_price - sl_price)
            else:
                rr = abs(entry_price - tp_price) / abs(sl_price - entry_price)
    
    # 评级
    grade = resonance.grade()
    if has_sequence and grade in ('C', 'D'):
        grade = 'C'  # 有序列则至少C
    
    # 动作 — 单TF模式降低门槛
    enter_threshold = 0.60 if is_single_tf else 0.70
    wait_threshold = 0.45 if is_single_tf else 0.55
    watch_threshold = 0.30 if is_single_tf else 0.40
    
    # 序列加成: Gold/Silver/Scout在单TF下提升信心
    seq_quality = seq_result.get('best_sequence', {}).get('name', '') if has_sequence else ''
    if has_sequence and is_single_tf:
        if 'GOLD' in seq_quality:
            confidence = max(confidence, 0.70)  # Gold至少0.70
        elif 'SILVER' in seq_quality:
            confidence = max(confidence, 0.60)  # Silver至少0.60
        elif 'BRONZE' in seq_quality:
            confidence = max(confidence, 0.50)  # Bronze至少0.50
        elif 'SCOUT' in seq_quality:
            confidence = max(confidence, 0.45)  # Scout至少0.45 (需高共振辅助)
    
    if confidence >= enter_threshold:
        action = 'enter'
        reason = f"{grade}级共振 + 序列确认, 预期WR={resonance.expected_wr():.0%}"
    elif confidence >= wait_threshold:
        action = 'wait'
        reason = f"{grade}级共振, 需更多确认"
    elif confidence >= watch_threshold:
        action = 'watch'
        reason = f"{grade}级共振, 观察等待"
    else:
        action = 'skip'
        reason = "共振不足, 不具备交易条件"
    
    # Scout/Bronze单TF特殊处理: B级共振+全信号数量充足时允许入场
    # [V11.3 REMOVED] dead code from V11.2 — sigs_before was never in scope
    
    # Scout仅在高共振时入场
    if has_sequence and 'SCOUT' in seq_quality:
        if resonance.total >= 0.60:
            action = 'enter'
            reason = f"Scout序列+B级共振({resonance.total:.2f}), 信号质量足够"
    
    # 过滤低RR (仅对enter生效)
    if rr is not None and rr < 1.5 and action == 'enter':
        action = 'wait'
        reason = f"RR={rr:.1f}x < 1.5, 盈亏比不足"
    
    # 检查序列等级: Bronze需要额外确认
    if action == 'enter' and seq_result.get('best_sequence'):
        seq_name = seq_result['best_sequence'].get('name', '')
        if 'BRONZE' in seq_name:
            bronze_threshold = 0.55 if is_single_tf else 0.60
            if resonance.total < bronze_threshold:
                action = 'wait'
                reason = f"Bronze序列需共振>={bronze_threshold:.0%} (当前={resonance.total:.2f})"
    
    return {
        'action': action,
        'grade': grade,
        'confidence': round(confidence, 3),
        'resonance_score': resonance.total,
        'sequence_boost': sequence_boost,
        'reason': reason,
        'expected_wr': resonance.expected_wr(),
        'entry_price': round(entry_price, 2) if entry_price else None,
        'sl': round(sl_price, 2) if sl_price else None,
        'tp': round(tp_price, 2) if tp_price else None,
        'rr': round(rr, 2) if rr else None,
        'direction': direction,
        'resonance_detail': resonance.to_dict(),
    }


# ═══════════════════════════════════════════════════════════════════════
# 7. Quick single-stock analysis
# ═══════════════════════════════════════════════════════════════════════

def quick_analyze_v11(ohlcv: List[Dict], params: Dict = None,
                      tf: str = 'daily') -> Dict:
    """一键分析: 信号检测 → 序列分析 → 共振评分 → 入场决策"""
    if params is None:
        params = {}
    
    # 1. 信号检测
    from .signals_v11 import detect_all_signals_v11
    signal_result = detect_all_signals_v11(ohlcv, params=params, tf=tf)
    all_signals = signal_result['all']
    adaptive = signal_result['adaptive']
    
    # 2. 序列分析
    from .sequencer_v11 import analyze_sequence_v11, score_entry_v11
    seq_result = analyze_sequence_v11(all_signals, params=params)
    
    # 3. 共振评估
    tf_sequences = {tf: seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=all_signals,
        tf_sequences=tf_sequences,
        ohlcv=ohlcv,
    )
    
    # 4. 入场决策
    decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
    
    return {
        'signal_stats': signal_result['stats'],
        'adaptive_thresholds': adaptive,
        'sequence': seq_result,
        'resonance': resonance.to_dict(),
        'decision': decision,
        'best_sequence': seq_result.get('best_sequence'),
    }
