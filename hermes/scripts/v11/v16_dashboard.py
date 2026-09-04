#!/usr/bin/env python3
"""V16 Complete Dashboard — Full Market Data + Signal Sequences"""
import json, http.server, os, sys
from pathlib import Path

PORT = 8900

def generate_html():
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMC V16 — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
h1{font-size:24px;margin-bottom:20px;color:#58a6ff}
h2{font-size:18px;margin:20px 0;color:#f0f6fc}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit, minmax(200px,1fr));gap:15px}
.metric{text-align:center;padding:15px}
.metric .value{font-size:32px;font-weight:bold}
.metric .label{font-size:12px;color:#8b949e;margin-top:5px}
.green{color:#3fb950}.red{color:#f85149}.blue{color:#58a6ff}.yellow{color:#d29922}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #21262d}
th{background:#21262d;color:#8b949e;font-weight:600;position:sticky;top:0}
tr:hover{background:#1c2128}
select,input{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:8px;border-radius:6px;font-size:14px}
.tabs{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.tab{padding:10px 20px;background:#21262d;border:1px solid #30363d;border-radius:6px;cursor:pointer;font-size:14px}
.tab.active{background:#1f6feb;border-color:#1f6feb}
.tab-content{display:none}
.tab-content.active{display:block}
</style>
</head>
<body>
<h1>SMC V16 — Complete Trading Dashboard</h1>
<div class="tabs">
  <div class="tab active" onclick="switchTab('overview')">Overview</div>
  <div class="tab" onclick="switchTab('versions')">Version Comparison</div>
  <div class="tab" onclick="switchTab('stocks')">Stock Browser</div>
  <div class="tab" onclick="switchTab('seq')">Signal Sequences</div>
  <div class="tab" onclick="switchTab('phases')">Phase Analysis</div>
  <div class="tab" onclick="switchTab('live')">Live Signals</div>
</div>

<div id="overview" class="tab-content active">
<div class="grid">
  <div class="card metric"><div class="value green" id="o-wr">--</div><div class="label">Win Rate (Full Market)</div></div>
  <div class="card metric"><div class="value blue" id="o-rr">--</div><div class="label">Avg RR</div></div>
  <div class="card metric"><div class="value green" id="o-pf">--</div><div class="label">Profit Factor</div></div>
  <div class="card metric"><div class="value green" id="o-pnl">--</div><div class="label">Avg P&L</div></div>
  <div class="card metric"><div class="value blue" id="o-trades">--</div><div class="label">Total Trades</div></div>
  <div class="card metric"><div class="value green" id="o-swing-wr">--</div><div class="label">Swing SL WR</div></div>
  <div class="card metric"><div class="value yellow" id="o-n80">--</div><div class="label">Stocks WR>=80%</div></div>
  <div class="card metric"><div class="value" id="o-coverage">--</div><div class="label">Tradable / Total</div></div>
</div>
<div class="card">
<h2>All Versions at a Glance</h2>
<div id="v-compare"></div>
</div>
</div>

<div id="versions" class="tab-content"><div class="card" id="v-table"></div></div>
<div id="stocks" class="tab-content"><div class="card">
<select id="sv" onchange="loadStocks()"></select>
<table id="st-table"><tr><th>Stock</th><th>Trades</th><th>WR</th><th>RR</th><th>PF</th><th>Swing%</th><th>Phase</th></tr></table>
</div></div>
<div id="seq" class="tab-content"><div class="card">
<h2>Signal Sequence Pattern Analysis</h2>
<p>Last 5 signals before entry: F=FVG, O=OB, S=Sweep, C=CHOCH, B=BPR</p>
Min trades: <input type="range" id="seq-min" min="1" max="10" value="3" onchange="loadSeq()"> <span id="seq-min-l">3</span>
<div id="seq-table"></div>
</div></div>
<div id="phases" class="tab-content"><div class="card" id="phase-table"></div></div>

<div id="live" class="tab-content">
<div class="card">
<h2>Live Trading Signals <span style="font-size:12px;color:#8b949e" id="live-ts"></span></h2>
<div id="live-table"></div>
</div>
</div>

<script>
let scanData = null; let seqData = null; let versionData = null;

fetch('/api/scan-summary').then(r=>r.json()).then(d=>{
  scanData=d;
  if(!d) return;
  document.getElementById('o-wr').textContent=d.wr+'%';
  document.getElementById('o-rr').textContent=d.rr+'x';
  document.getElementById('o-pf').textContent=d.pf;
  document.getElementById('o-pnl').textContent='+'+d.pnl+'%';
  document.getElementById('o-trades').textContent=d.trades;
  document.getElementById('o-swing-wr').textContent=d.swing_wr+'%';
  document.getElementById('o-n80').textContent=d.n80;
  document.getElementById('o-coverage').textContent=d.tradable+'/'+d.total;
});

fetch('/api/seq-patterns').then(r=>r.json()).then(d=>{seqData=d;loadSeq()});
fetch('/api/live-signals').then(r=>r.json()).then(d=>{
  if(!d || !d.signals || d.signals.length===0) return;
  document.getElementById('live-ts').textContent='Updated: '+d.timestamp;
  let html='<table><tr><th>#</th><th>Symbol</th><th>Type</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Quality</th><th>Cycle</th></tr>';
  d.signals.slice(0,50).forEach((s,i)=>{
    const c=s.sl_type==='swing'?'green':'yellow';
    html+=`<tr><td>${i+1}</td><td>${s.symbol}</td><td>${s.signal_type}</td><td>${s.entry_price}</td><td class="${c}">${s.sl}</td><td class="green">${s.tp}</td><td>${s.rr}x</td><td>${s.quality}</td><td>${s.cycle||''}</td></tr>`;
  });
  document.getElementById('live-table').innerHTML=html+'</table>';
});
fetch('/api/versions').then(r=>r.json()).then(d=>{
  versionData=d;
  let html='<table><tr><th>Version</th><th>Trades</th><th>WR</th><th>RR</th></tr>';
  Object.entries(d).forEach(([v,data])=>{
    const c=data.wr>=70?'green':data.wr>=60?'yellow':'red';
    html+='<tr><td>'+v+'</td><td>'+data.trades+'</td><td class="'+c+'">'+data.wr+'%</td><td>'+data.rr+'x</td></tr>';
  });
  document.getElementById('v-compare').innerHTML=html+'</table>';
  let sel='';
  Object.keys(d).sort().forEach(v=>sel+='<option>'+v+'</option>');
  document.getElementById('sv').innerHTML=sel;
  loadStocks();
});

function switchTab(name){
  document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));
  document.getElementById(name).classList.add('active');
  event.target.classList.add('active');
}

function loadStocks(){
  const v=document.getElementById('sv').value;
  fetch('/api/stocks?version='+v).then(r=>r.json()).then(data=>{
    let html='<tr><th>Stock</th><th>Trades</th><th>WR</th><th>RR</th><th>PF</th><th>Swing%</th><th>Phase</th></tr>';
    data.slice(0,200).forEach(s=>{
      const c=s.win_rate>=70?'green':s.win_rate>=60?'yellow':'red';
      html+='<tr><td>'+s.symbol+'</td><td>'+s.n_trades+'</td><td class="'+c+'">'+s.win_rate+'%</td><td>'+s.avg_rr+'x</td><td>'+s.profit_factor+'</td><td>'+(s.swing_sl_pct||0)+'%</td><td>'+(s.phase||'?')+'</td></tr>';
    });
    document.getElementById('st-table').innerHTML=html;
  });
}

function loadSeq(){
  if(!seqData) return;
  const min=parseInt(document.getElementById('seq-min').value);
  document.getElementById('seq-min-l').textContent=min;
  const f=seqData.filter(p=>p.total>=min).sort((a,b)=>b.total-a.total);
  let html='<table><tr><th>Pattern</th><th>Total</th><th>WR</th><th>Action</th></tr>';
  f.forEach(p=>{
    const c=p.wr>=80?'green':p.wr>=60?'yellow':'red';
    html+='<tr><td style="font-family:monospace">'+p.pattern+'</td><td>'+p.total+'</td><td class="'+c+'">'+p.wr.toFixed(1)+'%</td><td>'+(p.action||'')+'</td></tr>';
  });
  document.getElementById('seq-table').innerHTML=html+'</table>';
}
</script>
</body>
</html>'''

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type','text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(generate_html().encode('utf-8'))
        
        elif self.path == '/api/scan-summary':
            # Prefer V25 if available
            v25_path = Path('/root/.hermes/smc_opt_v25/v25_full_merged.json')
            if v25_path.exists():
                d = json.loads(v25_path.read_bytes())
                label = 'V25'
            else:
                v23_path = Path('/root/.hermes/smc_opt_v23/v23_full_merged.json')
            if v23_path.exists():
                d = json.loads(v23_path.read_bytes())
                label = 'V23'
            else:
                v21_path = Path('/root/.hermes/smc_opt_v21/v21_final_merged.json')
                if v21_path.exists():
                    d = json.loads(v21_path.read_bytes())
                    label = 'V21'
                else:
                    d = json.loads((Path('/root/.hermes/smc_opt_v16')/'v16_full_merged.json').read_bytes())
                    label = 'V16'
            s = d['summary']
            trades = d.get('all_trades',[])
            sw = [t for t in trades if t.get('sl_type')=='swing']
            fx = [t for t in trades if t.get('sl_type')!='swing']
            sw_wr = sum(1 for t in sw if t['won'])/len(sw)*100 if sw else 0
            n80 = sum(1 for st in d.get('stocks',[]) if st.get('win_rate',0)>=80)
            self.send_json({'wr':round(s['win_rate'],1),'rr':round(s['avg_rr'],2),
                           'pf':round(s['profit_factor'],1),'pnl':round(s['avg_pnl'],2),
                           'trades':s['total_trades'],'tradable':s['tradable'],'total':4800,
                           'swing_wr':round(sw_wr,1),'n80':n80})
        
        elif self.path == '/api/versions':
            import glob
            data={}
            # Include V21, V23 results
            for fp in list(Path('/root/.hermes/smc_opt_v21').glob('*_merged.json')) + list(Path('/root/.hermes/smc_opt_v23').glob('*_merged.json')) + list(Path('/root/.hermes/smc_opt_v11').glob('backtest_v1*.json')):
                try:
                    d=json.loads(fp.read_bytes())
                    s=d.get('summary',{})
                    vname = 'V23' if 'v23' in str(fp) else ('V21' if 'v21' in str(fp) else fp.stem.replace('backtest_v11_','V').replace('backtest_',''))
                    data[vname]={'trades':s.get('total_trades',0),'wr':round(s.get('win_rate',0),1),'rr':round(s.get('avg_rr',0),2)}
                except: pass
            self.send_json(data)
        
        elif self.path.startswith('/api/stocks'):
            from urllib.parse import urlparse, parse_qs
            qs=parse_qs(urlparse(self.path).query)
            v=qs.get('version',['V16'])[0]
            d={}
            for fp in list(Path('/root/.hermes/smc_opt_v11').glob('backtest_v1*.json')) + list(Path('/root/.hermes/smc_opt_v16').glob('*.json')):
                try:
                    dd=json.loads(fp.read_bytes())
                    if fp.stem.replace('backtest_v11_','V').replace('backtest_','')==v:
                        d=dd; break
                except: pass
            stocks=d.get('stocks',[])
            self.send_json(sorted(stocks,key=lambda x:-x.get('win_rate',0))[:500])
        
        elif self.path == '/api/seq-patterns':
            import sys
            sys.path.insert(0,'/root/.hermes/scripts')
            from v11.signals_v11 import detect_all_signals_v11
            from v11.adaptive_params import calc_stock_params, detect_market_phase
            from collections import defaultdict,Counter
            
            d=json.loads((Path('/root/.hermes/smc_opt_v16')/'v16_full_merged.json').read_bytes())
            trades=d.get('all_trades',[]); stocks=d.get('stocks',[])
            
            # Build offset map
            trade_to_sym={}; offset=0
            for s in stocks:
                for i in range(s['n_trades']):
                    trade_to_sym[offset+i]=s['symbol']
                offset+=s['n_trades']
            
            patterns=defaultdict(lambda:{'wins':0,'total':0})
            for idx,t in enumerate(trades[:200]):  # sample first 200
                sym=trade_to_sym.get(idx)
                if not sym: continue
                ohlcv=self._load_ohlcv(sym)
                if not ohlcv: continue
                entry_idx=t['entry_idx']; won=t['won']
                phase=detect_market_phase(ohlcv)
                params=calc_stock_params(ohlcv,sym,phase=phase,tf='daily')
                all_sigs=detect_all_signals_v11(ohlcv,params=params,tf='daily')['all']
                sigs_before=[s for s in all_sigs if s.get('idx',0)<entry_idx][-5:]
                seq=''.join({'F':'F','O':'O','S':'S','C':'C','B':'B','?':'?'}.get(s.get('type','?')[0],'?') for s in sigs_before)
                patterns[seq]['total']+=1
                if won: patterns[seq]['wins']+=1
            
            result=[]
            for seq,stats in sorted(patterns.items(),key=lambda x:-x[1]['total']):
                wr=stats['wins']/stats['total']*100 if stats['total']>0 else 0
                # Determine action
                if wr>=80: action='ENTER'
                elif wr>=60: action='caution'
                elif wr>=40: action='neutral'
                else: action='SKIP'
                if stats['total']>=3: result.append({'pattern':seq,'total':stats['total'],
                    'wr':round(wr,1),'action':action})
            self.send_json(result)
        
        elif self.path == '/api/phases':
            d=json.loads((Path('/root/.hermes/smc_opt_v16')/'v16_full_merged.json').read_bytes())
            stocks=d.get('stocks',[])
            from collections import defaultdict
            phases=defaultdict(lambda:{'stocks':0,'wins':0,'trades':0,'wr_sum':0})
            for s in stocks:
                p=s.get('phase','?')
                phases[p]['stocks']+=1
                phases[p]['trades']+=s['n_trades']
                phases[p]['wins']+=s.get('wins',0)
                phases[p]['wr_sum']+=s['win_rate']
            result=[]
            for p,data in sorted(phases.items()):
                avg_wr=data['wr_sum']/data['stocks'] if data['stocks'] else 0
                result.append({'phase':p,'stocks':data['stocks'],'trades':data['trades'],
                    'avg_wr':round(avg_wr,1)})
            self.send_json(result)
        
        elif self.path == '/api/live-signals':
            fp = Path('/root/.hermes/smc_signals/latest_signals.json')
            if fp.exists():
                try:
                    d = json.loads(fp.read_bytes())
                    self.send_json(d)
                except: self.send_json({'signals':[],'error':'parse error'})
            else:
                self.send_json({'signals':[],'error':'no live data'})
        
        else: self.send_error(404)
    
    def send_json(self,data):
        self.send_response(200)
        self.send_header('Content-type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data,default=str).encode())
    
    def _load_ohlcv(self,symbol):
        fname=f"{symbol.replace('.','_')}_daily_300.json"
        fpath=Path(f'/root/.hermes/kline_cache/{fname}')
        if not fpath.exists(): return None
        data=json.loads(fpath.read_bytes())
        if not data or len(data)<120: return None
        for bar in data:
            if 'date' not in bar and 't' in bar: bar['date']=str(bar['t'])
        return data

if __name__=='__main__':
    print(f"SMC Dashboard: http://localhost:{PORT}")
    server=http.server.HTTPServer(('0.0.0.0',PORT),Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: server.shutdown()
