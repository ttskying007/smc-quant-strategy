#!/usr/bin/env python3
"""
SMC Web Status API — 为WebUI提供优化器状态和同步数据
========================================================
提供REST API端点供前端获取:
  /api/status         - 优化器运行状态
  /api/progress       - 当前轮次进度
  /api/best           - 最佳参数
  /api/proxy          - 代理状态
  /api/history        - 历史迭代数据

用法:
  python3 smc_web_status_api.py    # 启动API服务器在8878端口
"""

import json, os, sys, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = 8878
OPT_DIR_V4 = Path.home() / '.hermes' / 'smc_opt_v4'
OPT_DIR_V3 = Path.home() / '.hermes' / 'smc_opt_v3'
OPT_DIR_V2 = Path.home() / '.hermes' / 'smc_opt'
OPT_DIR_V5 = Path.home() / '.hermes' / 'smc_opt_v5'
OPT_DIR_V6 = Path.home() / '.hermes' / 'smc_opt_v6'
OPT_DIR_V7 = Path.home() / '.hermes' / 'smc_opt_v7'
OPT_DIR_V7P = Path.home() / '.hermes' / 'smc_opt_v7plus'
PROXY_STATUS_FILE = Path.home() / '.hermes' / 'logs' / 'proxy_status.json'
PROXY_STATUS_V5_FILE = OPT_DIR_V7 / 'proxy_status.json'

# CORS headers
CORS_HEADERS = {
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


def get_latest_iter_file(dir_path):
    """获取最新的迭代文件"""
    path = Path(dir_path) if isinstance(dir_path, str) else dir_path
    if not path.exists():
        return None
    iter_files = sorted(path.glob('iter_*.json'))
    return iter_files[-1] if iter_files else None


def get_all_iter_files(dir_path):
    path = Path(dir_path) if isinstance(dir_path, str) else dir_path
    if not path.exists():
        return []
    return sorted(path.glob('iter_*.json'))


def collect_status():
    """收集所有系统状态"""
    status = {
        'timestamp': time.time(),
        'timestamp_str': time.strftime('%Y-%m-%d %H:%M:%S'),
        'versions': {},
    }
    
    # V4优化器
    v4_best = load_json(OPT_DIR_V4 / 'best_params.json')
    v4_latest = get_latest_iter_file(OPT_DIR_V4)
    v4_latest_data = load_json(v4_latest) if v4_latest else None
    
    v4_iter_files = get_all_iter_files(OPT_DIR_V4)
    v4_history = []
    for f in v4_iter_files[-30:]:  # 最近30轮
        data = load_json(f)
        if data:
            v4_history.append({
                'iteration': data.get('iteration', 0),
                'score': data.get('score', 0),
                'wr_s': data.get('wr_s', 0),
                'pf_s': data.get('pf_s', 0),
                'sr_s': data.get('sr_s', 0),
                'wr_t': data.get('wr_t', 0),
                'n_strict': data.get('n_strict', 0),
                'n_total': data.get('n_total', 0),
                'stagnation': data.get('stagnation', 0),
            })
    
    status['versions']['v4'] = {
        'best': v4_best,
        'latest_iter': v4_latest_data,
        'total_iters': len(v4_iter_files),
        'history': v4_history,
    }
    
    # V5优化器
    v5_best = load_json(OPT_DIR_V5 / 'v5_best_params.json')
    v5_latest = get_latest_iter_file(OPT_DIR_V5)
    v5_latest_data = load_json(v5_latest) if v5_latest else None
    
    v5_history_path = OPT_DIR_V5 / 'v5_results_history.json'
    v5_history = load_json(v5_history_path, [])
    
    status['versions']['v5'] = {
        'best': v5_best,
        'latest_iter': v5_latest_data,
        'total_iters': len(v5_history),
        'history': v5_history[-50:] if len(v5_history) > 50 else v5_history,
    }

    # V6引擎
    v6_best = load_json(OPT_DIR_V6 / 'best_params_v61.json')
    v6_ga_result = load_json(OPT_DIR_V6 / 'ga_v2_result.json')
    v6_ga_hist = v6_ga_result.get('history', []) if v6_ga_result else []
    v6_signals_full = load_json(OPT_DIR_V6 / 'v61_signals_full.json')
    
    v6_status = {
        'best': v6_best,
        'total_iters': len(v6_ga_hist),
        'history': v6_ga_hist[-20:] if v6_ga_hist else [],
        'signals': None,
        'state': 'idle',
    }
    
    if v6_signals_full:
        results = v6_signals_full.get('stocks', [])
        total_trades = sum(r.get('performance',{}).get('n_trades',0) for r in results)
        wrs = [r.get('performance',{}).get('wr',0) for r in results if r.get('performance',{}).get('n_trades',0) > 0]
        v6_status['signals'] = {
            'total_stocks': len(results),
            'avg_wr': round(sum(wrs)/len(wrs), 1) if wrs else 0,
            'wr_ge90': sum(1 for w in wrs if w >= 90),
            'wr_ge80': sum(1 for w in wrs if w >= 80),
            'wr_ge70': sum(1 for w in wrs if w >= 70),
            'total_trades': total_trades,
            'generated_at': v6_signals_full.get('generated_at', ''),
            'params': v6_signals_full.get('params', {}),
        }
        v6_status['state'] = 'complete' if v6_signals_full.get('generated_at') else 'running'
    
    # Also scan for V6 running processes
    try:
        import subprocess
        v6_procs = subprocess.run(['pgrep', '-f', 'smc_engine_v61|gen_v61'],
                                 capture_output=True, text=True, timeout=3)
        if v6_procs.stdout.strip():
            v6_status['state'] = 'running'
    except:
        pass
    
    status['versions']['v6'] = v6_status
    
    # V3优化器
    v3_best = load_json(OPT_DIR_V3 / 'best_params.json')
    v3_iter_files = get_all_iter_files(OPT_DIR_V3)
    status['versions']['v3'] = {
        'best': v3_best,
        'total_iters': len(v3_iter_files),
    }
    
    # V2优化器
    v2_best = load_json(OPT_DIR_V2 / 'best_params.json')
    status['versions']['v2'] = {
        'best': v2_best,
    }
    
    # V7+ 优化器 (新增)
    v7p_live = load_json(OPT_DIR_V7P / 'v7p_live_status.json')
    v7p_best = load_json(OPT_DIR_V7P / 'v7p_best.json')
    v7p_history = load_json(OPT_DIR_V7P / 'v7p_history.json', [])
    
    # 检测V7+是否在运行
    try:
        import subprocess
        v7p_running = subprocess.run(['pgrep', '-f', 'smc_engine_v7_plus'],
                                    capture_output=True, text=True, timeout=3)
        v7p_state_str = 'running' if v7p_running.stdout.strip() else 'idle'
    except:
        v7p_state_str = 'unknown'
    
    # 如果V7+有数据, 优先使用V7+替代V7
    if v7p_live and v7p_live.get('generation', 0) > 0:
        v7_live = v7p_live
        v7_best = v7p_best
        v7_history = v7p_history[-50:] if v7p_history else []
        v7_state_str = v7p_state_str if v7p_state_str == 'running' else v7_state_str
    else:
        # 回退到V7原本的数据
        v7_live = load_json(OPT_DIR_V7 / 'v7_live_status.json')
        v7_best = load_json(OPT_DIR_V7 / 'v7_best.json')
        v7_history = load_json(OPT_DIR_V7 / 'v7_history.json', [])
        try:
            v7_old_running = subprocess.run(['pgrep', '-f', 'smc_engine_v7'],
                                            capture_output=True, text=True, timeout=3)
            if v7_old_running.stdout.strip():
                v7_state_str = 'running'
        except:
            pass
    
    status['versions']['v7'] = {
        'live': v7_live,
        'best': v7_best,
        'history': v7_history[-50:] if v7_history else [],
        'state': v7_state_str,
        'total_iters': len(v7_history) if v7_history else len((v7_state or {}).get('generation_count', 0)),
    }

    # 代理状态 (V5优先)
    proxy_status = load_json(PROXY_STATUS_V5_FILE, {})
    if not proxy_status:
        proxy_status = load_json(PROXY_STATUS_FILE, {})
    status['proxy'] = proxy_status
    
    # 系统
    status['system'] = {
        'time': time.time(),
        'load_avg': os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0),
        'disk_free_gb': 0,
    }
    
    return status


class StatusHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
    
    def do_GET(self):
        path = self.path.rstrip('/')
        
        if path == '/api/status':
            self.json_response(collect_status())
        elif path == '/api/progress':
            status = collect_status()
            progress = {
                'v4_iters': status['versions']['v4']['total_iters'],
                'v4_best_score': status['versions']['v4'].get('best', {}).get('best_score', 0),
                'v4_best_wr_s': status['versions']['v4'].get('best', {}).get('best_wr_s', 0),
                'v4_best_pf_s': status['versions']['v4'].get('best', {}).get('best_pf_s', 0),
                'v4_latest_wr_s': status['versions']['v4'].get('latest_iter', {}).get('wr_s', 0),
                'proxy_ok': status.get('proxy', {}).get('all_ok', False),
                'v6_state': status['versions'].get('v6', {}).get('state', 'idle'),
                'v6_total_iters': status['versions'].get('v6', {}).get('total_iters', 0),
                'v6_signals_stocks': status['versions'].get('v6', {}).get('signals', {}).get('total_stocks', 0),
                'v6_avg_wr': status['versions'].get('v6', {}).get('signals', {}).get('avg_wr', 0),
                'v7_state': status['versions'].get('v7', {}).get('state', 'idle'),
                'v7_score': (status['versions'].get('v7', {}).get('live') or {}).get('best_score', 0),
                'v7_gen': (status['versions'].get('v7', {}).get('live') or {}).get('generation', 0),
                'v7_total': (status['versions'].get('v7', {}).get('live') or {}).get('total_generations', 0),
                'v7_running': status['versions'].get('v7', {}).get('state', 'idle') == 'running',
            }
            self.json_response(progress)
        elif path == '/api/best':
            status = collect_status()
            self.json_response(status['versions'])
        elif path == '/api/proxy':
            status = collect_status()
            proxy_raw = status.get('proxy', {})
            # Normalize v3 format to what WebUI expects
            state = proxy_raw.get('state', 'unknown')
            proxy_ok = state == 'healthy'
            self.json_response({
                'all_ok': proxy_ok,
                'running': proxy_raw.get('total_checks', 0) > 0,
                'api_ok': proxy_ok,
                'http_ok': proxy_ok,
                'state': state,
                'total_restarts': proxy_raw.get('total_restarts', 0),
                'total_checks': proxy_raw.get('total_checks', 0),
                'connectivity': {
                    'google': proxy_ok,
                    'github': proxy_ok,
                    'youtube': proxy_ok,
                    'overall': proxy_ok,
                },
                'timestamp': proxy_raw.get('timestamp', ''),
            })
        elif path == '/api/history':
            status = collect_status()
            self.json_response(status['versions'])
        elif path == '/api/signals':
            data = load_json(OPT_DIR_V4 / 'signal_details_full.json', [])
            self.json_response({'total': len(data), 'signals': data[:100]})
        elif path == '/api/v5/status':
            status = collect_status()
            self.json_response(status['versions'].get('v5', {}))
        elif path == '/api/v5/history':
            status = collect_status()
            self.json_response(status['versions'].get('v5', {}).get('history', []))
        elif path == '/api/v6/status':
            status = collect_status()
            self.json_response(status['versions'].get('v6', {}))
        elif path == '/api/v6/signals':
            data = load_json(OPT_DIR_V6 / 'v61_signals_full.json', {})
            stocks = data.get('stocks', [])
            self.json_response({
                'total': len(stocks),
                'generated_at': data.get('generated_at', ''),
                'params': data.get('params', {}),
                'stocks': stocks[:200],
            })
        elif path == '/api/v6/history':
            status = collect_status()
            self.json_response(status['versions'].get('v6', {}).get('history', []))
        elif path == '/api/v7/status':
            status = collect_status()
            self.json_response(status['versions'].get('v7', {}))
        elif path == '/api/v7/live':
            self.json_response(load_json(OPT_DIR_V7 / 'v7_live_status.json', {}))
        elif path == '/api/v7/history':
            status = collect_status()
            self.json_response(status['versions'].get('v7', {}).get('history', []))
        elif path == '/api/v7/progress':
            v7_live = load_json(OPT_DIR_V7 / 'v7_live_status.json', {})
            v7_best = load_json(OPT_DIR_V7 / 'v7_best.json', {})
            v7_state = load_json(OPT_DIR_V7 / 'v7_state.json', {})
            self.json_response({
                'current_iter': v7_live.get('generation', 0),
                'total_iters': v7_live.get('total_generations', 150),
                'best_score': v7_live.get('best_score', 0),
                'best_wr': v7_live.get('is_wr', 0),
                'best_oos_wr': v7_live.get('oos_wr', 0),
                'status': v7_live.get('strategy', 'idle'),
                'timestamp': v7_live.get('timestamp', ''),
            })
        elif path == '/api/v7/params':
            v7_best = load_json(OPT_DIR_V7 / 'v7_best.json', {})
            params = v7_best.get('best_params', {})
            details = v7_best.get('best_details', {})
            is_d = details.get('is', {})
            oos_d = details.get('oos', {})
            params['_score'] = v7_best.get('best_score', 0)
            params['_is_wr'] = is_d.get('wr', 0)
            params['_is_n'] = is_d.get('n', 0)
            params['_oos_wr'] = oos_d.get('wr', 0)
            params['_oos_n'] = oos_d.get('n', 0)
            params['_iter'] = v7_best.get('generation', 0)
            self.json_response(params)
        elif path == '/api/v7/proxy':
            proxy = load_json(PROXY_STATUS_V5_FILE, {})
            if not proxy:
                proxy = load_json(PROXY_STATUS_FILE, {})
            self.json_response(proxy)
        elif path == '/api/health':
            self.json_response({'status': 'ok', 'uptime': time.time() - self.server_start})
        else:
            self.json_response({'error': 'not found', 'paths': [
                '/api/status', '/api/progress', '/api/best',
                '/api/proxy', '/api/history', '/api/signals',
                '/api/v5/status', '/api/v5/history', '/api/v6/status',
                '/api/v6/signals', '/api/v6/history', '/api/health'
            ]}, 404)
    
    def json_response(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode('utf-8'))
    
    def log_message(self, format, *args):
        if '/api/' in args[0]:
            super().log_message(format, *args)
    
    server_start = time.time()


def main():
    server = HTTPServer(('0.0.0.0', PORT), StatusHandler)
    print(f"SMC Status API: http://0.0.0.0:{PORT}")
    print(f"  Endpoints:")
    print(f"    /api/status    - Full system status")
    print(f"    /api/progress  - Quick optimization progress")
    print(f"    /api/best      - Best parameters (all versions)")
    print(f"    /api/proxy     - Proxy status")
    print(f"    /api/history   - Optimization history")
    print(f"    /api/health    - Health check")
    print(f"  Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.server_close()


if __name__ == '__main__':
    main()