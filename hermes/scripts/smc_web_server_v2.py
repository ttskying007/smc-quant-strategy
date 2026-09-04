#!/usr/bin/env python3
"""
SMC Web Server v2 — 增强版HTTP文件服务器
===========================================
功能:
  1. 提供smc-webui静态文件
  2. 代理 /proxy/ 请求到SMC Status API
  3. 自动启动Status API
  4. 实时状态刷新

用法:
  python3 smc_web_server_v2.py [--port PORT]
"""

import http.server
import socketserver
import os, sys, json, subprocess, time, signal
from pathlib import Path
from urllib.request import Request, urlopen

PORT = 8877
STATUS_API_PORT = 8878
WEBUI_DIR = os.path.join(os.path.dirname(__file__), '..', 'smc-webui')

# 确保目录存在
os.makedirs(WEBUI_DIR, exist_ok=True)


class SMCWebHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEBUI_DIR, **kwargs)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        # 代理 /proxy/api/* 到 Status API
        if self.path.startswith('/proxy/api/'):
            proxy_path = self.path[6:]  # 去掉 /proxy
            api_url = f'http://127.0.0.1:{STATUS_API_PORT}{proxy_path}'
            self.proxy_request(api_url)
            return
        
        # 服务静态文件
        super().do_GET()
    
    def proxy_request(self, url):
        """代理请求到API服务器"""
        try:
            req = Request(url, headers={
                'User-Agent': 'SMC-WebUI',
            })
            resp = urlopen(req, timeout=5)
            data = resp.read()
            
            self.send_response(resp.status)
            self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            # API不可用，返回降级数据
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'error': f'API not available: {str(e)}',
                'degraded': True,
                'v4_iters': 0,
                'proxy_ok': False,
            }).encode('utf-8'))
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()
    
    def log_message(self, format, *args):
        # 不记录API请求
        if '/api/' in args[0]:
            return
        super().log_message(format, *args)


# 启动Status API (后台)
def start_status_api():
    api_script = os.path.join(os.path.dirname(__file__), 'smc_web_status_api.py')
    if os.path.exists(api_script):
        print(f"Starting Status API (port {STATUS_API_PORT})...")
        subprocess.Popen(
            ['python3', api_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(2)
        print(f"  Status API: http://localhost:{STATUS_API_PORT}")
    else:
        print(f"  ⚠ Status API script not found: {api_script}")


def main():
    parser = argparse.ArgumentParser(description='SMC Web Server v2')
    parser.add_argument('--port', type=int, default=PORT, help=f'Port (default: {PORT})')
    args = parser.parse_args()
    
    port = args.port
    
    # 启动Status API
    start_status_api()
    
    print(f"\n{'='*50}")
    print(f"SMC WebUI v2: http://0.0.0.0:{port}")
    print(f"  Static files: {WEBUI_DIR}")
    print(f"  Status API proxy: /proxy/api/")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*50}\n")
    
    with socketserver.TCPServer(("0.0.0.0", port), SMCWebHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped")
            httpd.server_close()


if __name__ == '__main__':
    import argparse
    main()