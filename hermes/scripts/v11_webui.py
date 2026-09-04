#!/usr/bin/env python3
# SMC V11 — WebUI Server (port 8895)
"""
用法: python3 v11_webui.py [--port 8895]
"""

import json, logging, http.server, os, sys, urllib.parse
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('v11.webui')

PORT = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == '--port' else 8895

HTML_PATH = Path(__file__).parent / 'v11_webui.html'
API_BASE = "http://43.167.234.49:3101"

class V11Handler(http.server.BaseHTTPRequestHandler):
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        
        try:
            if path == '/' or path == '/index.html':
                self.serve_html()
            elif path == '/api/analyze':
                symbol = params.get('symbol', ['600519.SH'])[0]
                self.analyze_symbol(symbol)
            elif path == '/api/status':
                self.system_status()
            elif path == '/api/stats':
                self.limiter_stats()
            else:
                self.send_error(404, 'Not found')
        except Exception as e:
            log.error(f"Error handling {path}: {e}")
            self.send_json({'error': str(e)}, 500)
    
    def serve_html(self):
        if HTML_PATH.exists():
            html = HTML_PATH.read_text()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_error(404, 'HTML not found')
    
    def analyze_symbol(self, symbol):
        """完整分析一个股票"""
        data = run_analysis(symbol)
        self.send_json(data)
    
    def system_status(self):
        """系统状态"""
        from v11.rate_limiter import get_limiter
        limiter = get_limiter()
        stats = limiter.get_stats()
        
        status = {
            'status': 'running',
            'version': '11.0.0',
            'limiter': {
                'total_requests': stats['total_requests'],
                '429_count': stats['429_count'],
                'cache_hits': stats['cache_hits'],
                'cache_hit_rate': stats.get('cache_hit_rate', 0),
                'tokens_available': stats.get('tokens_available', 0),
            },
            'port': PORT,
            'api_base': API_BASE,
        }
        self.send_json(status)
    
    def limiter_stats(self):
        from v11.rate_limiter import get_limiter
        stats = get_limiter().get_stats()
        self.send_json(stats)
    
    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())
    
    def log_message(self, format, *args):
        log.info(f"{self.client_address[0]} - {format % args}")


def run_analysis(symbol):
    """对一个股票运行完整的V11分析管道"""
    from v11.tf_data import fetch_multi_tf
    from v11.rate_limiter import get_limiter
    from v11.signals_v11 import detect_all_signals_v11
    from v11.sequencer_v11 import analyze_sequence_v11, score_entry_v11
    from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
    from v11.adaptive_params import calc_stock_params, detect_market_phase
    
    limiter = get_limiter()
    
    # 1. 获取多周期数据
    tf_data = fetch_multi_tf(symbol, tfs=['daily', '4h', '1h'], limiter=limiter)
    daily_ohlcv = tf_data.get('daily', [])
    
    if not daily_ohlcv or len(daily_ohlcv) < 30:
        return {'error': f'Insufficient data for {symbol}', 'data_length': len(daily_ohlcv)}
    
    # 2. 自适应参数
    phase = detect_market_phase(daily_ohlcv)
    params = calc_stock_params(daily_ohlcv, symbol=symbol, phase=phase, tf='daily')
    
    # 3. 信号检测
    sig_result = detect_all_signals_v11(daily_ohlcv, params=params, tf='daily')
    all_signals = sig_result['all']
    
    # 4. 序列分析
    seq_result = analyze_sequence_v11(all_signals, params=params)
    
    # 5. 共振评估
    resonance = evaluate_full_resonance_v11(
        all_signals=all_signals,
        ohlcv=daily_ohlcv,
    )
    
    # 6. 入场决策
    decision = make_entry_decision_v11(resonance, seq_result, params)
    
    return {
        'symbol': symbol,
        'phase': phase,
        'adaptive_thresholds': sig_result['adaptive'],
        'signal_stats': sig_result['stats'],
        'signals': all_signals[-50:],  # 最近50个信号
        'sequence': seq_result,
        'resonance': resonance.to_dict(),
        'decision': decision,
        'params': {k: v for k, v in params.items() if not k.startswith('_')},
        'data_bars': {
            'daily': len(tf_data.get('daily', [])),
            '4h': len(tf_data.get('4h', [])),
            '1h': len(tf_data.get('1h', [])),
        },
    }


def main():
    server = http.server.HTTPServer(('0.0.0.0', PORT), V11Handler)
    log.info(f"SMC V11 WebUI running on http://0.0.0.0:{PORT}")
    log.info(f"  Analyze: http://localhost:{PORT}/api/analyze?symbol=600519.SH")
    log.info(f"  Dashboard: http://localhost:{PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
