#!/usr/bin/env python3
# SMC V11 — API Rate Limiter
"""
核心功能: 防止HTTP 429 Too Many Requests

设计:
1. 令牌桶算法 — 控制请求速率 (默认3 req/s, 可配置)
2. 并发控制 — 限制同时进行的API请求数 (默认3)
3. 429自动退避 — 遇到429自动指数退避重试
4. 请求缓存 — 同一参数请求在TTL内返回缓存
5. 批量节流 — 批量请求自动分批+间隔
6. 统计监控 — 请求计数/429次数/缓存命中率

使用:
    from v11.rate_limiter import HubbleRateLimiter
    
    limiter = HubbleRateLimiter(max_rps=3, max_concurrent=3)
    data = limiter.fetch_kline('600519.SH', 'daily', 300)
    
    # 批量
    results = limiter.batch_fetch([('600519.SH', 'daily', 300), ...])
"""

import time, json, hashlib, threading, logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from functools import wraps
from collections import defaultdict

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

log = logging.getLogger('smc_v11.rate_limiter')

# ═══════════════════════════════════════════════════════════════════════
# Token Bucket
# ═══════════════════════════════════════════════════════════════════════

class TokenBucket:
    """令牌桶限流器 — 平滑控制请求速率"""
    
    def __init__(self, rate: float, capacity: int):
        """
        Args:
            rate: 令牌填充速率 (tokens/second)
            capacity: 桶容量 (最大突发量)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """尝试消费令牌, 阻塞等待直到有令牌或超时"""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                # 填充令牌
                elapsed = now - self.last_refill
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_refill = now
                
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
            
            if time.monotonic() > deadline:
                return False
            
            # 等待一小段时间再重试
            wait = max(0.01, (tokens - self.tokens) / self.rate)
            time.sleep(min(wait, 0.5))
    
    @property
    def available(self) -> float:
        """当前可用令牌数"""
        now = time.monotonic()
        elapsed = now - self.last_refill
        return min(self.capacity, self.tokens + elapsed * self.rate)


class ConcurrencyGuard:
    """并发控制 — 限制同时进行的请求数"""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self._semaphore = threading.Semaphore(max_concurrent)
        self._active = 0
        self._lock = threading.Lock()
    
    @property
    def active(self) -> int:
        return self._active
    
    def acquire(self, timeout: float = 60.0) -> bool:
        return self._semaphore.acquire(timeout=timeout)
    
    def release(self):
        self._semaphore.release()


class RequestCache:
    """请求缓存 — 同参数请求TTL内返回缓存"""
    
    def __init__(self, ttl: float = 3600, max_size: int = 5000):
        self.ttl = ttl
        self.max_size = max_size
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
    
    def _key(self, url: str, params: Dict = None) -> str:
        raw = f"{url}|{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.md5(raw.encode()).hexdigest()
    
    def get(self, url: str, params: Dict = None) -> Optional[Any]:
        key = self._key(url, params)
        with self._lock:
            if key in self._cache:
                ts, data = self._cache[key]
                if time.monotonic() - ts < self.ttl:
                    self.hits += 1
                    return data
                else:
                    del self._cache[key]
            self.misses += 1
            return None
    
    def put(self, url: str, params: Dict, data: Any):
        key = self._key(url, params)
        with self._lock:
            # 清理过期
            if len(self._cache) > self.max_size:
                now = time.monotonic()
                expired = [k for k, (ts, _) in self._cache.items() if now - ts > self.ttl]
                for k in expired:
                    del self._cache[k]
                # 如果还是太大, 淘汰最旧的
                if len(self._cache) > self.max_size * 0.8:
                    sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])
                    for k in sorted_keys[:len(self._cache) - self.max_size // 2]:
                        del self._cache[k]
            self._cache[key] = (time.monotonic(), data)
    
    @property
    def size(self) -> int:
        return len(self._cache)
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════
# HubbleRateLimiter — 主入口
# ═══════════════════════════════════════════════════════════════════════

class HubbleRateLimiter:
    """Hubble API限流器 — 防止429的核心组件
    
    配置:
        max_rps: 最大请求/秒 (默认3, 免费接口保守值)
        max_concurrent: 最大并发数 (默认3)
        cache_ttl: 缓存TTL秒 (默认3600, 1小时)
        max_retries: 429最大重试次数 (默认5)
        base_backoff: 退避基础秒数 (默认2)
    """
    
    API_BASE = "http://43.167.234.49:3101"
    API_KEY = "123456"
    
    def __init__(
        self,
        max_rps: float = 3.0,
        max_concurrent: int = 3,
        cache_ttl: float = 3600,
        max_retries: int = 5,
        base_backoff: float = 2.0,
    ):
        self.bucket = TokenBucket(rate=max_rps, capacity=int(max_rps * 2))
        self.concurrency = ConcurrencyGuard(max_concurrent)
        self.cache = RequestCache(ttl=cache_ttl)
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        
        # 统计
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            '429_count': 0,
            '5xx_count': 0,
            'timeout_count': 0,
            'success_count': 0,
            'total_wait_time': 0.0,
        }
        self._stats_lock = threading.Lock()
        
        # 文件缓存
        self._file_cache_dir = Path.home() / '.hermes' / 'kline_cache'
        self._file_cache_dir.mkdir(parents=True, exist_ok=True)
        
        log.info(f"RateLimiter init: rps={max_rps}, concurrent={max_concurrent}, "
                 f"cache_ttl={cache_ttl}s")
    
    def _api_url(self, endpoint: str) -> str:
        return f"{self.API_BASE}{endpoint}"
    
    def _headers(self) -> Dict:
        return {"X-API-Key": self.API_KEY, "Content-Type": "application/json"}
    
    def _request(self, method: str, endpoint: str, params: Dict = None,
                 timeout: float = 15.0) -> Optional[Any]:
        """执行一个限流+退避的API请求"""
        url = self._api_url(endpoint)
        
        # 检查内存缓存
        cached = self.cache.get(url, params)
        if cached is not None:
            with self._stats_lock:
                self.stats['cache_hits'] += 1
            return cached
        
        # 获取令牌(限流)
        wait_start = time.monotonic()
        if not self.bucket.consume(1, timeout=30):
            log.warning(f"Rate limiter timeout waiting for token: {url}")
            with self._stats_lock:
                self.stats['timeout_count'] += 1
            return None
        
        # 获取并发槽
        if not self.concurrency.acquire(timeout=60):
            log.warning(f"Concurrency limit reached: {url}")
            with self._stats_lock:
                self.stats['timeout_count'] += 1
            return None
        
        try:
            with self._stats_lock:
                self.stats['total_requests'] += 1
            
            # 429退避重试
            for attempt in range(self.max_retries):
                try:
                    if not HAS_REQUESTS:
                        log.error("requests library not installed")
                        return None
                    
                    resp = requests.request(
                        method, url, headers=self._headers(),
                        params=params, timeout=timeout
                    )
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        self.cache.put(url, params, data)
                        with self._stats_lock:
                            self.stats['success_count'] += 1
                            self.stats['total_wait_time'] += time.monotonic() - wait_start
                        return data
                    
                    elif resp.status_code == 429:
                        # 429 Too Many Requests — 指数退避
                        with self._stats_lock:
                            self.stats['429_count'] += 1
                        
                        # 从响应头获取Retry-After, 否则指数退避
                        retry_after = resp.headers.get('Retry-After')
                        if retry_after:
                            wait = float(retry_after)
                        else:
                            wait = self.base_backoff * (2 ** attempt) + random.uniform(0, 1)
                        
                        log.warning(f"HTTP 429 received, backing off {wait:.1f}s "
                                    f"(attempt {attempt+1}/{self.max_retries})")
                        time.sleep(wait)
                        
                        # 429后重新获取令牌(降速)
                        self.bucket.consume(1, timeout=60)
                        continue
                    
                    elif 500 <= resp.status_code < 600:
                        with self._stats_lock:
                            self.stats['5xx_count'] += 1
                        log.error(f"Server error {resp.status_code}: {url}")
                        time.sleep(self.base_backoff * (attempt + 1))
                        continue
                    
                    else:
                        log.error(f"HTTP {resp.status_code}: {resp.text[:200]}")
                        return None
                
                except requests.exceptions.Timeout:
                    with self._stats_lock:
                        self.stats['timeout_count'] += 1
                    log.warning(f"Request timeout (attempt {attempt+1}): {url}")
                    continue
                
                except requests.exceptions.ConnectionError:
                    log.warning(f"Connection error (attempt {attempt+1}): {url}")
                    time.sleep(self.base_backoff * (attempt + 1))
                    continue
            
            log.error(f"All retries exhausted: {url}")
            return None
        
        finally:
            self.concurrency.release()
    
    # ═══════════════════════════════════════════════════════════════════
    # High-level API
    # ═══════════════════════════════════════════════════════════════════
    
    def fetch_kline(self, symbol: str, interval: str = 'daily',
                    count: int = 300, use_file_cache: bool = True) -> List[Dict]:
        """获取K线数据(限流+缓存)
        
        Args:
            symbol: 如 '600519.SH'
            interval: 'daily', '60min', '30min', '15min', '5min'
            count: K线数量
            use_file_cache: 是否使用文件缓存
        
        Returns:
            [{o,h,l,c,v,date}, ...] 或空列表
        """
        # 文件缓存检查
        if use_file_cache:
            cache_file = self._file_cache_dir / f"{symbol.replace('.','_')}_{interval}_{count}.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text())
                    # 检查数据是否当天(日线缓存有效期1天)
                    if data and isinstance(data, list) and len(data) > 0:
                        last_date = data[-1].get('date', data[-1].get('t', ''))
                        if last_date and last_date >= time.strftime('%Y-%m-%d', time.localtime(time.time() - 86400)):
                            return data
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
        
        # API请求
        endpoint = f"/api/v2/kline/{symbol}"
        params = {"period": interval, "count": str(count)}
        result = self._request("GET", endpoint, params=params)
        
        if result and isinstance(result, dict):
            # 解析Hubble API格式
            klines = result.get('data', result.get('result', []))
            if isinstance(klines, list) and len(klines) > 0:
                # 标准化格式
                parsed = []
                for k in klines:
                    if isinstance(k, dict):
                        parsed.append({
                            'date': k.get('date', k.get('t', '')),
                            'o': float(k.get('open', k.get('o', 0))),
                            'h': float(k.get('high', k.get('h', 0))),
                            'l': float(k.get('low', k.get('l', 0))),
                            'c': float(k.get('close', k.get('c', 0))),
                            'v': float(k.get('volume', k.get('v', 0))),
                        })
                    elif isinstance(k, (list, tuple)) and len(k) >= 6:
                        parsed.append({
                            'date': str(k[0]),
                            'o': float(k[1]), 'h': float(k[2]),
                            'l': float(k[3]), 'c': float(k[4]),
                            'v': float(k[5]),
                        })
                
                # 写入文件缓存
                if use_file_cache and parsed:
                    try:
                        cache_file = self._file_cache_dir / f"{symbol.replace('.','_')}_{interval}_{count}.json"
                        cache_file.write_text(json.dumps(parsed, ensure_ascii=False))
                    except Exception as e:
                        log.warning(f"File cache write failed: {e}")
                
                return parsed
        
        return []
    
    def batch_fetch(self, requests_list: List[Tuple[str, str, int]],
                    batch_size: int = 5, batch_delay: float = 1.0,
                    progress_cb=None) -> Dict[str, List[Dict]]:
        """批量获取K线数据(自动分批+节流)
        
        Args:
            requests_list: [(symbol, interval, count), ...]
            batch_size: 每批数量
            batch_delay: 批次间延迟(秒)
            progress_cb: 进度回调 fn(done, total, symbol)
        
        Returns:
            {symbol: [ohlcv, ...]}
        """
        import random
        results = {}
        total = len(requests_list)
        
        for i in range(0, total, batch_size):
            batch = requests_list[i:i+batch_size]
            
            for symbol, interval, count in batch:
                data = self.fetch_kline(symbol, interval, count)
                results[symbol] = data
                
                if progress_cb:
                    progress_cb(len(results), total, symbol)
            
            # 批次间延迟 — 防止429
            if i + batch_size < total:
                # 加点随机抖动, 避免请求过于均匀被识别为机器人
                jitter = random.uniform(0, 0.5)
                time.sleep(batch_delay + jitter)
            
            # 每20个请求额外长休息
            if (i // batch_size) % 4 == 3:
                long_pause = batch_delay * 3 + random.uniform(0, 2)
                log.info(f"Batch pause: {long_pause:.1f}s after {len(results)} requests")
                time.sleep(long_pause)
        
        return results
    
    def get_stats(self) -> Dict:
        """获取限流统计"""
        with self._stats_lock:
            stats = dict(self.stats)
        stats['cache_hit_rate'] = self.cache.hit_rate
        stats['cache_size'] = self.cache.size
        stats['tokens_available'] = self.bucket.available
        stats['concurrent_active'] = self.concurrency.active
        return stats
    
    def reset_stats(self):
        """重置统计"""
        with self._stats_lock:
            for k in self.stats:
                self.stats[k] = 0 if isinstance(self.stats[k], int) else 0.0
        self.cache.hits = 0
        self.cache.misses = 0


# ═══════════════════════════════════════════════════════════════════════
# Singleton for global use
# ═══════════════════════════════════════════════════════════════════════

_global_limiter: Optional[HubbleRateLimiter] = None
_limiter_lock = threading.Lock()

def get_limiter(max_rps: float = 3.0, max_concurrent: int = 3) -> HubbleRateLimiter:
    """获取全局限流器单例"""
    global _global_limiter
    with _limiter_lock:
        if _global_limiter is None:
            _global_limiter = HubbleRateLimiter(max_rps=max_rps, max_concurrent=max_concurrent)
        return _global_limiter
