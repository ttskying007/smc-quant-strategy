#!/usr/bin/env python3
# SMC V11 — Adaptive Parameter Engine
"""
自适应参数系统 — 取代V8.4/V10的静态参数

核心创新:
1. 每股票参数: 基于ATR%/波动率/成交量特性计算独立参数
2. 每阶段参数: 基于市场阶段(trend/ranging/volatile)调整
3. 每周期参数: 不同TF使用不同的参数组合
4. 动态自适应: 参数随市场状态变化而更新
5. 从V8.4全局最优开始, 逐步个性化

设计:
  V11不再需要"全局最优参数"。每个股票在任何时刻都
  有自己独立的动态参数集。这解决了:
  - 茅台(低波动)和中芯(高波动)用同一套参数的问题
  - 趋势阶段和震荡阶段用同一套参数的问题
  - 日线和15分用同一套参数的问题
"""

import math, logging
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass

log = logging.getLogger('smc_v11.adaptive_params')


# ═══════════════════════════════════════════════════════════════════════
# V8.4 R13 Global Best (starting seed)
# ═══════════════════════════════════════════════════════════════════════

V84_R13_BEST = {
    'fvg_min_width': 0.22,
    'fvg_merge_dist': 2,
    'sweep_lookback': 12,
    'sweep_wick_ratio': 4.26,
    'ob_strength_min': 0.97,
    'confirm_range': 2,
    'min_sources': 3,
    'score_min': 3.71,
    'max_trades': 7,
    'atr_min_pct': 3.17,
    'atr_max_pct': 11.55,
    'sl_pct': 1.0,
    'tp_pct': 2.8,
    'vol_adapt_sl': 0.6,
}


# ═══════════════════════════════════════════════════════════════════════
# Phase definitions for per-stage params
# ═══════════════════════════════════════════════════════════════════════

PHASE_ADJUSTMENTS = {
    'trending_up': {
        'sl_multiplier': 0.8,    # 趋势中紧止损
        'tp_multiplier': 1.3,    # 趋势中宽止盈
        'score_min_offset': -0.5,  # 趋势中可降低门槛
        'max_trades_offset': 3,    # 趋势中可增加交易
        'fvg_min_width_offset': -0.03,  # 趋势中更敏感
    },
    'trending_down': {
        'sl_multiplier': 0.8,
        'tp_multiplier': 1.3,
        'score_min_offset': -0.5,
        'max_trades_offset': 3,
        'fvg_min_width_offset': -0.03,
    },
    'ranging': {
        'sl_multiplier': 1.2,    # 震荡中宽止损
        'tp_multiplier': 0.8,    # 震荡中短止盈
        'score_min_offset': 1.0,  # 震荡中提高门槛
        'max_trades_offset': -2,  # 震荡中少交易
        'fvg_min_width_offset': 0.05,  # 震荡中更严格
    },
    'volatile': {
        'sl_multiplier': 1.5,    # 高波大止损
        'tp_multiplier': 0.7,    # 高波小止盈
        'score_min_offset': 1.5,  # 高波很严格
        'max_trades_offset': -3,  # 高波少交易
        'fvg_min_width_offset': 0.08,  # 高波要求大FVG
    },
    'breakout': {
        'sl_multiplier': 0.7,    # 突破中紧止损
        'tp_multiplier': 1.5,    # 突破中宽止盈
        'score_min_offset': -1.0,  # 突破中可降低门槛
        'max_trades_offset': 5,    # 突破可多次交易
        'fvg_min_width_offset': -0.05,  # 突破中更敏感
    },
}


# ═══════════════════════════════════════════════════════════════════════
# TF-specific adjustments
# ═══════════════════════════════════════════════════════════════════════

TF_ADJUSTMENTS = {
    'daily': {
        'sweep_lookback': 12,
        'confirm_range': 3,
        'sl_pct_offset': 0.0,
        'tp_pct_offset': 0.0,
        'score_min_offset': 0.0,
        'max_trades': 7,
    },
    '4h': {
        'sweep_lookback': 8,
        'confirm_range': 2,
        'sl_pct_offset': -0.3,
        'tp_pct_offset': -0.5,
        'score_min_offset': 0.3,
        'max_trades': 5,
    },
    '1h': {
        'sweep_lookback': 6,
        'confirm_range': 2,
        'sl_pct_offset': -0.5,
        'tp_pct_offset': -1.0,
        'score_min_offset': 0.5,
        'max_trades': 4,
    },
    '15min': {
        'sweep_lookback': 5,
        'confirm_range': 1,
        'sl_pct_offset': -0.7,
        'tp_pct_offset': -1.5,
        'score_min_offset': 0.8,
        'max_trades': 3,
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Adaptive params calculator
# ═══════════════════════════════════════════════════════════════════════

def calc_stock_params(ohlcv: List[Dict], symbol: str = '',
                      phase: str = 'trending_up', tf: str = 'daily',
                      seed_params: Dict = None) -> Dict:
    """计算股票的完整自适应参数集
    
    这是V11的核心创新: 不是用一个全局参数集, 而是
    根据每只股票的实时特性计算独立的参数。
    
    Args:
        ohlcv: K线数据 [{o,h,l,c,v}, ...]
        symbol: 股票代码(用于日志)
        phase: 市场阶段
        tf: 时间框架
        seed_params: 种子参数(默认V8.4 R13)
    
    Returns:
        dict: 完整的自适应参数
    """
    if seed_params is None:
        seed_params = dict(V84_R13_BEST)
    
    # 1. 基础统计
    stats = _calc_stock_stats(ohlcv)
    
    # 2. 从种子参数开始
    params = dict(seed_params)
    
    # 3. ATR%自适应 — 核心调整
    atr_pct = stats['atr_pct']
    vol_class = stats['vol_class']
    
    # sl_pct: 基于ATR%的止损
    # 低波: 紧止损(ATR%的0.5倍) 高波: 宽止损(ATR%的1.0倍)
    base_sl = max(0.5, min(3.0, atr_pct * 0.6))
    params['sl_pct'] = round(base_sl, 1)
    
    # tp_pct: SL×2.5起步, 基于ATR%微调
    base_tp = max(1.5, min(5.0, base_sl * 2.5))
    params['tp_pct'] = round(base_tp, 1)
    
    # fvg_min_width: 基于波动率
    # 低波: 更敏感(检测更小缺口) 高波: 更大缺口
    if vol_class == 'low':
        params['fvg_min_width'] = round(max(0.0003, atr_pct / 300), 5)
    elif vol_class == 'medium':
        params['fvg_min_width'] = round(max(0.001, atr_pct / 200), 5)
    else:
        params['fvg_min_width'] = round(max(0.002, atr_pct / 150), 5)
    
    # sweep_wick_ratio: 基于波动率
    # 低波: 需要更明显影线 高波: 影线更常见
    base_wick = 4.0 if vol_class == 'low' else (3.0 if vol_class == 'medium' else 2.5)
    params['sweep_wick_ratio'] = round(base_wick, 1)
    
    # score_min: 基于信号质量和股票特性
    # 高波动需要更高的入门门槛
    base_score = 3.0 if vol_class == 'low' else (3.5 if vol_class == 'medium' else 4.0)
    params['score_min'] = base_score
    
    # 4. 阶段调整
    phase_adj = PHASE_ADJUSTMENTS.get(phase, {})
    params['sl_pct'] = round(params['sl_pct'] * phase_adj.get('sl_multiplier', 1.0), 1)
    params['tp_pct'] = round(params['tp_pct'] * phase_adj.get('tp_multiplier', 1.0), 1)
    params['score_min'] += phase_adj.get('score_min_offset', 0)
    params['max_trades'] += phase_adj.get('max_trades_offset', 0)
    params['fvg_min_width'] = round(
        params['fvg_min_width'] + phase_adj.get('fvg_min_width_offset', 0), 5
    )
    params['max_trades'] = max(1, min(15, params['max_trades']))
    
    # 5. TF调整
    tf_adj = TF_ADJUSTMENTS.get(tf, {})
    params['sweep_lookback'] = tf_adj.get('sweep_lookback', params['sweep_lookback'])
    params['confirm_range'] = tf_adj.get('confirm_range', params.get('confirm_range', 3))
    params['sl_pct'] = round(params['sl_pct'] + tf_adj.get('sl_pct_offset', 0), 1)
    params['tp_pct'] = round(params['tp_pct'] + tf_adj.get('tp_pct_offset', 0), 1)
    params['score_min'] += tf_adj.get('score_min_offset', 0)
    params['max_trades'] = tf_adj.get('max_trades', params['max_trades'])
    
    # 6. 参数边界限制
    params['sl_pct'] = max(0.3, min(5.0, params['sl_pct']))
    params['tp_pct'] = max(1.0, min(8.0, params['tp_pct']))
    params['score_min'] = max(0.5, min(8.0, params['score_min']))
    params['fvg_min_width'] = max(0.0001, min(0.05, params['fvg_min_width']))
    params['sweep_wick_ratio'] = max(1.0, min(8.0, params['sweep_wick_ratio']))
    params['ob_strength_min'] = max(0.3, min(3.0, params.get('ob_strength_min', 1.0)))
    params['sweep_lookback'] = max(3, min(30, int(params['sweep_lookback'])))
    params['max_trades'] = max(1, min(20, int(params['max_trades'])))
    params['confirm_range'] = max(1, min(10, int(params['confirm_range'])))
    params['fvg_merge_dist'] = max(1, min(5, int(params.get('fvg_merge_dist', 3))))
    
    # 7. 元数据
    params['_meta'] = {
        'symbol': symbol,
        'phase': phase,
        'tf': tf,
        'atr_pct': stats['atr_pct'],
        'vol_class': vol_class,
        'n_bars': len(ohlcv),
        'avg_volume': stats['avg_volume'],
    }
    
    return params


def _calc_stock_stats(ohlcv: List[Dict]) -> Dict:
    """计算股票统计特征"""
    n = len(ohlcv)
    if n < 20:
        return {
            'atr_pct': 2.0, 'avg_range_pct': 2.0,
            'vol_class': 'medium', 'avg_volume': 1e6,
            'volume_stability': 1.0,
        }
    
    # 波动率
    ranges = []
    for i in range(1, n):
        tr = max(
            ohlcv[i]['h'] - ohlcv[i]['l'],
            abs(ohlcv[i]['h'] - ohlcv[i-1]['c']),
            abs(ohlcv[i]['l'] - ohlcv[i-1]['c']),
        )
        ranges.append(tr / ohlcv[i]['c'] * 100 if ohlcv[i]['c'] > 0 else 0)
    
    atr_pct = sum(ranges[-min(14, len(ranges)):]) / min(14, len(ranges))
    
    # 波动率分类
    if atr_pct < 1.5:
        vol_class = 'low'
    elif atr_pct < 3.5:
        vol_class = 'medium'
    else:
        vol_class = 'high'
    
    # 成交量
    vols = [b['v'] for b in ohlcv[-50:] if b['v'] > 0] if n > 0 else [1]
    avg_vol = sum(vols) / len(vols) if vols else 1
    vol_std = math.sqrt(sum((v - avg_vol) ** 2 for v in vols) / len(vols)) if len(vols) > 1 else 0
    vol_stability = 1 - min(1, vol_std / avg_vol) if avg_vol > 0 else 0.5
    
    # 价格趋势
    recent = ohlcv[-min(20, n):]
    start_price = recent[0]['c'] if recent else 1
    end_price = recent[-1]['c'] if recent else 1
    trend_pct = (end_price - start_price) / start_price * 100 if start_price > 0 else 0
    
    return {
        'atr_pct': round(atr_pct, 2),
        'avg_range_pct': round(sum(ranges[-min(50, len(ranges)):]) / min(50, len(ranges)), 2),
        'vol_class': vol_class,
        'avg_volume': round(avg_vol, 0),
        'volume_stability': round(vol_stability, 3),
        'trend_pct': round(trend_pct, 2),
    }


# ═══════════════════════════════════════════════════════════════════════
# Phase detector
# ═══════════════════════════════════════════════════════════════════════

def detect_market_phase(ohlcv: List[Dict]) -> str:
    """检测当前市场阶段
    
    Returns: 'trending_up' | 'trending_down' | 'ranging' | 'volatile' | 'breakout'
    """
    if len(ohlcv) < 30:
        return 'ranging'
    
    recent = ohlcv[-30:]
    
    # 波动率
    ranges = []
    for i in range(1, len(recent)):
        tr = max(
            recent[i]['h'] - recent[i]['l'],
            abs(recent[i]['h'] - recent[i-1]['c']),
            abs(recent[i]['l'] - recent[i-1]['c']),
        )
        ranges.append(tr / recent[i]['c'] * 100 if recent[i]['c'] > 0 else 0)
    avg_range = sum(ranges) / len(ranges) if ranges else 2
    
    # 趋势
    highs = [b['h'] for b in recent]
    lows = [b['l'] for b in recent]
    
    # HH/LL count
    hh_count = 0
    for i in range(2, len(highs)):
        if highs[i] > highs[i-1] and highs[i-1] > highs[i-2]:
            hh_count += 1
    
    ll_count = 0
    for i in range(2, len(lows)):
        if lows[i] < lows[i-1] and lows[i-1] < lows[i-2]:
            ll_count += 1
    
    # 突破检测: 最后5根K线范围是否远超平均
    last_range = (max(b['h'] for b in recent[-5:]) - min(b['l'] for b in recent[-5:]))
    last_range_pct = last_range / recent[-1]['c'] * 100 if recent[-1]['c'] > 0 else 0
    
    if last_range_pct > avg_range * 2 and last_range_pct > 5:
        return 'breakout'
    
    if avg_range > 4:
        return 'volatile'
    
    if hh_count >= 4 and ll_count < 2:
        return 'trending_up'
    elif ll_count >= 4 and hh_count < 2:
        return 'trending_down'
    
    return 'ranging'


# ═══════════════════════════════════════════════════════════════════════
# Per-stock parameter file management
# ═══════════════════════════════════════════════════════════════════════

PER_STOCK_PARAMS_FILE = Path.home() / '.hermes' / 'smc_opt_v11' / 'per_stock_params.json'

def save_per_stock_params(params: Dict):
    """保存每股票参数到文件"""
    PER_STOCK_PARAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PER_STOCK_PARAMS_FILE.write_text(json.dumps(params, ensure_ascii=False, indent=2))


def load_per_stock_params() -> Dict:
    """加载每股票参数"""
    if PER_STOCK_PARAMS_FILE.exists():
        try:
            return json.loads(PER_STOCK_PARAMS_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


# ═══════════════════════════════════════════════════════════════════════
# SL/TP calculators
# ═══════════════════════════════════════════════════════════════════════

def calc_sl_price(entry_price: float, direction: str, 
                  sl_pct: float, ohlcv: List[Dict] = None) -> float:
    """计算止损价格"""
    if direction == 'bull':
        return entry_price * (1 - sl_pct / 100)
    else:
        return entry_price * (1 + sl_pct / 100)


def calc_tp_price(entry_price: float, sl_price: float,
                  direction: str, tp_pct: float = None,
                  rr_target: float = 2.5) -> float:
    """计算止盈价格"""
    if direction == 'bull':
        if tp_pct:
            return entry_price * (1 + tp_pct / 100)
        else:
            return entry_price + (entry_price - sl_price) * rr_target
    else:
        if tp_pct:
            return entry_price * (1 - tp_pct / 100)
        else:
            return entry_price - (sl_price - entry_price) * rr_target


# 确保json被导入
import json
