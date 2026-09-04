#!/usr/bin/env python3
"""
SMC Web Status API V8 — 统一状态API服务
=========================================
为WebUI前端提供完整的优化状态数据。

端点:
  /api/status         - 当前运行状态 (V8 + V7+代理)
  /api/progress       - 迭代历史 (含最优线)
  /api/best           - 最佳参数详情
  /api/proxy          - 代理监控状态
  /api/history/chart  - 历史图表数据
  /api/health         - 综合健康检查

兼容旧WebUI:
  /proxy/api/status   - 反向代理兼容

用法:
  python3 smc_web_status_api_v54.py [--port PORT]
"""

import json, os, sys, time, glob
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = int(sys.argv[sys.argv.index('--port')+1]) if '--port' in sys.argv else 8879

# ════════ 数据目录 ════════
V8_DIR = Path.home() / '.hermes' / 'smc_opt_v8'
V7_DIR = Path.home() / '.hermes' / 'smc_opt_v7'
V7P_DIR = Path.home() / '.hermes' / 'smc_opt_v7plus'
LOGS_DIR = Path.home() / '.hermes' / 'logs'
SCRIPTS_DIR = Path.home() / '.hermes' / 'scripts'

CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
}

def load_json(path, default=None):
    if not path or not os.path.exists(path):
        return default
    try:
        return json.load(open(path))
    except:
        return default

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()
    
    def do_GET(self):
        path = self.path.rstrip('/')
        
        # 兼容旧API路径
        if path == '/proxy/api/status':
            path = '/api/status'
        elif path == '/proxy/api/progress':
            path = '/api/progress'
        elif path == '/proxy/api/best':
            path = '/api/best'
        elif path == '/proxy/api/proxy':
            path = '/api/proxy'
        
        data = None
        if path == '/api/status':
            data = self.get_status()
        elif path == '/api/progress':
            data = self.get_progress()
        elif path == '/api/best':
            data = self.get_best()
        elif path == '/api/proxy':
            data = self.get_proxy()
        elif path == '/api/history/chart':
            data = self.get_history_chart()
        elif path == '/api/health':
            data = self.get_health()
        elif path.startswith('/api/kline/'):
            data = self.get_kline(path[11:])
        elif path == '/':
            data = {'service': 'SMC Web Status API V8', 'endpoints': [
                '/api/status', '/api/progress', '/api/best',
                '/api/proxy', '/api/history/chart', '/api/health',
                '/api/kline/<symbol>',
            ]}
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            for k, v in CORS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(json.dumps({'error': f'Unknown endpoint: {path}'}).encode())
            return
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=1).encode())
    
    def get_status(self):
        """合并V8/V7/代理状态"""
        v8_live = load_json(V8_DIR / 'live_status.json', {})
        v8_best = load_json(V8_DIR / 'best_params.json', {})
        v7_live = load_json(V7_DIR / 'v7_live_status.json', {})
        v7p_live = load_json(V7P_DIR / 'v7p_live_status.json', {})
        proxy = load_json(LOGS_DIR / 'proxy_status.json', {})
        
        return {
            'v8': {
                'running': v8_live.get('status') == 'running',
                'round': v8_live.get('round', 0),
                'total_rounds': v8_live.get('total_rounds', 200),
                'best_score': v8_live.get('best_score', 0),
                'best_wr': v8_live.get('best_wr', 0),
                'best_n': v8_live.get('best_n', 0),
                'status': v8_live.get('status', 'unknown'),
                'details': v8_live.get('details', {}),
                'timestamp': v8_live.get('timestamp', ''),
            },
            'v7': {
                'round': v7_live.get('generation', v7_live.get('round', 0)),
                'status': v7_live.get('status', 'stopped'),
                'last_update': v7_live.get('timestamp', ''),
            },
            'v7plus': {
                'round': v7p_live.get('generation', v7p_live.get('round', 0)),
                'status': v7p_live.get('status', 'stopped'),
                'last_update': v7p_live.get('timestamp', ''),
            },
            'proxy': {
                'ok': proxy.get('all_ok', False),
                'process': proxy.get('process', {}),
                'connectivity': proxy.get('connectivity', {}),
                'uptime': proxy.get('uptime_seconds', 0),
                'restarts': proxy.get('total_restarts', 0),
            },
        }
    
    def get_progress(self):
        """V8迭代历史"""
        v8_hist = load_json(V8_DIR / 'history.json', {})
        v8_progress = load_json(V8_DIR / 'progress.json', {})
        v7_hist = load_json(V7_DIR / 'v7_history.json', {})
        
        # V8 rounds
        rounds = v8_hist.get('rounds', v8_progress.get('rounds', []))
        
        # V7 history (for comparison)
        v7_history = v7_hist.get('rounds', [])[:50]
        
        return {
            'engine': 'V8',
            'rounds': rounds,
            'total_rounds': v8_hist.get('total_rounds', 200),
            'v7_history': v7_history[:200],
            'best_params_path': str(V8_DIR / 'best_params.json'),
        }
    
    def get_best(self):
        """V8最佳参数"""
        v8_best = load_json(V8_DIR / 'best_params.json', {})
        if v8_best:
            return v8_best
        
        # fallback: V7+
        v7p_best = load_json(V7P_DIR / 'v7p_best.json', {})
        if v7p_best:
            return {'engine': 'V7+', 'data': v7p_best}
        
        return {'error': 'No best params found'}
    
    def get_proxy(self):
        """代理状态"""
        proxy = load_json(LOGS_DIR / 'proxy_status.json', {})
        if not proxy:
            # 尝试其他位置
            for f in [V8_DIR / 'proxy_status.json', V7_DIR / 'proxy_status.json']:
                proxy = load_json(f, {})
                if proxy:
                    break
        return proxy or {'all_ok': False, 'error': 'No status file'}
    
    def get_history_chart(self):
        """V8评分+WR趋势"""
        hist = load_json(V8_DIR / 'history.json', {})
        rounds = hist.get('rounds', [])
        
        scores = [r.get('score', r.get('final_score', 0)) for r in rounds]
        wrs = [r.get('wr', 0) for r in rounds]
        ns = [r.get('n', 0) for r in rounds]
        best_scores = []
        running_best = 0
        for s in scores:
            running_best = max(running_best, s)
            best_scores.append(running_best)
        
        return {
            'scores': scores,
            'best_scores': best_scores,
            'wrs': wrs,
            'ns': ns,
            'total': len(rounds),
        }
    
    def get_health(self):
        """综合健康检查"""
        v8_live = load_json(V8_DIR / 'live_status.json', {})
        proxy = load_json(LOGS_DIR / 'proxy_status.json', {})
        
        return {
            'v8_running': v8_live.get('status') == 'running',
            'v8_progress': f"{v8_live.get('round', 0)}/{v8_live.get('total_rounds', 200)}",
            'v8_best_wr': v8_live.get('best_wr', 0),
            'proxy_ok': proxy.get('all_ok', False),
            'proxy_uptime': proxy.get('uptime_seconds', 0),
            'proxy_restarts': proxy.get('total_restarts', 0),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
    
    def get_kline(self, symbol):
        """获取特定股票的K线+信号"""
        cache_path = Path.home() / '.hermes' / 'kline_cache'
        file_key = symbol.replace('.', '_')
        
        # Try cache
        for f in cache_path.glob(f'{file_key}_daily*.json'):
            try:
                bars = json.load(open(f))
                return {
                    'symbol': symbol,
                    'klines': bars[-200:],  # last 200
                    'total': len(bars),
                }
            except:
                pass
        
        # Try computing on demand
        try:
            sys.path.insert(0, str(SCRIPTS_DIR))
            from smc_engine_v8 import load_bars, detect_entries_v8, get_vol_profile
            bars = load_bars(symbol, 'daily', 300)
            if bars:
                result = detect_entries_v8(bars)
                vol = get_vol_profile(bars)
                return {
                    'symbol': symbol,
                    'klines': bars[-200:],
                    'signals': result.get('signals', {}),
                    'entries': [{k: v for k, v in e.items() if k in ('ep','dir','sl','tp','rr','score','sources')} for e in result.get('entries', [])],
                    'vol': vol,
                    'ms': result.get('ms', {}),
                    'total_entries': result['total'],
                }
        except Exception as e:
            return {'error': str(e), 'symbol': symbol}
        
        return {'error': 'No data', 'symbol': symbol}
    
    def log_message(self, format, *args):
        """静默请求日志"""
        pass

# ════════ 启动 ════════
if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"  SMC Web Status API V8 running on http://0.0.0.0:{PORT}")
    print(f"  Endpoints:")
    print(f"    /api/status         - V8/V7/Proxy 综合状态")
    print(f"    /api/progress       - 迭代历史")
    print(f"    /api/best           - 最佳参数")
    print(f"    /api/proxy          - 代理状态")
    print(f"    /api/history/chart  - 图表数据")
    print(f"    /api/health         - 健康检查")
    print(f"    /api/kline/<symbol> - K线+信号")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()