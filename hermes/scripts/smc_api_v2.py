#!/usr/bin/env python3
"""
SMC V8.5 FastAPI Backend — Unified Signal Engine + WebSocket + Hot-Reload
===========================================================================
Port: 8880

Architecture:
  - Imports SMC engine DIRECTLY from smc_engine_v84.py (single source of truth)
  - FastAPI + Uvicorn (async, high performance)
  - WebSocket push for live status updates
  - File watcher for hot-reload frontend
  - Hubble proxy cache for kline data
  - Proxy Guardian integration

Run:
  python3 smc_api_v2.py               # Port 8880
  python3 smc_api_v2.py --port 8881   # Custom port
"""
import sys, os, json, time, math, asyncio, logging, glob, signal, subprocess
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

# ── FastAPI ──
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── Paths ──
HOME = Path.home()
V83_DIR = HOME / '.hermes' / 'smc_opt_v83'
V2_DIR = HOME / '.hermes' / 'smc_web_v2'
CACHE_DIR = HOME / '.hermes' / 'kline_cache'
LOGS_DIR = HOME / '.hermes' / 'logs'

for d in [V83_DIR, V2_DIR, CACHE_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ── Import V8.4 Engine (single source of truth) ──
sys.path.insert(0, str(HOME / '.hermes' / 'scripts'))
try:
    from smc_engine_v84 import (
        evaluate_params, evaluate_trades, detect_all_signals,
        v84_score, kline_to_ohlcv, calc_atr, fetch_kline_cached,
        V84_PARAM_SPACE, TEST_STOCKS
    )
    ENGINE_OK = True
    print(f"✓ Engine loaded: smc_engine_v84 (14 params, {len(TEST_STOCKS)} stocks)")
except Exception as e:
    ENGINE_OK = False
    print(f"✗ Engine load failed: {e} — using fallback mode")

# ── Global State ──
frontend_cache = {"html": None, "mtime": 0}
frontend_lock = asyncio.Lock()
ws_clients = set()

# ── Proxy state cache ──
last_proxy_check = 0
last_proxy_status = {}

# ════════════════════════════════════════════
# Hubble API (standalone, no proxy needed)
# ════════════════════════════════════════════

def safe_read_json(path):
    try:
        if path and Path(path).exists():
            return json.loads(Path(path).read_text())
    except: pass
    return {}

def fetch_hubble(endpoint, timeout=10):
    import urllib.request
    url = f"{HUBBLE_BASE}/{endpoint.lstrip('/')}"
    try:
        req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'error': str(e), 'url': url}

def get_cached_kline(symbol, period='daily', count=120):
    """Get kline data with Hubble → file cache fallback"""
    fname = f"{symbol.replace('.', '_')}_{period}_{count}.json"
    cache_path = CACHE_DIR / fname
    # Try cache
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text())
            if data: return normalize_kline_data(data)
        except: pass
    # Glob fallback (different count)
    fallback = sorted(CACHE_DIR.glob(f"{symbol.replace('.', '_')}_{period}_*.json"))
    if fallback:
        try:
            data = json.loads(fallback[-1].read_text())
            return normalize_kline_data(data)
        except: pass
    # Fetch from Hubble
    resp = fetch_hubble(f"/api/kline/{symbol}?period={period}&count={count}")
    if resp and not resp.get('error'):
        data = resp.get('data', resp.get('klines', resp.get('result', resp)))
        if data:
            cache_path.write_text(json.dumps(data, ensure_ascii=False))
            return normalize_kline_data(data)
    return {'error': 'no data', 'symbol': symbol}

def normalize_kline_data(data):
    """Normalize to [{open, high, low, close, volume, timestamp}]"""
    if isinstance(data, dict) and 'error' in data: return data
    if isinstance(data, dict) and 'klines' in data: data = data['klines']
    if isinstance(data, dict) and 'data' in data: data = data['data']
    if isinstance(data, dict) and 'result' in data: data = data['result']
    if not isinstance(data, list) or len(data) == 0: return {'error': 'empty data'}
    if isinstance(data[0], dict):
        keys = list(data[0].keys())
        if 'o' in keys or 'open' in keys:
            result = []
            for k in data:
                result.append({
                    'open': k.get('open', k.get('o', 0)),
                    'high': k.get('high', k.get('h', 0)),
                    'low': k.get('low', k.get('l', 0)),
                    'close': k.get('close', k.get('c', 0)),
                    'volume': k.get('volume', k.get('vol', k.get('v', 0))),
                    'timestamp': k.get('timestamp', k.get('time', k.get('t', 0))),
                })
            return result
        if 'open' in keys: return [{**k} for k in data]
    return {'error': f'unknown kline format'}

def klines_to_echarts(klines):
    """Convert kline data to ECharts format with MA"""
    result = []
    for k in klines:
        ts = k.get('timestamp', k.get('time', 0))
        if isinstance(ts, str):
            try:
                from datetime import datetime as dt
                ts = int(dt.strptime(str(ts)[:10], '%Y-%m-%d').timestamp())
            except: ts = 0
        elif isinstance(ts, (int, float)) and ts > 1e12: ts = int(ts / 1000)
        else: ts = int(ts)
        result.append({
            'date': datetime.fromtimestamp(ts).strftime('%Y-%m-%d') if ts > 1000000000 else str(ts),
            'open': float(k['open']), 'high': float(k['high']),
            'low': float(k['low']), 'close': float(k['close']),
            'volume': float(k.get('volume', 0)),
            'ma5': 0, 'ma10': 0, 'ma20': 0, 'ma60': 0,
        })
    closes = [r['close'] for r in result]
    for i, r in enumerate(result):
        if i >= 4: r['ma5'] = round(sum(closes[i-4:i+1])/5, 2)
        if i >= 9: r['ma10'] = round(sum(closes[i-9:i+1])/10, 2)
        if i >= 19: r['ma20'] = round(sum(closes[i-19:i+1])/20, 2)
        if i >= 59: r['ma60'] = round(sum(closes[i-59:i+1])/60, 2)
    return result

# ════════════════════════════════════════════
# Proxy Guardian Status
# ════════════════════════════════════════════

def get_proxy_status():
    global last_proxy_check, last_proxy_status
    now = time.time()
    if now - last_proxy_check < 3:
        return last_proxy_status
    last_proxy_check = now
    # Read from proxy_status.json (shared by guardian)
    status = safe_read_json(V2_DIR / 'proxy_status.json')
    if not status:
        status = safe_read_json(V83_DIR / 'proxy_status.json')
    if not status:
        # Quick live check
        import urllib.request
        try:
            req = urllib.request.Request('http://127.0.0.1:9090')
            with urllib.request.urlopen(req, timeout=2) as r:
                status['process_ok'] = True
        except:
            pass
        # Check process
        try:
            r = subprocess.run(['pgrep', '-f', 'mihomo'], capture_output=True, text=True, timeout=3)
            if r.stdout.strip():
                status['pid'] = int(r.stdout.strip().split('\n')[0])
                status['process_ok'] = True
        except:
            pass
    # Fallback fields
    if not status.get('port_ok'):
        # Check port 7890
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(1)
            s.connect(('127.0.0.1', 7890))
            status['port_ok'] = True
        except:
            status['port_ok'] = False
        finally:
            s.close()
    if not status.get('internet_ok'):
        # Check HTTP via proxy
        try:
            import urllib.request
            proxy = urllib.request.ProxyHandler({'http': '127.0.0.1:7890', 'https': '127.0.0.1:7890'})
            opener = urllib.request.build_opener(proxy)
            req = urllib.request.Request('http://www.gstatic.com/generate_204')
            with opener.open(req, timeout=3) as r:
                status['internet_ok'] = r.status == 204 or r.status == 200
        except:
            status['internet_ok'] = status.get('internet_ok', False)
    last_proxy_status = status
    return status

def get_proxy_logs(lines=40):
    log_path = LOGS_DIR / 'proxy_guardian_v8.log'
    if not log_path.exists():
        log_path = LOGS_DIR / 'proxy_guardian_v7.log'
    if not log_path.exists():
        return []
    try:
        text = log_path.read_text().strip().split('\n')
        return text[-lines:]
    except:
        return []

# ════════════════════════════════════════════
# Stock List
# ════════════════════════════════════════════

STOCKS = [
    {'code': '600519', 'market': 'SH', 'name': '贵州茅台'},
    {'code': '000858', 'market': 'SZ', 'name': '五粮液'},
    {'code': '300750', 'market': 'SZ', 'name': '宁德时代'},
    {'code': '601318', 'market': 'SH', 'name': '中国平安'},
    {'code': '002415', 'market': 'SZ', 'name': '海康威视'},
    {'code': '002594', 'market': 'SZ', 'name': '比亚迪'},
    {'code': '600036', 'market': 'SH', 'name': '招商银行'},
    {'code': '688981', 'market': 'SH', 'name': '中芯国际'},
    {'code': '300059', 'market': 'SZ', 'name': '东方财富'},
    {'code': '600030', 'market': 'SH', 'name': '中信证券'},
    {'code': '002230', 'market': 'SZ', 'name': '科大讯飞'},
    {'code': '000333', 'market': 'SZ', 'name': '美的集团'},
    {'code': '300124', 'market': 'SZ', 'name': '汇川技术'},
    {'code': '600276', 'market': 'SH', 'name': '恒瑞医药'},
    {'code': '600887', 'market': 'SH', 'name': '伊利股份'},
    {'code': '000001', 'market': 'SZ', 'name': '平安银行'},
    {'code': '002304', 'market': 'SZ', 'name': '洋河股份'},
    {'code': '600809', 'market': 'SH', 'name': '山西汾酒'},
    {'code': '300760', 'market': 'SZ', 'name': '迈瑞医疗'},
    {'code': '002475', 'market': 'SZ', 'name': '立讯精密'},
    {'code': '000568', 'market': 'SZ', 'name': '泸州老窖'},
    {'code': '300015', 'market': 'SZ', 'name': '爱尔眼科'},
    {'code': '002714', 'market': 'SZ', 'name': '牧原股份'},
    {'code': '601012', 'market': 'SH', 'name': '隆基绿能'},
    {'code': '300274', 'market': 'SZ', 'name': '阳光电源'},
    {'code': '002352', 'market': 'SZ', 'name': '顺丰控股'},
    {'code': '600585', 'market': 'SH', 'name': '海螺水泥'},
    {'code': '601166', 'market': 'SH', 'name': '兴业银行'},
    {'code': '000002', 'market': 'SZ', 'name': '万科A'},
    {'code': '688111', 'market': 'SH', 'name': '金山办公'},
    {'code': '600900', 'market': 'SH', 'name': '长江电力'},
    {'code': '601899', 'market': 'SH', 'name': '紫金矿业'},
    {'code': '300498', 'market': 'SZ', 'name': '温氏股份'},
    {'code': '002371', 'market': 'SZ', 'name': '北方华创'},
    {'code': '000725', 'market': 'SZ', 'name': '京东方A'},
    {'code': '603259', 'market': 'SH', 'name': '药明康德'},
    {'code': '300308', 'market': 'SZ', 'name': '中际旭创'},
    {'code': '002920', 'market': 'SZ', 'name': '德赛西威'},
    {'code': '605499', 'market': 'SH', 'name': '东鹏饮料'},
    {'code': '600941', 'market': 'SH', 'name': '中国移动'},
]

# ════════════════════════════════════════════
# Frontend Hot-Reload
# ════════════════════════════════════════════

async def load_frontend():
    global frontend_cache
    html_path = V2_DIR / 'frontend.html'
    idx_path = V2_DIR / 'index.html'
    paths = [html_path, idx_path]
    for p in paths:
        if p.exists():
            mtime = p.stat().st_mtime
            if frontend_cache['html'] is None or frontend_cache['mtime'] != mtime:
                frontend_cache['html'] = p.read_text('utf-8')
                frontend_cache['mtime'] = mtime
                print(f"  Frontend loaded: {p} ({len(frontend_cache['html'])} chars)")
            return True
    frontend_cache['html'] = '<html><body><h1>SMC API V2</h1><p>Frontend not found</p></body></html>'
    return False

async def frontend_watcher():
    """Background task: watch frontend file for changes every 5s"""
    while True:
        await load_frontend()
        await asyncio.sleep(5)

# ════════════════════════════════════════════
# WebSocket Manager
# ════════════════════════════════════════════

async def ws_broadcaster():
    """Push status to all websocket clients every 5 seconds"""
    await asyncio.sleep(2)  # initial delay
    while True:
        if ws_clients:
            payload = build_status_payload()
            msg = json.dumps(payload)
            dead = set()
            for ws in ws_clients:
                try:
                    await ws.send_text(msg)
                except:
                    dead.add(ws)
            ws_clients -= dead
        await asyncio.sleep(5)

def build_status_payload():
    """Build combined status payload for WebSocket push"""
    status = safe_read_json(V83_DIR / 'live_status.json')
    best = safe_read_json(V83_DIR / 'best_params.json')
    proxy = get_proxy_status()
    history = safe_read_json(V83_DIR / 'history.json')
    # Last 3 history entries for chart
    recent = (history or [])[-3:]
    return {
        'ts': time.time(),
        'optimizer': status,
        'best': best,
        'proxy': proxy,
        'recent': recent,
    }

# ════════════════════════════════════════════
# Optimizer Management
# ════════════════════════════════════════════

optimizer_process = None

def start_optimizer(iters=300, stocks=40, tighten=0.0, seed=None):
    global optimizer_process
    cmd = [
        sys.executable,
        str(HOME / '.hermes' / 'scripts' / 'smc_optimizer_v84.py'),
        str(iters), str(stocks),
    ]
    if tighten > 0:
        cmd.extend(['--tighten', str(tighten)])
    if seed:
        cmd.extend(['--seed', seed])
    try:
        optimizer_process = subprocess.Popen(
            cmd,
            stdout=open(LOGS_DIR / 'smc_optimizer.log', 'a'),
            stderr=subprocess.STDOUT,
        )
        return {'ok': True, 'pid': optimizer_process.pid, 'cmd': ' '.join(cmd)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def stop_optimizer():
    global optimizer_process
    if optimizer_process:
        try:
            optimizer_process.terminate()
            optimizer_process = None
            return {'ok': True}
        except: pass
    # Also try killing by name
    try:
        subprocess.run(['pkill', '-f', 'smc_optimizer_v84.py'], timeout=3)
    except:
        pass
    return {'ok': True}

# ════════════════════════════════════════════
# FastAPI App
# ════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app):
    """Start background tasks on startup"""
    await load_frontend()
    # Start background tasks
    tasks = [
        asyncio.create_task(frontend_watcher()),
        asyncio.create_task(ws_broadcaster()),
    ]
    print(f"\n{'='*50}")
    print(f"  SMC V8.5 API Server — Port {PORT}")
    print(f"{'='*50}")
    print(f"  Frontend: ~/smc_web_v2/frontend.html")
    print(f"  Engine:   smc_engine_v84.py (OK={ENGINE_OK})")
    print(f"  WS Push:  /ws/status (every 5s)")
    print(f"  Hubble:   {HUBBLE_BASE}")
    print(f"{'='*50}\n")
    yield
    for t in tasks:
        t.cancel()

app = FastAPI(title="SMC V8.5 API", version="8.5", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ════════════════════════════════════════════
# REST API Endpoints
# ════════════════════════════════════════════

# ── Frontend ──

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    await load_frontend()
    return frontend_cache.get('html') or '<html><body><h1>Loading...</h1></body></html>'

# ── Optimizer Status ──

@app.get("/api/v2/status")
async def get_status():
    status = safe_read_json(V83_DIR / 'live_status.json')
    proxy = get_proxy_status()
    return {**status, 'proxy': proxy, 'engine_ok': ENGINE_OK}

@app.get("/api/v2/best")
async def get_best():
    return safe_read_json(V83_DIR / 'best_params.json')

@app.get("/api/v2/history")
async def get_history(limit: int = Query(500, le=1000)):
    h = safe_read_json(V83_DIR / 'history.json')
    if isinstance(h, list):
        return {'rounds': h[-limit:]}
    return {'rounds': []}

@app.get("/api/v2/elite")
async def get_elite():
    return safe_read_json(V83_DIR / 'elite_pool.json')

@app.get("/api/v2/params")
async def get_params():
    """Return V8.4 parameter space definition"""
    return V84_PARAM_SPACE

# ── Stocks ──

@app.get("/api/v2/stocks")
async def get_stocks():
    return {'stocks': [
        {'symbol': f"{s['code']}.{s['market']}", 'code': s['code'],
         'market': s['market'], 'name': s['name']}
        for s in STOCKS
    ]}

# ── Kline ──

@app.get("/api/v2/kline/{symbol:path}")
async def get_kline(symbol: str, period: str = Query('daily'), count: int = Query(120)):
    data = get_cached_kline(symbol, period, count)
    if isinstance(data, dict) and 'error' in data:
        raise HTTPException(status_code=404, detail=data['error'])
    klines = klines_to_echarts(data)
    return {'symbol': symbol, 'period': period, 'count': len(klines), 'klines': klines}

# ── Signals ──

@app.get("/api/v2/signals/{symbol:path}")
async def get_signals(symbol: str, count: int = Query(120)):
    """Real-time SMC signal detection using the V8.4 engine"""
    data = get_cached_kline(symbol, 'daily', count)
    if isinstance(data, dict) and 'error' in data:
        return {'error': data['error'], 'signals': [], 'trades': []}

    # Convert to OHLCV for engine
    if isinstance(data, list) and len(data) > 0:
        from smc_engine_v84 import kline_to_ohlcv
        ohlcv = kline_to_ohlcv([{
            'o': float(k['open']), 'h': float(k['high']),
            'l': float(k['low']), 'c': float(k['close']),
            'v': float(k.get('volume', 0))
        } for k in data])

        # Use best params
        best = safe_read_json(V83_DIR / 'best_params.json')
        params = best.get('params', {}) if best else {}

        # Run engine
        eval_result = evaluate_trades(ohlcv, params)
        all_signals = detect_all_signals(ohlcv, params)

        # Format signals for frontend
        frontend_signals = []
        for s in all_signals:
            sig_type = s.get('type', '?')
            direction = 'bullish' if ('Bull' in str(sig_type) or s.get('direction') == 'bull') else 'bearish'
            frontend_signals.append({
                'date': s.get('date', f"idx-{s.get('idx',0)}"),
                'type': direction,
                'type_zh': '做多' if direction == 'bullish' else '做空',
                'signal_type': sig_type,
                'score': round(s.get('strength', s.get('width', 0)) * 5, 1),
                'strength': round(s.get('strength', 0), 2),
            })

        return {
            'symbol': symbol,
            'fusion_signals': frontend_signals,
            'simulated_trades': [],
            'summary': {
                'wr': eval_result.get('wr', 0),
                'n': eval_result.get('n_trades', 0),
                'pf': eval_result.get('pf', 0),
                'rr_avg': eval_result.get('rr_avg', 0),
                'total_trades': eval_result.get('n_trades', 0),
            },
            'signals': frontend_signals,
        }
    return {'error': 'no data', 'signals': []}

# ── Backtest ──

@app.get("/api/v2/backtest/{symbol:path}")
async def get_backtest(symbol: str, count: int = Query(120)):
    """Full backtest using V8.4 engine"""
    data = get_cached_kline(symbol, 'daily', count)
    if isinstance(data, dict) and 'error' in data:
        return {'error': f'no data for {symbol}'}

    if isinstance(data, list) and len(data) > 0:
        from smc_engine_v84 import evaluate_trades, kline_to_ohlcv, detect_all_signals
        ohlcv = kline_to_ohlcv([{
            'o': float(k['open']), 'h': float(k['high']),
            'l': float(k['low']), 'c': float(k['close']),
            'v': float(k.get('volume', 0))
        } for k in data])

        best = safe_read_json(V83_DIR / 'best_params.json')
        params = best.get('params', {}) if best else {}

        result = evaluate_trades(ohlcv, params)
        n = result.get('n_trades', 0)
        wins = result.get('wins', 0)

        wr = (wins / n * 100) if n > 0 else 0
        returns = result.get('returns', [])
        rr_list = result.get('rr_list', [])

        pf = 0
        if returns:
            gross_win = sum(r for r in returns if r > 0) or 0.001
            gross_loss = abs(sum(r for r in returns if r < 0)) or 0.001
            pf = gross_win / gross_loss

        rr_avg = sum(rr_list) / len(rr_list) if rr_list else 0

        # Equity curve
        balance = 100000
        equity_curve = [{'time': 'start', 'balance': balance}]
        for ret_val in returns:
            balance *= (1 + ret_val / 100)
            equity_curve.append({'time': 'trade', 'balance': round(balance, 2)})

        return {
            'symbol': symbol,
            'summary': {
                'wr': round(wr, 1),
                'n': n,
                'pf': round(pf, 2),
                'rr_avg': round(rr_avg, 2),
                'total_return': round(sum(returns), 2) if returns else 0,
                'wins': wins,
                'losses': n - wins,
            },
            'simulated_trades': [{
                'date': f'trade-{i}', 'type': 'bullish',
                'type_zh': '做多',
                'entry_price': 0, 'sl_price': 0, 'tp_price': 0,
                'exit_price': 0, 'pnl_pct': ret_val,
                'result': 'win' if ret_val > 0 else 'loss',
            } for i, ret_val in enumerate(returns[:30])],
            'equity_curve': equity_curve,
            'signals': [],
        }
    return {'error': f'no data for {symbol}'}

@app.post("/api/v2/backtest/batch")
async def batch_backtest(body: dict):
    """Multi-stock batch backtest"""
    symbols = body.get('symbols', [])
    params = body.get('params', {})
    count = body.get('count', 120)

    if not symbols:
        # Use all stocks
        symbols = [f"{s['code']}.{s['market']}" for s in STOCKS]

    if not params:
        best = safe_read_json(V83_DIR / 'best_params.json')
        params = best.get('params', {}) if best else {}

    results = {}
    for sym in symbols[:10]:  # limit for speed
        try:
            data = get_cached_kline(sym, 'daily', count)
            if isinstance(data, list) and len(data) > 0:
                from smc_engine_v84 import evaluate_trades, kline_to_ohlcv
                ohlcv = kline_to_ohlcv([{
                    'o': float(k['open']), 'h': float(k['high']),
                    'l': float(k['low']), 'c': float(k['close']),
                    'v': float(k.get('volume', 0))
                } for k in data])
                r = evaluate_trades(ohlcv, params)
                results[sym] = {
                    'n': r.get('n_trades', 0),
                    'wins': r.get('wins', 0),
                }
        except:
            results[sym] = {'error': 'failed'}

    return {'results': results}

# ── Proxy ──

@app.get("/api/v2/proxy")
async def get_proxy():
    return get_proxy_status()

@app.get("/api/v2/proxy/logs")
async def get_proxy_log_endpoint(lines: int = Query(40)):
    logs = get_proxy_logs(lines)
    return {'logs': logs}

@app.post("/api/v2/proxy/restart")
async def restart_proxy():
    try:
        subprocess.run(['sudo', 'systemctl', 'restart', 'mihomo'], timeout=10)
        return {'ok': True}
    except:
        try:
            subprocess.run(['killall', '-9', 'mihomo'], timeout=5)
            return {'ok': True, 'action': 'killed'}
        except:
            return {'ok': False, 'error': 'cannot restart'}

# ── Optimizer Control ──

@app.post("/api/v2/optimizer/start")
async def opt_start(iters: int = Query(300), stocks: int = Query(40),
                    tighten: float = Query(0.0)):
    result = start_optimizer(iters, stocks, tighten)
    return result

@app.post("/api/v2/optimizer/stop")
async def opt_stop():
    return stop_optimizer()

@app.get("/api/v2/optimizer/log")
async def opt_log(lines: int = Query(50)):
    log_path = LOGS_DIR / 'smc_optimizer.log'
    if not log_path.exists():
        return {'lines': []}
    try:
        text = log_path.read_text().strip().split('\n')
        return {'lines': text[-lines:]}
    except:
        return {'lines': []}

# ── Health ──

@app.get("/api/v2/health")
async def health():
    best_exists = (V83_DIR / 'best_params.json').exists()
    proxy = (V2_DIR / 'proxy_status.json').exists()
    return {
        'status': 'ok',
        'engine': 'loaded' if ENGINE_OK else 'failed',
        'time': datetime.now().isoformat(),
        'files': {
            'best_params': best_exists,
            'proxy_status': proxy,
        },
        'ws_clients': len(ws_clients),
    }

# ════════════════════════════════════════════
# WebSocket
# ════════════════════════════════════════════

@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        # Send initial payload immediately
        payload = build_status_payload()
        await websocket.send_text(json.dumps(payload))
        # Keep connection alive (messages are pushed by broadcaster)
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == 'ping':
                    await websocket.send_text('pong')
            except asyncio.TimeoutError:
                try:
                    await websocket.send_text('ping')
                except:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ws_clients.discard(websocket)

# ════════════════════════════════════════════
# Main
# ════════════════════════════════════════════

PORT = 8880
if '--port' in sys.argv:
    idx = sys.argv.index('--port')
    if idx + 1 < len(sys.argv):
        PORT = int(sys.argv[idx + 1])

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=PORT, log_level='info')