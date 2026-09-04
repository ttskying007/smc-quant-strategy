#!/usr/bin/env python3
# SMC V10 — Enhanced Web Dashboard
"""
V10 WebUI — 在V9基础上新增:
1. 共振分析标签页 (Resonance)
2. 信号序列标签页 (Sequence)
3. 摆动点结构树 (Swing Structure)
4. 每股票参数对比 (Per-Stock Compare)

端口: 8891 (不与V9的8881冲突)
"""

import json, math, time, logging, sys, os
from pathlib import Path
from typing import Dict, List

try:
    from fastapi import FastAPI, Query
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError:
    print("ERROR: fastapi/uvicorn not installed. Run: pip install fastapi uvicorn")
    sys.exit(1)

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import V10 modules
try:
    from v10 import swing_points, signal_sequencer, resonance_engine
    from v10 import per_stock_opt as pso
    from v10.smc_backtest_v10 import evaluate_trades_v10, compute_score_v10
except ImportError as e:
    print(f"WARNING: V10 module import issue: {e}")
    # Fallbacks
    swing_points = None
    signal_sequencer = None
    resonance_engine = None
    pso = None

# Try V9 modules for data
try:
    from v9.smc_hubble import fetch_kline, kline_to_ohlcv, calc_atr_pct
    from v9.smc_config import get_stocks, get_param_space, get_config
except ImportError:
    fetch_kline = lambda s, i, c: []
    kline_to_ohlcv = lambda k: []
    calc_atr_pct = lambda o: 0
    get_stocks = lambda: ['600519.SH', '000858.SZ', '300750.SZ']
    get_param_space = lambda: {}
    get_config = lambda: {}

log = logging.getLogger('smc_v10.webui')

app = FastAPI(title="SMC V10 — Multi-Resonance Dashboard", version="10.0.0")

# Store for in-memory results
_last_results = {}
_last_swing = {}
_last_seq = {}
_last_compare = {}


# ═══════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "10.0.0", "modules": {
        "swing_points": swing_points is not None,
        "signal_sequencer": signal_sequencer is not None,
        "resonance_engine": resonance_engine is not None,
        "per_stock_opt": pso is not None,
    }}


@app.get("/api/analyze")
async def analyze(
    symbol: str = Query(default="600519.SH"),
    count: int = Query(default=120),
):
    """Full V10 analysis: swing + sequence + resonance + backtest."""
    global _last_results, _last_swing, _last_seq
    
    try:
        kline = fetch_kline(symbol, 'daily', count)
        if not kline or len(kline) < 30:
            return {"error": f"No data for {symbol}"}
        
        ohlcv = kline_to_ohlcv(kline)
        
        # Default params
        params = {
            'fvg_min_width': 0.22, 'fvg_merge_dist': 2,
            'sweep_lookback': 12, 'sweep_wick_ratio': 4.26,
            'ob_strength_min': 0.97, 'confirm_range': 2,
            'min_sources': 3, 'score_min': 3.71, 'max_trades': 7,
            'atr_min_pct': 3.17, 'atr_max_pct': 11.55,
            'sl_pct': 1.0, 'tp_pct': 2.8, 'vol_adapt_sl': 0.6,
        }
        
        # 1. Swing points
        swing_data = swing_points.find_swing_points(ohlcv)
        swing_signals = swing_points.detect_swing_based_signals(ohlcv, swing_data)
        marks, lines = swing_points.swing_to_echarts(swing_data)
        
        # 2. V10 backtest
        bt_result = evaluate_trades_v10(
            ohlcv, params,
            phase=swing_data.get('current_phase', 'trending_up'),
            swing_data=swing_data,
        )
        
        # 3. Sequence analysis
        from v9.smc_signals import detect_all_signals
        raw_signals = detect_all_signals(ohlcv, params)
        seq_result = signal_sequencer.analyze_signal_sequence(raw_signals)
        seq_score = signal_sequencer.score_entry_from_sequence(seq_result)
        
        # 4. Full resonance
        res_score = resonance_engine.evaluate_full_resonance(
            tf_directions={'daily': swing_data['tree'].get('direction', 'bull')},
            signals=raw_signals,
            swing_tree=swing_data['tree'],
            seq_result=seq_result,
            symbol=symbol,
        )
        res_grade = resonance_engine.get_resonance_grade(res_score)
        
        # Build K-line data for ECharts
        kline_data = []
        for i, bar in enumerate(ohlcv):
            kline_data.append([
                bar.get('o', 0), bar.get('c', 0),
                bar.get('l', 0), bar.get('h', 0),
            ])
        
        _last_results[symbol] = bt_result
        _last_swing[symbol] = swing_data
        _last_seq[symbol] = seq_result
        
        return {
            'symbol': symbol,
            'bars': len(ohlcv),
            'kline': kline_data,
            'swing': {
                'phase': swing_data['current_phase'],
                'tree': swing_data['tree'],
                'signals': [{'type': s['type'], 'idx': s['idx'], 'price': s['price'],
                            'direction': s.get('direction', '')} for s in swing_signals],
                'marks': marks,
                'lines': lines,
                'macro_count': len(swing_data.get('macro', [])),
                'meso_count': len(swing_data.get('meso', [])),
            },
            'resonance': res_score.to_dict(),
            'resonance_grade': res_grade,
            'sequence': {
                'best': seq_result.get('best_sequence', {}).get('name', 'None'),
                'completeness': seq_result.get('best_sequence', {}).get('completeness', 0) if seq_result.get('best_sequence') else 0,
                'trace': seq_result.get('sequence_trace', []),
                'entry_score': seq_score,
                'direction': seq_result.get('direction'),
            },
            'backtest': {
                'n_trades': bt_result.get('n_trades', 0),
                'wins': bt_result.get('wins', 0),
                'losses': bt_result.get('losses', 0),
                'wr': round(bt_result.get('wins', 0) / max(1, bt_result.get('n_trades', 1)) * 100, 1),
                'avg_resonance': bt_result.get('avg_resonance', 0),
                'phase': bt_result.get('phase', 'unknown'),
                'trades': bt_result.get('trades', []),
                'rejected': len(bt_result.get('rejected_signals', [])),
            },
        }
    except Exception as e:
        log.exception(f"Error analyzing {symbol}")
        return {"error": str(e)}


@app.get("/api/compare")
async def compare(
    symbol: str = Query(default="600519.SH"),
):
    """Compare V9 vs V10 for a single stock."""
    global _last_compare
    
    try:
        from v10.smc_backtest_v10 import compare_v9_v10 as do_compare
        
        params = {
            'fvg_min_width': 0.22, 'fvg_merge_dist': 2,
            'sweep_lookback': 12, 'sweep_wick_ratio': 4.26,
            'ob_strength_min': 0.97, 'confirm_range': 2,
            'min_sources': 3, 'score_min': 3.71, 'max_trades': 7,
            'atr_min_pct': 3.17, 'atr_max_pct': 11.55,
            'sl_pct': 1.0, 'tp_pct': 2.8, 'vol_adapt_sl': 0.6,
        }
        
        result = do_compare(symbol, params)
        _last_compare[symbol] = result
        return result
    except Exception as e:
        log.exception(f"Error comparing {symbol}")
        return {"error": str(e)}


@app.get("/api/stocks")
async def list_stocks():
    """List available stocks."""
    try:
        stocks = get_stocks()
        return {"stocks": stocks, "count": len(stocks)}
    except:
        return {"stocks": ['600519.SH', '000858.SZ', '300750.SZ'], "count": 3}


@app.get("/api/per_stock_params")
async def get_per_stock_params():
    """Get per-stock optimized parameters."""
    data = pso.load_per_stock_params() if pso else None
    if data:
        return data
    return {"error": "No per-stock params available. Run per_stock_opt.batch_optimize() first."}


@app.get("/api/resonance_report")
async def resonance_report(
    symbol: str = Query(default="600519.SH"),
):
    """Text resonance report."""
    try:
        kline = fetch_kline(symbol, 'daily', 120)
        ohlcv = kline_to_ohlcv(kline)
        swing_data = swing_points.find_swing_points(ohlcv)
        
        from v9.smc_signals import detect_all_signals
        params = {
            'fvg_min_width': 0.22, 'sweep_lookback': 12,
            'sweep_wick_ratio': 4.26, 'ob_strength_min': 0.97,
        }
        raw_signals = detect_all_signals(ohlcv, params)
        seq_result = signal_sequencer.analyze_signal_sequence(raw_signals)
        
        res_score = resonance_engine.evaluate_full_resonance(
            tf_directions={'daily': swing_data['tree'].get('direction')},
            signals=raw_signals,
            swing_tree=swing_data['tree'],
            seq_result=seq_result,
            symbol=symbol,
        )
        
        report = resonance_engine.build_resonance_report(
            symbol, res_score,
            phase=swing_data.get('current_phase', 'ranging'),
            seq_result=seq_result,
            swing_result=swing_data,
        )
        
        return {"report": report, "resonance": res_score.to_dict()}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
# HTML Frontend
# ═══════════════════════════════════════════════════════════════════════

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>SMC V10 — Multi-Resonance Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:'SF Mono','Fira Code','Consolas',monospace;font-size:13px}
.header{background:#161b22;border-bottom:1px solid #30363d;padding:12px 20px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:18px;color:#58a6ff}
.header .version{color:#d29922;font-size:12px}
.tabs{display:flex;gap:0;background:#161b22;border-bottom:1px solid #30363d}
.tab{padding:10px 20px;cursor:pointer;border-bottom:2px solid transparent;color:#8b949e;transition:all 0.2s}
.tab:hover{color:#c9d1d9}
.tab.active{color:#58a6ff;border-bottom-color:#58a6ff}
.panel{display:none;padding:15px}
.panel.active{display:block}
.grid{display:grid;gap:15px}
.grid-2{grid-template-columns:1fr 1fr}
.grid-3{grid-template-columns:1fr 1fr 1fr}
.grid-4{grid-template-columns:1fr 1fr 1fr 1fr}
.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:15px}
.card h3{color:#58a6ff;font-size:14px;margin-bottom:10px}
.kpi{display:inline-block;text-align:center;padding:8px 12px;margin:4px;background:#0d1117;border-radius:4px;border:1px solid #30363d}
.kpi .val{font-size:20px;font-weight:bold}
.kpi .lbl{font-size:10px;color:#8b949e}
.green{color:#3fb950}
.red{color:#f85149}
.yellow{color:#d29922}
.blue{color:#58a6ff}
.chart{width:100%;height:500px}
.chart-sm{width:100%;height:300px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#1c2128;text-align:left;padding:6px 8px;border-bottom:1px solid #30363d;color:#8b949e}
td{padding:6px 8px;border-bottom:1px solid #21262d}
tr:hover{background:#1c2128}
.trade-log{padding:8px;margin:4px 0;border-radius:4px;font-size:12px;line-height:1.6;white-space:pre-wrap}
.trade-log.win{border-left:3px solid #3fb950}
.trade-log.loss{border-left:3px solid #f85149}
.progress-bar{height:6px;background:#21262d;border-radius:3px;margin:4px 0}
.progress-fill{height:100%;border-radius:3px;transition:width .3s}
.grade-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:bold;font-size:14px}
.grade-S{background:rgba(63,185,80,0.2);color:#3fb950}
.grade-A{background:rgba(88,166,255,0.2);color:#58a6ff}
.grade-B{background:rgba(210,153,34,0.2);color:#d29922}
.grade-C{background:rgba(248,81,73,0.2);color:#f85149}
.grade-D{background:rgba(139,148,158,0.2);color:#8b949e}
input,select{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:6px 10px;border-radius:4px;font-family:inherit;font-size:13px}
button{background:#238636;border:none;color:#fff;padding:8px 16px;border-radius:4px;cursor:pointer;font-family:inherit;font-size:13px}
button:hover{background:#2ea043}
button.secondary{background:#21262d;border:1px solid #30363d}
button.secondary:hover{background:#30363d}
.flex{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.mt{margin-top:10px}
.mb{margin-bottom:10px}
.resonance-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.resonance-item{text-align:center;padding:10px;background:#0d1117;border-radius:6px;border:1px solid #30363d}
.resonance-item .label{font-size:10px;color:#8b949e;margin-bottom:4px}
.resonance-item .value{font-size:22px;font-weight:bold}
.sequence-path{font-family:monospace;font-size:12px;padding:8px;background:#0d1117;border-radius:4px;margin:4px 0}
.arrow{color:#d29922;margin:0 4px}
</style>
</head>
<body>

<div class="header">
  <div class="flex">
    <h1>SMC V10</h1>
    <span class="version">Multi-Resonance Engine</span>
  </div>
  <div class="flex">
    <select id="symbolSelect" onchange="analyze()" style="min-width:120px">
      <option value="600519.SH">600519 贵州茅台</option>
      <option value="000858.SZ">000858 五粮液</option>
      <option value="300750.SZ">300750 宁德时代</option>
      <option value="601318.SH">601318 中国平安</option>
      <option value="002415.SZ">002415 海康威视</option>
      <option value="002594.SZ">002594 比亚迪</option>
      <option value="600036.SH">600036 招商银行</option>
      <option value="688981.SH">688981 中芯国际</option>
      <option value="300059.SZ">300059 东方财富</option>
      <option value="600030.SH">600030 中信证券</option>
    </select>
    <button onclick="analyze()">🔍 分析</button>
    <button class="secondary" onclick="compareV9V10()">⚖️ V9 vs V10</button>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('overview')">📊 总览</div>
  <div class="tab" onclick="switchTab('kline')">📈 K线+摆动</div>
  <div class="tab" onclick="switchTab('resonance')">🎯 共振分析</div>
  <div class="tab" onclick="switchTab('sequence')">🔗 信号序列</div>
  <div class="tab" onclick="switchTab('trades')">💰 交易明细</div>
</div>

<!-- Tab 1: Overview -->
<div id="overview" class="panel active">
  <div class="grid grid-2">
    <div class="card">
      <h3>📊 回测KPI</h3>
      <div id="overviewKPI"></div>
    </div>
    <div class="card">
      <h3>🎯 共振概览</h3>
      <div id="overviewResonance"></div>
    </div>
  </div>
  <div class="card mt">
    <h3>📋 V10 vs V9 对比</h3>
    <div id="compareTable"></div>
  </div>
</div>

<!-- Tab 2: K-line + Swing -->
<div id="kline" class="panel">
  <div class="card">
    <h3>📈 K线图 + 摆动点标注</h3>
    <div class="flex mb">
      <span class="kpi"><span class="lbl">阶段</span> <span class="val blue" id="phaseLabel">---</span></span>
      <span class="kpi"><span class="lbl">宏观摆动</span> <span class="val" id="macroCount">-</span></span>
      <span class="kpi"><span class="lbl">中观摆动</span> <span class="val" id="mesoCount">-</span></span>
    </div>
    <div id="chartKline" class="chart"></div>
  </div>
</div>

<!-- Tab 3: Resonance -->
<div id="resonance" class="panel">
  <div class="grid grid-2">
    <div class="card">
      <h3>🎯 共振四维度</h3>
      <div id="resonanceGrid"></div>
    </div>
    <div class="card">
      <h3>📋 共振评级</h3>
      <div id="resonanceGrade"></div>
    </div>
  </div>
  <div class="card mt">
    <h3>📊 共振雷达图</h3>
    <div id="chartResonance" class="chart-sm"></div>
  </div>
</div>

<!-- Tab 4: Sequence -->
<div id="sequence" class="panel">
  <div class="grid grid-2">
    <div class="card">
      <h3>🔗 信号序列分析</h3>
      <div id="sequenceInfo"></div>
    </div>
    <div class="card">
      <h3>📊 序列评分</h3>
      <div id="sequenceScore"></div>
    </div>
  </div>
  <div class="card mt">
    <h3>📜 信号时间线</h3>
    <div id="signalTimeline"></div>
  </div>
</div>

<!-- Tab 5: Trades -->
<div id="trades" class="panel">
  <div class="card">
    <h3>💰 交易明细</h3>
    <div id="tradesTable"></div>
  </div>
  <div class="card mt">
    <h3>🚫 被拒绝信号</h3>
    <div id="rejectedTable"></div>
  </div>
</div>

<script>
let data = null;
let chartKline = null;
let chartResonance = null;

function switchTab(name) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(name).classList.add('active');
  document.querySelector(`.tab:nth-child(${['overview','kline','resonance','sequence','trades'].indexOf(name)+1})`).classList.add('active');
  if (name === 'kline') setTimeout(renderKline, 100);
  if (name === 'resonance') setTimeout(renderResonanceChart, 100);
}

async function analyze() {
  const symbol = document.getElementById('symbolSelect').value;
  try {
    const resp = await fetch(`/api/analyze?symbol=${symbol}&count=120`);
    data = await resp.json();
    if (data.error) { alert(data.error); return; }
    renderOverview();
    renderResonance();
    renderSequence();
    renderTrades();
    console.log('V10 Analysis complete:', data.symbol, data.backtest.wr+'% WR');
  } catch(e) { console.error(e); }
}

async function compareV9V10() {
  const symbol = document.getElementById('symbolSelect').value;
  try {
    const resp = await fetch(`/api/compare?symbol=${symbol}`);
    const cmp = await resp.json();
    let html = '<table><tr><th>版本</th><th>交易数</th><th>胜率</th><th>收益</th><th>特征</th></tr>';
    html += `<tr><td>V9 (baseline)</td><td>${cmp.v9.n_trades}</td><td>${cmp.v9.wr}%</td><td>${cmp.v9.returns.length ? cmp.v9.returns.reduce((a,b)=>a+b,0).toFixed(2)+'%' : '-'}</td><td>基础</td></tr>`;
    html += `<tr><td><b>V10 (resonance)</b></td><td>${cmp.v10.n_trades}</td><td><b>${cmp.v10.wr}%</b></td><td>${cmp.v10.returns.length ? cmp.v10.returns.reduce((a,b)=>a+b,0).toFixed(2)+'%' : '-'}</td><td>共振=${cmp.v10.avg_resonance?.toFixed(3)||'-'}, 阶段=${cmp.v10.phase}, 拒绝${cmp.v10.rejected}信号</td></tr>`;
    html += '</table>';
    document.getElementById('compareTable').innerHTML = html;
  } catch(e) { console.error(e); }
}

function renderOverview() {
  const bt = data.backtest;
  const r = data.resonance_grade;
  let html = '<div class="flex">';
  html += `<div class="kpi"><span class="lbl">胜率 WR</span><br><span class="val green">${bt.wr}%</span></div>`;
  html += `<div class="kpi"><span class="lbl">交易数 N</span><br><span class="val">${bt.n_trades}</span></div>`;
  html += `<div class="kpi"><span class="lbl">赢/输</span><br><span class="val green">${bt.wins}</span>/<span class="val red">${bt.losses}</span></div>`;
  html += `<div class="kpi"><span class="lbl">平均共振</span><br><span class="val blue">${bt.avg_resonance?.toFixed(3)||'N/A'}</span></div>`;
  html += `<div class="kpi"><span class="lbl">市场阶段</span><br><span class="val yellow">${bt.phase||'N/A'}</span></div>`;
  html += `<div class="kpi"><span class="lbl">拒绝信号</span><br><span class="val red">${bt.rejected}</span></div>`;
  html += '</div>';
  document.getElementById('overviewKPI').innerHTML = html;
  
  let rhtml = `<div style="text-align:center;padding:20px">`;
  rhtml += `<span class="grade-badge grade-${r.grade}">${r.grade}</span><br><br>`;
  rhtml += `<b>${r.advice}</b><br>`;
  rhtml += `预期胜率: ${(r.expected_wr*100).toFixed(0)}% | 共振层级: ${r.layers}/4`;
  rhtml += `</div>`;
  document.getElementById('overviewResonance').innerHTML = rhtml;
}

function renderResonance() {
  const r = data.resonance;
  const g = data.resonance_grade;
  
  let html = '<div class="resonance-grid">';
  [['TF共振', r.tf, '#58a6ff'], ['指标共振', r.indicator, '#3fb950'],
   ['摆动共振', r.swing, '#d29922'], ['序列共振', r.sequence, '#bc8cff']].forEach(([label,val,color]) => {
    html += `<div class="resonance-item">
      <div class="label">${label}</div>
      <div class="value" style="color:${color}">${(val*100).toFixed(0)}%</div>
      <div class="progress-bar"><div class="progress-fill" style="width:${val*100}%;background:${color}"></div></div>
    </div>`;
  });
  html += '</div>';
  html += `<div class="mt"><b>综合共振: ${(r.total*100).toFixed(1)}%</b> | 层级: ${r.layers}/4</div>`;
  document.getElementById('resonanceGrid').innerHTML = html;
  
  let ghtml = `<div style="text-align:center;padding:20px">`;
  ghtml += `<span class="grade-badge grade-${g.grade}" style="font-size:32px">${g.grade}</span>`;
  ghtml += `<p style="margin-top:10px;font-size:16px"><b>${g.advice}</b></p>`;
  ghtml += `<p style="color:#8b949e">预期胜率: ${(g.expected_wr*100).toFixed(0)}% | 共振层级: ${g.layers}/4</p>`;
  ghtml += `<p style="color:#8b949e">建议: ${g.action}</p>`;
  ghtml += `</div>`;
  document.getElementById('resonanceGrade').innerHTML = ghtml;
}

function renderSequence() {
  const s = data.sequence;
  const es = s.entry_score;
  
  let html = `<div class="sequence-path">`;
  if (s.trace && s.trace.length > 0) {
    html += s.trace.map(t => `<span style="padding:2px 6px;background:#1c2128;border-radius:3px;margin:2px">${t}</span>`).join('<span class="arrow">→</span>');
  } else {
    html += '无信号序列';
  }
  html += '</div>';
  html += `<p class="mt">最佳序列: <b>${s.best||'None'}</b> | 完整度: ${(s.completeness*100).toFixed(0)}%</p>`;
  html += `<p>方向: <b>${s.direction||'N/A'}</b></p>`;
  document.getElementById('sequenceInfo').innerHTML = html;
  
  let shtml = `<div style="text-align:center;padding:10px">`;
  shtml += `<span class="grade-badge grade-${es.grade}">${es.grade}</span><br><br>`;
  shtml += `<b>${es.reason}</b><br>`;
  shtml += `序列得分: ${es.final_score.toFixed(3)} | 预期WR: ${(es.expected_wr*100).toFixed(0)}%<br>`;
  shtml += `动作: ${es.action}`;
  shtml += `</div>`;
  document.getElementById('sequenceScore').innerHTML = shtml;
}

function renderTrades() {
  const trades = data.backtest.trades || [];
  let html = '<table><tr><th>#</th><th>方向</th><th>信号</th><th>入场</th><th>出场</th><th>收益%</th><th>RR</th><th>共振</th><th>序列</th><th>结果</th></tr>';
  trades.forEach(t => {
    const cls = t.win ? 'green' : 'red';
    html += `<tr>
      <td>${t.idx}</td><td>${t.direction==='long'?'🟢多':'🔴空'}</td>
      <td>${t.signal_type}</td><td>${t.entry}</td><td>${t.exit}</td>
      <td class="${cls}">${t.ret}%</td><td>${t.rr}</td>
      <td>${(t.resonance_total||0).toFixed(2)}</td>
      <td>${t.sequence_grade||'-'}</td>
      <td class="${cls}">${t.win?'✅':'❌'}</td>
    </tr>`;
  });
  html += '</table>';
  document.getElementById('tradesTable').innerHTML = html || '无交易';
  
  const rejected = data.backtest.trades?.length ? (data.backtest.rejected||0) : 0;
  document.getElementById('rejectedTable').innerHTML = rejected > 0 
    ? `<p>拒绝了 <b>${rejected}</b> 个信号 (共振过滤)</p>` 
    : '<p>无被拒绝信号</p>';
}

function renderKline() {
  if (!data || !data.kline) return;
  
  if (!chartKline) {
    chartKline = echarts.init(document.getElementById('chartKline'));
  }
  
  document.getElementById('phaseLabel').innerText = data.swing?.phase||'N/A';
  document.getElementById('macroCount').innerText = data.swing?.macro_count||0;
  document.getElementById('mesoCount').innerText = data.swing?.meso_count||0;
  
  const dates = data.kline.map((_,i) => `K${i}`);
  const ohlc = data.kline.map(b => [b[0], b[3], b[2], b[1]]); // open,high,low,close
  
  const option = {
    backgroundColor: '#0d1117',
    tooltip: {trigger:'axis'},
    grid: {left:'8%',right:'4%',top:'8%',bottom:'8%'},
    xAxis: {data:dates,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{color:'#8b949e',fontSize:10}},
    yAxis: {scale:true,axisLine:{lineStyle:{color:'#30363d'}},splitLine:{lineStyle:{color:'#21262d'}},axisLabel:{color:'#8b949e'}},
    series: [{
      type:'candlestick', data:ohlc,
      itemStyle:{color:'#f85149',color0:'#3fb950',borderColor:'#f85149',borderColor0:'#3fb950'},
      markPoint:{data: data.swing?.marks||[],symbol:'pin'},
      markLine:{symbol:'none',data: data.swing?.lines||[],lineStyle:{type:'dashed',width:1}},
    }],
    dataZoom:[{type:'inside',start:60,end:100},{type:'slider',start:60,end:100,height:20,bottom:5}],
  };
  
  chartKline.setOption(option, true);
}

function renderResonanceChart() {
  if (!data || !data.resonance) return;
  if (!chartResonance) {
    chartResonance = echarts.init(document.getElementById('chartResonance'));
  }
  
  const r = data.resonance;
  const option = {
    backgroundColor: '#0d1117',
    radar: {
      center:['50%','55%'],radius:'75%',
      indicator:[
        {name:'TF共振',max:1},{name:'指标共振',max:1},
        {name:'摆动共振',max:1},{name:'序列共振',max:1},
      ],
      axisName:{color:'#8b949e',fontSize:11},
      splitArea:{areaStyle:{color:['#0d1117','#161b22']}},
      splitLine:{lineStyle:{color:'#30363d'}},
    },
    series:[{
      type:'radar',
      data:[{value:[r.tf,r.indicator,r.swing,r.sequence],
        name:`共振 ${(r.total*100).toFixed(0)}%`,
        areaStyle:{color:'rgba(88,166,255,0.2)'},
        lineStyle:{color:'#58a6ff'},
        itemStyle:{color:'#58a6ff'},
      }],
    }],
  };
  chartResonance.setOption(option, true);
}

// Auto-load on start
analyze();

window.addEventListener('resize', () => {
  chartKline?.resize();
  chartResonance?.resize();
});
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML


# ═══════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description='SMC V10 WebUI')
    parser.add_argument('--port', type=int, default=8891)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    
    print(f"\n  SMC V10 — Multi-Resonance Dashboard")
    print(f"  http://localhost:{args.port}")
    print(f"  Port: {args.port} (V9 uses 8881)")
    print(f"  Modules: Swing={swing_points is not None} "
          f"Seq={signal_sequencer is not None} "
          f"Resonance={resonance_engine is not None}\n")
    
    uvicorn.run(app, host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    main()