#!/usr/bin/env python3
"""
Multi-TF Filter: Weekly trend → Daily signals → 60min entry
"""
import json
from pathlib import Path

CACHE_W = Path('/root/.hermes/kline_cache_weekly')
CACHE_60M = Path('/root/.hermes/kline_cache_60min')

def get_weekly_trend(symbol):
    """Determine weekly trend: bullish (>MA20), bearish (<MA20), or neutral."""
    fname = symbol.replace('.','_') + '_weekly_100.json'
    fpath = CACHE_W / fname
    if not fpath.exists():
        return 'neutral'
    
    bars = json.loads(fpath.read_bytes())
    if len(bars) < 20:
        return 'neutral'
    
    closes = [b['c'] for b in bars[-20:]]  # Last 20 weeks
    ma20 = sum(closes) / len(closes)
    current = closes[-1]
    
    if current > ma20 * 1.02:  # 2% above MA20 = bullish
        return 'bullish'
    elif current < ma20 * 0.98:  # 2% below MA20 = bearish
        return 'bearish'
    return 'neutral'

def get_daily_entries_with_weekly_filter(symbol, daily_signals, ohlcv):
    """Filter daily entry signals by weekly trend."""
    trend = get_weekly_trend(symbol)
    
    # A-share: only long entries. Skip if weekly bearish.
    if trend == 'bearish':
        return [], trend
    
    # Filter to only FVG_Bull and OB_Bull
    entries = [s for s in daily_signals if s.type in ('FVG_Bull', 'OB_Bull')]
    entries.sort(key=lambda s: s.idx)
    
    # Apply trend alignment bonus
    for s in entries:
        s.trend_aligned = (trend == 'bullish')
        if trend == 'bullish':
            s.confidence = min(1.0, s.confidence + 0.1)
    
    return entries, trend

def refine_entry_60min(symbol, daily_entry_idx, entry_price, ohlcv_daily):
    """
    Use 60min data to find better entry price.
    For the entry day, find the lowest low in the first 4 hours.
    """
    fname = symbol.replace('.','_') + '_60min_200.json'
    fpath = CACHE_60M / fname
    if not fpath.exists():
        return entry_price  # No 60min data, use daily entry
    
    bars_60m = json.loads(fpath.read_bytes())
    if not bars_60m:
        return entry_price
    
    # Get the entry date from daily bar
    entry_date = str(ohlcv_daily[daily_entry_idx].get('date', ohlcv_daily[daily_entry_idx].get('t','')))[:8]
    
    # Find matching 60min bars for that date
    day_bars = [b for b in bars_60m if str(b['t'])[:8] == entry_date]
    if not day_bars or len(day_bars) < 2:
        return entry_price
    
    # Entry refinement: use the best price from the first few 60min bars
    first_bars = day_bars[:4]  # First 4 hours
    best_entry = min(b['l'] for b in first_bars)
    
    # Only use if it gives better entry (< daily entry_price)
    if best_entry < entry_price:
        return best_entry
    return entry_price

if __name__ == '__main__':
    # Test
    print("600519.SH weekly trend:", get_weekly_trend('600519.SH'))
    print("000001.SZ weekly trend:", get_weekly_trend('000001.SZ'))
