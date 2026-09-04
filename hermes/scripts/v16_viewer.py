#!/usr/bin/env python3
"""V16信号查看器 — Pine Script质量对齐版"""
import json
from pathlib import Path

CACHE = Path('/root/.hermes/kline_cache')
ECHARTS = '/tmp/echarts.min.js'

SIG_STYLE = {
    'FVG_Bull':  {'fill': '1','stroke': 'rgba(156,39,176,0.6)','label': 'FVG'},
    'FVG_Bear':  {'fill': '1','stroke': 'rgba(233,30,99,0.6)','label': 'FVG'},
    'OB_Bull':   {'fill': '1','stroke': 'rgba(33,150,243,0.5)','label': 'OB'},
    'OB_Bear':   {'fill': '1','stroke': 'rgba(244,67,54,0.5)','label': 'OB'},
    'SweepDown': {'stroke': '#FFEB3B','type':'dashed','width':2,'label':'Sweep'},
    'SweepUp':   {'stroke': '#FF9800','type':'dashed','width':2,'label':'Sweep'},
    'CHOCH_Bull':{'stroke': '#00BCD4','type':'solid','width':2,'label':'CHOCH'},
    'CHOCH_Bear':{'stroke': '#E91E63','type':'solid','width':2,'label':'CHOCH'},
    'BOS_Bull':  {'stroke': '#4CAF50','type':'solid','width':2,'label':'BOS'},
    'BOS_Bear':  {'stroke': '#FF5722','type':'solid','width':2,'label':'BOS'},
    'MSS_Bull':  {'stroke': '#81D4FA','type':'dashed','width':1,'label':'MSS'},
    'MSS_Bear':  {'stroke': '#81D4FA','type':'dashed','width':1,'label':'MSS'},
    'EQL_High':  {'stroke': '#B0BEC5','type':'solid','width':1,'label':'EQL'},
    'EQL_Low':   {'stroke': '#B0BEC5','type':'solid','width':1,'label':'EQL'},
    'BPR':       {'fill': '1','stroke': 'rgba(0,150,136,0.5)','label':'BPR'},
    'IFVG_Bull': {'fill': '1','stroke': 'rgba(138,43,226,0.5)','label':'IFVG'},
    'IFVG_Bear': {'fill': '1','stroke': 'rgba(138,43,226,0.5)','label':'IFVG'},
}

SIG_FAMILY = {
    'FVG_Bull':'fvg','FVG_Bear':'fvg','OB_Bull':'ob','OB_Bear':'ob',
    'SweepDown':'sweep','SweepUp':'sweep','CHOCH_Bull':'choch','CHOCH_Bear':'choch',
    'BOS_Bull':'bos','BOS_Bear':'bos','MSS_Bull':'mss','MSS_Bear':'mss',
    'EQL_High':'eql','EQL_Low':'eql','BPR':'bpr','IFVG_Bull':'ifvg','IFVG_Bear':'ifvg',
}

def load_ohlcv(symbol):
    fname = symbol.replace('.','_') + '_daily_300.json'
    fpath = CACHE / fname
    if not fpath.exists(): return None
    return json.loads(fpath.read_bytes())

def build_v16(symbol, nav=''):
    try:
        from v11.signals_v16 import detect_all_signals_v16
    except:
        return nav + '<p style="padding:20px;color:#f85149;">V16 engine not found</p>'

    ohlcv = load_ohlcv(symbol)
    if not ohlcv:
        return nav + '<p style="padding:20px;color:#8b949e;">No data for ' + symbol + '</p>'

    try:
        result = detect_all_signals_v16(ohlcv)
        all_sigs = result.get('all', [])
    except Exception as e:
        return nav + f'<p style="padding:20px;color:#f85149;">Error: {e}</p>'

    dates = [str(b.get('date', b.get('t', '')))[:10] for b in ohlcv]
    ohlcv_data = [[b['o'],b['c'],b['l'],b['h']] for b in ohlcv]

    snum = 0; nsigs = []
    for s in all_sigs:
        snum += 1; s['seq'] = snum; nsigs.append(s)

    max_idx = len(dates) - 1
    areas, lines, pts = [], [], []

    for s in nsigs:
        st = s['type']; sty = SIG_STYLE.get(st, {}); fam = SIG_FAMILY.get(st, 'other')
        seq = s['seq']; idx = s['idx']
        if idx < 0 or idx >= len(dates): continue
        up = s.get('upper', 0); lo = s.get('lower', 0); pr = s.get('price', 0)

        if 'fill' in sty and up > 0 and lo > 0 and up != lo:
            ex = dates[min(idx+10, max_idx)]
            areas.append({
                'family': fam,
                'data': [{'xAxis': dates[idx], 'yAxis': lo,
                    'itemStyle': {'color': 'rgba(100,100,255,0.1)',
                        'borderColor': sty.get('stroke','#888'), 'borderWidth': 1}},
                    {'xAxis': ex, 'yAxis': up}]
            })

        if 'stroke' in sty and 'fill' not in sty:
            pr2 = s.get('price', s.get('upper', 0))
            if pr2 > 0:
                ex = dates[min(idx+20, max_idx)]
                lines.append({
                    'family': fam,
                    '_pair': [{'xAxis': dates[idx], 'yAxis': pr2}, {'xAxis': ex, 'yAxis': pr2}],
                    'lineStyle': {'color': sty['stroke'], 'type': sty.get('type','dashed'), 'width': sty.get('width',1)},
                })

        if pr > 0:
            color_map = {
                'FVG_Bull':'#9C27B0','FVG_Bear':'#E91E63','OB_Bull':'#2196F3','OB_Bear':'#F44336',
                'SweepDown':'#FFEB3B','SweepUp':'#FF9800','CHOCH_Bull':'#00BCD4','CHOCH_Bear':'#E91E63',
                'BOS_Bull':'#4CAF50','BOS_Bear':'#FF5722','MSS_Bull':'#81D4FA','MSS_Bear':'#81D4FA',
                'EQL_High':'#B0BEC5','EQL_Low':'#B0BEC5','BPR':'#4CAF50',
                'IFVG_Bull':'#9C27B0','IFVG_Bear':'#9C27B0',
            }
            pts.append({
                'family': fam, 'name': str(seq),
                'coord': [dates[idx], pr], 'value': str(seq),
                'symbol': 'circle', 'symbolSize': 8,
                'itemStyle': {'color': color_map.get(st, '#888'), 'borderColor': '#fff', 'borderWidth': 1},
                'label': {'show': True, 'formatter': str(seq), 'color': '#fff', 'fontSize': 7, 'position': 'right'},
            })

    slist = sorted([p.stem.replace('_daily_300','').replace('_','.') for p in CACHE.glob('*_daily_300.json')])
    so = ''.join(f'<option value="{s}"{" selected" if s==symbol else ""}>{s}</option>' for s in slist[:200])

    stats = result.get('stats', {})
    ob_c = stats.get('ob',0); ch_c = stats.get('choch',0); bo_c = stats.get('bos',0)
    eq_c = stats.get('eql',0); fg_c = stats.get('fvg',0); sw_c = stats.get('sweep',0)
    ms_c = stats.get('mss',0); bp_c = stats.get('bpr',0)

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{symbol} V16</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d1117;color:#c9d1d9;font-family:sans-serif}}
.header{{background:#161b22;padding:15px 20px;border-bottom:1px solid #30363d}}
.header h1{{font-size:22px;color:#f0f6fc}}
.sub{{color:#8b949e;font-size:13px;margin-top:4px}}
.controls{{background:#161b22;padding:12px 20px;border-bottom:1px solid #30363d}}
.controls select{{padding:8px 12px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;font-size:14px;min-width:200px}}
#chart{{width:100%;height:600px}}
.filters{{background:#161b22;padding:8px 20px;display:flex;gap:10px;flex-wrap:wrap;font-size:12px;border-bottom:1px solid #30363d}}
.filters label{{display:flex;align-items:center;gap:4px;cursor:pointer;padding:3px 8px;border-radius:4px;background:#0d1117;border:1px solid #30363d;font-size:11px}}
</style>
<script src="/echarts.min.js"></script></head><body>
{nav}
<div class="header"><h1>{symbol} V16 Pine-Quality</h1>
<div class="sub">{len(all_sigs)} signals | OB={ob_c} CH={ch_c} BOS={bo_c} EQL={eq_c} FVG={fg_c} SW={sw_c} MSS={ms_c} BPR={bp_c}</div></div>
<div class="controls"><select onchange="location.href='/v16?s='+this.value">{so}</select></div>
<div class="filters">'''

    for f in ['fvg','ob','sweep','choch','bos','mss','eql','bpr','ifvg']:
        html += f'<label><input type="checkbox" class="sig-filter" data-family="{f}" checked> {f.upper()}</label>'

    html += f'''</div>
<div id="chart"></div>
<script>
var dates = {json.dumps(dates)};
var od = {json.dumps(ohlcv_data)};
var areas = {json.dumps(areas)};
var lines = {json.dumps(lines)};
var pts = {json.dumps(pts)};
function af(){{var a={{}};document.querySelectorAll(".sig-filter").forEach(function(c){{a[c.dataset.family]=c.checked;}});return a;}}
function render(){{
  var a=af();
  chart.setOption({{
    series: [{{
      name: "K", type: "candlestick", data: od,
      itemStyle: {{color:"#f85149",color0:"#3fb950",borderColor:"#f85149",borderColor0:"#3fb950"}},
      markPoint: {{data: pts.filter(function(m){{return a[m.family]}})}},
      markArea: {{data: areas.filter(function(m){{return a[m.family]}}).map(function(m){{return m.data}})}},
      markLine: {{data: lines.filter(function(m){{return a[m.family]}}).map(function(m){{return m._pair||m}})}}
    }}]
  }});
}}
var dom=document.getElementById("chart");var chart=echarts.init(dom,"dark");
chart.setOption({{animation:false,backgroundColor:"#0d1117",tooltip:{{trigger:"axis"}},dataZoom:[{{type:"inside",start:0,end:100}},{{type:"slider",start:0,end:100,bottom:10,height:25}}],grid:{{left:"5%",right:"5%",bottom:"15%",top:"5%"}},xAxis:{{type:"category",data:dates,axisLine:{{lineStyle:{{color:"#30363d"}}}},axisLabel:{{rotate:45,fontSize:10,interval:30,color:"#8b949e"}}}},yAxis:{{scale:true,splitLine:{{lineStyle:{{color:"#21262d",type:"dashed"}}}},axisLabel:{{color:"#8b949e"}}}}}});
setTimeout(render,100);
document.querySelectorAll(".sig-filter").forEach(function(c){{c.addEventListener("change",render);}});
window.addEventListener("resize",function(){{chart.resize();}});
</script></body></html>'''
    return html
