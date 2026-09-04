#!/usr/bin/env python3
# SMC V9 — 专业级交易终端 WebUI (v4 — 完全重构)
"""
SMC V9 WebUI — 完全重构，独立前端 + 专业交易终端。

架构:
  smc_webui.py        ← FastAPI 服务 (API + 静态文件代理)
  static/index.html   ← 完整 SPA 前端 (9 标签页)
  static/echarts.js   ← 本地 ECharts (可选回退)

前端架构 (9 Tab 专业交易终端):
  1. K线图     — 多层图表(K线+成交量+信号)+dataZoom联动
  2. 信号扫描   — 全信号列表+过滤+排序+详情
  3. 回测分析   — KPI网格+交易表+收益率曲线
  4. 交易日志   — 结构化卡片+入场/出场原因
  5. 市场扫描   — Watchlist+股票/ETF/板块/指数
  6. 系统配置   — 参数空间可视化+编辑
  7. 运行状态   — 引擎/代理/Hubble/系统
  8. 优化历史   — 迭代记录+性能曲线
  9. 信号标识   — 15种SMC信号标注+图表
"""

import sys, os, json, time, math, logging, traceback, urllib.request
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_this_dir)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from v9 import smc_config as config
from v9.smc_hubble import fetch_kline, kline_to_ohlcv, fetch_and_prepare, calc_atr_pct, hubble_api
from v9.smc_signals import detect_all_signals, score_signal, signal_summary
from v9.smc_backtest import evaluate_trades, evaluate_params
from v9.smc_annotations import generate_chart_data
from v9.smc_watchlist import scan_and_build_watchlist, load_cnstock_list, load_etf_list, load_index_list

log = logging.getLogger('smc_v9.webui')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')

HOME = Path.home()
OUTPUT_DIR = Path(config.get_config()['paths']['output_dir'])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ws_clients = set()


# ─── CACHE ──────────────────────────────────────────────────────────
_cache = {}  # simple in-memory cache for market data


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("V9 WebUI v4 starting...")
    yield
    log.info("V9 WebUI shutting down")

app = FastAPI(title="SMC V9 Trading Terminal", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


# ════════════════════════════════════════════════════════════════════
# API v2 — 全面优化
# ════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "9.0", "time": datetime.now().isoformat()}


@app.get("/api/status")
async def get_status():
    """完整系统状态 — 引擎/代理/Hubble/CPU/内存"""
    try: import psutil
    except ImportError: psutil = None
    status = {
        'v9': {'running': False, 'round': 0, 'phase': 'idle'},
        'proxy': _proxy_status(),
        'hubble': _hubble_status(),
    }
    # Load best params
    best_file = OUTPUT_DIR / 'best_params.json'
    if best_file.exists():
        try:
            data = json.loads(best_file.read_text())
            fe = data.get('full_eval', {})
            status['v9'].update({
                'best_wr': fe.get('wr', 0), 'best_rr': fe.get('rr_avg', 0),
                'best_pf': fe.get('pf', 0), 'best_n': fe.get('n', 0),
                'best_score': fe.get('score', 0),
                'best_params': data.get('params', {}),
            })
        except:
            pass
    # Live status
    live_file = OUTPUT_DIR / 'live_status.json'
    if live_file.exists():
        try:
            live = json.loads(live_file.read_text())
            status['v9'].update({
                'running': live.get('running', False),
                'round': live.get('round', 0),
                'total_rounds': live.get('total_rounds', 0),
                'phase': live.get('phase', 'idle'),
            })
        except:
            pass
    # System info
    try:
        import psutil
        status['system'] = {
            'cpu': psutil.cpu_percent(interval=0.5),
            'memory': psutil.virtual_memory().percent,
            'uptime': time.time() - psutil.boot_time(),
        }
    except ImportError:
        pass
    return status


@app.get("/api/config")
async def get_config():
    cfg = dict(config.get_config())
    if 'hubble' in cfg:
        cfg['hubble'] = {k: '***' if k == 'api_key' else v for k, v in cfg['hubble'].items()}
    return cfg


@app.get("/api/config/params")
async def get_param_space():
    """参数空间预览"""
    return config.get_param_space()


@app.get("/api/chart/data")
async def chart_data(
    symbol: str = Query('600519.SH'),
    period: str = Query('daily'),
    count: int = Query(200),
    sl_pct: float = Query(1.0),
    tp_pct: float = Query(3.0),
    score_min: float = Query(1.0),
    max_trades: int = Query(5),
):
    """核心图表数据 — K线+信号+回测+标注"""
    raw = fetch_kline(symbol, period, count)
    if not raw or len(raw) < 30:
        raise HTTPException(status_code=400, detail=f"No data for {symbol}")
    ohlcv = kline_to_ohlcv(raw)
    params = {k: pdef['default'] for k, pdef in config.get_param_space().items()}
    params.update({'sl_pct': sl_pct, 'tp_pct': tp_pct, 'score_min': score_min, 'max_trades': max_trades})
    signals = detect_all_signals(ohlcv, params)
    scored = [(score_signal(s, ohlcv), s) for s in signals]
    bt_result = evaluate_trades(ohlcv, params)
    annotations = generate_chart_data(ohlcv, signals, bt_result.get('trades', []), params)
    counts, dirs = signal_summary(signals)
    return {
        'symbol': symbol, 'period': period, 'bars': len(ohlcv),
        'current_price': ohlcv[-1]['c'], 'atr_pct': round(calc_atr_pct(ohlcv), 2),
        'signal_count': len(signals), 'summary': counts, 'directions': dirs,
        'signals': [{'score': round(sc, 1), **sig} for sc, sig in scored],
        'backtest': {
            'n_trades': bt_result['n_trades'], 'wins': bt_result['wins'], 'losses': bt_result['losses'],
            'win_rate': round(bt_result['wins'] / max(bt_result['n_trades'], 1) * 100, 1),
            'avg_rr': round(sum(bt_result['rr_list']) / len(bt_result['rr_list']), 2) if bt_result['rr_list'] else 0,
            'total_return': round(sum(bt_result['returns']), 2),
            'trades': bt_result.get('trades', []),
            'trade_logs': bt_result.get('trade_logs', []),
            'rejected_signals': bt_result.get('rejected_signals', []),
            'returns': bt_result.get('returns', []),
        },
        'annotations': annotations,
    }


@app.get("/api/signals/scan")
async def scan_signals(
    symbol: str = Query('600519.SH'),
    period: str = Query('daily'),
    count: int = Query(200),
):
    raw = fetch_kline(symbol, period, count)
    if not raw or len(raw) < 30:
        raise HTTPException(status_code=400, detail=f"No data for {symbol}")
    ohlcv = kline_to_ohlcv(raw)
    params = {k: pdef['default'] for k, pdef in config.get_param_space().items()}
    signals = detect_all_signals(ohlcv, params)
    scored = [(score_signal(s, ohlcv), s) for s in signals]
    counts, dirs = signal_summary(signals)
    return {
        'symbol': symbol, 'bars': len(ohlcv), 'current_price': ohlcv[-1]['c'],
        'atr_pct': round(calc_atr_pct(ohlcv), 2), 'signal_count': len(signals),
        'summary': counts, 'directions': dirs,
        'signals': [{'score': round(sc, 1), **sig} for sc, sig in scored],
    }


@app.get("/api/backtest/run")
async def run_backtest(
    symbol: str = Query('600519.SH'), count: int = Query(200),
    sl_pct: float = Query(1.0), tp_pct: float = Query(3.0),
    min_sources: int = Query(2), score_min: float = Query(1.0), max_trades: int = Query(5),
):
    ohlcv, atr_pct, _ = fetch_and_prepare(symbol, 'daily', count)
    if not ohlcv or len(ohlcv) < 30:
        raise HTTPException(status_code=400, detail=f"Insufficient data for {symbol}")
    params = {k: pdef['default'] for k, pdef in config.get_param_space().items()}
    params.update({
        'sl_pct': sl_pct, 'tp_pct': tp_pct, 'min_sources': min_sources,
        'score_min': score_min, 'max_trades': max_trades,
    })
    result = evaluate_trades(ohlcv, params)
    return {
        'symbol': symbol, 'bars': len(ohlcv), 'atr_pct': round(atr_pct, 2),
        'current_price': ohlcv[-1]['c'],
        'n_trades': result['n_trades'], 'wins': result['wins'], 'losses': result['losses'],
        'win_rate': round(result['wins'] / max(result['n_trades'], 1) * 100, 1),
        'avg_rr': round(sum(result['rr_list']) / len(result['rr_list']), 2) if result['rr_list'] else 0,
        'total_return': round(sum(result['returns']), 2),
        'trades': result.get('trades', []),
        'trade_logs': result.get('trade_logs', []),
        'returns': result.get('returns', []),
    }


@app.get("/api/backtest/batch")
async def batch_backtest(
    stock_count: int = Query(20), sl_pct: float = Query(1.0), tp_pct: float = Query(3.0),
    min_sources: int = Query(2), score_min: float = Query(1.0), max_trades: int = Query(5),
):
    stocks = config.get_stocks()[:stock_count]
    params = {k: pdef['default'] for k, pdef in config.get_param_space().items()}
    params.update({
        'sl_pct': sl_pct, 'tp_pct': tp_pct, 'min_sources': min_sources,
        'score_min': score_min, 'max_trades': max_trades,
    })
    t0 = time.time()
    result = evaluate_params(params, stocks)
    return {'params': params, 'stocks_tested': stock_count, 'time_elapsed': round(time.time() - t0, 1), **result}


@app.get("/api/market/scan")
async def market_scan(limit: int = Query(50), min_score: float = Query(2.0)):
    try:
        return scan_and_build_watchlist(
            limit_stocks=limit, limit_etfs=20, limit_indices=10,
            limit_sectors=10, min_score=min_score,
        )
    except Exception as e:
        log.error(f"market_scan failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market/stocks")
async def market_stocks(limit: int = Query(100)):
    stocks = load_cnstock_list(limit)
    return {'stocks': stocks, 'total': len(stocks)}


@app.get("/api/market/etfs")
async def market_etfs(limit: int = Query(50)):
    etfs = load_etf_list(limit)
    return {'etfs': etfs, 'total': len(etfs)}


@app.get("/api/market/indices")
async def market_indices(limit: int = Query(30)):
    indices = load_index_list(limit)
    return {'indices': indices, 'total': len(indices)}


@app.get("/api/proxy")
async def proxy_status():
    return _proxy_status()


@app.get("/api/history")
async def get_history():
    """优化历史记录"""
    hist_file = OUTPUT_DIR / 'history.json'
    if hist_file.exists():
        try:
            return json.loads(hist_file.read_text())
        except:
            pass
    return {'history': []}


@app.get("/api/hubble/check")
async def hubble_check():
    """Hubble API 连通性测试"""
    try:
        resp = hubble_api("/api/v2/cnstock/stocks", {'symbol': '600519.SH'})
        if isinstance(resp, dict) and resp.get('error'):
            return {'ok': False, 'error': resp['error']}
        return {'ok': True, 'response': 'valid'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ─── Internal helpers ───────────────────────────────────────────────

def _proxy_status():
    try:
        req = urllib.request.Request("http://127.0.0.1:9090/proxies")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            px = data.get('proxies', {})
            alive, total = 0, 0
            for name, p in px.items():
                if isinstance(p, dict) and p.get('type') in ('Shadowsocks', 'VMess', 'Trojan', 'Hysteria2', 'VLESS', 'Vless'):
                    total += 1
                    history = p.get('history', [])
                    if history and history[-1].get('delay', 0) > 0:
                        alive += 1
            return {'ok': True, 'alive_nodes': alive, 'total_nodes': total, 'running': True}
    except Exception as e:
        return {'ok': False, 'error': str(e), 'running': False}


def _hubble_status():
    try:
        resp = hubble_api("/api/v2/cnstock/stocks", {'symbol': '600519.SH'})
        if isinstance(resp, dict) and resp.get('error'):
            return {'ok': False, 'error': resp['error']}
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ─── WebSocket ──────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == 'ping':
                await websocket.send_json({'type': 'pong', 'time': datetime.now().isoformat()})
            elif msg.startswith('load:'):
                sym = msg.split(':', 1)[1].strip()
                try:
                    raw = fetch_kline(sym, 'daily', 200)
                    ohlcv = kline_to_ohlcv(raw)
                    params = {k: pdef['default'] for k, pdef in config.get_param_space().items()}
                    signals = detect_all_signals(ohlcv, params)
                    scored = [(score_signal(s, ohlcv), s) for s in signals]
                    bt = evaluate_trades(ohlcv, params)
                    ann = generate_chart_data(ohlcv, signals, bt.get('trades', []), params)
                    await websocket.send_json({
                        'type': 'chart_data', 'symbol': sym, 'bars': len(ohlcv),
                        'current_price': ohlcv[-1]['c'], 'atr_pct': round(calc_atr_pct(ohlcv), 2),
                        'signal_count': len(signals),
                        'signals': [{'score': round(sc, 1), **s} for sc, s in scored],
                        'backtest': {
                            'n_trades': bt['n_trades'], 'wins': bt['wins'], 'losses': bt['losses'],
                            'win_rate': round(bt['wins'] / max(bt['n_trades'], 1) * 100, 1),
                        },
                        'annotations': ann,
                    })
                except Exception as e:
                    await websocket.send_json({'type': 'error', 'message': str(e)})
            elif msg == 'status':
                s = await get_status()
                await websocket.send_json({'type': 'status', 'data': s})
    except WebSocketDisconnect:
        ws_clients.discard(websocket)


# ─── Frontend ───────────────────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
INDEX_HTML = os.path.join(STATIC_DIR, 'index.html')


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the SPA frontend"""
    if os.path.exists(INDEX_HTML):
        return FileResponse(INDEX_HTML)
    return HTMLResponse("<h1>SMC V9 WebUI</h1><p>Frontend not found. Run with static/index.html.</p>")


@app.get("/api/export/{symbol}")
async def export_data(symbol: str = Query('600519.SH')):
    """导出全量数据JSON"""
    try:
        raw = fetch_kline(symbol, 'daily', 500)
        ohlcv = kline_to_ohlcv(raw)
        params = {k: pdef['default'] for k, pdef in config.get_param_space().items()}
        signals = detect_all_signals(ohlcv, params)
        scored = [(score_signal(s, ohlcv), s) for s in signals]
        bt = evaluate_trades(ohlcv, params)
        ann = generate_chart_data(ohlcv, signals, bt.get('trades', []), params)
        counts, dirs = signal_summary(signals)
        return {
            'symbol': symbol, 'bars': len(ohlcv), 'current_price': ohlcv[-1]['c'],
            'signals': [{'score': round(sc, 1), **sig} for sc, sig in scored],
            'backtest': {
                'n_trades': bt['n_trades'], 'wins': bt['wins'], 'losses': bt['losses'],
                'win_rate': round(bt['wins'] / max(bt['n_trades'], 1) * 100, 1),
                'avg_rr': round(sum(bt['rr_list']) / len(bt['rr_list']), 2) if bt['rr_list'] else 0,
                'total_return': round(sum(bt['returns']), 2),
                'trades': bt.get('trades', []),
            },
            'annotations': ann,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main():
    port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8881
    host = '0.0.0.0'
    log.info(f"Starting SMC V9 WebUI v4 on {host}:{port}")
    print(f"\n  {'='*50}")
    print(f"  SMC V9 — 专业交易终端 v4")
    print(f"  http://localhost:{port}")
    print(f"  9 Tab | ECharts | WS | Full API")
    print(f"  {'='*50}\n")
    uvicorn.run(app, host=host, port=port, log_level='info')


if __name__ == '__main__':
    main()