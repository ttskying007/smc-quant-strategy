#!/usr/bin/env python3
"""
SMC Navigator — 全量市场导航 + 实时分析 WebUI v3
端口: 8896 (不冲突v2)
"""
import json, sys, os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
V13_DIR = Path('/root/.hermes/smc_opt_v13')
V14_DIR = Path('/root/.hermes/smc_opt_v14')

PORT = 8896

# ============================================================
# 加载全量数据
# ============================================================
def load_full_market():
    """加载V13所有批次结果"""
    all_stocks = []
    for f in sorted(V13_DIR.glob('batch_*.json')):
        if 'merged' in f.name: continue
        data = json.loads(f.read_text())
        all_stocks.extend(data.get('stocks', []))
    return all_stocks

def load_v14_optimized():
    """加载V14参数优化结果"""
    stocks = []
    for f in sorted(V14_DIR.glob('v14_*.json')):
        data = json.loads(f.read_text())
        stocks.extend(data.get('stocks', []))
    return stocks

# Pre-load
ALL_STOCKS = load_full_market()
V14_STOCKS = load_v14_optimized()

# Build lookup
STOCK_LOOKUP = {s['symbol']: s for s in ALL_STOCKS}
V14_LOOKUP = {s['symbol']: s for s in V14_STOCKS}

def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data

def get_symbols_with_backtest():
    return sorted(STOCK_LOOKUP.keys())

def get_symbols_with_v14():
    return sorted(V14_LOOKUP.keys())


# ============================================================
# HTTP Handler
# ============================================================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        if path == '/':
            self.send_html()
        elif path == '/api/status':
            self.send_json({
                'version': 'SMC Navigator v3',
                'total_cached': len(list(CACHE_DIR.glob('*_daily_300.json'))),
                'v13_tradable': len(ALL_STOCKS),
                'v14_tradable': len(V14_STOCKS),
            })
        elif path == '/api/symbols':
            self.send_json(get_symbols_with_backtest())
        elif path == '/api/v14-symbols':
            self.send_json(get_symbols_with_v14())
        elif path == '/api/analyze':
            symbol = params.get('symbol', [''])[0]
            if not symbol: self.send_error(400, 'symbol required')
            self.handle_analyze(symbol.upper())
        elif path == '/api/market-overview':
            self.handle_market_overview()
        elif path == '/api/optimized':
            self.handle_optimized()
        else:
            self.send_error(404)
    
    def handle_analyze(self, symbol):
        data = load_ohlcv(symbol)
        if not data:
            self.send_json({'error': f'No data for {symbol}'})
            return
        
        phase = detect_market_phase(data)
        params = calc_stock_params(data, symbol, phase=phase, tf='daily')
        result = detect_all_signals_v11(data, params=params, tf='daily')
        signals = result['all']
        
        seq_result = analyze_sequence_v11(signals, params=params)
        best_seq = seq_result.get('best_sequence', {})
        
        tf_sequences = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(
            all_signals=signals, tf_sequences=tf_sequences, ohlcv=data
        )
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        
        v13_info = STOCK_LOOKUP.get(symbol, {})
        v14_info = V14_LOOKUP.get(symbol, {})
        
        self.send_json({
            'symbol': symbol,
            'phase': phase,
            'bars': len(data),
            'signals': len(signals),
            'best_sequence': best_seq.get('name', 'NONE'),
            'resonance': {
                'total': round(resonance.total, 3),
                'grade': resonance.grade(),
            },
            'decision': {
                'action': decision['action'],
                'confidence': round(decision['confidence'], 3),
                'direction': decision.get('direction', ''),
            },
            'v13': {
                'win_rate': v13_info.get('win_rate', 0),
                'n_trades': v13_info.get('n_trades', 0),
                'avg_rr': v13_info.get('avg_rr', 0),
                'profit_factor': v13_info.get('profit_factor', 0),
            } if v13_info else None,
            'v14_optimized': {
                'sl_pct': v14_info.get('perf', {}).get('sl_pct', 0),
                'tp_pct': v14_info.get('perf', {}).get('tp_pct', 0),
                'win_rate': v14_info.get('perf', {}).get('win_rate', 0),
                'n_trades': v14_info.get('perf', {}).get('n_trades', 0),
                'avg_rr': v14_info.get('perf', {}).get('avg_rr', 0),
            } if v14_info else None,
        })
    
    def handle_market_overview(self):
        # Aggregate stats
        total = len(ALL_STOCKS)
        wr_dist = {}
        for lo, hi in [(0,30), (30,50), (50,60), (60,70), (70,80), (80,90), (90,101)]:
            cnt = sum(1 for s in ALL_STOCKS if lo <= s['win_rate'] < hi)
            if cnt:
                wr_dist[f'{lo}-{hi}%'] = cnt
        
        phase_dist = {}
        from collections import Counter
        pc = Counter(s.get('phase','?') for s in ALL_STOCKS)
        for p, c in pc.most_common():
            phase_dist[p] = c
        
        top50 = sorted(ALL_STOCKS, 
                       key=lambda s: -(s['win_rate']**2 * s['avg_rr'] * min(3, s['n_trades']/5))
                      )[:50]
        
        self.send_json({
            'tradable': total,
            'total_trades': sum(s['n_trades'] for s in ALL_STOCKS),
            'avg_win_rate': round(sum(s['win_rate'] for s in ALL_STOCKS)/total, 1) if total else 0,
            'avg_rr': round(sum(s['avg_rr'] for s in ALL_STOCKS)/total, 2) if total else 0,
            'wr_distribution': wr_dist,
            'phase_distribution': phase_dist,
            'top50': [{
                'symbol': s['symbol'],
                'win_rate': s['win_rate'],
                'n_trades': s['n_trades'],
                'avg_rr': s['avg_rr'],
                'profit_factor': s['profit_factor'],
                'phase': s.get('phase', ''),
            } for s in top50],
        })
    
    def handle_optimized(self):
        if not V14_STOCKS:
            self.send_json({'error': 'V14 optimization data not available yet'})
            return
        
        total = len(V14_STOCKS)
        sl_dist = {}
        tp_dist = {}
        from collections import Counter
        slc = Counter(s.get('perf',{}).get('sl_pct',0) for s in V14_STOCKS)
        tpc = Counter(s.get('perf',{}).get('tp_pct',0) for s in V14_STOCKS)
        for v, c in slc.most_common(): sl_dist[f'SL={v}%'] = c
        for v, c in tpc.most_common(): tp_dist[f'TP={v}%'] = c
        
        top = sorted(V14_STOCKS, key=lambda s: -s.get('perf',{}).get('score',0))[:30]
        
        self.send_json({
            'tradable': total,
            'avg_win_rate': round(sum(s.get('perf',{}).get('win_rate',0) for s in V14_STOCKS)/total, 1),
            'avg_rr': round(sum(s.get('perf',{}).get('avg_rr',0) for s in V14_STOCKS)/total, 2),
            'sl_distribution': sl_dist,
            'tp_distribution': tp_dist,
            'top30': [{
                'symbol': s['symbol'],
                'win_rate': s.get('perf',{}).get('win_rate', 0),
                'n_trades': s.get('perf',{}).get('n_trades', 0),
                'avg_rr': s.get('perf',{}).get('avg_rr', 0),
                'sl_pct': s.get('perf',{}).get('sl_pct', 0),
                'tp_pct': s.get('perf',{}).get('tp_pct', 0),
                'phase': s.get('phase', ''),
            } for s in top],
        })
    
    def send_html(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        
        html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>SMC Navigator v3 — 全量市场导航</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }
.container { max-width: 1400px; margin: 0 auto; }
h1 { color: #00ff88; font-size: 24px; margin-bottom: 20px; }
h2 { color: #00ccff; font-size: 18px; margin: 20px 0 10px; }
.card { background: #141420; border: 1px solid #2a2a3a; border-radius: 8px; padding: 15px; margin-bottom: 15px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; }
.stat { font-size: 28px; font-weight: bold; color: #00ff88; }
.stat-label { color: #888; font-size: 12px; text-transform: uppercase; }
.bar-wrap { background: #1a1a2a; border-radius: 4px; height: 20px; margin: 5px 0; overflow: hidden; }
.bar { height: 100%; background: linear-gradient(90deg, #00ff88, #00ccff); border-radius: 4px; transition: width 0.5s; }
.bar-label { display: flex; justify-content: space-between; font-size: 11px; margin-top: 2px; color: #888; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { text-align: left; padding: 8px 4px; border-bottom: 1px solid #2a2a3a; color: #00ccff; }
td { padding: 6px 4px; border-bottom: 1px solid #1a1a2a; }
tr:hover { background: #1a1a2a; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: bold; }
.badge-high { background: #00ff8844; color: #00ff88; }
.badge-mid { background: #ffaa0044; color: #ffaa00; }
.badge-low { background: #ff444444; color: #ff4444; }
input, select { background: #1a1a2a; border: 1px solid #2a2a3a; color: #e0e0e0; padding: 8px 12px; border-radius: 4px; font-size: 14px; width: 100%; }
button { background: #00ff88; color: #000; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; }
button:hover { background: #00cc66; }
#analysis { white-space: pre-wrap; font-family: monospace; font-size: 12px; }
.loading { color: #888; font-style: italic; }
</style>
</head>
<body>
<div class="container">
<h1>SMC Navigator v3 — 全量市场导航</h1>

<div class="grid" id="stats">
  <div class="card"><div class="stat" id="stat-total">-</div><div class="stat-label">可交易股票</div></div>
  <div class="card"><div class="stat" id="stat-trades">-</div><div class="stat-label">总交易数</div></div>
  <div class="card"><div class="stat" id="stat-wr">-</div><div class="stat-label">平均胜率</div></div>
  <div class="card"><div class="stat" id="stat-rr">-</div><div class="stat-label">平均盈亏比</div></div>
</div>

<div class="grid">
  <div class="card">
    <h2>胜率分布 (V13)</h2>
    <div id="wr-dist"></div>
  </div>
  <div class="card">
    <h2>阶段分布</h2>
    <div id="phase-dist"></div>
  </div>
</div>

<div class="card">
  <h2>V14 每股参数优化</h2>
  <div id="v14-optimized" class="loading">加载中...</div>
</div>

<div class="card">
  <h2>实时分析</h2>
  <div style="display:flex; gap:10px; margin-bottom:10px">
    <input id="symbol-input" placeholder="输入股票代码 (000001.SZ)" list="symbols">
    <datalist id="symbols"></datalist>
    <button onclick="analyze()">分析</button>
  </div>
  <div id="analysis" class="loading">等待输入...</div>
</div>

<div class="card">
  <h2>V13 TOP 50 最佳股票</h2>
  <div style="max-height:400px; overflow-y:auto">
    <table><thead><tr>
      <th>排名</th><th>代码</th><th>胜率</th><th>交易数</th><th>盈亏比</th><th>PF</th><th>阶段</th>
    </tr></thead><tbody id="top50-table"></tbody></table>
  </div>
</div>
</div>

<script>
async function loadMarket() {
  const r = await fetch('/api/market-overview');
  const d = await r.json();
  
  document.getElementById('stat-total').textContent = d.tradable;
  document.getElementById('stat-trades').textContent = d.total_trades;
  document.getElementById('stat-wr').textContent = d.avg_win_rate + '%';
  document.getElementById('stat-rr').textContent = d.avg_rr;
  
  // WR distribution
  const wrDiv = document.getElementById('wr-dist');
  wrDiv.innerHTML = '';
  for (const [bucket, cnt] of Object.entries(d.wr_distribution)) {
    const pct = (cnt / d.tradable * 100).toFixed(1);
    wrDiv.innerHTML += '<div class="bar-label"><span>' + bucket + ' (' + cnt + ')</span><span>' + pct + '%</span></div>' +
      '<div class="bar-wrap"><div class="bar" style="width:' + pct + '%"></div></div>';
  }
  
  // Phase distribution
  const phDiv = document.getElementById('phase-dist');
  phDiv.innerHTML = '';
  for (const [phase, cnt] of Object.entries(d.phase_distribution)) {
    const pct = (cnt / d.tradable * 100).toFixed(1);
    phDiv.innerHTML += '<div class="bar-label"><span>' + phase + ' (' + cnt + ')</span><span>' + pct + '%</span></div>' +
      '<div class="bar-wrap"><div class="bar" style="width:' + pct + '%"></div></div>';
  }
  
  // Top 50
  const tbl = document.getElementById('top50-table');
  tbl.innerHTML = '';
  d.top50.forEach((s, i) => {
    const badge = s.win_rate >= 80 ? 'badge-high' : s.win_rate >= 60 ? 'badge-mid' : 'badge-low';
    tbl.innerHTML += '<tr><td>' + (i+1) + '</td><td><b>' + s.symbol + '</b></td>' +
      '<td><span class="badge ' + badge + '">' + s.win_rate + '%</span></td>' +
      '<td>' + s.n_trades + '</td><td>' + s.avg_rr + 'x</td><td>' + s.profit_factor + '</td><td>' + s.phase + '</td></tr>';
  });
  
  // Symbols for datalist
  const symR = await fetch('/api/symbols');
  const syms = await symR.json();
  document.getElementById('symbols').innerHTML = syms.slice(0, 200).map(s => '<option value="' + s + '">').join('');
}

async function loadV14() {
  const r = await fetch('/api/optimized');
  const d = await r.json();
  if (d.error) { document.getElementById('v14-optimized').textContent = d.error; return; }
  
  let html = '<div class="grid" style="margin-bottom:10px">';
  html += '<div><span class="stat">' + d.tradable + '</span><div class="stat-label">优化股票</div></div>';
  html += '<div><span class="stat">' + d.avg_win_rate + '%</span><div class="stat-label">平均胜率</div></div>';
  html += '<div><span class="stat">' + d.avg_rr + 'x</span><div class="stat-label">平均盈亏比</div></div>';
  html += '</div>';
  
  html += '<div style="display:flex; gap:40px; margin-bottom:10px">';
  html += '<div><b>SL分布:</b><br>';
  for (const [k, v] of Object.entries(d.sl_distribution)) html += k + ': ' + v + '<br>';
  html += '</div><div><b>TP分布:</b><br>';
  for (const [k, v] of Object.entries(d.tp_distribution)) html += k + ': ' + v + '<br>';
  html += '</div></div>';
  
  html += '<table><thead><tr><th>代码</th><th>胜率</th><th>交易数</th><th>RR</th><th>SL</th><th>TP</th><th>阶段</th></tr></thead><tbody>';
  d.top30.forEach(s => {
    const badge = s.win_rate >= 80 ? 'badge-high' : s.win_rate >= 60 ? 'badge-mid' : 'badge-low';
    html += '<tr><td><b>' + s.symbol + '</b></td>' +
      '<td><span class="badge ' + badge + '">' + s.win_rate + '%</span></td>' +
      '<td>' + s.n_trades + '</td><td>' + s.avg_rr + 'x</td>' +
      '<td>' + s.sl_pct + '%</td><td>' + s.tp_pct + '%</td><td>' + s.phase + '</td></tr>';
  });
  html += '</tbody></table>';
  
  document.getElementById('v14-optimized').innerHTML = html;
}

async function analyze() {
  const sym = document.getElementById('symbol-input').value.trim();
  if (!sym) return;
  
  document.getElementById('analysis').textContent = '分析中...';
  const r = await fetch('/api/analyze?symbol=' + encodeURIComponent(sym));
  const d = await r.json();
  
  document.getElementById('analysis').textContent = JSON.stringify(d, null, 2);
}

loadMarket();
loadV14();
</script>
</body>
</html>
'''
        self.wfile.write(html.encode('utf-8'))
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def send_error(self, code, msg=''):
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(f'Error {code}: {msg}'.encode())
    
    def log_message(self, format, *args):
        pass  # quiet


if __name__ == '__main__':
    print(f'SMC Navigator v3 running on http://localhost:{PORT}')
    print(f'  V13 tradable stocks: {len(ALL_STOCKS)}')
    print(f'  V14 optimized stocks: {len(V14_STOCKS)}')
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
