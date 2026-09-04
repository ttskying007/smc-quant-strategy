#!/usr/bin/env python3
"""
SMC V3 — 统计仪表板 (WR分布, 入口类型, Wyckoff阶段)
独立页面, port 8895, 与V2(8896)互补。
"""
import json, html
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from collections import Counter

V38_JSON = '/root/.hermes/smc_opt_v38/backtest_v384_full.json'
ECHARTS = '/tmp/echarts.min.js'

DATA = json.loads(Path(V38_JSON).read_bytes())
SUM = DATA['summary']
STOCKS = DATA['stock_results']

def stats_html():
    n_trades = SUM['n_trades']
    wr = SUM['win_rate']
    rr = SUM['avg_rr']
    pf = SUM['profit_factor']
    pnl = SUM['avg_pnl']

    # WR distribution for histogram
    wr_dist = Counter()
    for s in STOCKS:
        w = int(s['win_rate'] // 10 * 10)
        wr_dist[w] += 1
    
    wr_cats = ','.join(f'"{k}-{k+9}%"' for k in sorted(wr_dist.keys()))
    wr_vals = ','.join(str(wr_dist[k]) for k in sorted(wr_dist.keys()))
    
    # Entry type breakdown - aggregate from stock_results
    et_stats = Counter()
    for s in STOCKS:
        for k, v in s.get('entry_types', {}).items():
            et_stats[k] += v
    
    et_data = ','.join(f'{{name:"{k}",value:{v}}}' for k,v in et_stats.most_common())
    
    # Direction breakdown
    dir_stats = Counter()
    for s in STOCKS:
        for k, v in s.get('directions', {}).items():
            dir_stats[k] += v
    dir_data = ','.join(f'{{name:"{k}",value:{v}}}' for k,v in dir_stats.most_common())
    
    # Wyckoff phase breakdown
    ph_stats = Counter()
    for s in STOCKS:
        ph_stats[s.get('phase','unknown')] += 1
    ph_cats = ','.join(f'"{k}"' for k,v in ph_stats.most_common())
    ph_vals = ','.join(str(v) for k,v in ph_stats.most_common())
    
    # SL type breakdown
    sl_stats = Counter()
    for s in STOCKS:
        for k, v in s.get('sl_types', {}).items():
            sl_stats[k] += v
    sl_cats = ','.join(f'"{k}"' for k,v in sl_stats.most_common(10))
    sl_vals = ','.join(str(v) for k,v in sl_stats.most_common(10))
    
    # WR >= 80% stocks list
    top_stocks = sorted([s for s in STOCKS if s['win_rate'] >= 100],
                        key=lambda x: x['n_trades'], reverse=True)[:30]
    top_rows = ''.join(f'<tr><td>{s["symbol"]}</td><td>{s["n_trades"]}</td>'
                       f'<td>{s["win_rate"]:.0f}%</td><td>{s["profit_factor"]:.0f}</td></tr>'
                       for s in top_stocks)

    return f'''<!DOCTYPE html><html><head>
<meta charset="utf-8"><title>SMC V3 统计仪表板</title>
<script src="{ECHARTS}"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:system-ui,sans-serif; padding:20px; }}
  h1 {{ color:#00d4aa; font-size:1.5em; margin-bottom:20px; }}
  .row {{ display:flex; gap:20px; flex-wrap:wrap; }}
  .card {{ background:#16213e; border-radius:12px; padding:20px; min-width:300px; flex:1; }}
  .card h2 {{ color:#ffd700; font-size:1em; margin-bottom:15px; border-bottom:1px solid #333; padding-bottom:8px; }}
  .metric {{ display:inline-block; margin:8px 16px 8px 0; }}
  .metric .val {{ font-size:1.8em; font-weight:bold; display:block; }}
  .metric .lbl {{ font-size:0.75em; color:#888; }}
  .chart {{ height:300px; margin-top:10px; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.85em; }}
  th, td {{ padding:6px 10px; text-align:left; border-bottom:1px solid #2a2a50; }}
  th {{ color:#00d4aa; font-weight:normal; }}
  .green {{ color:#4caf50; }} .red {{ color:#f44336; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:0.75em; margin:2px; }}
</style></head><body>
<h1>SMC V38 全量4800 统计仪表板</h1>

<div class="row">
  <div class="card">
    <h2>核心指标</h2>
    <div class="metric"><span class="val green">{wr:.1f}%</span><span class="lbl">WR</span></div>
    <div class="metric"><span class="val">{rr:.2f}x</span><span class="lbl">RR</span></div>
    <div class="metric"><span class="val">{pf:.0f}</span><span class="lbl">PF</span></div>
    <div class="metric"><span class="val">{pnl:+.2f}%</span><span class="lbl">P&L</span></div>
    <div class="metric"><span class="val">{n_trades}</span><span class="lbl">Trades</span></div>
    <div class="metric"><span class="val">{len(STOCKS)}/{len(STOCKS)}</span><span class="lbl">Tradable</span></div>
  </div>
</div>

<div class="row">
  <div class="card">
    <h2>WR 分布</h2>
    <div id="wrChart" class="chart"></div>
  </div>
  <div class="card">
    <h2>入口类型</h2>
    <div id="etChart" class="chart"></div>
  </div>
</div>

<div class="row">
  <div class="card">
    <h2>方向 & 阶段</h2>
    <div id="dirChart" class="chart" style="height:200px"></div>
    <div id="phChart" class="chart" style="height:200px"></div>
  </div>
  <div class="card">
    <h2>SL类型</h2>
    <div id="slChart" class="chart"></div>
  </div>
</div>

<div class="row">
  <div class="card">
    <h2>WR=100% 股票 (n≥5)</h2>
    <div style="max-height:400px;overflow-y:auto">
    <table><tr><th>Symbol</th><th>Trades</th><th>WR</th><th>PF</th></tr>{top_rows}</table>
    </div>
  </div>
</div>

<script>
echarts.init(document.getElementById('wrChart')).setOption({{
  tooltip: {{ trigger:'axis' }},
  xAxis: {{ type:'category', data:[{wr_cats}], axisLabel:{{color:'#888'}} }},
  yAxis: {{ type:'value', axisLabel:{{color:'#888'}} }},
  series: [{{ type:'bar', data:[{wr_vals}], itemStyle:{{color:'#00d4aa'}}, barWidth:'80%' }}],
  grid: {{ top:20, bottom:40, left:50, right:20 }}
}});
echarts.init(document.getElementById('etChart')).setOption({{
  tooltip: {{ trigger:'item', formatter:'{{b}}: {{c}} ({{d}}%)' }},
  series: [{{ type:'pie', radius:['30%','70%'], data:[{et_data}],
    label:{{color:'#ccc',fontSize:11}},
    itemStyle:{{borderColor:'#1a1a2e',borderWidth:2}} }}]
}});
echarts.init(document.getElementById('dirChart')).setOption({{
  tooltip: {{ trigger:'item' }},
  series: [{{ type:'pie', radius:['20%','50%'], data:[{dir_data}],
    label:{{color:'#ccc',fontSize:11}},
    itemStyle:{{borderColor:'#1a1a2e',borderWidth:2}} }}]
}});
echarts.init(document.getElementById('phChart')).setOption({{
  tooltip: {{ trigger:'axis' }},
  xAxis: {{ type:'category', data:[{ph_cats}], axisLabel:{{color:'#888',rotate:30}} }},
  yAxis: {{ type:'value', axisLabel:{{color:'#888'}} }},
  series: [{{ type:'bar', data:[{ph_vals}], itemStyle:{{color:'#ffd700'}}, barWidth:'60%' }}],
  grid: {{ top:20, bottom:60, left:50, right:20 }}
}});
echarts.init(document.getElementById('slChart')).setOption({{
  tooltip: {{ trigger:'axis' }},
  xAxis: {{ type:'category', data:[{sl_cats}], axisLabel:{{color:'#888',rotate:30}} }},
  yAxis: {{ type:'value', axisLabel:{{color:'#888'}} }},
  series: [{{ type:'bar', data:[{sl_vals}], itemStyle:{{color:'#7c4dff'}}, barWidth:'60%' }}],
  grid: {{ top:20, bottom:60, left:50, right:20 }}
}});
</script>
</body></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(stats_html().encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, *a):
        pass

if __name__ == '__main__':
    port = 8894
    srv = HTTPServer(('0.0.0.0', port), Handler)
    print(f"SMC V3 Dashboard on http://localhost:{port}")
    srv.serve_forever()
