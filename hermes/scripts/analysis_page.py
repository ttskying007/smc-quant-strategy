#!/usr/bin/env python3
"""
SMC V7.0 — Analysis Dashboard
个股排名 + 时间趋势 + 信号性能对比 + FVG vs OB SL率
"""
import json
from pathlib import Path
from collections import defaultdict

OUT = Path('/root/.hermes/smc_opt_v21')
PER_STOCK = OUT / 'per_stock_v71.json'
TRADES = OUT / 'detailed_trades_v63.json'

def build_analysis_page():
    # Load data
    ps_data = {}
    if PER_STOCK.exists():
        ps_data = json.loads(PER_STOCK.read_bytes())
    
    trade_data = {}
    if TRADES.exists():
        trade_data = json.loads(TRADES.read_bytes())
    
    stock_stats = ps_data.get('stock_stats', {})
    monthly = ps_data.get('monthly', {})
    tf_stats = ps_data.get('tf_stats', {})
    pattern_summary = trade_data.get('pattern_summary', {})
    meta = trade_data.get('meta', {})
    
    # ═══ Top 20 stocks ═══
    ranked = sorted(stock_stats.items(), key=lambda x: (x[1]['total'] >= 3, x[1]['cum']), reverse=True)
    stock_rows = ''
    for sym, s in ranked[:20]:
        wr_color = '#3fb950' if s['wr'] >= 80 else ('#f0883e' if s['wr'] >= 60 else '#f85149')
        stock_rows += (
            f'<tr><td><code>{sym}</code></td>'
            f'<td style="text-align:right;">{s["total"]}</td>'
            f'<td style="text-align:right;color:{wr_color};font-weight:bold;">{s["wr"]}%</td>'
            f'<td style="text-align:right;">{s["avg"]:+.2f}%</td>'
            f'<td style="text-align:right;">{s["cum"]:+.1f}%</td>'
            f'<td style="text-align:right;color:#f85149;">{s["sl_rate"]}%</td>'
            f'<td style="font-size:10px;color:#58a6ff;">{s["best_pat"]}</td>'
            f'<td style="text-align:right;color:#3fb950;">{s["best_wr"]}%</td></tr>'
        )
    
    # ═══ Pattern ranking ═══
    pattern_rows = ''
    for pat, s in sorted(pattern_summary.items(), key=lambda x: -x[1]['n']):
        wr_color = '#3fb950' if s['wr'] >= 80 else ('#f0883e' if s['wr'] >= 60 else '#f85149')
        avg_color = '#3fb950' if s['avg_pnl'] > 0 else '#f85149'
        is_combo = '→' in pat
        badge = '🔗' if is_combo else '⭐'
        pattern_rows += (
            f'<tr><td>{badge} {pat}</td>'
            f'<td style="text-align:right;">{s["n"]}</td>'
            f'<td style="text-align:right;color:{wr_color};font-weight:bold;">{s["wr"]}%</td>'
            f'<td style="text-align:right;color:{avg_color};">{s["avg_pnl"]:+.2f}%</td>'
            f'<td style="text-align:right;">{s["cum_pnl"]:+.1f}%</td></tr>'
        )
    
    # ═══ Monthly trend data for chart ═══
    months_sorted = sorted(monthly.keys())
    monthly_wr = [monthly[m]['wr'] for m in months_sorted]
    monthly_avg = [monthly[m]['avg'] for m in months_sorted]
    monthly_n = [monthly[m]['n'] for m in months_sorted]
    monthly_cum = []
    running = 0
    for m in months_sorted:
        running += monthly[m]['cum']
        monthly_cum.append(round(running, 1))
    
    # ═══ Multi-TF data ═══
    tf_labels = []
    tf_wr_vals = []
    tf_avg_vals = []
    for trend in ['bullish', 'neutral', 'bearish']:
        ts = tf_stats.get(trend, {})
        if ts.get('n', 0) > 0:
            tf_labels.append(f"{trend}(n={ts['n']})")
            tf_wr_vals.append(ts['wr'])
            tf_avg_vals.append(ts['avg'])
    
    import json as jmod
    mj = jmod.dumps(months_sorted)
    wrj = jmod.dumps(monthly_wr)
    avgj = jmod.dumps(monthly_avg)
    nj = jmod.dumps(monthly_n)
    cumj = jmod.dumps(monthly_cum)
    tflj = jmod.dumps(tf_labels)
    tfwrj = jmod.dumps(tf_wr_vals)
    tfavgj = jmod.dumps(tf_avg_vals)
    
    # ═══ SL rate comparison for chart ═══
    all_trades = trade_data.get('all_trades', [])
    sl_by_pattern = defaultdict(lambda: {'total': 0, 'sl': 0})
    for t in all_trades:
        pat = t.get('pattern', '?')
        sl_by_pattern[pat]['total'] += 1
        if t.get('exit_reason') == 'sl_hit':
            sl_by_pattern[pat]['sl'] += 1
    
    sl_pats = []
    sl_rates = []
    for pat in sorted(sl_by_pattern, key=lambda x: -sl_by_pattern[x]['total']):
        s = sl_by_pattern[pat]
        if s['total'] >= 3:
            sl_pats.append(pat.split('_')[0][:12])
            sl_rates.append(round(s['sl']/s['total']*100, 1))
    
    slpj = jmod.dumps(sl_pats)
    slrj = jmod.dumps(sl_rates)
    
    meta_config = meta.get('config', '?')
    meta_wr = meta.get('wr', 0)
    meta_avg = meta.get('avg_pnl', 0)
    meta_n = meta.get('total_trades', 0)
    
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>V7.0 Analysis</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,sans-serif}}
.nav{{background:#0d1117;border-bottom:2px solid #30363d;display:flex;align-items:center;padding:0;flex-wrap:wrap}}
.nav a{{padding:12px 20px;color:#f0f6fc;text-decoration:none;font-size:14px}}
.nav a:hover{{color:#58a6ff}}
.nav .active{{color:#00d4aa;font-weight:bold;border-bottom:2px solid #00d4aa}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:20px;max-width:1600px;margin:0 auto}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}}
.card h3{{color:#f0f6fc;font-size:14px;margin-bottom:12px;border-bottom:1px solid #21262d;padding-bottom:8px}}
.chart{{width:100%;height:350px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:#0d1117;padding:6px 8px;text-align:left;color:#8b949e;font-weight:600;border-bottom:2px solid #30363d;position:sticky;top:0}}
td{{padding:5px 8px;border-bottom:1px solid #21262d}}
tr:hover{{background:#1c2128}}
.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:20px 20px 0 20px;max-width:1600px;margin:0 auto}}
.kpi-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;text-align:center}}
.kpi-label{{color:#8b949e;font-size:10px}}
.kpi-val{{font-size:24px;font-weight:bold}}
</style>
<script src="/echarts.min.js"></script></head><body>
<div style="background:#0d1117;border-bottom:2px solid #30363d;display:flex;align-items:center;padding:0;flex-wrap:wrap;">
<a href="/" style="padding:12px 20px;color:#f0f6fc;font-weight:bold;text-decoration:none;font-size:15px;">SMC V7.3</a>
<a href="/v21?s=600519.SH" style="padding:12px 16px;color:#00d4aa;text-decoration:none;font-size:13px;font-weight:bold;">📊 K线+信号</a>
<a href="/analysis" style="padding:12px 16px;color:#ffa726;text-decoration:none;font-size:13px;font-weight:bold;">📈 分析面板</a>
<a href="/monitor" style="padding:12px 16px;color:#ffa726;text-decoration:none;font-size:13px;font-weight:bold;">📡 L→D监控</a>
<span style="color:#484f58;font-size:11px;padding:12px 8px;">V7.3 Trailing-Stop | BOS→FVG主力 | 诚实回测</span>
</div>

<div class="nav">
<a href="/" style="font-weight:bold;">SMC V7.2</a>
<a href="/v21?s=600519.SH">📊 K线+信号</a>
<a href="/monitor">📡 监控</a>
<a href="/analysis" class="active">📈 分析面板</a>
</div>

<div class="kpi">
<div class="kpi-card"><div class="kpi-label">最优配置</div><div class="kpi-val" style="color:#ffa726;font-size:14px;">{meta_config}</div></div>
<div class="kpi-card"><div class="kpi-label">总交易</div><div class="kpi-val" style="color:#f0f6fc;">{meta_n}</div></div>
<div class="kpi-card"><div class="kpi-label">胜率</div><div class="kpi-val" style="color:#3fb950;">{meta_wr}%</div></div>
<div class="kpi-card"><div class="kpi-label">均收益</div><div class="kpi-val" style="color:#3fb950;">{meta_avg:+.2f}%</div></div>
</div>

<div class="grid2">
<!-- Monthly Trend -->
<div class="card">
<h3>📅 月度表现趋势</h3>
<div id="chart_monthly" class="chart"></div>
</div>

<!-- Multi-TF -->
<div class="card">
<h3>🔭 多周期共振 (周线趋势)</h3>
<div id="chart_tf" class="chart"></div>
</div>

<!-- SL Rate by Pattern -->
<div class="card">
<h3>🛑 各信号SL率对比</h3>
<div id="chart_sl" class="chart"></div>
</div>

<!-- Cumulative PnL -->
<div class="card">
<h3>💰 累计PnL曲线</h3>
<div id="chart_cum" class="chart"></div>
</div>
</div>

<!-- Stock Ranking -->
<div style="max-width:1600px;margin:0 auto;padding:0 20px 20px;">
<div class="card">
<h3>🏆 个股表现排名 (Top 20, ≥3笔)</h3>
<div style="overflow-x:auto;">
<table>
<thead><tr><th>代码</th><th>笔数</th><th>WR</th><th>均PnL</th><th>累计PnL</th><th>SL率</th><th>最优信号</th><th>bWR</th></tr></thead>
<tbody>{stock_rows}</tbody>
</table></div>
</div>
</div>

<!-- Pattern Ranking -->
<div style="max-width:1600px;margin:0 auto;padding:0 20px 20px;">
<div class="card">
<h3>📊 信号模式表现排名</h3>
<div style="overflow-x:auto;">
<table>
<thead><tr><th>信号模式</th><th>笔数</th><th>WR</th><th>均PnL</th><th>累计PnL</th></tr></thead>
<tbody>{pattern_rows}</tbody>
</table></div>
<div style="color:#8b949e;font-size:10px;margin-top:8px;">⭐单信号 | 🔗组合信号</div>
</div>
</div>

<script>
var c1 = echarts.init(document.getElementById('chart_monthly'));
c1.setOption({{
  tooltip: {{trigger:'axis'}},
  legend: {{data:['WR%','avgPnL%','交易数'],textStyle:{{color:'#8b949e'}},top:0}},
  grid: {{left:50,right:50,top:40,bottom:30}},
  xAxis: {{type:'category',data:{mj},axisLabel:{{color:'#8b949e',fontSize:9,rotate:45}}}},
  yAxis: [{{type:'value',name:'%',axisLabel:{{color:'#8b949e'}},splitLine:{{lineStyle:{{color:'#21262d'}}}}}},
          {{type:'value',name:'笔',axisLabel:{{color:'#8b949e'}},splitLine:{{show:false}}}}],
  series: [
    {{name:'WR%',type:'line',data:{wrj},lineStyle:{{color:'#3fb950',width:2}},itemStyle:{{color:'#3fb950'}},smooth:true}},
    {{name:'avgPnL%',type:'line',data:{avgj},lineStyle:{{color:'#58a6ff',width:2}},itemStyle:{{color:'#58a6ff'}},smooth:true}},
    {{name:'交易数',type:'bar',data:{nj},yAxisIndex:1,itemStyle:{{color:'rgba(255,167,38,0.3)'}},barWidth:'60%'}}
  ]
}});

var c2 = echarts.init(document.getElementById('chart_tf'));
c2.setOption({{
  tooltip: {{trigger:'axis'}},
  grid: {{left:80,right:20,top:20,bottom:50}},
  xAxis: {{type:'category',data:{tflj},axisLabel:{{color:'#8b949e',fontSize:10}}}},
  yAxis: [{{type:'value',name:'WR%',axisLabel:{{color:'#8b949e'}},splitLine:{{lineStyle:{{color:'#21262d'}}}}}},
          {{type:'value',name:'avg%',axisLabel:{{color:'#8b949e'}},splitLine:{{show:false}}}}],
  series: [
    {{name:'WR',type:'bar',data:{tfwrj},itemStyle:{{color:'#3fb950'}},barWidth:'50%',label:{{show:true,position:'top',color:'#3fb950',formatter:'{{c}}%'}}}},
    {{name:'avgPnL',type:'line',data:{tfavgj},yAxisIndex:1,lineStyle:{{color:'#ffa726',width:2}},itemStyle:{{color:'#ffa726'}},symbol:'diamond',symbolSize:10,label:{{show:true,color:'#ffa726',formatter:'{{c:+.2f}}%'}}}}
  ]
}});

var c3 = echarts.init(document.getElementById('chart_sl'));
c3.setOption({{
  tooltip: {{trigger:'axis'}},
  grid: {{left:100,right:20,top:20,bottom:80}},
  xAxis: {{type:'category',data:{slpj},axisLabel:{{color:'#8b949e',fontSize:9,rotate:45}}}},
  yAxis: {{type:'value',name:'SL率%',max:50,axisLabel:{{color:'#8b949e'}},splitLine:{{lineStyle:{{color:'#21262d'}}}}}},
  series: [{{name:'SL率',type:'bar',data:{slrj},
    itemStyle:{{color:function(p){{return p.value>25?'#f85149':p.value>15?'#f0883e':'#3fb950'}}}},
    label:{{show:true,position:'top',color:'#8b949e',formatter:'{{c}}%',fontSize:9}}
  }}]
}});

var c4 = echarts.init(document.getElementById('chart_cum'));
c4.setOption({{
  tooltip: {{trigger:'axis'}},
  grid: {{left:60,right:20,top:20,bottom:30}},
  xAxis: {{type:'category',data:{mj},axisLabel:{{color:'#8b949e',fontSize:9,rotate:45}}}},
  yAxis: {{type:'value',name:'累计PnL%',axisLabel:{{color:'#8b949e'}},splitLine:{{lineStyle:{{color:'#21262d'}}}}}},
  series: [{{name:'累计PnL',type:'line',data:{cumj},
    lineStyle:{{color:'#00d4aa',width:2.5}},itemStyle:{{color:'#00d4aa'}},
    areaStyle:{{color:{{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{{offset:0,color:'rgba(0,212,170,0.3)'}},{{offset:1,color:'rgba(0,212,170,0.02)'}}]}}}},
    smooth:true
  }}]
}});
</script>
</body></html>'''


if __name__ == '__main__':
    print(build_analysis_page()[:200])
