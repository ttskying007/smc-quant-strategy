#!/usr/bin/env python3
"""Load cached kline data with format normalization"""
import json, time
from pathlib import Path
from typing import Dict, List, Optional

CACHE_DIR = Path('/root/.hermes/kline_cache')

def load_cached_ohlcv(symbol: str, interval: str = 'daily', bars: int = 300) -> Optional[List[Dict]]:
    """Load & normalize cached OHLCV data — handles all cache formats"""
    safe = symbol.replace('.', '_')
    f = CACHE_DIR / f"{safe}_{interval}_{bars}.json"
    if not f.exists():
        return None
    try:
        raw = json.loads(f.read_text())
    except:
        return None
    if not raw or not isinstance(raw, list):
        return None
    # Normalize to {date, o, h, l, c, v}
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        # Get date
        date = entry.get('date') or entry.get('t') or ''
        if date:
            date = str(date)
        # Unpack all fields
        o = float(entry.get('open', entry.get('o', 0)))
        h = float(entry.get('high', entry.get('h', 0)))
        l = float(entry.get('low', entry.get('l', 0)))
        c = float(entry.get('close', entry.get('c', 0)))
        v = float(entry.get('volume', entry.get('vol', entry.get('v', 0))))
        out.append({'date': date, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    out.sort(key=lambda x: x['date'])
    return out if len(out) >= 20 else None


def get_backtest_universe() -> Dict[str, List[str]]:
    """Get symbols from cache files"""
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.') 
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    return {
        'a_stocks': symbols[:200],
        'all': symbols,
    }
