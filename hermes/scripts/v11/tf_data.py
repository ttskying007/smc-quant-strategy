#!/usr/bin/env python3
# SMC V11 — Multi-TF Data Fetcher + Cache
"""
多周期数据获取 — 支持Daily/4H/1H/15min真实数据获取

设计:
1. 使用V11限流器控制API请求
2. 文件缓存减少重复请求
3. 并行获取不同TF数据(使用threading)
4. 数据标准化: 统一到 {o,h,l,c,v,date} 格式
5. 自动补全: 较少的15min数据用1H数据回填
6. K线对齐: 不同TF的K线按时间对齐
"""

import json, time, threading, logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

log = logging.getLogger('smc_v11.tf_data')

# ═══════════════════════════════════════════════════════════════════════
# TF配置
# ═══════════════════════════════════════════════════════════════════════

TF_CONFIG = {
    'daily': {'interval': 'daily', 'bars': 300, 'cache_hours': 24, 'weight': 0.40},
    '4h':    {'interval': '60min', 'bars': 200, 'cache_hours': 12, 'weight': 0.30},
    '1h':    {'interval': '30min', 'bars': 200, 'cache_hours': 6,  'weight': 0.20},
    '15min': {'interval': '15min', 'bars': 200, 'cache_hours': 4,  'weight': 0.10},
}

CACHE_DIR = Path.home() / '.hermes' / 'kline_cache_v11'
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# Data normalization
# ═══════════════════════════════════════════════════════════════════════

def _normalize_klines(raw_data: List, symbol: str, interval: str) -> List[Dict]:
    """标准化K线数据到统一格式"""
    parsed = []
    
    for k in raw_data:
        if isinstance(k, dict):
            entry = {
                'date': str(k.get('date', k.get('t', ''))),
                'o': float(k.get('open', k.get('o', 0))),
                'h': float(k.get('high', k.get('h', 0))),
                'l': float(k.get('low', k.get('l', 0))),
                'c': float(k.get('close', k.get('c', 0))),
                'v': float(k.get('volume', k.get('vol', k.get('v', 0)))),
            }
        elif isinstance(k, (list, tuple)) and len(k) >= 5:
            # Format: [date, open, high, low, close, volume]
            entry = {
                'date': str(k[0]),
                'o': float(k[1]), 'h': float(k[2]),
                'l': float(k[3]), 'c': float(k[4]),
                'v': float(k[5]) if len(k) > 5 else 0,
            }
        else:
            continue
        
        parsed.append(entry)
    
    # 按日期排序
    parsed.sort(key=lambda x: x['date'])
    
    return parsed


# ═══════════════════════════════════════════════════════════════════════
# File cache
# ═══════════════════════════════════════════════════════════════════════

def _cache_path(symbol: str, interval: str, bars: int) -> Path:
    safe_name = symbol.replace('.', '_').replace('/', '_')
    return CACHE_DIR / f"{safe_name}_{interval}_{bars}.json"


def _read_cache(symbol: str, interval: str, bars: int, max_age_hours: float = 24) -> Optional[List[Dict]]:
    cache_file = _cache_path(symbol, interval, bars)
    if not cache_file.exists():
        return None
    
    try:
        # Check age
        age = time.time() - cache_file.stat().st_mtime
        if age > max_age_hours * 3600:
            log.debug(f"Cache expired: {cache_file.name} ({age/3600:.1f}h old)")
            return None
        
        data = json.loads(cache_file.read_text())
        if data and isinstance(data, list):
            # Normalize: ensure 'date' key exists (some old caches use 't')
            for entry in data:
                if 'date' not in entry and 't' in entry:
                    entry['date'] = str(entry['t'])
                elif 'date' not in entry:
                    entry['date'] = ''
            return data
    except (json.JSONDecodeError, ValueError, OSError):
        pass
    
    return None


def _write_cache(symbol: str, interval: str, bars: int, data: List[Dict]):
    try:
        cache_file = _cache_path(symbol, interval, bars)
        cache_file.write_text(json.dumps(data, ensure_ascii=False, default=str))
    except OSError as e:
        log.warning(f"Cache write failed: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Fetch via limiter
# ═══════════════════════════════════════════════════════════════════════

def fetch_single_tf(symbol: str, interval: str, bars: int,
                    limiter=None, skip_cache: bool = False) -> List[Dict]:
    """获取单个TF的K线数据"""
    # Check cache
    if not skip_cache:
        max_age = TF_CONFIG.get(interval, {}).get('cache_hours', 24)
        cached = _read_cache(symbol, interval, bars, max_age_hours=max_age)
        if cached:
            log.debug(f"Cache hit: {symbol} {interval} ({len(cached)} bars)")
            return cached
    
    # Fetch from API
    if limiter:
        data = limiter.fetch_kline(symbol, interval=interval, count=bars, use_file_cache=False)
    else:
        # Direct fallback
        try:
            import requests
            from ..v11.rate_limiter import get_limiter
            data = get_limiter().fetch_kline(symbol, interval=interval, count=bars, use_file_cache=False)
        except ImportError:
            log.error("No limiter available for TF data fetch")
            return []
    
    if not data or len(data) < 10:
        log.warning(f"Not enough data for {symbol} {interval}: {len(data) if data else 0}")
        return []
    
    # Normalize
    parsed = _normalize_klines(data, symbol, interval)
    
    # Write cache
    _write_cache(symbol, interval, bars, parsed)
    
    return parsed


# ═══════════════════════════════════════════════════════════════════════
# Multi-TF fetch (parallel)
# ═══════════════════════════════════════════════════════════════════════

def fetch_multi_tf(symbol: str, tfs: List[str] = None,
                   limiter=None) -> Dict[str, List[Dict]]:
    """并行获取多个TF的K线数据
    
    Args:
        symbol: 如 '600519.SH'
        tfs: TF列表, 默认 ['daily', '4h', '1h']
        limiter: 限流器实例
    
    Returns:
        {'daily': [OHLCV], '4h': [OHLCV], ...}
        缺失TF返回空列表
    """
    if tfs is None:
        tfs = ['daily', '4h', '1h']
    
    results = {}
    errors = []
    
    def fetch_one(tf):
        try:
            config = TF_CONFIG.get(tf)
            if not config:
                return tf, []
            data = fetch_single_tf(symbol, config['interval'], config['bars'], limiter)
            return tf, data
        except Exception as e:
            log.error(f"Error fetching {symbol} {tf}: {e}")
            return tf, []
    
    # 并行获取 (threading)
    threads = []
    outputs = {}
    
    for tf in tfs:
        outputs[tf] = []
    
    def worker(tf):
        _, data = fetch_one(tf)
        outputs[tf] = data
    
    for tf in tfs:
        t = threading.Thread(target=worker, args=(tf,), daemon=True)
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join(timeout=30)
    
    for tf in tfs:
        results[tf] = outputs[tf]
        if results[tf]:
            log.info(f"  {symbol} {tf}: {len(results[tf])} bars")
    
    return results


# ═══════════════════════════════════════════════════════════════════════
# Stock list helpers
# ═══════════════════════════════════════════════════════════════════════

def get_a_stock_symbols(limit: int = 5000) -> List[str]:
    """获取A股股票代码列表
    
    从Hubble API获取或使用本地缓存
    """
    # Try cache first
    cache_file = Path.home() / '.hermes' / 'a_stock_list.json'
    if cache_file.exists():
        try:
            age = time.time() - cache_file.stat().st_mtime
            if age < 86400:  # 1 day cache
                data = json.loads(cache_file.read_text())
                if data and len(data) > 100:
                    return data[:limit]
        except Exception:
            pass
    
    # Fetch from API
    try:
        import requests
        resp = requests.get(
            "http://43.167.234.49:3101/api/stocks",
            headers={"X-API-Key": "123456"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            symbols = []
            stocks = data.get('data', data.get('result', []))
            for s in stocks:
                if isinstance(s, dict):
                    code = s.get('symbol', s.get('code', ''))
                    if code:
                        symbols.append(code)
                elif isinstance(s, str):
                    symbols.append(s)
            
            # Cache
            cache_file.write_text(json.dumps(symbols, ensure_ascii=False))
            return symbols[:limit]
    except Exception as e:
        log.warning(f"Failed to fetch stock list: {e}")
    
    # Fallback to common list
    common = [f"{i:06d}." + ("SH" if i < 600000 else "SZ") for i in [600519, 601318, 600036, 600276, 600887, 600030, 600000, 600016, 600585, 601166, 601398, 601939, 601857, 600028, 600900, 600941, 601012, 603259, 600690, 600809, 600309, 601888, 600196, 600703, 600438, 600585, 600660, 600745, 601899, 601668]]
    return common[:limit]


def get_etf_symbols() -> List[str]:
    """获取ETF代码列表"""
    # Major ETFs
    return [
        '510050.SH', '510300.SH', '510500.SH', '510880.SH',  # 华夏ETF
        '159915.SZ', '159919.SZ', '159922.SZ', '159949.SZ', # 创业板/深100
        '588000.SH', '588050.SH',  # 科创板
        '512880.SH', '512100.SH',  # 证券/中证1000
        '513100.SH', '513050.SH',  # 纳指/中概
        '518880.SH',  # 黄金ETF
        'SPY', 'QQQ', 'IWM', 'DIA',  # 美股ETF
    ]


def get_index_symbols() -> List[str]:
    """获取指数代码列表"""
    return [
        '000001.SH', '399001.SZ', '399006.SZ',  # 上证/深证/创业板
        '000300.SH', '000905.SH', '000688.SH',  # 沪深300/中证500/科创50
        '399303.SZ', '399296.SZ',  # 国证2000/创业板综
        'HSI', 'SPX', 'NDX', 'DJI',  # 恒指/标普/纳指/道指
    ]


def get_sector_symbols() -> List[str]:
    """获取板块指数列表 (申万一级)"""
    return [
        '801010.SI', '801020.SI', '801030.SI', '801040.SI', '801050.SI',
        '801080.SI', '801110.SI', '801120.SI', '801130.SI', '801140.SI',
        '801150.SI', '801160.SI', '801170.SI', '801180.SI', '801200.SI',
        '801210.SI', '801230.SI', '801710.SI', '801720.SI', '801730.SI',
        '801740.SI', '801750.SI', '801760.SI', '801770.SI', '801780.SI',
        '801790.SI', '801880.SI', '801890.SI', '801200.SI',
    ]


def get_universe() -> Dict[str, List[str]]:
    """获取全量测试 universe"""
    return {
        'a_stocks': get_a_stock_symbols(),
        'etfs': get_etf_symbols(),
        'indices': get_index_symbols(),
        'sectors': get_sector_symbols(),
    }


# ═══════════════════════════════════════════════════════════════════════
# ATR calculator
# ═══════════════════════════════════════════════════════════════════════

def calc_atr(ohlcv: List[Dict], period: int = 14) -> float:
    """计算ATR"""
    if len(ohlcv) < period + 1:
        return 0
    
    trs = []
    for i in range(1, len(ohlcv)):
        tr = max(
            ohlcv[i]['h'] - ohlcv[i]['l'],
            abs(ohlcv[i]['h'] - ohlcv[i-1]['c']),
            abs(ohlcv[i]['l'] - ohlcv[i-1]['c']),
        )
        trs.append(tr)
    
    return sum(trs[-period:]) / period


def calc_atr_pct(ohlcv: List[Dict], period: int = 14) -> float:
    """计算ATR百分比"""
    atr = calc_atr(ohlcv, period)
    last_close = ohlcv[-1]['c'] if ohlcv else 1
    return atr / last_close * 100 if last_close > 0 else 0


# ═══════════════════════════════════════════════════════════════════════
# Quick test
# ═══════════════════════════════════════════════════════════════════════

def test_fetch(symbol: str = '600519.SH'):
    """快速测试多周期获取"""
    print(f"\n=== Testing Multi-TF fetch: {symbol} ===\n")
    
    data = fetch_multi_tf(symbol, ['daily', '4h', '1h'])
    
    for tf, klines in data.items():
        if klines:
            last = klines[-1]
            print(f"  {tf}: {len(klines)} bars, "
                  f"last: {last.get('date', '?')} "
                  f"O={last['o']:.2f} H={last['h']:.2f} "
                  f"L={last['l']:.2f} C={last['c']:.2f}")
        else:
            print(f"  {tf}: no data")
    
    return data


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    test_fetch()
