#!/usr/bin/env python3
"""
SMC Web Status API V8.2 — 统一状态API服务（支持V8.2引擎）
===========================================================
覆盖V8/V8.2/V7+/代理状态

端口: 8879 (兼容旧版本)

端点:
  /api/status         - V8.2 + V8 + V7+ + 代理综合状态
  /api/progress       - V8.2迭代历史
  /api/best           - V8.2最佳参数
  /api/proxy          - 代理监控状态
  /api/history/chart  - 图表数据
  /api/health         - 健康检查
  /api/kline/<symbol> - K线+信号(V8.2引擎)
  /                    - 索引页

兼容:
  /proxy/api/status   -> /api/status (反向代理兼容)
"""

import json, os, sys, time, glob
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = int(sys.argv[sys.argv.index('--port')+1]) if '--port' in sys.argv else 8879

# ════════ 数据目录 ════════
V82_DIR = Path.home() / '.hermes' / 'smc_opt_v82'
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
        if path in ('/proxy/api/status', '/api/status'):
            data = self.get_status()
        elif path in ('/proxy/api/progress', '/api/progress'):
            data = self.get_progress()
        elif path in ('/proxy/api/best', '/api/best'):
            data = self.get_best()
        elif path in ('/proxy/api/proxy', '/api/proxy'):
            data = self.get_proxy()
        elif path == '/api/history/chart':
            data = self.get_history_chart()
        elif path == '/api/health':
            data = self.get_health()
        elif path.startswith('/api/kline/'):
            data = self.get_kline(path[11:])
        elif path == '/':
            data = {
                'service': 'SMC Web Status API V8.2',
                'note': 'V8.2引擎 = RR引导 + N黄金区间 + 过拟合惩罚',
                'endpoints': [
                    '/api/status', '/api/progress', '/api/best',
                    '/api/proxy', '/api/history/chart', '/api/health',
                    '/api/kline/<symbol>',
                ],
                'monitored_dirs': {
                    'v82': str(V82_DIR),
                    'v8': str(V8_DIR),
                    'v7': str(V7_DIR),
                    'v7p': str(V7P_DIR),
                }
            }
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
        """合并V8.2/V8/V7/代理状态"""
        v82_live = load_json(V82_DIR / 'live_status.json', {})
        v82_best = load_json(V82_DIR / 'best_params.json', {})
        v8_live = load_json(V8_DIR / 'live_status.json', {})
        v7_live = load_json(V7_DIR / 'v7_live_status.json', {})
        v7p_live = load_json(V7P_DIR / 'v7p_live_status.json', {})
        proxy = load_json(V82_DIR / 'proxy_status.json', {})
        if not proxy:
            proxy = load_json(LOGS_DIR / 'proxy_status.json', {})
        
        v82_best_detail = {}
        if v82_best:
            fe = v82_best.get('full_eval', {})
            v82_best_detail = {
                'wr': fe.get('wr', 0),
                'pf': fe.get('pf', 0),
                'n': fe.get('n', 0),
                'ret': fe.get('ret', 0),
                'rr_avg': fe.get('rr_avg', 0),
                'sr': fe.get('sr', 0),
                'score': fe.get('final_score', 0),
            }
        
        return {
            'v82': {
                'running': v82_live.get('status') == 'running',
                'round': v82_live.get('round', 0),
                'total_rounds': v82_live.get('total_rounds', 200),
                'best_score': v82_live.get('best_score', 0),
                'best_wr': v82_live.get('best_wr', 0),
                'best_n': v82_live.get('best_n', 0),
                'status': v82_live.get('status', 'unknown'),
                'details': v82_live.get('details', {}),
                'timestamp': v82_live.get('timestamp', ''),
                'best_detail': v82_best_detail,
            },
            'v8': {
                'running': v8_live.get('status') == 'running',
                'round': v8_live.get('round', 0),
                'total_rounds': v8_live.get('total_rounds', 200),
                'best_score': v8_live.get('best_score', 0),
                'best_wr': v8_live.get('best_wr', 0),
                'best_n': v8_live.get('best_n', 0),
                'status': v8_live.get('status', 'unknown'),
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
                'running': proxy.get('running', False),
                'pid': proxy.get('pid', 0),
                'port_ok': proxy.get('port_ok', False),
                'internet_ok': proxy.get('internet_ok', False),
                'connectivity': proxy.get('connectivity', {}),
                'uptime': proxy.get('uptime', 0),
                'restarts': proxy.get('total_restarts', 0),
                'alive_nodes': proxy.get('alive_nodes', 0),
                'total_nodes': proxy.get('total_nodes', 0),
                'last_check': proxy.get('last_check', ''),
            },
        }
    
    def get_progress(self):
        """V8.2迭代历史"""
        v82_hist = load_json(V82_DIR / 'history.json', {})
        v82_progress = load_json(V82_DIR / 'progress.json', {})
        v8_hist = load_json(V8_DIR / 'history.json', {})
        v7_hist = load_json(V7_DIR / 'v7_history.json', {})
        
        rounds = v82_hist.get('rounds', v82_progress.get('rounds', []))
        v8_rounds = v8_hist.get('rounds', [])[:200]
        v7_history = v7_hist.get('rounds', [])[:50]
        
        return {
            'engine': 'V8.2',
            'rounds': rounds,
            'total_rounds': v82_hist.get('total_rounds', v82_progress.get('total_rounds', 200)),
            'v8_rounds': v8_rounds,
            'v7_history': v7_history,
            'best_params_path': str(V82_DIR / 'best_params.json'),
        }
    
    def get_best(self):
        """V8.2最佳参数"""
        v82_best = load_json(V82_DIR / 'best_params.json', {})
        if v82_best:
            return v82_best
        v8_best = load_json(V8_DIR / 'best_params.json', {})
        if v8_best:
            return {'engine': 'V8', 'data': v8_best}
        v7p_best = load_json(V7P_DIR / 'v7p_best.json', {})
        if v7p_best:
            return {'engine': 'V7+', 'data': v7p_best}
        return {'error': 'No best params found'}
    
    def get_proxy(self):
        """代理状态"""
        for f in [V82_DIR / 'proxy_status.json', V8_DIR / 'proxy_status.json',
                  V7_DIR / 'proxy_status.json', LOGS_DIR / 'proxy_status.json']:
            proxy = load_json(f, {})
            if proxy:
                return proxy
        return {'all_ok': False, 'error': 'No status file'}
    
    def get_history_chart(self):
        """V8.2评分+WR趋势"""
        hist = load_json(V82_DIR / 'history.json', {})
        rounds = hist.get('rounds', [])
        
        scores = [r.get('score', 0) for r in rounds]
        wrs = [r.get('wr', 0) for r in rounds]
        ns = [r.get('n', 0) for r in rounds]
        rrs = [r.get('rr', 0) for r in rounds]
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
            'rrs': rrs,
            'total': len(rounds),
        }
    
    def get_health(self):
        """综合健康检查"""
        v82_live = load_json(V82_DIR / 'live_status.json', {})
        proxy = load_json(V82_DIR / 'proxy_status.json', {})
        if not proxy:
            proxy = load_json(LOGS_DIR / 'proxy_status.json', {})
        
        return {
            'v82_running': v82_live.get('status') == 'running',
            'v82_progress': f"{v82_live.get('round', 0)}/{v82_live.get('total_rounds', 200)}",
            'v82_best_wr': v82_live.get('best_wr', 0),
            'v82_best_n': v82_live.get('best_n', 0),
            'proxy_ok': proxy.get('all_ok', False),
            'proxy_running': proxy.get('running', False),
            'proxy_uptime': proxy.get('uptime', 0),
            'proxy_restarts': proxy.get('total_restarts', 0),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
    
    def get_kline(self, symbol):
        """获取特定股票的K线+信号(使用V8.2引擎)"""
        cache_path = Path.home() / '.hermes' / 'kline_cache'
        file_key = symbol.replace('.', '_')
        
        for f in cache_path.glob(f'{file_key}_daily*.json'):
            try:
                bars = json.load(open(f))
                return {
                    'symbol': symbol,
                    'klines': bars[-200:],
                    'total': len(bars),
                }
            except:
                pass
        
        try:
            sys.path.insert(0, str(SCRIPTS_DIR))
            from smc_engine_v82 import load_bars, detect_entries_v82, get_vol_profile
            bars = load_bars(symbol, 'daily', 300)
            if bars:
                result = detect_entries_v82(bars)
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
        pass

# ════════ 启动 ════════
if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"  SMC Web Status API V8.2 running on http://0.0.0.0:{PORT}")
    print(f"  Endpoints:")
    print(f"    /api/status         - V8.2/V8/V7/Proxy 综合状态")
    print(f"    /api/progress       - V8.2迭代历史 (含RR)")
    print(f"    /api/best           - 最佳参数")
    print(f"    /api/proxy          - 代理状态")
    print(f"    /api/history/chart  - 图表数据 (含RR线)")
    print(f"    /api/health         - 健康检查")
    print(f"    /api/kline/<symbol> - K线+信号")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()