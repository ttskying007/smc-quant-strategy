
# ═══════════════════════════════════════════════════
# V19 — Enhanced K-line with V19 Signals + Backtest Trades
# ═══════════════════════════════════════════════════
V19_DATA_DIR = Path('/root/.hermes/smc_opt_v19')

def get_v19_backtest_files():
    if not V19_DATA_DIR.exists(): return {}
    files = {}
    for fp in sorted(V19_DATA_DIR.glob('v19_backtest_*.json')):
        code = fp.stem.replace('v19_backtest_', '')
        if code: files[code] = fp
    return files

def load_v19_backtest(symbol_code):
    fp = V19_DATA_DIR / f'v19_backtest_{symbol_code}.json'
    if not fp.exists(): return None
    data = json.loads(fp.read_bytes())
    trades = data.get('trades', data.get('all_trades', []))
    summary = data.get('summary', {})
    symbol = data.get('symbol', f'{symbol_code}.SH')
    return {'symbol': symbol, 'trades': trades, 'summary': summary,
            'signal_stats': data.get('signal_stats', {}),
            'swings': data.get('swings', [])}

def build_v19(symbol_code=None):
    if symbol_code is None: symbol_code = '600519'
    available = get_v19_backtest_files()
    bt = load_v19_backtest(symbol_code)
    
    if bt is None:
        opts = ''.join(f'<option value="{c}"{" selected" if c==symbol_code else ""}>{c}</option>' for c in sorted(available.keys()))
        if not opts: opts = f'<option value="{symbol_code}">{symbol_code}</option>'
        return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>V19 — {symbol_code}</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif}}
.ctrl{{background:#161b22;padding:12px 20px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #30363d}}
.ctrl select{{padding:8px 12px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;font-size:14px}}
.ctrl .btn{{padding:8px 16px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px}}
</style></head><body>
{NAV}
<div class="ctrl">
<form method="get"><select name="s" onchange="this.form.submit()">{opts}</select>
<input type="submit" class="btn" value="View"></form>
</div>
<div style="padding:40px;text-align:center;color:#f85149;">
<h2>No V19 backtest data for {symbol_code}</h2>
<p style="color:#8b949e;margin-top:10px;">Run V19 backtest engine to generate data.</p>
<p style="color:#8b949e;">Available: {', '.join(sorted(available.keys())) if available else 'none'}</p>
</div></body></html>'''
    
    symbol = bt['symbol']
    trades = bt['trades']
    summary = bt['summary']
    
    ohlcv = load_ohlcv(symbol)
    if not ohlcv: ohlcv = []
    
    dates = [str(b.get('date', b.get('t', ''))) for b in ohlcv]
    ohlcv_data = [[b['o'], b['c'], b['l'], b['h']] for b in ohlcv]
    
    # ── V19 Signal Detection ──
    sig_areas = []; sig_lines = []; sig_stats_str = ''
    try:
        from v11.signals_v19 import detect_all_signals_v19
        sigs_result, sig_stats, _, _ = detect_all_signals_v19(ohlcv)
        tc = sig_stats.get('type_counts', {})
        sig_stats_str = ' | '.join(f'{k}:{v}' for k,v in sorted(tc.items()))
        for s in sigs_result:
            idx = s.idx
            if idx < 0 or idx >= len(dates): continue
            up = s.upper; lo = s.lower; pr = s.price; st = s.type
            if st in ('FVG_Bull','FVG_Bear','OB_Bull','OB_Bear','BPR','IFVG_Bull','IFVG_Bear'):
                if up > 0 and lo > 0 and up != lo:
                    ex = min(idx+10, len(dates)-1)
                    c = 'rgba(33,150,243,0.15)' if 'Bull' in st else 'rgba(244,67,54,0.15)'
                    b = 'rgba(33,150,243,0.5)' if 'Bull' in st else 'rgba(244,67,54,0.5)'
                    if 'OB' in st: c = 'rgba(33,150,243,0.12)' if 'Bull' in st else 'rgba(244,67,54,0.12)'
                    if 'BPR' in st: c = 'rgba(0,150,136,0.15)'; b = 'rgba(0,150,136,0.5)'
                    sig_areas.append({'data':[{'xAxis':dates[idx],'yAxis':lo,'itemStyle':{'color':c,'borderColor':b,'borderWidth':1}},{'xAxis':dates[ex],'yAxis':up}]})
            if st in ('Sweep_BSL','Sweep_SSL','CHOCH_Bull','CHOCH_Bear','BOS_Bull','BOS_Bear','MSS_Bull','MSS_Bear','EQL','EQH'):
                if pr > 0:
                    lc = '#FFEB3B'
                    if 'CHOCH' in st: lc = '#00BCD4' if 'Bull' in st else '#E91E63'
                    if 'BOS' in st: lc = '#4CAF50' if 'Bull' in st else '#FF5722'
                    if 'MSS' in st: lc = '#81D4FA'
                    if 'BSL' in st: lc = '#F44336'
                    if 'SSL' in st: lc = '#4CAF50'
                    if 'EQL' in st or 'EQH' in st: lc = '#B0BEC5'
                    sig_lines.append({'yAxis':pr,'lineStyle':{'color':lc,'type':'dashed','width':1.5,'opacity':0.6},'label':{'show':True,'formatter':st.replace('_',' '),'color':lc,'fontSize':8,'position':'start'}})
    except Exception as e:
        sig_stats_str = f'Signal load error: {e}'
    
    # Trade markers
    entry_marks = []; exit_marks = []; sl_marks = []; tp_marks = []
    for i, t in enumerate(trades):
        eidx = t.get('entry_idx', 0); xidx = t.get('exit_idx', 0)
        ep = t.get('entry_price', 0); xp = t.get('exit_price', 0)
        slp = t.get('sl_price', 0); tpp = t.get('tp_price', 0)
        pnl = t.get('pnl_pct', 0); won = pnl > 0
        
        if eidx < len(dates):
            entry_marks.append({'name':f'E{i+1}','coord':[dates[eidx],ep],'value':f'E{i+1}','symbol':'pin','symbolSize':36,'itemStyle':{'color':'#3fb950' if won else '#f85149','borderColor':'#fff','borderWidth':1},'label':{'show':True,'formatter':f'E{i+1}','fontSize':9,'color':'#fff','position':'top'}})
        if xidx < len(dates):
            exit_marks.append({'coord':[dates[xidx],xp],'value':f'{pnl:+.1f}%','symbol':'diamond','symbolSize':18,'itemStyle':{'color':'#79c0ff' if pnl>0 else '#d29922','borderColor':'#fff','borderWidth':1},'label':{'show':True,'formatter':f'{pnl:+.1f}%','fontSize':8,'color':'#79c0ff' if pnl>0 else '#d29922','position':'bottom'}})
        if slp > 0: sl_marks.append({'yAxis':slp,'lineStyle':{'color':'#f85149','type':'dashed','width':1.5,'opacity':0.7},'label':{'show':True,'formatter':f'SL {slp:.2f}','color':'#f85149','fontSize':9,'position':'start'}})
        if tpp > 0: tp_marks.append({'yAxis':tpp,'lineStyle':{'color':'#3fb950','type':'dotted','width':1.5,'opacity':0.7},'label':{'show':True,'formatter':f'TP {tpp:.2f}','color':'#3fb950','fontSize':9,'position':'start'}})
    
    # Trade table
    trade_rows = []
    for i, t in enumerate(trades):
        eidx = t.get('entry_idx',0); xidx = t.get('exit_idx',0)
        ed = dates[eidx] if eidx < len(dates) else '?'
        xd = dates[xidx] if xidx < len(dates) else '?'
        ep = t.get('entry_price',0); xp = t.get('exit_price',0)
        pnl = t.get('pnl_pct',0); hb = t.get('hold_bars', xidx-eidx if xidx>eidx else 0)
        es = t.get('entry_type','?'); em = t.get('exit_method','?')
        slp = t.get('sl_price',0); tpp = t.get('tp_price',0)
        pc = 'win' if pnl > 0 else 'loss'
        trade_rows.append(f'<tr><td>{i+1}</td><td>{ed}</td><td>{ep:.2f}</td><td>{xd}</td><td>{xp:.2f}</td><td class="{pc}">{pnl:+.2f}%</td><td>{hb}</td><td>{es}</td><td>{em}</td><td>{slp:.2f}</td><td>{tpp:.2f}</td></tr>')
    rows_html = ''.join(trade_rows)
    
    total_pnl = sum(t.get('pnl_pct',0) for t in trades)
    wins = sum(1 for t in trades if t.get('pnl_pct',0) > 0)
    wr_val = (wins/len(trades)*100) if trades else 0
    best = max((t.get('pnl_pct',0) for t in trades), default=0)
    worst = min((t.get('pnl_pct',0) for t in trades), default=0)
    
    opts = ''.join(f'<option value="{c}"{" selected" if c==symbol_code else ""}>{c}</option>' for c in sorted(available.keys()))
    if not opts: opts = f'<option value="{symbol_code}">{symbol_code}</option>'
    
    dates_j = json.dumps(dates)
    ohlcv_j = json.dumps(ohlcv_data)
    entry_j = json.dumps(entry_marks)
    exit_j = json.dumps(exit_marks)
    sl_j = json.dumps(sl_marks)
    tp_j = json.dumps(tp_marks)
    sig_areas_j = json.dumps(sig_areas)
    sig_lines_j = json.dumps(sig_lines)
    sym_j = json.dumps(symbol)
    
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>V19 — {symbol}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}
.ctrl{{background:#161b22;padding:12px 20px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #30363d;flex-wrap:wrap}}
.ctrl select{{padding:8px 12px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;font-size:14px;min-width:160px}}
.ctrl .btn{{padding:8px 16px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px}}
.stats{{display:flex;gap:16px;flex-wrap:wrap;padding:0 20px;margin-top:-1px;background:#161b22;border-bottom:1px solid #30363d}}
.stat{{padding:10px 16px;text-align:center}}
.stat .val{{font-size:20px;font-weight:bold;color:#f0f6fc}}
.stat .lbl{{font-size:10px;color:#8b949e;text-transform:uppercase;margin-top:2px}}
.win{{color:#3fb950}}.loss{{color:#f85149}}
#chart{{width:100%;height:600px}}
.detail{{padding:20px;max-width:1600px;margin:0 auto}}
.detail h2{{font-size:16px;margin-bottom:10px;color:#f0f6fc}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:#161b22;padding:10px 8px;text-align:left;color:#8b949e;font-weight:600;border-bottom:2px solid #30363d;position:sticky;top:0;white-space:nowrap}}
td{{padding:7px 8px;border-bottom:1px solid #21262d;white-space:nowrap}}
tr:hover{{background:#161b22}}
.filters{{background:#161b22;padding:8px 20px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px}}
.filters label{{display:flex;align-items:center;gap:4px;cursor:pointer;padding:3px 8px;border-radius:4px;background:#0d1117;border:1px solid #30363d}}
</style>
<script src="/echarts.min.js"></script></head><body>
{NAV}
<div class="ctrl">
<form method="get" style="display:flex;align-items:center;gap:10px;">
<select name="s" onchange="this.form.submit()">{opts}</select>
<input type="submit" class="btn" value="View">
</form>
<span style="color:#8b949e;font-size:13px;">V19 Signals + Backtest | Signal counts: {sig_stats_str}</span>
</div>
<div class="stats">
<div class="stat"><div class="val">{len(trades)}</div><div class="lbl">Trades</div></div>
<div class="stat"><div class="val" style="color:#3fb950">{wr_val:.1f}%</div><div class="lbl">Win Rate</div></div>
<div class="stat"><div class="val" style="color:{'#3fb950' if total_pnl>=0 else '#f85149'}">{total_pnl:+.2f}%</div><div class="lbl">Total P&L</div></div>
<div class="stat"><div class="val" style="color:#3fb950">+{best:.2f}%</div><div class="lbl">Best Trade</div></div>
<div class="stat"><div class="val" style="color:#f85149">{worst:+.2f}%</div><div class="lbl">Worst Trade</div></div>
</div>
<div id="chart"></div>
<div class="detail"><h2>Trade Details</h2>
<div style="overflow-x:auto;">
<table>
<tr><th>#</th><th>Entry Date</th><th>Entry Price</th><th>Exit Date</th><th>Exit Price</th><th>P&L%</th><th>Hold Bars</th><th>Entry Signal</th><th>Exit Method</th><th>SL Price</th><th>TP Price</th></tr>
{rows_html}
</table></div></div>
<script>
var dom=document.getElementById('chart');var chart=echarts.init(dom,'dark');
var dates={dates_j};var ohlcvData={ohlcv_j};
var entryMarks={entry_j};var exitMarks={exit_j};
var slLines={sl_j};var tpLines={tp_j};
var sigAreas={sig_areas_j};var sigLines={sig_lines_j};
var allMarkPoints = entryMarks.concat(exitMarks);
var allMarkLines = slLines.concat(tpLines).concat(sigLines);
var allMarkAreas = sigAreas;
chart.setOption({{
  animation: false,
  backgroundColor: '#0d1117',
  tooltip: {{trigger: 'axis', axisPointer: {{type: 'cross'}}}},
  dataZoom: [
    {{type: 'inside', start: 0, end: 100}},
    {{type: 'slider', start: 0, end: 100, bottom: 10, height: 25, borderColor: '#30363d', backgroundColor: '#161b22'}}
  ],
  grid: {{left: '5%', right: '5%', bottom: '15%', top: '5%'}},
  xAxis: {{
    type: 'category', data: dates,
    axisLine: {{lineStyle: {{color: '#30363d'}}}},
    axisLabel: {{rotate: 45, fontSize: 10, interval: 30, color: '#8b949e'}},
    splitLine: {{show: false}}
  }},
  yAxis: {{
    scale: true,
    splitLine: {{lineStyle: {{color: '#21262d', type: 'dashed'}}}},
    axisLabel: {{color: '#8b949e', fontSize: 11}}
  }},
  series: [{{
    name: 'K线', type: 'candlestick', data: ohlcvData,
    itemStyle: {{color: '#f85149', color0: '#3fb950', borderColor: '#f85149', borderColor0: '#3fb950'}},
    markArea: {{silent: true, data: allMarkAreas}},
    markLine: {{data: allMarkLines, symbol: 'none', label: {{show: true, fontSize: 9}}}},
    markPoint: {{data: allMarkPoints, symbol: 'pin', symbolSize: 30, label: {{show: true, fontSize: 9}}}}
  }}]
}});
window.addEventListener('resize', function(){{chart.resize()}});
</script></body></html>'''


# ═══════════════════════════════════════════════════
# HTTP REQUEST HANDLER
# ═══════════════════════════════════════════════════

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)
            symbol_code = qs.get('s', [None])[0]
            
            html = None
            
            if path == '/' or path == '':
                # Home page with module links
                modules = [
                    ('V19 📊', 'V19信号+交易明细', '/v19?s=600519', '#ff6bcb'),
                    ('V2 信号', '13 SMC信号查看器', '/v2?s=000001.SZ', '#8b949e'),
                    ('V1 K线', 'K线+出入点', '/v1?s=000001.SZ', '#8b949e'),
                ]
                mod_html = ''.join(f'<div class="module"><h2>{m[0]}</h2><p>{m[1]}</p><a class="btn" href="{m[2]}" style="background:{m[3]}22;color:{m[3]};border:1px solid {m[3]}44;padding:8px 16px;border-radius:6px;text-decoration:none;display:inline-block;margin-top:10px;">打开</a></div>' for m in modules)
                html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>SMC Unified</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif;padding:40px;text-align:center}}
h1{{color:#00d4aa;font-size:2em}}p{{color:#8b949e;margin:20px 0}}
.module{{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:12px;padding:30px;margin:15px;width:280px;vertical-align:top;text-align:left}}
.module h2{{color:#f0f6fc;font-size:1.2em;margin-bottom:10px}}
</style></head><body>
<h1>SMC Unified WebUI</h1><p>Port 8890</p>
{mod_html}
</body></html>'''
            
            elif path == '/v1' and symbol_code:
                html = build_v1(symbol_code)
            elif path == '/v2' and symbol_code:
                html = build_v2(symbol_code)
            elif path == '/v19':
                code = symbol_code or '600519'
                html = build_v19(code)
            elif path == '/echarts.min.js':
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript')
                self.end_headers()
                with open(ECHARTS, 'rb') as f:
                    self.wfile.write(f.read())
                return
            elif path == '/v17' and symbol_code:
                try:
                    from v17_viewer import build_v17
                    html = build_v17(symbol_code, nav=NAV)
                except:
                    html = NAV + '<p style="padding:20px;color:#f85149;">V17 engine not available</p>'
            elif path == '/v18':
                try:
                    from v18_dashboard import build_v18
                    html = build_v18(nav=NAV)
                except:
                    html = NAV + '<p style="padding:20px;color:#f85149;">V18 dashboard not available</p>'
            elif path == '/v7' and symbol_code:
                try:
                    html = build_v7(symbol_code, nav=NAV)
                except:
                    html = NAV + '<p style="padding:20px;color:#f85149;">V7 not available</p>'
            
            if html:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'Not Found')
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'Error: {e}'.encode())

    def log_message(self, format, *args):
        pass  # Quiet


# ═══════════════════════════════════════════════════
# SERVER STARTUP
# ═══════════════════════════════════════════════════

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'SMC Unified WebUI: http://0.0.0.0:{PORT}')
    print(f'V19 Signals: http://0.0.0.0:{PORT}/v19?s=600519')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
