#!/usr/bin/env python3
# SMC V11 — 全量验证启动脚本
"""
V11全量验证流程:
  1. 确保API限流器就绪
  2. 读取全量股票/ETF/指数/板块列表
  3. 批量获取数据(限流保护)
  4. 自适应参数回测
  5. 记录结果到JSON/报告
  6. 可选: 对表现差的股票做参数优化
  7. 输出汇总报告

使用:
  python3 run_v11_full.py                    # 默认: 全A股回测
  python3 run_v11_full.py --limit 50         # 快速测试50只
  python3 run_v11_full.py --optimize         # 回测后优化
  python3 run_v11_full.py --symbol 600519.SH # 单股票测试
  python3 run_v11_full.py --all-universe     # 股票+ETF+指数+板块
"""

import json, sys, time, logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path.home() / '.hermes' / 'logs' / 'v11_full.log'),
    ]
)
logging.getLogger('smc_v11').setLevel(logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

log = logging.getLogger('v11.runner')

# Paths
OUTPUT_DIR = Path.home() / '.hermes' / 'smc_opt_v11'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def test_limiter():
    """测试限流器"""
    print("\n=== Testing Rate Limiter ===")
    from v11.rate_limiter import HubbleRateLimiter
    
    limiter = HubbleRateLimiter(max_rps=3, max_concurrent=3)
    print(f"  Bucket: capacity={limiter.bucket.capacity}, rate={limiter.bucket.rate}/s")
    print(f"  Concurrency: max={limiter.concurrency.max_concurrent}")
    print(f"  Cache: TTL={limiter.cache.ttl}s")
    
    # Quick fetch test
    data = limiter.fetch_kline('600519.SH', 'daily', 100)
    if data and len(data) > 20:
        print(f"  Fetch OK: {len(data)} bars for 600519.SH")
        last = data[-1]
        print(f"  Last: {last.get('date','?')} O={last['o']:.2f} "
              f"H={last['h']:.2f} L={last['l']:.2f} C={last['c']:.2f}")
    else:
        print(f"  Fetch: {data}")
    
    stats = limiter.get_stats()
    print(f"  Stats: {stats['total_requests']} req, "
          f"{stats['cache_hits']} cache hits, "
          f"{stats['429_count']} 429s")
    
    return limiter


def test_signals(symbol='600519.SH'):
    """测试信号检测引擎"""
    print(f"\n=== Testing V11 Signal Engine: {symbol} ===")
    
    from v11.tf_data import fetch_single_tf
    from v11.rate_limiter import get_limiter
    from v11.signals_v11 import detect_all_signals_v11
    from v11.adaptive_params import calc_stock_params, detect_market_phase
    
    limiter = get_limiter()
    ohlcv = fetch_single_tf(symbol, 'daily', 300, limiter=limiter)
    
    if not ohlcv or len(ohlcv) 