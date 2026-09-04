#!/usr/bin/env python3
"""SMC V5.5 Status API — 轻量版"""
import http.server, socketserver, json, time, subprocess, os
from pathlib import Path

PORT = 8879
OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v55'

def lj(path, default=None):
    try:
        if path and os.path.exists(path):
            return json.load(open(path))
    except:
        pass
    return default

def proxy_status():
    s = {'running': False, 'port_7890': False, 'state': 'unknown'}
    try:
        pid = subprocess.check_output(['pgrep', '-o', '-x', 'mihomo'], timeout=2, stderr=subprocess.DEVNULL).strip()
        if pid: s['running'] = True; s['state'] = 'healthy'
    except:
        pass
    try:
        ss = subprocess.check_output(['ss', '-tlnp'], timeout=3, stderr=subprocess.DEVNULL).decode()
        s['port_7890'] = ':7890' in ss
    except:
        pass
    s['all_ok'] = s['running'] and s['port_7890']
    return s

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.rstrip('/')
        try:
            if p == '/api/health':
                self.r({'status':'ok','uptime':int(time.time()-self._start),'t':time.strftime('%H:%M:%S')})
            elif p == '/api/status':
                fp = lj(OPT_DIR / 'final.json', {})
                running = False
                try:
                    o = subprocess.check_output(['pgrep','-f','smc_opt_v55'], timeout=2, stderr=subprocess.DEVNULL)
                    running = bool(o.strip())
                except:
                    pass
                hist = fp.get('history', [])[-30:]
                fe = fp.get('final_eval', {})
                self.r({
                    'v5_5': {
                        'best_score': fp.get('best_score', 0),
                        'is_running': running,
                        'best_params': fp.get('best_params', {}),
                        'history': [{'r':h.get('r',i),'score':h.get('score',0),'wr':h.get('wr',0),'pf':h.get('pf',0),'n':h.get('n',0)} for i,h in enumerate(hist)],
                        'final_wr': fe.get('wr', 0),
                        'final_pf': fe.get('pf', 0),
                        'final_n': fe.get('n', 0),
                        'final_ret': fe.get('ret', 0),
                        'stocks_sig': fe.get('stocks_sig', 0),
                    },
                    'proxy': proxy_status(),
                })
            elif p == '/api/progress':
                fp = lj(OPT_DIR / 'final.json', {})
                fe = fp.get('final_eval', {})
                self.r({
                    'best_score': fp.get('best_score', 0),
                    'wr': fe.get('wr', 0),
                    'pf': fe.get('pf', 0),
                    'n': fe.get('n', 0),
                    'ret': fe.get('ret', 0),
                    'sig': fe.get('stocks_sig', 0),
                })
            elif p == '/api/proxy':
                self.r(proxy_status())
            elif p == '/api/signals':
                self.r({'stocks_found': 0, 'signals': [], 'total_signals': 0})
            else:
                self.r({'error': 'not found'}, 404)
        except Exception as e:
            self.r({'error': str(e)}, 500)
    
    def r(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())
    
    def log_message(self, *a): pass
    _start = time.time()

if __name__ == '__main__':
    srv = socketserver.TCPServer(('0.0.0.0', PORT), H)
    print(f"SMC API v5.5 on :{PORT}")
    try:
        srv.serve_forever()
    except:
        srv.server_close()