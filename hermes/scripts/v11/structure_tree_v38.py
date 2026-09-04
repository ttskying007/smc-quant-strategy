#!/usr/bin/env python3
"""
V38 — 层次化摆动结构树
========================
3层结构 (micro/meso/macro):
- micro: (3,2) 窗口 — 日内/短期摆动点
- meso: (8,5) 窗口 — 中周期结构
- macro: (20,10) 窗口 — 大周期趋势结构

每个层级追踪:
- HH (Higher High) / HL (Higher Low) 序列
- 趋势状态 (up/down/neutral)
- 最近摆动点位置
"""

def detect_swings(ohlcv, window=5, min_bars=3):
    """检测所有摆动高点和低点"""
    n = len(ohlcv)
    highs, lows = [], []
    
    for i in range(min_bars, n - min_bars):
        # 摆动高点: 左右各min_bars根K线都不超过它
        left_h = all(ohlcv[j]['h'] <= ohlcv[i]['h'] for j in range(i-min_bars, i))
        right_h = all(ohlcv[j]['h'] <= ohlcv[i]['h'] for j in range(i+1, i+min_bars+1))
        if left_h and right_h:
            highs.append({'idx': i, 'price': ohlcv[i]['h'], 'time': ohlcv[i].get('date', i)})
        
        # 摆动低点
        left_l = all(ohlcv[j]['l'] >= ohlcv[i]['l'] for j in range(i-min_bars, i))
        right_l = all(ohlcv[j]['l'] >= ohlcv[i]['l'] for j in range(i+1, i+min_bars+1))
        if left_l and right_l:
            lows.append({'idx': i, 'price': ohlcv[i]['l'], 'time': ohlcv[i].get('date', i)})
    
    return highs, lows


class StructureTree:
    """3层层次化结构树"""
    
    LEVELS = {
        'micro': {'window': 3, 'min_bars': 2, 'lookback': 10},
        'meso': {'window': 8, 'min_bars': 5, 'lookback': 30},
        'macro': {'window': 20, 'min_bars': 10, 'lookback': 60},
    }
    
    def __init__(self, ohlcv):
        self.ohlcv = ohlcv
        self.n = len(ohlcv)
        self.structures = {}
        for level_name, cfg in self.LEVELS.items():
            highs, lows = detect_swings(ohlcv, cfg['window'], cfg['min_bars'])
            self.structures[level_name] = {
                'highs': highs,
                'lows': lows,
                'trend': self._calc_trend(highs, lows, cfg['lookback']),
                'levels': self._calc_levels(highs, lows),
            }
    
    def _calc_trend(self, highs, lows, lookback):
        """基于最近的HH/HL序列判断趋势"""
        recent_highs = [h for h in highs if h['idx'] >= self.n - lookback]
        recent_lows = [l for l in lows if l['idx'] >= self.n - lookback]
        
        if len(recent_highs) < 2 or len(recent_lows) < 2:
            return 'neutral'
        
        # HH序列: 连续higher highs
        hh_count = sum(1 for i in range(1, len(recent_highs))
                       if recent_highs[i]['price'] > recent_highs[i-1]['price'])
        # HL序列: 连续higher lows
        hl_count = sum(1 for i in range(1, len(recent_lows))
                       if recent_lows[i]['price'] > recent_lows[i-1]['price'])
        
        total = len(recent_highs) - 1 + len(recent_lows) - 1
        if total == 0:
            return 'neutral'
        
        up_ratio = (hh_count + hl_count) / total
        if up_ratio >= 0.7:
            return 'up'
        elif up_ratio <= 0.3:
            return 'down'
        return 'neutral'
    
    def _calc_levels(self, highs, lows):
        """关键价格水平: 前摆动高点和低点"""
        if not highs and not lows:
            return {'nearest_support': None, 'nearest_resistance': None}
        
        current = self.ohlcv[-1]['c']
        
        support = None
        resistance = None
        
        # 最近的摆动低点=支撑
        for l in reversed(lows):
            if l['price'] < current * 1.15:  # 在15%以内
                support = l
                break
        
        # 最近的摆动高点=阻力
        for h in reversed(highs):
            if h['price'] > current * 0.85:  # 在15%以内
                resistance = h
                break
        
        return {
            'nearest_support': support,
            'nearest_resistance': resistance,
        }
    
    def get_sl_level(self, entry_idx, entry_price):
        """基于结构树的止损水平
        返回: (sl_price, level_name, sl_pct) 或 None
        """
        # 优先macro支撑 → 然后meso → 然后micro
        for level in ['macro', 'meso', 'micro']:
            cfg = self.LEVELS[level]
            lookback = cfg['lookback']
            lows = self.structures[level]['lows']
            
            # 找入场前最近的有效摆动低点
            prev_lows = [l for l in lows if l['idx'] < entry_idx and l['idx'] >= entry_idx - lookback]
            if prev_lows:
                # 找到距入场最近的摆动低点
                nearest = max(prev_lows, key=lambda l: l['idx'])
                price = nearest['price']
                sl_pct = (entry_price - price) / entry_price * 100
                
                # 结构SL必须在合理范围内
                if 0.08 <= sl_pct <= 1.5:
                    return price, f'structure_{level}', sl_pct
        
        return None
    
    def get_tp_level(self, entry_idx, entry_price, direction='bull'):
        """基于结构树的止盈水平
        bull: 找前方摆动高点 (阻力位)
        bear: 找前方摆动低点 (支撑位)
        返回: (tp_price, level_name, tp_pct, tp_idx) 或 None
        """
        if direction == 'bull':
            for level in ['micro', 'meso', 'macro']:
                cfg = self.LEVELS[level]
                lookahead = cfg['lookback']
                highs = self.structures[level]['highs']
                next_highs = [h for h in highs if h['idx'] > entry_idx and h['idx'] <= entry_idx + lookahead]
                if next_highs:
                    nearest = min(next_highs, key=lambda h: h['idx'])
                    price = nearest['price']
                    tp_pct = (price - entry_price) / entry_price * 100
                    if tp_pct >= 0.3:
                        return price, f'swing_high_{level}', tp_pct, nearest['idx']
        else:  # bear: 找前方摆动低点 (支撑位)
            for level in ['micro', 'meso', 'macro']:
                cfg = self.LEVELS[level]
                lookahead = cfg['lookback']
                lows = self.structures[level]['lows']
                next_lows = [l for l in lows if l['idx'] > entry_idx and l['idx'] <= entry_idx + lookahead]
                if next_lows:
                    nearest = min(next_lows, key=lambda l: l['idx'])
                    price = nearest['price']
                    tp_pct = (entry_price - price) / entry_price * 100
                    if tp_pct >= 0.3:
                        return price, f'swing_low_{level}', tp_pct, nearest['idx']
        return None
    
    def get_multi_level_support(self):
        """获取多层支撑 — 用于阶段判断"""
        supports = {}
        for level in ['micro', 'meso', 'macro']:
            lows = self.structures[level]['lows']
            if lows:
                supports[level] = lows[-1]['price']
            else:
                supports[level] = None
        return supports
    
    def get_multi_level_resistance(self):
        """获取多层阻力"""
        resistances = {}
        for level in ['micro', 'meso', 'macro']:
            highs = self.structures[level]['highs']
            if highs:
                resistances[level] = highs[-1]['price']
            else:
                resistances[level] = None
        return resistances
    
    def is_consolidation(self, lookback=20):
        """检测是否在盘整 (价格被压缩在窄区间)"""
        seg = self.ohlcv[-lookback:]
        if not seg:
            return False
        
        high = max(b['h'] for b in seg)
        low = min(b['l'] for b in seg)
        mid = (high + low) / 2
        range_pct = (high - low) / mid * 100
        
        # 波动率收缩 = 盘整信号
        return range_pct < 8.0  # 8%以内算盘整
    
    def summary(self, at_idx=None):
        """在指定位置的结构摘要"""
        if at_idx is None:
            at_idx = self.n - 1
        current = self.ohlcv[at_idx]['c']
        
        s = {}
        for level_name in ['micro', 'meso', 'macro']:
            st = self.structures[level_name]
            s[level_name] = {
                'trend': st['trend'],
                'support': st['levels']['nearest_support'],
                'resistance': st['levels']['nearest_resistance'],
            }
        s['consolidation'] = self.is_consolidation()
        return s


def calc_atr_v38(ohlcv, idx, period=14):
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100


def calc_stock_atr_profile(ohlcv):
    """计算股票的ATR特征 — 用于参数自适应"""
    n = len(ohlcv)
    if n < 30:
        return {'atr14': 1.0, 'atr30': 1.0, 'vol_class': 'medium'}
    
    atr14_list = []
    for i in range(20, n):
        atr14_list.append(calc_atr_v38(ohlcv, i, 14))
    
    avg_atr14 = sum(atr14_list) / len(atr14_list) if atr14_list else 1.0
    atr30_list = []
    for i in range(30, n):
        atr30_list.append(calc_atr_v38(ohlcv, i, 30))
    avg_atr30 = sum(atr30_list) / len(atr30_list) if atr30_list else 1.0
    
    # 波动率等级
    if avg_atr14 < 0.5:
        vol_class = 'low'
    elif avg_atr14 < 1.5:
        vol_class = 'medium'
    else:
        vol_class = 'high'
    
    return {
        'atr14': round(avg_atr14, 4),
        'atr30': round(avg_atr30, 4),
        'vol_class': vol_class,
    }
