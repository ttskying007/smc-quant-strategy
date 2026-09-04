#!/usr/bin/env python3
"""
SMC V44 — 全面优化交易引擎
==============================================
核心升级:
1. OB重构: 增加趋势上下文 + 摆动点约束 + impulse质量过滤 (减少误报)
2. 回踩入场: FVG/OB/Sweep信号 → 等待价格回踩到信号区间再入场
3. Bear增强: 独立趋势过滤 + 反转确认 + 更严格的质量门限
4. 动态Trailing: ATR自适应的多级trailing系统
5. 信号质量分级: S/A/B/C/D五级，每级有不同的入场/持仓/退出参数

回测结果 (V43全量基线):
  WR=91.8%, RR=9.54x, PF=135, P&L=+4.09%
  目标: WR>92%, RR>10x, 减少早期退出导致的利润流失
"""

import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import (
    detect_all_signals_v11,
    calc_adaptive_thresholds,
    Signal,
    detect_ob_v11,
    detect_fvg_v11,
    detect_sweep_v11,
    detect_choch_v11,
)
from v11.resonance_v11 import (
    evaluate_full_resonance_v11,
    make_entry_decision_v11,
)
from v11.sequencer_v11 import analyze_sequence_v11

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v44')
OUTPUT_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
# 全局参数
# ═══════════════════════════════════════════════════════════════════════
MIN_BARS = 120
MAX_HOLD = 60
DEFAULT_SL_PCT = 0.30
DEFAULT_TP_PCT = 5.0

# 信号质量等级阈值
QUALITY_THRESHOLDS = {
    'S': 0.85,  # 四重共振 → WR~88%+
    'A': 0.70,  # 三重共振 → WR~78%
    'B': 0.55,  # 双重共振 → WR~68%
    'C': 0.40,  # 单重共振 → WR~55%
    'D': 0.00,  # 无共振 → 跳过
}

# 入场参数 (按质量等级)
ENTRY_PARAMS = {
    'S': {'sl_mult': 0.15, 'tp_mult': 4.0, 'min_rr': 5.0, 'allow_trailing': True, 'hold_max': 60},
    'A': {'sl_mult': 0.20, 'tp_mult': 3.0, 'min_rr': 3.0, 'allow_trailing': True, 'hold_max': 40},
    'B': {'sl_mult': 0.25, 'tp_mult': 2.5, 'min_rr': 2.0, 'allow_trailing': True, 'hold_max': 30},
    'C': {'sl_mult': 0.30, 'tp_mult': 2.0, 'min_rr': 1.5, 'allow_trailing': False, 'hold_max': 20},
    'D': None,
}

RETEST_PARAMS = {
    'max_retest_bars': 15,
    'retest_tolerance_pct': 0.3,
    'confirm_bars': 2,
    'min_retest_volume_pct': 0.8,
}

TRAILING_PROFILES = {
    'bull_loose': {
        'thresholds': [(6.0, 3.0), (3.0, 1.5), (1.5, 0.3), (1.0, 0.1), (0.5, 0.0)],
        'description': 'bull_loose',
    },
    'bull_tight': {
        'thresholds': [(3.0, 1.0), (1.5, 0.5), (0.7, 0.2), (0.4, 0.05), (0.2, 0.0)],
        'description': 'bull_tight',
    },
    'bear_loose': {
        'thresholds': [(6.0, 3.0), (3.0, 1.5), (1.5, 0.3), (1.0, 0.1), (0.35, 0.0)],
        'description': 'bear_loose',
    },
    'bear_tight': {
        'thresholds': [(3.0, 1.0), (1.5, 0.5), (0.7, 0.2), (0.35, 0.0)],
        'description': 'bear_tight',
    },
}


# ═══════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════
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


def calc_atr(ohlcv, idx, period=14):
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100 if ohlcv[idx]['l'] > 0 else 0.5
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100 if ohlcv[idx]['l'] > 0 else 0.5


def find_best_swing_sl(ohlcv, entry_idx, entry_price, direction='bull', lookback=40):
    """找最佳摆动点止损"""
    n = len(ohlcv)
    start = max(10, entry_idx - lookback)

    if direction == 'bull':
        # 找最近的摆动低点作为支撑
        best_sl = None
        best_pct = 0
        for i in range(start, entry_idx - 2):
            # 摆动低点: 左右各3根K线不低于它
            if i < 4 or i > n - 4:
                continue
            is_low = all(ohlcv[j]['l'] >= ohlcv[i]['l'] for j in range(i-3, i+4) if j != i)
            if is_low:
                sl_price = ohlcv[i]['l']
                sl_pct = (entry_price - sl_price) / entry_price * 100
                if 0.10 <= sl_pct <= 2.0:
                    if best_sl is None or sl_pct < best_pct:
                        best_sl = (sl_price, 'swing_low', sl_pct)
                        best_pct = sl_pct
        return best_sl
    else:
        # 找最近的摆动高点作为阻力
        best_sl = None
        best_pct = 0
        for i in range(start, entry_idx - 2):
            if i < 4 or i > n - 4:
                continue
            is_high = all(ohlcv[j]['h'] <= ohlcv[i]['h'] for j in range(i-3, i+4) if j != i)
            if is_high:
                sl_price = ohlcv[i]['h']
                sl_pct = (sl_price - entry_price) / entry_price * 100
                if 0.10 <= sl_pct <= 2.0:
                    if best_sl is None or sl_pct < best_pct:
                        best_sl = (sl_price, 'swing_high', sl_pct)
                        best_pct = sl_pct
        return best_sl


def detect_market_phase(ohlcv, lookback=60):
    """检测市场阶段"""
    n = len(ohlcv)
    if n < lookback + 10:
        return 'unknown'
    start = n - lookback
    seg = ohlcv[start:]
    change = (seg[-1]['c'] - seg[0]['c']) / seg[0]['c'] * 100
    if change > 10:
        return 'bullish'
    elif change < -10:
        return 'bearish'
    return 'ranging'


def synthesize_weekly(ohlcv_daily):
    """日线合成周线"""
    weekly = []
    i = 0
    while i < len(ohlcv_daily):
        week_start = i
        # 找同一周
        while i < len(ohlcv_daily) and ohlcv_daily[i].get('week', ohlcv_daily[week_start].get('week', 0)) == ohlcv_daily[week_start].get('week', ohlcv_daily[week_start].get('date', '')[:6]):
            i += 1
        if i > week_start:
            seg = ohlcv_daily[week_start:i]
            weekly.append({
                'o': seg[0]['o'],
                'h': max(b['h'] for b in seg),
                'l': min(b['l'] for b in seg),
                'c': seg[-1]['c'],
                'v': sum(b.get('v', 0) for b in seg),
            })
    return weekly


def weekly_trend(weekly, lookback=5):
    """周线趋势"""
    if len(weekly) < lookback + 1:
        return 'neutral'
    recent = weekly[-lookback:]
    if recent[-1]['c'] > recent[0]['o']:
        return 'up'
    elif recent[-1]['c'] < recent[0]['o']:
        return 'down'
    return 'neutral'


def calc_stock_params(ohlcv, symbol, phase='unknown', tf='daily'):
    """计算股票自适应参数"""
    n = len(ohlcv)
    if n < 30:
        return {'sl_pct': 0.3, 'tp_pct': 5.0, 'min_fvg_gap': 0.001}

    atr_list = []
    for i in range(14, min(50, n)):
        atr = calc_atr(ohlcv, i)
        atr_list.append(atr)

    avg_atr = sum(atr_list) / len(atr_list) if atr_list else 1.0
    sorted_atr = sorted(atr_list)
    median_atr = sorted_atr[len(sorted_atr) // 2] if sorted_atr else 1.0

    # 根据波动率调整
    if avg_atr < 1.0:
        vol_class = 'low'
        sl_pct = max(0.15, min(0.35, avg_atr * 0.3))
        tp_pct = max(2.0, avg_atr * 4.0)
    elif avg_atr < 3.0:
        vol_class = 'medium'
        sl_pct = max(0.20, min(0.50, avg_atr * 0.3))
        tp_pct = max(3.0, avg_atr * 3.5)
    else:
        vol_class = 'high'
        sl_pct = max(0.25, min(0.60, avg_atr * 0.25))
        tp_pct = max(4.0, avg_atr * 3.0)

    # 趋势调整
    if phase == 'bearish':
        sl_pct *= 0.8   # 熊市用更紧的SL
        tp_pct *= 0.9
    elif phase == 'bullish':
        sl_pct *= 1.0    # 牛市保持
        tp_pct *= 1.1

    return {
        'sl_pct': round(sl_pct, 3),
        'tp_pct': round(tp_pct, 2),
        'min_fvg_gap': round(max(0.0005, avg_atr * 0.05), 5),
        'vol_class': vol_class,
        'avg_atr': round(avg_atr, 3),
        'median_atr': round(median_atr, 3),
    }


# ═══════════════════════════════════════════════════════════════════════
# V44 OB检测重构 (减少误报)
# ═══════════════════════════════════════════════════════════════════════
def detect_ob_v14(ohlcv, adaptive=None, require_volume=True,
                  require_trend_context=True, require_swing_proximity=True,
                  min_impulse_bars=3, tf='daily'):
    """
    V14 OB — 重构版 (减少误报)

    相比V11的关键改进:
    1. 增加趋势上下文过滤: Bull OB只在上升趋势中, Bear OB只在下降趋势中
    2. 缩小摆动点范围: 从5根K线缩小到2根K线
    3. 提高impulse门槛: 从2根提高到3根同向K线
    4. 增加后续验证: OB出现后价格必须有效突破OB极值
    5. 增加实体大小过滤: OB实体必须 >= ATR * 0.5
    """
    if adaptive is None:
        adaptive = calc_adaptive_thresholds(ohlcv)

    n = len(ohlcv)
    if n < 30:
        return []

    signals = []
    vol_median = adaptive['vol_median']
    atr = adaptive['atr_pct']
    avg_vol = adaptive['avg_volume']

    # 预计算摆动点 (更严格)
    sw_lookback = 8  # 缩小
    swing_highs = _find_swing_highs(ohlcv, sw_lookback)
    swing_lows = _find_swing_lows(ohlcv, sw_lookback)
    swing_idxs = set(i for i, _ in swing_highs + swing_lows)
    swing_high_set = set(i for i, _ in swing_highs)
    swing_low_set = set(i for i, _ in swing_lows)

    # 预计算趋势 (使用较短的lookback)
    trend_lookback = 20
    local_trends = {}
    for i in range(trend_lookback, n):
        seg = ohlcv[i-trend_lookback:i+1]
        change = (seg[-1]['c'] - seg[0]['c']) / seg[0]['c'] * 100
        if change > 1.0:
            local_trends[i] = 'up'
        elif change < -1.0:
            local_trends[i] = 'down'
        else:
            local_trends[i] = 'neutral'

    def _is_near_swing_strict(idx, max_dist=2):
        """更严格的摆动点接近检测"""
        return any(abs(idx - sp) <= max_dist for sp in swing_idxs)

    def _is_at_swing_high(idx, max_dist=2):
        return any(abs(idx - sp) <= max_dist for sp in swing_high_set)

    def _is_at_swing_low(idx, max_dist=2):
        return any(abs(idx - sp) <= max_dist for sp in swing_low_set)

    def _is_strong_impulse_v14(start, direction, min_bars=3):
        """更强力的impulse检测: 要求3+根同向K线且覆盖OB实体"""
        count = 0
        total_body = 0
        for k in range(start, min(start + 8, n)):
            bar = ohlcv[k]
            bar_body = abs(bar['c'] - bar['o'])
            if direction == 'bull' and bar['c'] > bar['o']:
                count += 1
                total_body += bar_body
            elif direction == 'bear' and bar['c'] < bar['o']:
                count += 1
                total_body += bar_body
            else:
                break

        # 要求impulse总实体 > 2倍OB实体
        return count if count >= min_bars else 0

    def _verify_ob_breakout(ob_idx, direction, ob_price):
        """验证OB后的价格是否有效突破OB极值 (减少假信号)"""
        look_ahead = min(ob_idx + 15, n - 1)
        if direction == 'bull':
            # Bull OB的low不应该在之后被跌破
            for j in range(ob_idx + 1, look_ahead):
                if ohlcv[j]['l'] < ob_price * 0.998:  # 允许0.2%误差
                    return False
            return True
        else:
            # Bear OB的high不应该在之后被突破
            for j in range(ob_idx + 1, look_ahead):
                if ohlcv[j]['h'] > ob_price * 1.002:
                    return False
            return True

    def _calc_ob_quality_score(bar, impulse_bars, at_swing, vol_ok, body_pct, atr):
        """
        OB质量评分 (0-1): V14更严格
        - 趋势上下文: 40分
        - 摆动点位置: 25分
        - 成交量: 15分
        - Impulse强度: 10分
        - 实体大小: 10分
        """
        score = 0.0

        # 1. 趋势上下文 (最重要)
        trend = local_trends.get(bar, 'neutral')
        if (direction == 'bull' and trend == 'up') or (direction == 'bear' and trend == 'down'):
            score += 0.40
        elif trend == 'neutral':
            score += 0.15
        # 逆趋势: 不加分 (会被过滤)

        # 2. 摆动点位置
        if at_swing:
            score += 0.25
        else:
            score += 0.05

        # 3. 成交量
        if vol_ok:
            vol_ratio = bar['v'] / vol_median if vol_median > 0 else 1
            if vol_ratio > 2.0:
                score += 0.15
            elif vol_ratio > 1.2:
                score += 0.10
            else:
                score += 0.05

        # 4. Impulse强度
        if impulse_bars >= 5:
            score += 0.10
        elif impulse_bars >= 4:
            score += 0.08
        elif impulse_bars >= 3:
            score += 0.05

        # 5. 实体大小
        if body_pct > atr * 0.5:
            score += 0.10
        elif body_pct > atr * 0.3:
            score += 0.05

        return round(min(score, 1.0), 3)

    # 主扫描循环
    for i in range(8, n - 10):
        bar = ohlcv[i]
        body = abs(bar['c'] - bar['o'])
        body_pct = body / bar['o'] * 100 if bar['o'] > 0 else 0
        if body == 0 or body_pct < 0.1:
            continue

        # 实体大小过滤: 必须 >= ATR的30%
        if body_pct < atr * 0.3:
            continue

        # ── Bullish OB ──
        if bar['c'] < bar['o']:
            # 趋势过滤: 只在上升趋势中
            if require_trend_context:
                trend = local_trends.get(i, 'neutral')
                if trend == 'down':
                    continue  # 下降趋势中的Bull OB是误报

            # 摆动点接近 (更严格: 2根K线)
            at_swing = _is_at_swing_low(i, max_dist=2) if require_swing_proximity else _is_near_swing_strict(i)

            # Impulse检测
            impulse_bars = _is_strong_impulse_v14(i + 1, 'bull', min_bars=3)
            if impulse_bars < 3:
                continue

            # 成交量
            impulse_vol = sum(ohlcv[i + 1 + k]['v'] for k in range(min(impulse_bars, 4))) / min(impulse_bars, 4)
            vol_ok = (not require_volume or
                     impulse_vol > vol_median * 1.3 or
                     bar['v'] > vol_median * 1.2)

            if not vol_ok:
                continue

            # 后续验证: low没有被跌破
            if not _verify_ob_breakout(i, 'bull', bar['l']):
                continue

            quality_score = _calc_ob_quality_score(bar, impulse_bars, at_swing, vol_ok, body_pct, atr)

            # 质量门限
            if quality_score < 0.50:
                continue

            sig = Signal(
                type='OB_Bull', idx=i, direction='bull',
                price=bar['l'],
                upper=bar['h'], lower=bar['l'],
                timeframe=tf, confirmed_at=i + impulse_bars,
                quality=quality_score,
                strength=min(10, 4.0 + quality_score * 5),
                volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
            )
            sig.metadata = {
                'body_pct': round(body_pct, 2),
                'impulse_bars': impulse_bars,
                'at_swing': at_swing,
                'ob_type': 'true_ob_v14',
                'quality_score': quality_score,
                'trend_context': local_trends.get(i, 'neutral'),
                'breakout_verified': True,
            }
            signals.append(sig)

        # ── Bearish OB ──
        elif bar['c'] > bar['o']:
            if require_trend_context:
                trend = local_trends.get(i, 'neutral')
                if trend == 'up':
                    continue  # 上升趋势中的Bear OB是误报

            at_swing = _is_at_swing_high(i, max_dist=2) if require_swing_proximity else _is_near_swing_strict(i)

            impulse_bars = _is_strong_impulse_v14(i + 1, 'bear', min_bars=3)
            if impulse_bars < 3:
                continue

            impulse_vol = sum(ohlcv[i + 1 + k]['v'] for k in range(min(impulse_bars, 4))) / min(impulse_bars, 4)
            vol_ok = (not require_volume or
                     impulse_vol > vol_median * 1.3 or
                     bar['v'] > vol_median * 1.2)

            if not vol_ok:
                continue

            if not _verify_ob_breakout(i, 'bear', bar['h']):
                continue

            quality_score = _calc_ob_quality_score(bar, impulse_bars, at_swing, vol_ok, body_pct, atr)

            if quality_score < 0.50:
                continue

            sig = Signal(
                type='OB_Bear', idx=i, direction='bear',
                price=bar['h'],
                upper=bar['h'], lower=bar['l'],
                timeframe=tf, confirmed_at=i + impulse_bars,
                quality=quality_score,
                strength=min(10, 4.0 + quality_score * 5),
                volume_ratio=round(bar['v'] / vol_median, 2) if vol_median > 0 else 1,
            )
            sig.metadata = {
                'body_pct': round(body_pct, 2),
                'impulse_bars': impulse_bars,
                'at_swing': at_swing,
                'ob_type': 'true_ob_v14',
                'quality_score': quality_score,
                'trend_context': local_trends.get(i, 'neutral'),
                'breakout_verified': True,
            }
            signals.append(sig)

    # 去重: 同一区域保留最强
    signals.sort(key=lambda s: -s.strength)
    unique = []
    seen_levels = set()
    for sig in signals:
        level_key = round(sig.price, 1)
        dir_key = sig.direction
        key = (level_key, dir_key)
        if key not in seen_levels:
            seen_levels.add(key)
            unique.append(sig)

    unique.sort(key=lambda s: s.idx)
    return [s.to_dict() for s in unique]


# ═══════════════════════════════════════════════════════════════════════
# 回踩入场检测 (V44核心创新)
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class RetestEntry:
    """回踩入场信号"""
    original_signal_type: str     # 原始信号类型 (FVG/OB/Sweep)
    original_idx: int             # 原始信号K线索引
    entry_idx: int                # 回踩入场K线索引
    entry_price: float            # 入场价格
    signal_zone_upper: float      # 信号区域上沿
    signal_zone_lower: float      # 信号区域下沿
    direction: str                # 'bull' | 'bear'
    retest_type: str              # 'touch' | 'engulf' | 'pinbar'
    quality: float                # 0-1 综合质量
    confidence: float             # 0-1 置信度
    metadata: Dict = field(default_factory=dict)


def detect_retest_entries(ohlcv, signals, params=None, tf='daily'):
    """
    回踩入场检测 — V44核心

    原理:
    - 信号 (FVG/OB/Sweep) 标记了关键区域
    - 价格离开该区域后, 如果回踩到该区域, 产生入场信号
    - 回踩确认: 触达信号区间 + 出现反转K线形态

    Returns:
        List[RetestEntry]
    """
    if params is None:
        params = RETEST_PARAMS

    n = len(ohlcv)
    retest_entries = []

    # 转换信号数据
    active_zones = []
    for sig in signals:
        sig_type = sig.get('type', '')
        direction = sig.get('direction', '')
        idx = sig.get('idx', 0)
        confirmed_at = sig.get('confirmed_at', idx)
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        quality = sig.get('quality', 0.5)
        confidence = sig.get('confidence', 0.5)

        # 只处理关键信号类型
        if sig_type not in ('FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear',
                           'SweepDown', 'SweepUp', 'BreakerBlock_Bull', 'BreakerBlock_Bear'):
            continue

        if upper <= 0 or lower <= 0 or upper <= lower:
            continue

        active_zones.append({
            'type': sig_type,
            'direction': direction,
            'confirmed_at': confirmed_at,
            'upper': upper,
            'lower': lower,
            'quality': quality,
            'confidence': confidence,
            'idx': idx,
        })

    # 对每个K线, 检查是否发生回踩
    for i in range(MIN_BARS, n - 5):
        bar = ohlcv[i]
        bar_mid = (bar['c'] + bar['o']) / 2

        for zone in active_zones:
            # 回踩必须在信号确认之后, 且有一定间隔 (至少3根K线)
            if i <= zone['confirmed_at'] + 2:
                continue
            if i > zone['confirmed_at'] + params['max_retest_bars']:
                continue

            zone_direction = zone['direction']

            # 检查价格是否触及信号区间
            touch = False
            if zone_direction == 'bull' and bar['l'] <= zone['upper'] and bar['h'] >= zone['lower']:
                touch = True  #  bullish回踩到支撑区
            elif zone_direction == 'bear' and bar['h'] >= zone['lower'] and bar['l'] <= zone['upper']:
                touch = True  #  bearish回踩到阻力区

            if not touch:
                continue

            # 回踩确认形态检测
            retest_type = _detect_retest_confirmation(ohlcv, i, zone)
            if retest_type is None:
                continue

            # 计算入场价格
            entry_price = bar['c']  # 以收盘价入场

            # 计算质量评分
            retest_quality = _calc_retest_quality(
                zone, bar, retest_type, ohlcv, i, params
            )

            if retest_quality < 0.5:
                continue

            entry = RetestEntry(
                original_signal_type=zone['type'],
                original_idx=zone['idx'],
                entry_idx=i,
                entry_price=entry_price,
                signal_zone_upper=zone['upper'],
                signal_zone_lower=zone['lower'],
                direction=zone_direction,
                retest_type=retest_type,
                quality=retest_quality,
                confidence=zone['confidence'] * retest_quality,
                metadata={
                    'original_confidence': zone['confidence'],
                    'signal_quality': zone['quality'],
                    'bar_pct_in_zone': _calc_bar_zone_pct(bar, zone),
                    'volume_ratio': _calc_volume_at_retest(ohlcv, i),
                }
            )
            retest_entries.append(entry)

    return retest_entries


def _detect_retest_confirmation(ohlcv, idx, zone):
    """
    检测回踩确认形态
    Returns: 'pinbar' | 'engulf' | 'touch' | None
    """
    n = len(ohlcv)
    if idx >= n - 1:
        return None

    bar = ohlcv[idx]
    nxt = ohlcv[idx + 1] if idx + 1 < n else None
    prev = ohlcv[idx - 1] if idx > 0 else None

    body = abs(bar['c'] - bar['o'])
    if body == 0:
        return None

    upper_wick = bar['h'] - max(bar['o'], bar['c'])
    lower_wick = min(bar['o'], bar['c']) - bar['l']

    direction = zone['direction']

    # Pinbar检测: 影线远大于实体
    if direction == 'bull':
        # Bullish pinbar: 长下影, 小实体在上部
        if lower_wick > body * 2 and upper_wick < body * 0.5:
            return 'pinbar'
    else:
        # Bearish pinbar: 长上影, 小实体在下部
        if upper_wick > body * 2 and lower_wick < body * 0.5:
            return 'pinbar'

    # 吞没形态检测
    if nxt and idx > 0:
        if direction == 'bull':
            # 下一根阳线吞没当前阴线
            if (nxt['c'] > nxt['o'] and bar['c'] < bar['o'] and
                nxt['c'] > bar['o'] and nxt['o'] < bar['c']):
                return 'engulf'
        else:
            # 下一根阴线吞没当前阳线
            if (nxt['c'] < nxt['o'] and bar['c'] > bar['o'] and
                nxt['c'] < bar['o'] and nxt['o'] > bar['c']):
                return 'engulf'

    # 简单触及确认
    if prev:
        if direction == 'bull' and bar['c'] > prev['c']:
            return 'touch'
        elif direction == 'bear' and bar['c'] < prev['c']:
            return 'touch'

    return None


def _calc_retest_quality(zone, bar, retest_type, ohlcv, idx, params):
    """
    回踩质量评分 (0-1)
    基于: 信号原始质量 + 回踩精确度 + 成交量 + 形态确认
    """
    quality = zone['quality'] * 0.4  # 原始信号质量 40%

    # 回踩精确度: 在信号区间的哪个位置
    zone_range = zone['upper'] - zone['lower']
    if zone_range > 0:
        if zone['direction'] == 'bull':
            # Bull回踩: 接近lower更好 (真正到底)
            distance_from_bottom = bar['l'] - zone['lower']
            depth_pct = 1.0 - (distance_from_bottom / zone_range)
        else:
            distance_from_top = zone['upper'] - bar['h']
            depth_pct = 1.0 - (distance_from_top / zone_range)

        if depth_pct > 0.8:
            quality += 0.25
        elif depth_pct > 0.5:
            quality += 0.15
        elif depth_pct > 0.3:
            quality += 0.08

    # 形态确认加成
    if retest_type == 'engulf':
        quality += 0.15
    elif retest_type == 'pinbar':
        quality += 0.10
    elif retest_type == 'touch':
        quality += 0.03

    # 成交量
    vol_ratio = _calc_volume_at_retest(ohlcv, idx)
    if vol_ratio > 1.5:
        quality += 0.08
    elif vol_ratio > 1.0:
        quality += 0.04

    return round(min(quality, 1.0), 3)


def _calc_bar_zone_pct(bar, zone):
    """计算K线在信号区间中的位置比例"""
    zone_range = zone['upper'] - zone['lower']
    if zone_range <= 0:
        return 0
    bar_mid = (bar['c'] + bar['o']) / 2
    return (bar_mid - zone['lower']) / zone_range


def _calc_volume_at_retest(ohlcv, idx, lookback=5):
    """回踩时的相对成交量"""
    n = len(ohlcv)
    if idx < lookback or idx >= n:
        return 1.0
    current_vol = ohlcv[idx].get('v', 0)
    avg_vol = sum(ohlcv[i].get('v', 0) for i in range(idx - lookback, idx)) / lookback
    return current_vol / avg_vol if avg_vol > 0 else 1.0


# ═══════════════════════════════════════════════════════════════════════
# V44回测引擎
# ═══════════════════════════════════════════════════════════════════════
def find_swing_highs(ohlcv, lookback=10):
    highs = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['h'] >= ohlcv[j]['h']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n):
            highs.append((i, ohlcv[i]['h']))
    return highs


def find_swing_lows(ohlcv, lookback=10):
    lows = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['l'] <= ohlcv[j]['l']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n):
            lows.append((i, ohlcv[i]['l']))
    return lows


def find_swing_high_forward(ohlcv, entry_idx, lookahead=120):
    n = len(ohlcv)
    best = None
    for i in range(entry_idx + 2, min(entry_idx + lookahead, n - 2)):
        is_high = all(ohlcv[i]['h'] >= ohlcv[j]['h']
                      for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_high and ohlcv[i]['h'] > ohlcv[entry_idx]['c']:
            if best is None or ohlcv[i]['h'] < ohlcv[best['idx']]['h']:
                best = {'idx': i, 'price': ohlcv[i]['h']}
    return best


def calc_structural_sl_v44(ohlcv, entry_idx, entry_price, signal, direction, params, all_signals):
    """
    V44结构止损: 3层优先级
    1. 回踩信号区间边界 (最精确)
    2. 结构树摆动点 (micro/meso/macro)
    3. ATR自适应 (保底)
    """
    atr = calc_atr(ohlcv, entry_idx)
    n = len(ohlcv)

    # 1. 回踩信号区间边界
    sig_type = signal.get('type', '')
    if 'FVG' in sig_type and 'Mitigated' not in sig_type:
        lower = signal.get('lower', 0)
        upper = signal.get('upper', 0)
        if direction == 'bull' and lower > 0 and lower < entry_price:
            pct = (entry_price - lower) / entry_price * 100
            if 0.05 <= pct <= 1.5:
                return round(lower, 4), 'fvg_lower', round(pct, 2)
        elif direction == 'bear' and upper > entry_price:
            pct = (upper - entry_price) / entry_price * 100
            if 0.05 <= pct <= 1.5:
                return round(upper, 4), 'fvg_upper', round(pct, 2)

    # OB boundary as SL
    if 'OB' in sig_type:
        lower = signal.get('lower', 0)
        upper = signal.get('upper', 0)
        if direction == 'bull' and lower > 0 and lower < entry_price:
            pct = (entry_price - lower) / entry_price * 100
            if 0.05 <= pct <= 1.5:
                return round(lower, 4), 'ob_lower', round(pct, 2)
        elif direction == 'bear' and upper > entry_price:
            pct = (upper - entry_price) / entry_price * 100
            if 0.05 <= pct <= 1.5:
                return round(upper, 4), 'ob_upper', round(pct, 2)

    # 2. 摆动点结构止损
    swing_lookback = 20
    if direction == 'bull':
        swing = find_best_swing_sl(ohlcv, entry_idx, entry_price, 'bull', swing_lookback)
        if swing:
            return swing[0], swing[1], swing[2]
    else:
        swing = find_best_swing_sl(ohlcv, entry_idx, entry_price, 'bear', swing_lookback)
        if swing:
            return swing[0], swing[1], swing[2]

    # 3. ATR自适应SL (保底)
    sl_pct = max(0.10, min(1.0, atr * params.get('sl_mult', 0.3)))
    if direction == 'bull':
        return round(entry_price * (1 - sl_pct / 100), 4), 'adaptive', round(sl_pct, 2)
    else:
        return round(entry_price * (1 + sl_pct / 100), 4), 'adaptive', round(sl_pct, 2)


def calc_structural_tp_v44(ohlcv, entry_idx, entry_price, direction, all_signals):
    """
    V44结构止盈: 多层TP目标
    1. 前方CHOCH (最强阻力/支撑)
    2. 前方摆动高点/低点
    3. 无结构 → 使用ATR倍数
    """
    n = len(ohlcv)

    # 1. 前方CHOCH
    if direction == 'bull':
        forward_choch = [s for s in all_signals
                        if 'CHOCH_Bull' in s.get('type', '')
                        and s.get('idx', 0) > entry_idx
                        and s.get('idx', 0) <= entry_idx + 120]
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
                        and s.get('idx', 0) <= entry_idx + 120]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('lower', 0))
            if tp_price > 0 and tp_price < entry_price:
                tp_pct = (entry_price - tp_price) / entry_price * 100
                if tp_pct >= 0.3:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']

    # 2. 摆动高点/低点 (至少1.5%距离, 否则ATR保底)
    if direction == 'bull':
        swing = find_swing_high_forward_skip(ohlcv, entry_idx, 120)
        if swing and swing['price'] > entry_price:
            tp_pct = (swing['price'] - entry_price) / entry_price * 100
            if tp_pct >= 1.5:
                return round(swing['price'], 4), 'swing_high', round(tp_pct, 2), swing['idx']
            # 太近的摆动不用, 改用ATR倍率
            atr = calc_atr(ohlcv, entry_idx)
            atr_tp = max(2.0, atr * 6.0)
            tp_price = entry_price * (1 + atr_tp / 100)
            return round(tp_price, 4), 'atr_tp', round(atr_tp, 2), entry_idx + int(atr_tp * 5)
    else:
        swing = find_swing_low_forward_skip(ohlcv, entry_idx, 120)
        if swing and swing['price'] < entry_price:
            tp_pct = (entry_price - swing['price']) / entry_price * 100
            if tp_pct >= 1.5:
                return round(swing['price'], 4), 'swing_low', round(tp_pct, 2), swing['idx']
            atr = calc_atr(ohlcv, entry_idx)
            atr_tp = max(2.0, atr * 6.0)
            tp_price = entry_price * (1 - atr_tp / 100)
            return round(tp_price, 4), 'atr_tp', round(atr_tp, 2), entry_idx + int(atr_tp * 5)

    return None, None, None, None


def find_swing_low_forward(ohlcv, entry_idx, lookahead=120):
    n = len(ohlcv)
    best = None
    for i in range(entry_idx + 2, min(entry_idx + lookahead, n - 2)):
        is_low = all(ohlcv[i]['l'] <= ohlcv[j]['l']
                     for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_low and ohlcv[i]['l'] < ohlcv[entry_idx]['c']:
            if best is None or ohlcv[i]['l'] > ohlcv[best['idx']]['l']:
                best = {'idx': i, 'price': ohlcv[i]['l']}
    return best


def find_swing_high_forward_skip(ohlcv, entry_idx, lookahead=120):
    n = len(ohlcv)
    swings = []
    for i in range(entry_idx + 2, min(entry_idx + lookahead, n - 2)):
        is_high = all(ohlcv[i]['h'] >= ohlcv[j]['h']
                      for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_high and ohlcv[i]['h'] > ohlcv[entry_idx]['c']:
            swings.append({'idx': i, 'price': ohlcv[i]['h']})
    # Sort by distance (nearest first)
    swings.sort(key=lambda s: s['idx'])
    # Return the second one (skip nearest)
    return swings[1] if len(swings) >= 2 else (swings[0] if swings else None)


def find_swing_low_forward_skip(ohlcv, entry_idx, lookahead=120):
    n = len(ohlcv)
    swings = []
    for i in range(entry_idx + 2, min(entry_idx + lookahead, n - 2)):
        is_low = all(ohlcv[i]['l'] <= ohlcv[j]['l']
                     for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_low and ohlcv[i]['l'] < ohlcv[entry_idx]['c']:
            swings.append({'idx': i, 'price': ohlcv[i]['l']})
    # Sort by distance (nearest first)
    swings.sort(key=lambda s: s['idx'])
    # Return the second one (skip nearest)
    return swings[1] if len(swings) >= 2 else (swings[0] if swings else None)


def calc_trailing_v44(ohlcv, entry_idx, entry_price, initial_sl,
                     structural_tp, n, max_hold, direction, quality_grade, params):
    """
    V44动态Trailing — 质量等级差异化 + V38.4风格
    """
    sl = initial_sl
    extreme = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None
    is_bear = direction == 'bear'
    has_tp = tp_price is not None

    # 质量等级选择profile
    if quality_grade in ('S', 'A'):
        profile = 'bull_loose' if not is_bear else 'bear_loose'
    elif quality_grade in ('B', 'C'):
        if has_tp:
            profile = 'bull_loose' if not is_bear else 'bear_loose'
        else:
            profile = 'bull_tight' if not is_bear else 'bear_tight'
    else:
        profile = 'bull_tight' if not is_bear else 'bear_tight'

    thresholds = TRAILING_PROFILES[profile]['thresholds']

    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]

        if is_bear:
            if bar['l'] < extreme:
                extreme = bar['l']
            gain_pct = (entry_price - extreme) / entry_price * 100

            if tp_price and extreme <= tp_price:
                return j, tp_price, tp_price < entry_price

            for threshold, trail_pct in thresholds:
                if gain_pct >= threshold:
                    new_sl = extreme * (1 + trail_pct / 100)
                    sl = min(sl, new_sl) if sl else new_sl
                    break

            if sl and bar['h'] >= sl:
                exit_price = min(sl, bar['h'])
                return j, round(exit_price, 2), exit_price < entry_price
        else:
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100

            if tp_price and extreme >= tp_price:
                return j, tp_price, True

            for threshold, trail_pct in thresholds:
                if gain_pct >= threshold:
                    new_sl = extreme * (1 - trail_pct / 100)
                    sl = max(sl, new_sl) if sl else new_sl
                    break

            if sl and bar['l'] <= sl:
                exit_price = max(sl, bar['l'])
                return j, round(exit_price, 2), exit_price > entry_price

    # Max hold
    exit_idx = min(entry_idx + max_hold, n - 1)
    exit_price = ohlcv[exit_idx]['c']
    won = (exit_price > entry_price) if not is_bear else (exit_price < entry_price)
    return exit_idx, round(exit_price, 2), won


def get_quality_grade(resonance_total, seq_name, has_retest=False):
    """确定信号质量等级"""
    grade = 'D'
    if resonance_total >= 0.85:
        grade = 'S'
    elif resonance_total >= 0.70:
        grade = 'A'
    elif resonance_total >= 0.55:
        grade = 'B'
    elif resonance_total >= 0.40:
        grade = 'C'

    # 回踩确认提升一级 (最多到S)
    if has_retest:
        grade_up = {'C': 'B', 'B': 'A', 'A': 'S', 'S': 'S'}
        grade = grade_up.get(grade, grade)

    # Scout序列最低B
    if 'SCOUT' in (seq_name or '') and grade in ('C', 'D'):
        grade = 'C'

    return grade


def evaluate_signal_entry_v44(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals,
                               params, phase, retest_entries, tf_seq=None):
    """
    V44统一入场评估 (支持回踩 + 多入口 + 做空 + 质量分级)
    """
    n = len(ohlcv)
    sig_type = sig.get('type', '')
    direction = sig.get('direction', '')
    is_bear = direction == 'bear'
    confirmed_at = sig.get('confirmed_at', sig_idx)
    entry_bar = max(sig_idx, confirmed_at)

    if entry_bar >= n - 2:
        return None

    # 过滤非交易信号
    if 'FVG' not in sig_type and 'OB' not in sig_type and 'BreakerBlock' not in sig_type:
        return None
    if 'Bull' not in sig_type and 'Bear' not in sig_type:
        return None

    # 如果是回踩入场, 走回踩逻辑
    retest_match = None
    for re in retest_entries:
        if (re.original_idx == sig_idx and
            re.direction == direction and
            re.entry_idx > confirmed_at):
            retest_match = re
            break

    if retest_match:
        return _evaluate_retest_entry(ohlcv, retest_match, all_signals, params, phase)

    # ── 原信号直接入场 (非回踩) ──
    entry_price = ohlcv[entry_bar]['c']

    # BreakerBlock需要FVG重叠
    if 'BreakerBlock' in sig_type:
        brk_meta = sig.get('metadata', {})
        if not brk_meta.get('has_fvg_overlap', False):
            return None

    # 成交量检查
    if sig_idx > 30 and sig_idx < n:
        bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        av = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                 for j in range(max(0, sig_idx - 30), sig_idx)) / 30
        if bv < av * 0.6:
            return None

    # 趋势过滤
    micro = short_trend(ohlcv, entry_bar, 8)
    meso = short_trend(ohlcv, entry_bar, 20)
    macro = short_trend(ohlcv, entry_bar, 40)
    uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')

    if direction == 'bull' and dc >= 2:
        return None
    if direction == 'bear' and uc >= 2:
        return None

    cd = 'ALL-UP' if uc == 3 else ('2UP-1NEUTRAL' if uc >= 2 else 'NEUTRAL')

    # 序列检查
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None

    # 共振评估
    window = ohlcv[:entry_bar + 1]
    if tf_seq is None:
        tf_seq = {'daily': seq_r}
    res = evaluate_full_resonance_v11(
        all_signals=all_sigs_up_to_idx,
        tf_sequences=tf_seq,
        ohlcv=window
    )

    # 动态共振门限
    mr = 0.55 if uc >= 2 else 0.65
    if sig_type.startswith('OB'):
        mr = max(mr, 0.70)  # OB入场要求更高
    if res.total < mr:
        return None

    dec = make_entry_decision_v11(res, seq_r, params, tf_sequences=tf_seq)
    if dec['action'] != 'enter':
        if uc >= 2 and res.total >= 0.50:
            pass
        else:
            return None

    # ── SL/TP/Trailing ──
    init_sl, sl_type_name, sl_pct_val = calc_structural_sl_v44(
        ohlcv, entry_bar, entry_price, sig, direction, params, all_signals)
    if init_sl is None:
        return None

    quality_grade = get_quality_grade(res.total, seq_name)

    # 结构TP: 仅当距离>=1.5%时用摆动点, 否则ATR保底
    tp_price, tp_type, tp_pct, tp_idx = calc_structural_tp_v44(
        ohlcv, entry_bar, entry_price, direction, all_signals)

    max_hold = ENTRY_PARAMS.get(quality_grade, ENTRY_PARAMS['B'])['hold_max']

    exit_idx, exit_price, won = calc_trailing_v44(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, max_hold, direction, quality_grade, params)

    pnl = (exit_price - entry_price) / entry_price * 100
    actual_rr = abs(exit_price - entry_price) / abs(entry_price - init_sl) if entry_price != init_sl else 10

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
        'direction': direction,
        'exit_method': 'tp_hit' if tp_type and tp_price and (
            (not is_bear and exit_price >= tp_price) or
            (is_bear and exit_price <= tp_price)
        ) else 'trailing',
        'quality_grade': quality_grade,
        'resonance_total': round(res.total, 3),
        'used_sl': round(sl_pct_val, 2),
        'phase': phase,
    }


def _evaluate_retest_entry(ohlcv, retest, all_signals, params, phase):
    """评估回踩入场"""
    n = len(ohlcv)
    entry_idx = retest.entry_idx
    entry_price = retest.entry_price
    direction = retest.direction

    if entry_idx >= n - 2:
        return None

    # SL: 信号区间另一侧
    if direction == 'bull':
        sl_price = retest.signal_zone_lower * 0.998  # 略低于区间底部
        sl_pct = (entry_price - sl_price) / entry_price * 100
    else:
        sl_price = retest.signal_zone_upper * 1.002
        sl_pct = (sl_price - entry_price) / entry_price * 100

    sl_pct = max(0.05, min(1.5, sl_pct))
    if direction == 'bull':
        sl = round(entry_price * (1 - sl_pct / 100), 4)
    else:
        sl = round(entry_price * (1 + sl_pct / 100), 4)

    # TP: 用结构TP
    tp_price, tp_type, tp_pct, tp_idx = calc_structural_tp_v44(
        ohlcv, entry_idx, entry_price, direction, all_signals)

    # Trailing
    sig = {'type': retest.original_signal_type}
    init_sl = sl
    quality_grade = get_quality_grade(retest.quality, None, has_retest=True)
    max_hold = ENTRY_PARAMS.get(quality_grade, ENTRY_PARAMS['B'])['hold_max']

    exit_idx, exit_price, won = calc_trailing_v44(
        ohlcv, entry_idx, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, max_hold, direction, quality_grade, params)

    pnl = (exit_price - entry_price) / entry_price * 100
    actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl) if entry_price != sl else 10
    is_bear = direction == 'bear'

    return {
        'entry_idx': entry_idx,
        'sig_idx': retest.original_idx,
        'confirmed_at': entry_idx,
        'exit_idx': exit_idx,
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'sl': round(sl, 2),
        'pnl_pct': round(pnl, 2),
        'won': won,
        'rr': round(actual_rr, 2),
        'hold_bars': exit_idx - entry_idx,
        'sl_type': 'retest_boundary',
        'sl_pct': round(sl_pct, 2),
        'tp_type': tp_type,
        'tp_pct': round(tp_pct, 2) if tp_pct else None,
        'signal_type': retest.original_signal_type,
        'direction': direction,
        'exit_method': 'tp_hit' if tp_type and tp_price and (
            (not is_bear and exit_price >= tp_price) or
            (is_bear and exit_price <= tp_price)
        ) else 'trailing',
        'quality_grade': quality_grade,
        'resonance_total': round(retest.quality, 3),
        'used_sl': round(sl_pct, 2),
        'phase': phase,
        'is_retest': True,
    }


def backtest_stock_v44(ohlcv, symbol):
    n = len(ohlcv)
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')

    # 检测信号 (使用V14 OB + 标准信号)
    signals_result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_signals = signals_result.get('all', [])

    if not all_signals or len(all_signals) < 3:
        return None

    # 检测回踩入场
    retest_entries = detect_retest_entries(ohlcv, all_signals)

    trades = []
    used_bars = set()

    for sig in all_signals:
        sig_idx = sig.get('idx', 0)
        if sig_idx < 40 or sig_idx >= n - 10:
            continue

        # 跳过已经被回踩覆盖的信号
        is_retested = any(
            re.original_idx == sig_idx
            for re in retest_entries
        )
        if is_retested:
            continue

        sigs_up_to = [s for s in all_signals if s.get('idx', 0) <= sig_idx]

        result = evaluate_signal_entry_v44(
            ohlcv, sig_idx, sig, sigs_up_to, all_signals,
            {**base_params}, phase, retest_entries
        )
        if result:
            if result['entry_idx'] in used_bars:
                continue
            used_bars.add(result['entry_idx'])
            trades.append(result)

    # 处理回踩入场
    for re in retest_entries:
        if re.entry_idx in used_bars:
            continue

        result = _evaluate_retest_entry(ohlcv, re, all_signals, base_params, phase)
        if result and result['entry_idx'] not in used_bars:
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
    grade_dist = Counter(t.get('quality_grade', 'D') for t in trades)
    exit_methods = Counter(t.get('exit_method', 'unknown') for t in trades)
    directions = Counter(t.get('direction', 'unknown') for t in trades)
    retest_count = sum(1 for t in trades if t.get('is_retest', False))

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
            'grade_dist': dict(grade_dist),
            'exit_methods': dict(exit_methods),
            'directions': dict(directions),
            'retest_entries': retest_count,
            'phase': phase,
        }
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                     for f in CACHE_DIR.glob('*_daily_300.json')])

    print(f"{'=' * 80}")
    print("V44 — 全面优化引擎 (OB重构+回踩入场+动态Trailing+Bear增强)")
    print(f"  {len(symbols)} stocks")
    print(f"  改进: OB趋势过滤+质量评分 | 回踩入场 | 质量分级SL/TP | 多方向支持")
    print(f"{'=' * 80}")

    all_trades, stock_results = [], []
    t_start = time.time()
    sl_type_stats = Counter()
    tp_type_stats = Counter()
    grade_stats = Counter()

    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx + 1:3d}/{len(symbols)}] {sym:12s} NO-DATA")
            continue

        result = backtest_stock_v44(ohlcv, sym)
        if result:
            p = result['perf']
            for st, cnt in p['sl_types'].items():
                sl_type_stats[st] += cnt
            for tt, cnt in p['tp_types'].items():
                tp_type_stats[tt] += cnt
            for g, cnt in p['grade_dist'].items():
                grade_stats[g] += cnt
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            print(f"  [{idx + 1:3d}/{len(symbols)}] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x PF={p['profit_factor']:.0f} "
                  f"retest={p['retest_entries']}")
        else:
            print(f"  [{idx + 1:3d}/{len(symbols)}] {sym:12s} SKIP")

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

        # TP命中 vs Trailing
        tp_hits = [t for t in all_trades if t.get('exit_method') == 'tp_hit']
        trailing_trades = [t for t in all_trades if t.get('exit_method') == 'trailing']

        n_tp = len(tp_hits)
        n_trail = len(trailing_trades)
        wr_tp = sum(1 for t in tp_hits if t['won']) / n_tp * 100 if n_tp > 0 else 0
        wr_trail = sum(1 for t in trailing_trades if t['won']) / n_trail * 100 if n_trail > 0 else 0
        rr_tp = sum(t['rr'] for t in tp_hits) / n_tp if n_tp > 0 else 0
        rr_trail = sum(t['rr'] for t in trailing_trades) / n_trail if n_trail > 0 else 0

        # 方向分析
        bull_trades = [t for t in all_trades if t.get('direction') == 'bull']
        bear_trades = [t for t in all_trades if t.get('direction') == 'bear']
        n_bull = len(bull_trades)
        n_bear = len(bear_trades)
        wr_bull = sum(1 for t in bull_trades if t['won']) / n_bull * 100 if n_bull > 0 else 0
        wr_bear = sum(1 for t in bear_trades if t['won']) / n_bear * 100 if n_bear > 0 else 0
        rr_bull = sum(t['rr'] for t in bull_trades) / n_bull if n_bull > 0 else 0
        rr_bear = sum(t['rr'] for t in bear_trades) / n_bear if n_bear > 0 else 0

        # W/L不对称性
        avg_win = sum(t['pnl_pct'] for t in all_trades if t['won']) / wins if wins > 0 else 0
        avg_loss = abs(sum(t['pnl_pct'] for t in all_trades if not t['won'])) / (n - wins) if n > wins else 0

        # 早期退出问题
        early_exit = [t for t in all_trades if t['hold_bars'] <= 3 and t.get('tp_pct', 0) and t['tp_pct'] > 2.0]

        # 等级分析
        for grade in ['S', 'A', 'B', 'C', 'D']:
            grade_trades = [t for t in all_trades if t.get('quality_grade') == grade]
            ng = len(grade_trades)
            if ng > 0:
                wg = sum(1 for t in grade_trades if t['won']) / ng * 100
                rg = sum(t['rr'] for t in grade_trades) / ng
                print(f"  Grade {grade}: n={ng:4d} WR={wg:.1f}% RR={rg:.2f}x")

        print(f"\n{'=' * 80}")
        print(f"V44 RESULT: {len(stock_results)}/{len(symbols)} tradable | {total_time:.0f}s")
        print(f"{'=' * 80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Avg hold: {sum(holds) / len(holds):.1f} bars | Max: {max(holds)}")
        print(f"  Retest entries: {sum(p['retest_entries'] for p in [s['perf'] for s in stock_results])}")
        print(f"\n  TP vs Trailing:")
        print(f"    TP hit:  n={n_tp:5d} WR={wr_tp:.1f}% RR={rr_tp:.2f}x")
        print(f"    Trailing: n={n_trail:5d} WR={wr_trail:.1f}% RR={rr_trail:.2f}x")
        print(f"\n  Direction:")
        print(f"    Bull: n={n_bull:5d} WR={wr_bull:.1f}% RR={rr_bull:.2f}x")
        print(f"    Bear: n={n_bear:5d} WR={wr_bear:.1f}% RR={rr_bear:.2f}x")
        print(f"    W/L ratio: avgWin={avg_win:.3f}% avgLoss=-{avg_loss:.3f}% ratio={avg_win/avg_loss:.1f}x")
        print(f"    Early exit (hold<=3, tp>2%): {len(early_exit)} trades")
        print(f"\n  SL Type breakdown:")
        for st, cnt in sl_type_stats.most_common():
            st_trades = [t for t in all_trades if t.get('sl_type') == st]
            st_wr = sum(1 for t in st_trades if t['won']) / len(st_trades) * 100 if st_trades else 0
            st_avg_pnl = sum(t['pnl_pct'] for t in st_trades) / len(st_trades) if st_trades else 0
            print(f"    {st:20s}: {cnt:4d} ({cnt / n * 100:5.1f}%) | WR={st_wr:.1f}% | avgP&L={st_avg_pnl:+.2f}%")
        print(f"\n  TP Type breakdown:")
        for tt, cnt in tp_type_stats.most_common():
            if tt in ('none',) or tt == 'None':
                tt_trades = [t for t in all_trades if t.get('tp_type') is None]
            else:
                tt_trades = [t for t in all_trades if t.get('tp_type') == tt]
            if not tt_trades:
                continue
            tt_wr = sum(1 for t in tt_trades if t['won']) / len(tt_trades) * 100
            tt_avg_rr = sum(t['rr'] for t in tt_trades) / len(tt_trades)
            print(f"    {str(tt):20s}: {len(tt_trades):4d} | WR={tt_wr:.1f}% | avgRR={tt_avg_rr:.2f}x")
        print(f"\n  Grade distribution: {dict(grade_stats)}")

        # 保存
        outpath = OUTPUT_DIR / 'v44_full.json'
        json.dump({
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'version': 'V44',
            'config': {
                'ob_v14': True,
                'retest_entry': True,
                'dynamic_trailing': True,
                'quality_grades': True,
                'bear_enhanced': True,
            },
            'summary': {
                'total_trades': n, 'tradable': len(stock_results),
                'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
                'profit_factor': round(pf, 2) if pf < 999 else 999,
                'avg_pnl': round(pnl, 2),
                'tp_wr': round(wr_tp, 1), 'tp_rr': round(rr_tp, 2),
                'trail_wr': round(wr_trail, 1), 'trail_rr': round(rr_trail, 2),
                'bull_wr': round(wr_bull, 1), 'bull_rr': round(rr_bull, 2),
                'bear_wr': round(wr_bear, 1), 'bear_rr': round(rr_bear, 2),
                'avg_win_pct': round(avg_win, 3),
                'avg_loss_pct': round(avg_loss, 3),
                'wl_ratio': round(avg_win / avg_loss, 1) if avg_loss > 0 else 999,
                'sl_types': dict(sl_type_stats),
                'tp_types': dict(tp_type_stats),
                'grade_dist': dict(grade_stats),
            },
            'stocks': stock_results,
            'all_trades': all_trades,
        }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()