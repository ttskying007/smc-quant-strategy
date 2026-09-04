#!/usr/bin/env python3
# SMC V9 — Hubble API Client
"""
Hubble API client with retry, caching, and error handling.
Replaces hubble_api(), fetch_kline_cached(), kline_to_ohlcv(), calc_atr() from V84.
"""

import json, time, logging, urllib.request, urllib.error, urllib.parse
from pathlib import Path

from . import smc_config as config

log = logging.getLogger('smc_v9.hubble')

# ─── Hubble API ────────────────────────────────────────────────────


def hubble_api(endpoint, params=None, max_retries=3):
    """Call Hubble API with retry and proper error handling.
    
    Args:
        endpoint: API path (e.g. '/api/kline/600519.SH')
        params: Optional dict of query parameters
        max_retries: Number of retries on network failure (default: 3)
    
    Returns:
        Parsed JSON response dict, or {'error': msg} on failure
    """
    cfg = config.get_hubble_config()
    base = cfg['base']
    api_key = cfg['api_key']
    timeout = cfg['timeout']

    url = f"{base.rstrip('/')}/{endpoint.lstrip('/')}"
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{qs}"

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode()
                result = json.loads(body)
                return result

        except urllib.error.HTTPError as e:
            # HTTP errors are not retried (bad request, auth error, etc.)
            msg = f"HTTP {e.code}: {e.reason} for {url}"
            log.error(msg)
            return {"error": msg, "http_code": e.code}

        except urllib.error.URLError as e:
            # Network errors are retried
            last_error = f"Network error (attempt {attempt + 1}/{max_retries}): {e.reason}"
            log.warning(last_error)
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 1.5)  # 1.5s, 3s, 4.5s backoff
            continue

        except json.JSONDecodeError as e:
            msg = f"JSON decode error: {e} for {url}"
            log.error(msg)
            return {"error": msg}

        except Exception as e:
            msg = f"Unexpected error: {e}"
            log.error(msg)
            return {"error": msg}

    return {"error": last_error or f"Failed after {max_retries} retries"}


# ─── Kline data fetching with cache ────────────────────────────────


def _cache_dir():
    return Path(config.get_config()['paths']['cache_dir'])


def _cache_path(symbol, period, count):
    clean = symbol.replace('.', '_')
    return _cache_dir() / f"{clean}_{period}_{count}.json"


def _fetch_kline_from_hubble(symbol, period, count):
    """Fetch kline data from Hubble API (V2 endpoint).
    
    Hubble V2 API returns data in newest-first order with {time, open, high, low, close, volume}.
    The function normalises this to oldest-first order for signal detection.
    """
    # Map period to Hubble format
    period_map = {'daily': 'daily', 'weekly': 'weekly', '60min': '60min', '30min': '30min', '15min': '15min'}
    hb_period = period_map.get(period, 'daily')
    
    # Use V2 endpoint
    if symbol.endswith('.SH') or symbol.endswith('.SZ'):
        resp = hubble_api(f"/api/v2/cnstock/stocks", {'symbol': symbol, 'interval': hb_period})
    elif symbol.endswith('.HK'):
        resp = hubble_api(f"/api/v2/hkstock/stocks", {'symbol': symbol, 'interval': hb_period})
    else:
        resp = hubble_api(f"/api/v2/usstock/stocks", {'symbol': symbol, 'interval': hb_period})
    
    if isinstance(resp, dict) and resp.get('error'):
        log.error(f"Failed to fetch {symbol}: {resp['error']}")
        return []
    
    data = resp
    if isinstance(data, dict):
        data = data.get('data', data.get('klines', data.get('result', [])))
    
    if not isinstance(data, list) or len(data) == 0:
        log.warning(f"No data for {symbol} (period={hb_period})")
        return []
    
    # Hubble V2 returns newest-first → reverse to oldest-first for signal detection
    # Check if it's already oldest-first by comparing first/last timestamps
    try:
        if len(data) >= 2:
            t0 = _get_timestamp(data[0])
            t1 = _get_timestamp(data[-1])
            if t0 and t1 and t0 > t1:
                data = list(reversed(data))
                log.debug(f"Reversed {symbol} data (was newest-first)")
    except Exception:
        pass  # If timestamp parsing fails, keep as-is
    
    # Trim to requested count
    if len(data) > count:
        data = data[-count:]
    
    return data


def _get_timestamp(bar):
    """Extract timestamp from a bar dict (supports multiple formats)."""
    if isinstance(bar, dict):
        t = bar.get('time', bar.get('t', bar.get('timestamp', 0)))
        if isinstance(t, str):
            try:
                from datetime import datetime
                if len(t) == 8 and t.isdigit():
                    return datetime.strptime(t, '%Y%m%d').timestamp()
                return datetime.fromisoformat(t).timestamp()
            except:
                pass
        return float(t) if t else 0
    return bar[0] if bar else 0


def fetch_kline(symbol, period='daily', count=120):
    """Fetch kline data with multi-tier caching.
    
    Priority:
    1. Exact cache match
    2. Any existing cache file for this symbol+period (different count)
    3. Fresh fetch from Hubble API
    
    Returns: list of kline bars (dict or list format, per Hubble API)
    """
    cpath = _cache_path(symbol, period, count)
    cdir = _cache_dir()
    cdir.mkdir(parents=True, exist_ok=True)

    # 1. Exact cache match
    if cpath.exists():
        try:
            data = json.loads(cpath.read_text())
            if isinstance(data, list) and len(data) > 0:
                log.debug(f"Cache hit (exact): {symbol} {period} {count}")
                return data
        except Exception as e:
            log.warning(f"Cache read error (exact): {e}")

    # 2. Glob fallback — any cache for this symbol+period
    clean = symbol.replace('.', '_')
    for f in sorted(cdir.glob(f"{clean}_{period}_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            if isinstance(data, list) and len(data) > 0:
                log.debug(f"Cache hit (fallback): {f.name} for {symbol}")
                return data
        except Exception:
            continue

    # 3. Fresh fetch
    log.info(f"Fetching {symbol} {period} {count} from Hubble")
    data = _fetch_kline_from_hubble(symbol, period, count)
    if data and len(data) > 0:
        try:
            cpath.write_text(json.dumps(data, ensure_ascii=False))
            log.debug(f"Cached to {cpath.name} ({len(data)} bars)")
        except Exception as e:
            log.warning(f"Cache write error: {e}")
    else:
        log.warning(f"No data for {symbol} {period} {count}")

    return data


def kline_to_ohlcv(kline_data):
    """Normalise kline data to standard OHLCV format.
    
    Input: list of dicts with {open/high/low/close/volume, o/h/l/c/v, o/h/l/c/v/timestamp}
           or list of lists [timestamp, open, high, low, close, volume]
    Output: list of dicts with {o, h, l, c, v} (earliest to latest)
    """
    if not kline_data:
        return []

    ohlcv = []
    for bar in kline_data:
        if isinstance(bar, dict):
            o = float(bar.get('open', bar.get('o', 0)))
            h = float(bar.get('high', bar.get('h', 0)))
            l = float(bar.get('low', bar.get('l', 0)))
            c = float(bar.get('close', bar.get('c', 0)))
            v = float(bar.get('volume', bar.get('v', 0)))
        elif isinstance(bar, (list, tuple)):
            if len(bar) >= 5:
                # [timestamp, open, high, low, close, volume]
                o = float(bar[1]) if len(bar) > 1 else 0
                h = float(bar[2]) if len(bar) > 2 else 0
                l = float(bar[3]) if len(bar) > 3 else 0
                c = float(bar[4]) if len(bar) > 4 else 0
                v = float(bar[5]) if len(bar) > 5 else 0
            else:
                continue
        else:
            continue
        ohlcv.append({'o': o, 'h': h, 'l': l, 'c': c, 'v': v})

    return ohlcv


# ─── ATR ───────────────────────────────────────────────────────────


def calc_atr(ohlcv, period=14):
    """Calculate Average True Range.
    
    Args:
        ohlcv: list of {o, h, l, c, v} dicts (earliest to latest)
        period: ATR period (default: 14)
    
    Returns: ATR value (same price unit as input), or 0 if insufficient data
    """
    if len(ohlcv) < period + 1:
        return 0.0

    trs = []
    for i in range(1, len(ohlcv)):
        h = ohlcv[i]['h']
        l = ohlcv[i]['l']
        pc = ohlcv[i - 1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)

    if len(trs) < period:
        return 0.0

    return sum(trs[-period:]) / period


def calc_atr_pct(ohlcv, period=14):
    """Calculate ATR as percentage of current close price."""
    if not ohlcv:
        return 0.0
    atr = calc_atr(ohlcv, period)
    if atr == 0 or ohlcv[-1]['c'] == 0:
        return 0.0
    return atr / ohlcv[-1]['c'] * 100


# ─── Utility ────────────────────────────────────────────────────────


def normalize_kline_data(data):
    """Alias for kline_to_ohlcv — backward compatibility."""
    return kline_to_ohlcv(data)


def fetch_and_prepare(symbol, period='daily', count=120):
    """Fetch kline and convert to OHLCV in one call.
    
    Returns: (ohlcv_list, atr_pct, bar_count)
    """
    raw = fetch_kline(symbol, period, count)
    if not raw:
        return [], 0.0, 0
    ohlcv = kline_to_ohlcv(raw)
    atr_pct = calc_atr_pct(ohlcv)
    return ohlcv, atr_pct, len(ohlcv)


# ─── Quick test ────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else '600519.SH'
    ohlcv, atr_pct, n = fetch_and_prepare(symbol)
    print(f"{symbol}: {n} bars, ATR={atr_pct:.2f}%")
    print(f"Last bar: o={ohlcv[-1]['o']:.2f} h={ohlcv[-1]['h']:.2f} l={ohlcv[-1]['l']:.2f} c={ohlcv[-1]['c']:.2f}")