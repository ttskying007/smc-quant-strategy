#!/usr/bin/env python3
"""V37 — Enhanced Liquidity Zone Detection
=========================================
ICT核心: 流动性(止损单)聚集在摆动点附近, 机构猎杀这些止损后价格反转.

核心改进 (vs V11.2 sweep):
1. 流动性区域检测: 聚类附近摆动点 → BSL/SSL池, 不是单点
2. 猎杀追踪: 价格刺穿区域后是否反转
3. 多级流动性: 微/中/宏三级流动性池
4. 区域密度评分: 越多摆动点聚集 → 流动性越大
5. 猎杀后行为分类: 成功反转 vs 假突破趋势延续
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LiquidityZone:
    """流动性区域 — BSL/SSL池"""
    type: str                            # 'BSL' | 'SSL'
    price: float                         # 区域价格(加权平均)
    upper: float                         # 区域上沿
    lower: float                         # 区域下沿
    cluster_size: int                    # 包含的摆动点数量
    density: float                       # 密度评分 0-1 (越多=越高)
    formed_at: int                       # 形成K线
    last_updated: int                    # 最后更新K线
    swept_at: int = -1                   # 被猎杀的K线
    swept_price: float = 0.0             # 猎杀价格
    reversal_confirmed: bool = False     # 猎杀后是否反转
    reversal_at: int = -1                # 反转确认K线
    failed: bool = False                 # 猎杀后未反转
    
    def to_dict(self) -> Dict:
        return {
            'type': self.type,
            'price': round(self.price, 4),
            'upper': round(self.upper, 4),
            'lower': round(self.lower, 4),
            'cluster_size': self.cluster_size,
            'density': round(self.density, 3),
            'formed_at': self.formed_at,
            'last_updated': self.last_updated,
            'swept_at': self.swept_at,
            'swept_price': round(self.swept_price, 4),
            'reversal_confirmed': self.reversal_confirmed,
            'reversal_at': self.reversal_at,
            'failed': self.failed,
        }


@dataclass  
class LiquiditySignal:
    """流动性信号 — 从Zone衍生"""
    type: str            # 'Pool_BSL' | 'Pool_SSL' | 'Sweep_Bull' | 'Sweep_Bear' | 'Failed_Bull' | 'Failed_Bear'
    idx: int
    direction: str       # 'bull' | 'bear'
    price: float
    strength: float      # 0-10
    confidence: float    # 0-1
    zone: Dict           # 关联的Zone信息
    
    def to_dict(self) -> Dict:
        return {
            'type': self.type,
            'idx': self.idx,
            'direction': self.direction,
            'price': round(self.price, 4),
            'strength': round(self.strength, 2),
            'confidence': round(self.confidence, 3),
            'zone_cluster_size': self.zone.get('cluster_size', 0),
            'zone_density': self.zone.get('density', 0),
            'zone_upper': self.zone.get('upper', 0),
            'zone_lower': self.zone.get('lower', 0),
        }


# ═══════════════════════════════════════════════════════════════════════
# 核心检测
# ═══════════════════════════════════════════════════════════════════════

def detect_liquidity_zones(ohlcv: List[Dict], 
                           swing_lookback: int = 8,
                           cluster_window: int = 15,
                           zone_merge_dist: float = 0.005,  # 0.5% distance to merge zones
                           tf: str = 'daily') -> Dict:
    """检测流动性区域和猎杀事件
    
    三步法:
    1. 找所有摆动点(微/中/宏三级)
    2. 聚类摆动点 → 流动性区域
    3. 追踪每个区域的猎杀状态
    4. 标记猎杀后反转
    
    Returns:
        {
            'zones': [LiquidityZone, ...],
            'signals': [LiquiditySignal, ...],
            'pool_signals': [...],  # 纯池信号(区域形成)
            'sweep_signals': [...], # 猎杀信号(扫荡+反转)
            'failed_signals': [...],# 假突破信号
        }
    """
    n = len(ohlcv)
    if n < 60:
        return {'zones': [], 'signals': [], 'pool_signals': [], 
                'sweep_signals': [], 'failed_signals': []}
    
    # 1. 三级摆动点: micro(3), meso(8), macro(20)
    sw_levels = {
        'micro': {'lookback': 3, 'swings': [], 'zones': []},
        'meso':  {'lookback': 8, 'swings': [], 'zones': []},
        'macro': {'lookback': 20, 'swings': [], 'zones': []},
    }
    
    for level_name, level in sw_levels.items():
        lb = level['lookback']
        # Find swing highs
        for i in range(lb, n - lb):
            is_high = True
            for j in range(i - lb, i + lb + 1):
                if j == i: continue
                if ohlcv[j]['h'] > ohlcv[i]['h']:
                    is_high = False
                    break
            if is_high:
                level['swings'].append((i, ohlcv[i]['h'], 'high'))
        
        # Find swing lows
        for i in range(lb, n - lb):
            is_low = True
            for j in range(i - lb, i + lb + 1):
                if j == i: continue
                if ohlcv[j]['l'] < ohlcv[i]['l']:
                    is_low = False
                    break
            if is_low:
                level['swings'].append((i, ohlcv[i]['l'], 'low'))
    
    # 2. 合并所有摆动点并排序
    all_swings = []
    for level_name, level in sw_levels.items():
        weight = {'micro': 1, 'meso': 2, 'macro': 3}[level_name]
        for idx, price, swing_type in level['swings']:
            all_swings.append({'idx': idx, 'price': price, 'type': swing_type, 'level_weight': weight})
    all_swings.sort(key=lambda s: s['idx'])
    
    # 3. 聚类成流动性区域
    # BSL zones: 聚集在摆动高点附近的区域
    # SSL zones: 聚集在摆动低点附近的区域
    bsl_swings = [s for s in all_swings if s['type'] == 'high']
    ssl_swings = [s for s in all_swings if s['type'] == 'low']
    
    bsl_zones = _cluster_swings(bsl_swings, cluster_window, zone_merge_dist, 'BSL')
    ssl_zones = _cluster_swings(ssl_swings, cluster_window, zone_merge_dist, 'SSL')
    
    all_zones = bsl_zones + ssl_zones
    all_zones.sort(key=lambda z: z.formed_at)
    
    # 4. 追踪猎杀状态
    # BSL zone: 价格上冲突破zone.upper后回撤 → 猎杀
    # SSL zone: 价格下探突破zone.lower后反弹 → 猎杀
    signals = []
    pool_signals = []
    sweep_signals = []
    failed_signals = []
    
    for zone in all_zones:
        zone_type = zone.type  # 'BSL' or 'SSL'
        zone_price = zone.price
        zone_upper = zone.upper
        zone_lower = zone.lower
        
        # 池形成信号(每只股票只生成最显著的)
        if zone.cluster_size >= 2 and zone.density >= 0.5:
            sig_type = f"Pool_{zone_type}"
            direction = 'bear' if zone_type == 'BSL' else 'bull'
            sig = LiquiditySignal(
                type=sig_type,
                idx=zone.formed_at,
                direction=direction,
                price=zone_price,
                strength=min(10, zone.cluster_size * 1.5 + zone.density * 3),
                confidence=min(1.0, 0.3 + zone.density * 0.4),
                zone=zone.to_dict(),
            )
            pool_signals.append(sig.to_dict())
        
        # 猎杀追踪: 从区域形成后扫描
        scan_start = zone.last_updated
        for j in range(scan_start, min(scan_start + 30, n)):
            bar = ohlcv[j]
            
            if zone_type == 'BSL':
                # BSL = 上方流动性: 价格刺破zone_upper
                if bar['h'] > zone_upper and zone.swept_at < 0:
                    zone.swept_at = j
                    zone.swept_price = bar['h']
                    
                    # 检查猎杀后是否反转: 1-3根K线内收回到zone_upper内
                    for k in range(j + 1, min(j + 4, n)):
                        if ohlcv[k]['c'] < zone_upper:
                            zone.reversal_confirmed = True
                            zone.reversal_at = k
                            break
                    
                    if not zone.reversal_confirmed:
                        # 猎杀后未反转 → 假突破/趋势延续
                        zone.failed = True
            
            elif zone_type == 'SSL':
                # SSL = 下方流动性: 价格刺破zone_lower
                if bar['l'] < zone_lower and zone.swept_at < 0:
                    zone.swept_at = j
                    zone.swept_price = bar['l']
                    
                    # 反转检查
                    for k in range(j + 1, min(j + 4, n)):
                        if ohlcv[k]['c'] > zone_lower:
                            zone.reversal_confirmed = True
                            zone.reversal_at = k
                            break
                    
                    if not zone.reversal_confirmed:
                        zone.failed = True
        
        # 生成猎杀信号
        if zone.swept_at >= 0:
            if zone.reversal_confirmed:
                # 成功的流动性猎杀 → 最强的入场信号
                direction = 'bull' if zone_type == 'SSL' else 'bear'
                sig_type = f"Sweep_{'Bull' if direction == 'bull' else 'Bear'}"
                sig = LiquiditySignal(
                    type=sig_type,
                    idx=zone.reversal_at if zone.reversal_confirmed else zone.swept_at,
                    direction=direction,
                    price=zone.swept_price,
                    strength=min(10, 4.0 + zone.cluster_size * 1.0 + zone.density * 2.0),
                    confidence=min(1.0, 0.5 + zone.density * 0.3 + (0.1 if zone.reversal_confirmed else 0)),
                    zone=zone.to_dict(),
                )
                sweep_signals.append(sig.to_dict())
            
            elif zone.failed:
                direction = 'bull' if zone_type == 'BSL' else 'bear'
                sig = LiquiditySignal(
                    type=f"Failed_{direction.capitalize()}",
                    idx=zone.swept_at,
                    direction=direction,
                    price=zone.swept_price,
                    strength=3.0,
                    confidence=0.3,
                    zone=zone.to_dict(),
                )
                failed_signals.append(sig.to_dict())
    
    all_signals = pool_signals + sweep_signals + failed_signals
    all_signals.sort(key=lambda s: s.get('idx', 0))
    
    return {
        'zones': [z.to_dict() for z in all_zones],
        'signals': all_signals,
        'pool_signals': pool_signals,
        'sweep_signals': sweep_signals,
        'failed_signals': failed_signals,
        'stats': {
            'total_zones': len(all_zones),
            'bsl_zones': len(bsl_zones),
            'ssl_zones': len(ssl_zones),
            'swept_zones': sum(1 for z in all_zones if z.swept_at >= 0),
            'reversals': sum(1 for z in all_zones if z.reversal_confirmed),
            'failed_sweeps': sum(1 for z in all_zones if z.failed),
        }
    }


def _cluster_swings(swings: List[Dict], 
                    max_dist: int, 
                    merge_price_pct: float,
                    zone_type: str) -> List[LiquidityZone]:
    """聚类摆动点 → 流动性区域
    
    Args:
        swings: 排序的摆动点列表
        max_dist: 同区域内摆动点最大K线距离
        merge_price_pct: 价格接近阈值(0.5%)
    
    Returns:
        流动性区域列表
    """
    if not swings:
        return []
    
    zones = []
    current_cluster = [swings[0]]
    
    for sw in swings[1:]:
        last = current_cluster[-1]
        dist = sw['idx'] - last['idx']
        price_diff = abs(sw['price'] - last['price']) / max(last['price'], 0.01)
        
        if dist <= max_dist and price_diff <= merge_price_pct * 3:
            # 同一个区域
            current_cluster.append(sw)
        else:
            # 新区域
            if current_cluster:
                zone = _make_zone(current_cluster, zone_type)
                if zone:
                    zones.append(zone)
            current_cluster = [sw]
    
    # Last cluster
    if current_cluster:
        zone = _make_zone(current_cluster, zone_type)
        if zone:
            zones.append(zone)
    
    return zones


def _make_zone(cluster: List[Dict], zone_type: str) -> Optional[LiquidityZone]:
    """从聚类创建流动性区域"""
    if len(cluster) < 2:
        return None
    
    prices = [s['price'] for s in cluster]
    idxs = [s['idx'] for s in cluster]
    weights = [s.get('level_weight', 1) for s in cluster]
    
    # 加权平均价格: 高级别摆动点权重更大
    total_weight = sum(weights)
    weighted_price = sum(p * w for p, w in zip(prices, weights)) / total_weight
    
    upper = max(prices)
    lower = min(prices)
    
    # 密度: 价格分散度 / 时间跨度
    price_spread = (upper - lower) / weighted_price * 100  # %
    time_span = max(idxs) - min(idxs)
    
    if price_spread > 5.0:  # 太分散了, 不是真正的簇
        return None
    
    # 密度评分: 摆动点越多, 价格越集中 → 密度越高
    density = min(1.0, (len(cluster) / 8) * (1.0 - min(1.0, price_spread / 5.0)))
    avg_weight = total_weight / len(cluster)
    density = min(1.0, density * (avg_weight / 1.5))  # 高级别加成
    
    return LiquidityZone(
        type=zone_type,
        price=weighted_price,
        upper=upper,
        lower=lower,
        cluster_size=len(cluster),
        density=round(density, 3),
        formed_at=min(idxs),
        last_updated=max(idxs),
    )


# ═══════════════════════════════════════════════════════════════════════
# 自适应序列窗口 (从liquidity视角)
# ═══════════════════════════════════════════════════════════════════════

def calc_adaptive_windows_v37(ohlcv: List[Dict]) -> Dict:
    """根据波动率计算自适应信号序列窗口
    
    原则:
    - 高波动: 信号快速发展, 窗口收紧
    - 低波动: 信号缓慢发展, 窗口放宽
    
    Returns:
        {
            'tight': int,    # 同方向连续信号
            'medium': int,   # 序列第一步→第二步
            'loose': int,    # 序列第二步→第三步
            'sequence_max': int,  # 整个序列最大跨度
        }
    """
    n = min(len(ohlcv), 100)
    if n < 20:
        return {'tight': 4, 'medium': 6, 'loose': 8, 'sequence_max': 15}
    
    # 计算ATR百分比
    trs = []
    for i in range(1, n):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr / max(l, 0.01) * 100)
    
    atr_pct = sum(trs[-14:]) / min(14, len(trs)) if trs else 2.0
    
    # 波动率分类
    if atr_pct < 1.5:
        vol_class = 'low'
    elif atr_pct < 3.5:
        vol_class = 'medium'
    else:
        vol_class = 'high'
    
    # 窗口映射
    windows = {
        'low':    {'tight': 5, 'medium': 8, 'loose': 12, 'sequence_max': 20},
        'medium': {'tight': 4, 'medium': 6, 'loose': 8,  'sequence_max': 15},
        'high':   {'tight': 3, 'medium': 4, 'loose': 6,  'sequence_max': 10},
    }
    
    result = windows[vol_class]
    result['atr_pct'] = round(atr_pct, 2)
    result['vol_class'] = vol_class
    return result


# ═══════════════════════════════════════════════════════════════════════
# 与V11信号引擎的桥接
# ═══════════════════════════════════════════════════════════════════════

def enhance_signals_with_liquidity(all_signals: List[Dict],
                                    ohlcv: List[Dict]) -> List[Dict]:
    """用流动性信息增强现有V11信号
    
    对每个信号, 添加流动性上下文:
    - 信号前是否有流动性被猎杀?
    - 信号是否在流动性区域内?
    - 信号方向是否与流动性猎杀方向一致?
    """
    if not all_signals:
        return all_signals
    
    liq_result = detect_liquidity_zones(ohlcv)
    sweep_sigs = liq_result.get('sweep_signals', [])
    zones = liq_result.get('zones', [])
    
    # 按时间排序猎杀信号
    sweep_sigs.sort(key=lambda s: s.get('idx', 0))
    
    enhanced = []
    for sig in all_signals:
        sig_idx = sig.get('idx', 0)
        sig_dir = sig.get('direction', '')
        
        # Hunted zone context
        hunted_recently = False
        hunted_same_dir = False
        hunted_idx = -1
        
        for ss in sweep_sigs:
            ss_idx = ss.get('idx', 0)
            ss_dir = ss.get('direction', '')
            if 0 < sig_idx - ss_idx <= 8:  # 8 bar窗口内
                hunted_recently = True
                hunted_same_dir = (ss_dir == sig_dir)
                hunted_idx = ss_idx
                break
        
        # Zone proximity
        near_zone = False
        zone_price = 0
        zone_type = ''
        for z in zones:
            z_upper = z.get('upper', 0)
            z_lower = z.get('lower', 0)
            sig_price = sig.get('price', 0)
            if z_lower <= sig_price <= z_upper:
                near_zone = True
                zone_price = z.get('price', 0)
                zone_type = z.get('type', '')
                break
        
        sig['liquidity_context'] = {
            'hunted_recently': hunted_recently,
            'hunted_same_direction': hunted_same_dir,
            'hunted_bars_ago': sig_idx - hunted_idx if hunted_idx > 0 else -1,
            'near_liquidity_zone': near_zone,
            'zone_type': zone_type,
            'zone_price': round(zone_price, 4) if zone_price else 0,
        }
        
        # 加分: 流动性猎杀后同向信号
        if hunted_recently and hunted_same_dir:
            sig['strength'] = min(10, sig.get('strength', 0) + 1.5)
            sig['confidence'] = min(1.0, sig.get('confidence', 0) + 0.15)
        
        enhanced.append(sig)
    
    return enhanced



