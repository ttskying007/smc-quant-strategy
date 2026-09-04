#!/usr/bin/env python3
"""
SMC Web Server V4 — Python http.server + 代理路由 + V8/V7状态API
用法: python3 smc_web_server_v4.py [--port PORT] [--api-v8 V8_PORT]
"""
import http.server, socketserver, urllib.request, json, os, sys
from pathlib import Path

PORT = int(sys.argv[sys.argv.index('--port')+1]) if '--port' in sys.argv else 8877
V8_API_PORT = int(sys.argv[sys.argv.index('--api-v8')+1]) if '--api-v8' in sys.argv else 8879
WEBUI_DIR = os.path.expanduser('~/hermes-webui/smc-webui')

V8_API = f'http://127.0.0.1:{V8_API_PORT}'

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEBUI_DIR, **kw)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _proxy_request(self, target_url):
        """代理请求到后端API并返回结果"""
        try:
            req = urllib.request.Request(target_url)
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read()
            self.send_response(resp.status)
            self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e), 'degraded': True, 'target': target_url}).encode())

    def do_GET(self):
        path = self.path

        # API路由: /proxy/api/v8/status
        if path.startswith('/proxy/api/v8/'):
            suffix = path[14:]  # strip /proxy/api/v8
            self._proxy_request(f'{V8_API}{suffix}')
            return

        # API路由: /proxy/api/v7/status  
        if path.startswith('/proxy/api/v7/'):
            suffix = path[14:]  # strip /proxy/api/v7
            self._proxy_request(f'{V8_API}/api/v7/status')
            return

        # 综合API
        if path.startswith('/proxy/api/'):
            suffix = path[11:]  # strip /proxy/api -> /status
            self._proxy_request(f'{V8_API}/api{"/status" if not suffix else suffix}')
            return

        # 默认: 服务静态文件
        super().do_GET()

    def end_headers(self):
        self._cors_headers()
        super().end_headers()

os.makedirs(WEBUI_DIR, exist_ok=True)
server = socketserver.TCPServer(('0.0.0.0', PORT), Handler)
print(f"SMC Web V4: http://0.0.0.0:{PORT}")
print(f"  Serving: {WEBUI_DIR}")
print(f"  V8 API: /proxy/api/v8/* -> {V8_API}")
try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()