#!/usr/bin/env python3
"""
SMC Web Server V3 — Python自带http.server + 代理
用法: python3 smc_web_server_v3.py [--port PORT] [--api-port API_PORT]
"""
import http.server, socketserver, urllib.request, json, os, sys
from pathlib import Path

PORT = int(sys.argv[sys.argv.index('--port')+1]) if '--port' in sys.argv else 8877
API_PORT = int(sys.argv[sys.argv.index('--api-port')+1]) if '--api-port' in sys.argv else 8878
WEBUI_DIR = os.path.expanduser('~/hermes-webui/smc-webui')
WEBUI_V82 = os.path.join(WEBUI_DIR, 'index.html')

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEBUI_DIR, **kw)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/proxy/api/v8/'):
            # V8 API (port 8879)
            target_path = self.path[14:]  # strip /proxy/api/v8
            target = f'http://127.0.0.1:8879{target_path}'
        elif self.path.startswith('/proxy/api/v7/'):
            # V7 API (port 8878)
            target_path = self.path[12:]  # strip /proxy/api/v7
            target = f'http://127.0.0.1:8878{target_path}'
        elif self.path.startswith('/proxy/api/'):
            # Combined: try V8 first, fallback V7
            target_path = self.path[11:]  # strip /proxy/api
            # /status -> /api/status on 8879 (V8)
            target = f'http://127.0.0.1:8879/api{target_path}'
            try:
                req = urllib.request.Request(target)
                resp = urllib.request.urlopen(req, timeout=10)
                data = resp.read()
                self.send_response(resp.status)
                self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e), 'degraded': True}).encode())
            return
        super().do_GET()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

os.makedirs(WEBUI_DIR, exist_ok=True)
server = socketserver.TCPServer(('0.0.0.0', PORT), Handler)
print(f"SMC Web V3: http://0.0.0.0:{PORT}")
print(f"  Serving: {WEBUI_DIR}")
print(f"  Proxy: /proxy/* -> 127.0.0.1:{API_PORT}")
try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()