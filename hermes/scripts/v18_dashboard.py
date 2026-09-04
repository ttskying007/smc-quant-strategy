#!/usr/bin/env python3
"""V18 Dashboard — V17 Entry-at-Zone 回测结果仪表板"""
import json
from pathlib import Path
from collections import Counter

RESULT_FILE = '/root/.hermes/smc_opt_v17/v17_backtest_4800_v6.json'

def build_v18(nav=''):
    data = json.loads(Path(RESULT_FILE).read_bytes())
    summary = data['summary']
    stocks = data['stock_results']
    trades = data['all_trades']
    
    # Stats
    wr = summary['wr']
    avg_pnl = summary['avg_pnl']
    total_trades = summary['total_trades']
    n_stocks = summary['stocks_traded']
    avg_hold = summary['avg_hold_bars']
    
    # WR distribution
    wr_bins = Counter()
    for s in stocks:
        if s['n_trades'] > 0:
            bucket = int(s['wr'] / 10) * 10
            wr_bins[bucket] += 1
    
    # Exit methods for chart
    exits = summary['exit_methods']
    
    # SL sources for chart
    sl_src = summary['sl_sources']
    
    # Entry sources for chart
    entry_src = summary['entry_sources']
    
    # Top/Bottom stocks table
    traded = [s for s in stocks if s['n_trades'] >= 3]
    top_wr = sorted(traded, key=lambda x: -x['wr'])[:10]
    top_pnl = sorted(traded, key=lambda x: -x['total_pnl'])[:10]
    
    # Score distribution
    scores = summary['score_distribution']
    
    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>V17 Entry-at-Zone Dashboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d1117;color:#c9d1d9;font-family:sans-serif}}
.header{{background:#161b22;padding:20px;border-bottom:1px solid #30363d}}
.header h1{{font-size:24px;color:#f0f6fc}}
.header .sub{{color:#8b949e;font-size:13px;margin-top:5px}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:15px;padding:20px}}
.kpi{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;text-align:center}}
.kpi .value{{font-size:32px;font-weight:bold;color:#3fb950}}
.kpi .value.warn{{color:#f0883e}}
.kpi .label{{font-size:12px;color:#8b949e;margin-top:5px;text-transform:uppercase}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:15px;padding:0 20px 20px}}
.chart-box{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:15px}}
.chart-box h3{{font-size:14px;color:#f0f6fc;margin-bottom:10px}}
.chart{{width:100%;height:280px}}
.table-box{{padding:0 20px 20px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#21262d;color:#8b949e;padding:8px 12px;text-align:left;font-weight:normal}}
td{{padding:6px 12px;border-bottom:1px solid #21262d}}
tr:hover{{background:#1c2128}}
.green{{color:#3fb950}}
.red{{color:#f85149}}
.orange{{color:#f0883e}}
</style>
<script src="/echarts.min.js"></script></head><body>
{nav}
<div class="header">
  <h1>V17 Entry-at-Zone Dashboard</h1>
  <div class="sub">Pine-Exact signals + Multi-source SL/TP + Quality-scored entries | {n_stocks} stocks | min quality≥3.0</div>
</div>

<div class="kpis">
  <div class="kpi"><div class="value">{wr}%</div><div class="label">Win Rate</div></div>
  <div class="kpi"><div class="value">{avg_pnl:+.2f}%</div><div class="label">Avg P&L/trade</div></div>
  <div class="kpi"><div class="value">{total_trades}</div><div class="label">Total Trades</div></div>
  <div class="kpi"><div class="value">{n_stocks}</div><div class="label">Stocks Traded</div></div>
  <div class="kpi"><div class="value">{avg_hold}</div><div class="label">Avg Hold (bars)</div></div>
</div>

<div class="charts">
  <div class="chart-box"><h3>Exit Methods</h3><div id="exit-chart" class="chart"></div></div>
  <div class="chart-box"><h3>SL Sources (Diversified!)</h3><div id="sl-chart" class="chart"></div></div>
  <div class="chart-box"><h3>Entry Sources</h3><div id="entry-chart" class="chart"></div></div>
  <div class="chart-box"><h3>WR Distribution (by stock)</h3><div id="wr-chart" class="chart"></div></div>
</div>

<div class="table-box" style="display:grid;grid-template-columns:1fr 1fr;gap:15px">
<div>
<h3 style="color:#f0f6fc;font-size:14px;margin-bottom:10px">Top 10 by Win Rate</h3>
<table>
<tr><th>Symbol</th><th>Trades</th><th>WR</th><th>Avg P&L</th></tr>
{''.join(f'<tr><td>{s["symbol"]}</td><td>{s["n_trades"]}</td><td class="green">{s["wr"]}%</td><td class="green">{s["avg_pnl"]:+.2f}%</td></tr>' for s in top_wr)}
</table>
</div>
<div>
<h3 style="color:#f0f6fc;font-size:14px;margin-bottom:10px">Top 10 by Total P&L</h3>
<table>
<tr><th>Symbol</th><th>Trades</th><th>Total P&L</th><th>WR</th></tr>
{''.join(f'<tr><td>{s["symbol"]}</td><td>{s["n_trades"]}</td><td class="green">{s["total_pnl"]:+.2f}%</td><td class="green">{s["wr"]}%</td></tr>' for s in top_pnl)}
</table>
</div>
</div>

<script>
// Exit methods pie
(function(){{
  var c=echarts.init(document.getElementById('exit-chart'),'dark');
  c.setOption({{
    tooltip:{{trigger:'item'}},backgroundColor:'#161b22',
    series:[{{type:'pie',radius:['40%','70%'],center:['50%','50%'],
      label:{{color:'#c9d1d9',fontSize:11}},
      data:[
        {{value:{exits.get('tp_hit',0)},name:'TP Hit',itemStyle:{{color:'#3fb950'}}}},
        {{value:{exits.get('trailing',0)},name:'Trailing',itemStyle:{{color:'#58a6ff'}}}},
        {{value:{exits.get('sl_hit',0)},name:'SL Hit',itemStyle:{{color:'#f85149'}}}},
        {{value:{exits.get('eod',0)},name:'EOD',itemStyle:{{color:'#8b949e'}}}},
      ]
    }}]
  }});
}})();

// SL sources bar
(function(){{
  var c=echarts.init(document.getElementById('sl-chart'),'dark');
  c.setOption({{
    tooltip:{{trigger:'axis'}},backgroundColor:'#161b22',
    grid:{{left:100,right:20,top:10,bottom:30}},
    xAxis:{{type:'value',axisLabel:{{color:'#8b949e'}}}},
    yAxis:{{type:'category',data:{json.dumps(list(sl_src.keys()))},axisLabel:{{color:'#c9d1d9',fontSize:10}}}},
    series:[{{type:'bar',data:{json.dumps(list(sl_src.values()))},
      itemStyle:{{color:'#3fb950'}},barMaxWidth:20,
      label:{{show:true,position:'right',color:'#c9d1d9',fontSize:10}}
    }}]
  }});
}})();

// Entry sources pie
(function(){{
  var c=echarts.init(document.getElementById('entry-chart'),'dark');
  c.setOption({{
    tooltip:{{trigger:'item'}},backgroundColor:'#161b22',
    series:[{{type:'pie',radius:'70%',center:['50%','50%'],
      label:{{color:'#c9d1d9',fontSize:11}},
      data:[
        {{value:{entry_src.get('FVG',0)},name:'FVG',itemStyle:{{color:'#9C27B0'}}}},
        {{value:{entry_src.get('OB',0)},name:'OB',itemStyle:{{color:'#2196F3'}}}},
      ]
    }}]
  }});
}})();

// WR distribution histogram
(function(){{
  var c=echarts.init(document.getElementById('wr-chart'),'dark');
  c.setOption({{
    tooltip:{{trigger:'axis'}},backgroundColor:'#161b22',
    grid:{{left:50,right:20,top:10,bottom:30}},
    xAxis:{{type:'category',data:{json.dumps([f'{k}-{k+9}%' for k in sorted(wr_bins.keys())])},axisLabel:{{color:'#8b949e',fontSize:10}}}},
    yAxis:{{type:'value',axisLabel:{{color:'#8b949e'}}}},
    series:[{{type:'bar',data:{json.dumps([wr_bins[k] for k in sorted(wr_bins.keys())])},
      itemStyle:{{color:'#58a6ff'}},barMaxWidth:40
    }}]
  }});
}})();
</script></body></html>'''
    return html
