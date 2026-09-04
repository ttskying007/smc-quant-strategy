#!/usr/bin/env python3
"""
K线数据前复权 — 检测并修复送转股/拆股导致的断层

A股k线数据来自Hubble API，部分股票含未复权的拆股/送转股断层。
9%的股票有>25%单bar跳空（500只抽样中45只）。

策略: 前向复权(forward adjustment) — 将跳空前所有价格乘以调整因子。
"""

import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional


def detect_splits(ohlcv: List[Dict], threshold: float = 0.20) -> List[Tuple[int, float]]:
    """
    检测拆股/送转股事件。
    
    Returns: [(split_bar, forward_adjustment_multiplier), ...]
    前向复权因子 = pre_split_price / post_split_price
    将 split_bar 之前所有 bar 乘以 1/multiplier = post/pre
    """
    splits = []
    for i in range(1, len(ohlcv)):
        c0 = ohlcv[i-1].get('c', 0)
        c1 = ohlcv[i].get('c', 0)
        if c0 <= 0 or c1 <= 0:
            continue
        change = abs(c1 - c0) / c0
        if change > threshold:
            # This is a split/dividend event
            # forward_mult = pre_price / post_price
            forward_mult = c0 / c1
            splits.append((i, forward_mult))
    return splits


def adjust_forward(ohlcv: List[Dict], splits: List[Tuple[int, float]]) -> List[Dict]:
    """
    前向复权: 将split_bar之前所有bar的价格乘以 1/forward_mult。
    使所有历史价格与最新价格可比。
    """
    if not splits:
        return ohlcv
    
    adjusted = []
    # Apply adjustments in chronological order (earliest first)
    splits_sorted = sorted(splits, key=lambda x: x[0])
    
    for i, bar in enumerate(ohlcv):
        new_bar = dict(bar)
        
        # Determine cumulative adjustment for this bar
        cum_mult = 1.0
        for split_bar, forward_mult in splits_sorted:
            if i < split_bar:
                cum_mult *= (1.0 / forward_mult)
        
        if abs(cum_mult - 1.0) > 0.001:
            for field in ['o', 'h', 'l', 'c']:
                if field in new_bar and new_bar[field] is not None:
                    new_bar[field] = round(new_bar[field] * cum_mult, 4)
            if 'upper' in new_bar:
                new_bar['upper'] = round(new_bar.get('upper', 0) * cum_mult, 4)
            if 'lower' in new_bar:
                new_bar['lower'] = round(new_bar.get('lower', 0) * cum_mult, 4)
        
        adjusted.append(new_bar)
    
    return adjusted


def load_adjusted(symbol: str, cache_dir: str = '/root/.hermes/kline_cache') -> Optional[Tuple[List[Dict], bool]]:
    """
    加载并前复权K线数据。
    
    Returns: (ohlcv_adjusted, was_adjusted)
    """
    fname = symbol.replace('.', '_') + '_daily_300.json'
    fpath = Path(cache_dir) / fname
    if not fpath.exists():
        return None
    
    ohlcv = json.loads(fpath.read_bytes())
    splits = detect_splits(ohlcv)
    
    if splits:
        adjusted = adjust_forward(ohlcv, splits)
        return adjusted, True
    
    return ohlcv, False


def scan_all_splits(cache_dir: str = '/root/.hermes/kline_cache', limit: int = None):
    """扫描所有股票的拆股/送转股事件"""
    files = sorted(Path(cache_dir).glob('*_daily_300.json'))
    if limit:
        files = files[:limit]
    
    results = []
    for fpath in files:
        sym = fpath.stem.replace('_daily_300', '').replace('_', '.')
        try:
            ohlcv = json.loads(fpath.read_bytes())
        except:
            continue
        
        splits = detect_splits(ohlcv)
        if splits:
            for bar, mult in splits:
                pre_price = ohlcv[bar-1]['c']
                post_price = ohlcv[bar]['c']
                results.append({
                    'symbol': sym,
                    'split_bar': bar,
                    'total_bars': len(ohlcv),
                    'pre_price': round(pre_price, 2),
                    'post_price': round(post_price, 2),
                    'change_pct': round(abs(post_price-pre_price)/pre_price*100, 1),
                    'forward_mult': round(mult, 4),
                })
    
    return results


if __name__ == '__main__':
    print("Scanning for split/dividend events...")
    splits = scan_all_splits(limit=500)
    print(f"Found {len(splits)} split events in 500 stocks ({len(splits)/500*100:.1f}%)")
    
    if splits:
        print("\nSample split events:")
        for s in splits[:10]:
            print(f"  {s['symbol']}: bar {s['split_bar']}/{s['total_bars']} "
                  f"¥{s['pre_price']}→¥{s['post_price']} ({s['change_pct']}%) "
                  f"mult={s['forward_mult']}")
        
        # Test adjustment on first stock
        sym = splits[0]['symbol']
        print(f"\nTesting forward adjustment on {sym}...")
        adj_data, was_adj = load_adjusted(sym)
        if was_adj:
            fname = sym.replace('.', '_') + '_daily_300.json'
            raw = json.loads(Path('/root/.hermes/kline_cache', fname).read_bytes())
            prices = [b['c'] for b in raw]
            print(f"  Before: range {min(prices):.2f} - {max(prices):.2f}")
            print(f"  After:  range {min(b['c'] for b in adj_data):.2f} - {max(b['c'] for b in adj_data):.2f}")
