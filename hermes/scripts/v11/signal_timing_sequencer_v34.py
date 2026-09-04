#!/usr/bin/env python3
"""
V34 Advanced Signal Time-Sequence System
========================================
超越V33的"信号链码匹配"，增加三层核心机制:

Layer 1: POI (Point of Interest) 检测
  - FVG下边界/上边界 = 自然支撑/阻力POI
  - OB顶部/底部 = 订单块POI
  - 摆动低点/高点 = 结构POI
  - 信号发生在哪个POI位置决定信号质量

Layer 2: 价格行为上下文分类
  - 新鲜FVG: 价格刚在FVG区域外 → 等待价格回测POI
  - POI回调: 价格曾到POI→离开→再次回来 → 高信度入场
  - 趋势延续: 趋势方向一致 + 价格回调到POI → 最佳入场
  - 反转确认: CHOCH→FVG + 价格在结构转折点 → 反转入场

Layer 3: 完整序列演化追踪
  Signal→Movement→POI_Return→Confirmation→Entry
  不再只看"进场前有什么信号"，而是追踪信号后价格行为的演化

A股日线适配:
- 日线1-3根K线内完成POI测试是理想的
- 超过10根K线的FVG视为"过期"
- 摆动点SL天然让POI=FVG lower成为止损参考
"""

from typing import List, Dict, Tuple, Optional
from collections import defaultdict


# ============================================================
# SIGNAL TYPE CODES (与V33保持一致)
# ============================================================
SIGNAL_CODES = {
    'FVG_Bull': 'F', 'FVG_Bear': 'f',
    'OB_Bull': 'O', 'OB_Bear': 'o',
    'SweepDown': 'S', 'SweepUp': 's',
    'CHOCH_Bull': 'C', 'CHOCH_Bear': 'c',
    'BPR': 'B',
    'LiquidityVoid_Bull': 'L', 'LiquidityVoid_Bear': 'l',
    'RejectionBlock_Bull': 'R', 'RejectionBlock_Bear': 'r',
}

CORE_SIGNAL_TYPES = {'FVG', 'OB', 'Sweep', 'CHOCH'}

PATTERN_DB = {
    # ═══ GOLD ═══
    'CF':  {'desc': 'CHOCH→FVG', 'bonus': 0.35, 'min': 2, 'wr': 0.85},
    'FO':  {'desc': 'FVG→OB(双确认)', 'bonus': 0.30, 'min': 2, 'wr': 0.82},
    'SF':  {'desc': 'SSL扫荡→FVG(流动性抓取)', 'bonus': 0.30, 'min': 2, 'wr': 0.80},
    # ═══ SILVER ═══
    'FF':  {'desc': 'FVG→FVG(连续gap)', 'bonus': 0.20, 'min': 2, 'wr': 0.72},
    'SO':  {'desc': '扫荡→OB', 'bonus': 0.18, 'min': 2, 'wr': 0.68},
    'OF':  {'desc': 'OB→FVG', 'bonus': 0.18, 'min': 2, 'wr': 0.65},
    'CSF': {'desc': 'CHOCH→Sweep→FVG(三级)', 'bonus': 0.50, 'min': 3, 'wr': 0.90},
    'SCF': {'desc': 'Sweep→CHOCH→FVG', 'bonus': 0.45, 'min': 3, 'wr': 0.88},
    'COF': {'desc': 'CHOCH→OB→FVG', 'bonus': 0.40, 'min': 3, 'wr': 0.83},
    'OFC': {'desc': 'OB→FVG→CHOCH', 'bonus': 0.45, 'min': 3, 'wr': 0.88},
    # ═══ BRONZE ═══
    'CO':  {'desc': 'CHOCH→OB', 'bonus': 0.15, 'min': 2, 'wr': 0.60},
    'OO':  {'desc': 'OB→OB', 'bonus': 0.05, 'min': 2, 'wr': 0.45},
    'SS':  {'desc': '扫荡→扫荡(双流)', 'bonus': -0.10, 'min': 2, 'wr': 0.35},
    'SFF': {'desc': '扫荡→FVG→FVG', 'bonus': 0.40, 'min': 3, 'wr': 0.85},
    'OFF': {'desc': 'OB→FVG→FVG', 'bonus': 0.35, 'min': 3, 'wr': 0.82},
    'FCF': {'desc': 'FVG→CHOCH→FVG', 'bonus': 0.35, 'min': 3, 'wr': 0.80},
}


# ============================================================
# LAYER 1: POI (Point of Interest) 检测
# ============================================================

class POI:
    """POI = 价格可能反应的区域
    
    Examples:
      FVG_Bull: lower=支撑边界, upper=阻力边界 (gap区域)
      OB_Bull:  lower=OB底部, upper=OB顶部
      SwingLow: lower=低点本身
    
    V34关键洞察:
      如果FVG的POI已经被价格"测试"过(low <= FVG.lower)，
      则FVG已部分填充，不再是"fresh"
      最佳入场时机 = 价格刚从POI弹起的第二根K线
    """
    def __init__(self, poi_type: str, price_low: float, price_high: float,
                 bar_idx: int, signal_idx: int, strength: float = 0.5):
        self.type = poi_type        # 'FVG_lower', 'FVG_mid', 'OB', 'swing'
        self.low = price_low        # POI下边界
        self.high = price_high      # POI上边界
        self.bar_idx = bar_idx      # POI形成的bar
        self.signal_idx = signal_idx  # 对应的信号idx
        self.strength = strength    # 0-1
        self.times_tested = 0       # 被价格测试的次数
        self.last_test_idx = -1
        self.last_test_direction = None  # 'bounce_up' or 'break_down'

    def is_tested(self, bar, current_idx: int) -> bool:
        """检查当前bar是否测试了POI"""
        if current_idx <= self.bar_idx:
            return False
        test_low = bar['l']
        test_high = bar['h']
        # POI被"触摸" = bar的低低于或等于POI上边界, 且bar的高高于或等于POI下边界
        touches = test_low <= self.high and test_high >= self.low
        if touches:
            self.times_tested += 1
            self.last_test_idx = current_idx
            # 判断方向: bar的close在POI下边界之上 = bounce_up
            if bar['c'] > self.low:
                self.last_test_direction = 'bounce_up'
            else:
                self.last_test_direction = 'break_down'
        return touches

    def is_bounced(self) -> bool:
        """POI是否产生了有效反弹(确认)"""
        return (self.last_test_direction == 'bounce_up' 
                and self.times_tested >= 1)

    def value_score(self) -> float:
        """POI的价值评分"""
        score = self.strength
        # 被测试过的POI更有价值(价格验证了)
        if self.times_tested >= 1:
            score += 0.10
        if self.times_tested >= 2:
            score += 0.05  # 双测试 = 更强支撑
        if self.last_test_direction == 'bounce_up':
            score += 0.10  # 有效反弹
        return min(score, 1.0)


def extract_poi_from_fvg(signal: Dict) -> Optional[POI]:
    """从FVG信号中提取POI区域
    
    FVG_Bull: gap between lower and upper, lower=支撑POI
    FVG_Bear: gap between lower and upper, upper=阻力POI
    """
    stype = signal.get('type', '')
    direction = signal.get('direction', '')
    idx = signal.get('idx', 0)
    upper = signal.get('upper', 0)
    lower = signal.get('lower', 0)
    
    if upper <= 0 or lower <= 0:
        return None
    
    if 'FVG' in stype and 'Bull' in direction:
        # Bull FVG: lower boundary = 关键支撑POI
        return POI(
            poi_type='FVG_lower',
            price_low=lower,
            price_high=upper,
            bar_idx=idx,
            signal_idx=idx,
            strength=0.7  # FVG天然高价值
        )
    elif 'FVG' in stype and 'Bear' in direction:
        return POI(
            poi_type='FVG_upper',
            price_low=lower,
            price_high=upper,
            bar_idx=idx,
            signal_idx=idx,
            strength=0.7
        )
    return None


def extract_poi_from_ob(signal: Dict) -> Optional[POI]:
    """从OB信号中提取POI区域"""
    stype = signal.get('type', '')
    direction = signal.get('direction', '')
    idx = signal.get('idx', 0)
    upper = signal.get('upper', 0)
    lower = signal.get('lower', 0)
    
    if upper <= 0 or lower <= 0:
        return None
    
    if 'OB' in stype and 'Bull' in direction:
        return POI('OB_top', lower, upper, idx, idx, strength=0.6)
    return None


def extract_poi_from_swing(ohlcv: List[Dict], end_idx: int, 
                           direction: str = 'bull',
                           lookback: int = 50) -> Optional[POI]:
    """从摆动低点/高点提取POI"""
    if end_idx < 3: 
        return None
    start = max(0, end_idx - lookback)
    
    if direction == 'bull':
        # 找摆动低点 (近期最低)
        low_idx, low_val = -1, 999999
        for i in range(start, end_idx):
            left = ohlcv[i-1] if i > start else None
            right = ohlcv[i+1] if i < end_idx else None
            lv = left['l'] if left else 999999
            rv = right['l'] if right else 999999
            if ohlcv[i]['l'] < lv and ohlcv[i]['l'] < rv:
                gains = (ohlcv[end_idx]['c'] - ohlcv[i]['l']) / ohlcv[i]['l'] * 100
                if gains >= 1.0:  # 从低点起涨了至少1%
                    if ohlcv[i]['l'] < low_val:
                        low_idx, low_val = i, ohlcv[i]['l']
        
        if low_idx >= 0:
            return POI('swing_low', low_val * 0.998, low_val * 1.002, 
                       low_idx, low_idx, strength=0.8)
    return None


# ============================================================
# LAYER 2: 价格行为上下文分类
# ============================================================

def classify_price_context(ohlcv: List[Dict], current_idx: int,
                           fvg_signal: Dict) -> Dict:
    """
    分析当前价格相对于FVG POI的位置和行为
    
    Returns:
      context: 'fresh' | 'poi_pullback' | 'trend_continuation' | 'reversal'
      poi_tested: bool — FVG lower是否被价格测试过
      bars_since_test: int — 距离上次测试的K线数
      price_position: 'inside_poi' | 'above_poi' | 'below_poi' | 'far_above'
    """
    idx = fvg_signal.get('idx', 0)
    upper = fvg_signal.get('upper', 0)
    lower = fvg_signal.get('lower', 0)
    
    if upper <= 0 or lower <= 0:
        return {'context': 'unknown', 'poi_tested': False}
    
    current_price = ohlcv[current_idx]['c'] if current_idx < len(ohlcv) else 0
    avg_price = (upper + lower) / 2
    
    # 1. 检查POI(FVG lower)是否被测试过
    poi_tested = False
    last_test_idx = -1
    for i in range(idx + 1, current_idx + 1):
        if i < len(ohlcv):
            bar = ohlcv[i]
            # 价格触及或低于FVG lower = POI被测试
            if bar['l'] <= lower * 1.005:  # 0.5%容差
                poi_tested = True
                last_test_idx = i
    
    # 2. 检查是否从POI反弹
    bounced = False
    if poi_tested and last_test_idx > 0 and last_test_idx + 1 < len(ohlcv):
        after_bar = ohlcv[min(last_test_idx + 1, len(ohlcv) - 1)]
        if after_bar['c'] > lower and after_bar['c'] > after_bar['o']:
            bounced = True
    
    # 3. 检查趋势方向
    if current_idx >= 20:
        macro_start = max(0, current_idx - 40)
        macro_trend = (ohlcv[current_idx]['c'] - ohlcv[macro_start]['c']) / ohlcv[macro_start]['c'] * 100
        micro_trend = (ohlcv[current_idx]['c'] - ohlcv[max(0,current_idx-10)]['c']) / ohlcv[max(0,current_idx-10)]['c'] * 100
    else:
        macro_trend, micro_trend = 0, 0
    
    # 4. 价格相对于POI的位置
    dist_from_poi = (current_price - lower) / lower * 100
    
    if current_price <= upper and current_price >= lower:
        price_position = 'inside_poi'
    elif current_price > upper and dist_from_poi <= 2:
        price_position = 'above_poi'
    elif dist_from_poi > 2:
        price_position = 'far_above'
    else:
        price_position = 'below_poi'
    
    # 5. 综合分类
    context = 'fresh'
    if poi_tested and bounced:
        if micro_trend > 0 and macro_trend > 0:
            context = 'trend_continuation'  # 趋势延续回调
        elif 'CHOCH' in fvg_signal.get('type', ''):
            context = 'reversal'            # 反转确认
        else:
            context = 'poi_pullback'        # 普通POI回调
    elif poi_tested and not bounced:
        context = 'fresh'                   # POI被测试但未反弹
    elif not poi_tested and price_position == 'above_poi':
        context = 'fresh'                   # 新鲜FVG, 等待回测
    
    return {
        'context': context,
        'poi_tested': poi_tested,
        'bounced': bounced,
        'bars_since_test': current_idx - last_test_idx if last_test_idx > 0 else 999,
        'price_position': price_position,
        'distance_from_poi_pct': round(dist_from_poi, 2),
        'macro_trend_pct': round(macro_trend, 2),
        'micro_trend_pct': round(micro_trend, 2),
    }


# ============================================================
# LAYER 3: 完整序列演化追踪
# ============================================================

def extract_signal_chain_v34(all_signals: List[Dict], target_bar: int,
                              lookback: int = 30, max_signals: int = 6,
                              direction: str = 'bull',
                              exclude_idx: int = -1) -> Tuple[str, List[Dict]]:
    """从V33升级: 只提取小于target_bar的信号(严格前序)"""
    preceding = [s for s in all_signals
                 if s.get('idx', 0) < target_bar  # 严格小于, 不等
                 and s.get('idx', 0) >= target_bar - lookback
                 and s.get('direction') == direction
                 and _is_core_signal(s)
                 and s.get('idx', 0) != exclude_idx]
    
    preceding.sort(key=lambda s: s.get('idx', 0))
    recent = preceding[-max_signals:]
    codes = ''.join(classify_signal_code(s) for s in recent)
    return codes, recent


def _is_core_signal(signal: Dict) -> bool:
    stype = signal.get('type', '')
    return any(core in stype for core in CORE_SIGNAL_TYPES)


def classify_signal_code(signal: Dict) -> str:
    stype = signal.get('type', '')
    for pattern, code in SIGNAL_CODES.items():
        if pattern in stype:
            return code
    return stype[0].upper() if stype else '?'


def score_chain_by_pattern(code_string: str, direction: str = 'bull') -> Dict:
    """V33模式匹配引擎"""
    best = {'pattern': 'isolated', 'desc': '孤立信号(无前序确认)',
            'bonus': 0.0, 'matched_length': 0, 'complexity': 1}
    
    max_len = len(code_string)
    for length in range(min(5, max_len), 1, -1):
        for start in range(max_len - length + 1):
            sub = code_string[start:start+length]
            if sub in PATTERN_DB:
                p = PATTERN_DB[sub]
                if direction == 'bull' and not sub[0].isupper():
                    continue
                match = {'pattern': sub, 'desc': p['desc'], 'bonus': p['bonus'],
                         'matched_length': length, 'complexity': length,
                         'expected_wr': p.get('wr', 0.5)}
                if length > best['matched_length']:
                    best = match
                elif length == best['matched_length'] and p['bonus'] > best['bonus']:
                    best = match
                break
    
    if best['pattern'] == 'isolated' and len(code_string) >= 2:
        best['pattern'] = 'unrecognized'
        best['desc'] = f'未识别序列({code_string[-3:]})'
    
    return best


# ============================================================
# V34 综合评分引擎
# ============================================================

def score_signal_v34(all_signals: List[Dict], fvg_signal: Dict,
                      ohlcv: List[Dict], current_idx: int,
                      params: Dict = None) -> Dict:
    """
    V34完整评分: V33信号链 + V34 POI + 价格行为上下文
    
    Score Components:
      Base: 0.50 (任何FVG的基线分)
      + V33 Pattern bonus: 0.00 ~ 0.50 (信号链模式匹配)
      + POI return bonus: 0.00 ~ 0.15 (价格回测POI)
      + Trend continuation bonus: 0.00 ~ 0.15 (趋势延续)
      + Structure reversal bonus: 0.00 ~ 0.10 (结构反转)
      + Bounce confirmation bonus: 0.00 ~ 0.10 (POI反弹确认)
      - Time decay: -0.00 ~ -0.20 (信号越旧越差)
      - Price distance penalty: -0.00 ~ -0.15 (价格离POI太远)
      - Multiple test penalty: -0.10 (测试太多次=POI在减弱)
    """
    target_idx = fvg_signal.get('idx', 0)
    direction = fvg_signal.get('direction', 'bull')
    
    if 'FVG' not in fvg_signal.get('type', ''):
        return _default_result('not_fvg', 0.50)
    
    # ================================================================
    # COMPONENT 1: V33 Signal Chain Pattern (维持V33的链码评分)
    # ================================================================
    raw_code, preceding = extract_signal_chain_v34(
        all_signals, target_idx, lookback=30, max_signals=6,
        direction=direction, exclude_idx=target_idx
    )
    n_preceding = len([s for s in preceding if s.get('idx', 0) < target_idx])
    pattern_match = score_chain_by_pattern(raw_code, direction)
    pattern_bonus = pattern_match['bonus']
    
    # ================================================================
    # COMPONENT 2: POI & 价格行为上下文 (V34新增)
    # ================================================================
    context = classify_price_context(ohlcv, current_idx, fvg_signal)
    
    poi_bonus = 0.0
    trend_bonus = 0.0
    reversal_bonus = 0.0
    bounce_bonus = 0.0
    
    if context['context'] == 'trend_continuation':
        trend_bonus = 0.15  # 趋势延续回测 = 最高加分
    elif context['context'] == 'poi_pullback':
        poi_bonus = 0.10    # POI回调 = 第二加分
    elif context['context'] == 'reversal':
        reversal_bonus = 0.10  # 反转确认
    
    # POI被测试过本身就有价值
    if context['poi_tested']:
        poi_bonus = max(poi_bonus, 0.05)
    
    # POI反弹确认 (价格碰到了POI并反弹)
    if context.get('bounced'):
        bounce_bonus = 0.10
    
    # ================================================================
    # PENALTIES
    # ================================================================
    time_penalty = 0.0
    age = current_idx - target_idx
    if age <= 3:
        time_penalty = 0.05  # 新鲜信号
    elif age <= 8:
        time_penalty = 0.0
    elif age <= 15:
        time_penalty = -0.05
    else:
        time_penalty = -0.20  # 过期信号
    
    # 价格离POI太远 = 惩罚
    distance_penalty = 0.0
    dist = context.get('distance_from_poi_pct', 0)
    if dist > 3:
        distance_penalty = -0.10  # 价格高出POI 3%+，已跑太远
    elif dist > 5:
        distance_penalty = -0.15
    
    # 测试次数过多 = POI在减弱
    test_penalty = 0.0
    # (from context we can't get times_tested directly here, skip)
    
    # ================================================================
    # COMPOSITE SCORE
    # ================================================================
    score = 0.50  # 基线
    
    score += pattern_bonus
    score += poi_bonus
    score += trend_bonus
    score += reversal_bonus
    score += bounce_bonus
    score += time_penalty
    score += distance_penalty
    
    score = max(0.0, min(1.0, score))
    
    # ================================================================
    # GRADING (V34自适应阈值)
    # ================================================================
    grade, action, entry_mult = _grade_v34(score, context, pattern_match)
    
    return {
        'score': round(score, 3),
        'grade': grade,
        'action': action,
        'entry_mult': entry_mult,
        'chain': raw_code,
        'desc': pattern_match['desc'],
        'pattern_bonus': pattern_bonus,
        'time_penalty': time_penalty,
        'poi_bonus': poi_bonus,
        'trend_bonus': trend_bonus,
        'reversal_bonus': reversal_bonus,
        'bounce_bonus': bounce_bonus,
        'distance_penalty': distance_penalty,
        'n_preceding': n_preceding,
        'pattern': pattern_match['pattern'],
        'poi_context': context['context'],
        'poi_tested': context['poi_tested'],
        'bounced': context.get('bounced', False),
        'price_position': context['price_position'],
        'distance_from_poi': context['distance_from_poi_pct'],
    }


def _grade_v34(score: float, context: Dict, pattern: Dict) -> Tuple[str, str, float]:
    """
    V34分级逻辑 — 比V33更灵活
    
    A (enter, mult=1.3): 趋势延续+POI回调+强模式
    B (enter, mult=1.0): 良好条件
    C (enter, mult=0.7): 普通条件
    D (wait): 需要等待更多确认
    F (skip): 跳过
    
    V34关键改进: 即使模式链分数一般，如果POI已经测试/反弹，也可以提升等级
    """
    # 如果是趋势延续+POI反弹，即使分数略低也允许
    if context['context'] == 'trend_continuation' and context.get('bounced'):
        if score >= 0.55:
            return ('A', 'enter', 1.2)
        if score >= 0.40:
            return ('B', 'enter', 1.0)
    
    # POI回调+有效反弹 >= 普通入场
    if context['poi_tested'] and context.get('bounced'):
        if score >= 0.50:
            return ('B', 'enter', 1.0)
        if score >= 0.40:
            return ('C', 'enter', 0.7)
    
    # 如果价格已经在POI内部或刚突破，更高要求
    if context['price_position'] in ('inside_poi', 'above_poi') and not context.get('bounced'):
        if score >= 0.65:
            return ('B', 'enter', 1.0)
        if score >= 0.55:
            return ('C', 'enter', 0.7)
    
    # 标准分级
    if score >= 0.75:
        return ('A', 'enter', 1.3)
    elif score >= 0.60:
        return ('B', 'enter', 1.0)
    elif score >= 0.50:
        return ('C', 'enter', 0.7)
    elif score >= 0.35:
        return ('D', 'wait', 0.0)
    else:
        return ('F', 'skip', 0.0)


def _default_result(reason: str, score: float = 0.5):
    return {
        'score': score, 'grade': 'D', 'action': 'wait',
        'entry_mult': 0.5,
        'chain': '', 'desc': reason, 'pattern_bonus': 0,
        'time_penalty': 0, 'poi_bonus': 0, 'trend_bonus': 0,
        'reversal_bonus': 0, 'bounce_bonus': 0, 'distance_penalty': 0,
        'n_preceding': 0, 'pattern': 'none',
        'poi_context': 'unknown', 'poi_tested': False, 'bounced': False,
        'price_position': 'unknown', 'distance_from_poi': 999,
    }


# ============================================================
# 测试/演示函数
# ============================================================

def run_v34_diagnostics(symbol: str, all_signals: List[Dict],
                         ohlcv: List[Dict]) -> Dict:
    """对一只股票运行V34诊断
    
    输出每个FVG信号的V33 vs V34评分对比
    """
    bull_fvgs = [s for s in all_signals if 'FVG_Bull' in s.get('type', '')
                 and s.get('direction') == 'bull']
    
    results = []
    for sig in bull_fvgs:
        idx = sig.get('idx', 0)
        v34 = score_signal_v34(all_signals, sig, ohlcv, idx)
        results.append({
            'idx': idx,
            'price': ohlcv[idx]['c'] if idx < len(ohlcv) else 0,
            'fvg_lower': sig.get('lower', 0),
            'fvg_upper': sig.get('upper', 0),
            'v34_score': v34['score'],
            'v34_grade': v34['grade'],
            'v34_context': v34['poi_context'],
            'poi_tested': v34['poi_tested'],
            'bounced': v34['bounced'],
            'dist_from_poi': v34['distance_from_poi'],
            'chain': v34['chain'],
            'pattern': v34['pattern'],
        })
    
    return {
        'symbol': symbol,
        'n_fvg': len(bull_fvgs),
        'results': results,
        'summary': {
            'n_grade_a': sum(1 for r in results if r['v34_grade'] == 'A'),
            'n_grade_b': sum(1 for r in results if r['v34_grade'] == 'B'),
            'n_grade_c': sum(1 for r in results if r['v34_grade'] == 'C'),
            'n_poi_tested': sum(1 for r in results if r['poi_tested']),
            'n_bounced': sum(1 for r in results if r['bounced']),
            'n_trend_continuation': sum(1 for r in results if r['v34_context'] == 'trend_continuation'),
        }
    }
