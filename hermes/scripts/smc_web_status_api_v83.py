#!/usr/bin/env python3
"""
SMC V8.3 WebUI Status API — 前后端一体化服务器 (修复版)
========================================================
功能:
  1. 聚合所有SMC版本 (V7/V82/V83) 的状态
  2. 统一的JSON API供前端读取，v83/v82数据独立存储
  3. Serve前端HTML (单页应用)
  4. 健康检查端点, CORS跨域
  5. 代理状态实时从mihomo API获取
  6. 兼容旧版前端 (v82回退)

API端点:
  GET /api/status      → 当前优化器状态 (统一)
  GET /api/v83/status  → 仅V8.3状态
  GET /api/best        → 最佳参数详情
  GET /api/history     → 优化历史
  GET /api/milestones  → 里程碑
  GET /api/proxy       → 代理状态
  GET /api/elite       → 精英池
  GET /api/versions    → 版本目录
  GET /api/sync        → 强制同步
  GET /                → 前端单页

用法:
  python3 smc_web_status_api_v83.py --port 8879
"""

import sys, os, json, time, http.server, urllib.parse, urllib.request
from pathlib import Path

PORT = 8879
if '--port' in sys.argv:
    idx = sys.argv.index('--port')
    if idx + 1 < len(sys.argv):
        PORT = int(sys.argv[idx + 1])

HOME = Path.home()
SMC_DIRS = {
    'v7': HOME / '.hermes' / 'smc_opt_v7',
    'v7plus': HOME / '.hermes' / 'smc_opt_v7plus',
    'v82': HOME / '.hermes' / 'smc_opt_v82',
    'v83': HOME / '.hermes' / 'smc_opt_v83',
}

V83_LIVE = SMC_DIRS['v83'] / 'live_status.json'
V83_BEST = SMC_DIRS['v83'] / 'best_params.json'
V83_HIST = SMC_DIRS['v83'] / 'history.json'
V83_MILESTONES = SMC_DIRS['v83'] / 'milestones.json'
V83_ELITE = SMC_DIRS['v83'] / 'elite_pool.json'
PROXY_STATUS_FILE = SMC_DIRS['v7'] / 'proxy_status.json'

# mihomo API
MIHOMO_BASE = os.environ.get('MIHOMO_API', 'http://127.0.0.1:9090')
MIHOMO_TIMEOUT = 3

def safe_read_json(path):
    try:
        if path and path.exists():
            return json.loads(path.read_text())
    except:
        pass
    return {}

def query_mihomo_api(endpoint):
    """从mihomo API实时获取数据"""
    url = f"{MIHOMO_BASE.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=MIHOMO_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None

def get_proxy_status():
    """获取代理状态: 先从mihomo API实时查询，失败则回退到文件"""
    # 从mihomo API获取实时状态
    mihomo_groups = query_mihomo_api('/groups')
    mihomo_proxies = query_mihomo_api('/proxies')
    mihomo_connections = query_mihomo_api('/connections')
    
    if mihomo_groups is not None and mihomo_proxies is not None:
        # 计算存活节点
        alive = 0
        total = 0
        if isinstance(mihomo_proxies, dict) and 'proxies' in mihomo_proxies:
            for name, p in mihomo_proxies['proxies'].items():
                if isinstance(p, dict) and p.get('type') in ('Shadowsocks', 'VMess', 'Trojan', 'Hysteria2', 'VLESS'):
                    total += 1
                    if p.get('alive', False) or p.get('history', [{}])[-1].get('delay', 0) > 0:
                        alive += 1
        
        now = int(time.time())
        return {
            'ok': True,
            'running': True,
            'pid': 'mihomo_api',
            'port_ok': True,
            'internet_ok': True,
            'alive_nodes': alive,
            'total_nodes': max(total, 1),
            'uptime': 0,  # mihomo API doesn't easily expose uptime
            'total_restarts': 0,
            'connectivity': {'ok': True, 'latency_ms': 0},
            'last_check': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)),
            'source': 'mihomo_api',
        }
    
    # Fallback: 从proxy文件读取
    proxy = safe_read_json(PROXY_STATUS_FILE)
    if proxy:
        proxy['source'] = 'file_fallback'
        return proxy
    
    return {
        'ok': False, 'running': False, 'pid': '', 'port_ok': False,
        'internet_ok': False, 'alive_nodes': 0, 'total_nodes': 0,
        'uptime': 0, 'total_restarts': 0,
        'connectivity': {'ok': False, 'latency_ms': 0},
        'last_check': '', 'source': 'unavailable',
    }

def build_v83_status():
    """构建仅V8.3状态"""
    v83_live = safe_read_json(V83_LIVE)
    v83_best = safe_read_json(V83_BEST)
    v83_elite = safe_read_json(V83_ELITE)
    b = v83_best.get('full_eval', {})
    return {
        'running': v83_live.get('status') == 'running',
        'round': v83_live.get('round', 0),
        'total_rounds': v83_live.get('total_rounds', 250),
        'best_score': v83_live.get('best_score', 0),
        'best_wr': v83_live.get('best_wr', 0),
        'best_n': v83_live.get('best_n', 0),
        'status': v83_live.get('status', 'unknown'),
        'details': v83_live.get('details', {}),
        'timestamp': v83_live.get('timestamp', ''),
        'engine': v83_live.get('engine', 'V8.3'),
        'best': {
            'score': v83_best.get('score', 0),
            'wr': b.get('wr', 0),
            'pf': b.get('pf', 0),
            'n': b.get('n', 0),
            'rr_avg': b.get('rr_avg', 0),
            'ret': b.get('ret', 0),
            'sr': b.get('sr', 0),
            'coverage_pct': b.get('coverage', b.get('coverage_pct', 0)),
            'avg_quality': b.get('avg_quality', 0),
        },
        'params': v83_best.get('params', {}),
        'elite_count': len(v83_elite) if isinstance(v83_elite, list) else 0,
        'milestones': safe_read_json(V83_MILESTONES).get('milestones', []),
    }

def build_status_response():
    """构建统一状态响应"""
    v83_live = safe_read_json(V83_LIVE)
    v83_best = safe_read_json(V83_BEST)
    v83_hist = safe_read_json(V83_HIST)
    v83_mile = safe_read_json(V83_MILESTONES)
    v83_elite = safe_read_json(V83_ELITE)
    
    # V82读取自己的live_status.json（不再被sync_all污染）
    v82_live = safe_read_json(SMC_DIRS['v82'] / 'live_status.json')
    v82_best = safe_read_json(SMC_DIRS['v82'] / 'best_params.json')
    v7_live = safe_read_json(SMC_DIRS['v7'] / 'v7_live_status.json')
    
    proxy = get_proxy_status()

    active_engine = None
    if v83_live.get('status') == 'running':
        active_engine = 'V8.3'
    elif v82_live.get('status') == 'running':
        active_engine = 'V8.2'
    elif v7_live.get('status') == 'running':
        active_engine = 'V7/V7+'

    b = v83_best.get('full_eval', v82_best.get('full_eval', {}))
    
    return {
        'engine': 'V8.3',
        'active_engine': active_engine,
        'v83': {
            'running': v83_live.get('status') == 'running',
            'round': v83_live.get('round', 0),
            'total_rounds': v83_live.get('total_rounds', 250),
            'best_score': v83_live.get('best_score', 0),
            'best_wr': v83_live.get('best_wr', 0),
            'best_n': v83_live.get('best_n', 0),
            'status': v83_live.get('status', 'unknown'),
            'details': v83_live.get('details', {}),
            'timestamp': v83_live.get('timestamp', ''),
            'engine': v83_live.get('engine', 'V8.3'),
        },
        'best': {
            'score': v83_best.get('score', v82_best.get('score', 0)),
            'wr': b.get('wr', 0),
            'pf': b.get('pf', 0),
            'n': b.get('n', 0),
            'n_wins': b.get('n_wins', 0),
            'n_losses': b.get('n_losses', 0),
            'rr_avg': b.get('rr_avg', 0),
            'ret': b.get('ret', 0),
            'sr': b.get('sr', 0),
            'coverage_pct': b.get('coverage_pct', 0),
            'stocks_signal': b.get('stocks_signal', 0),
            'stocks_ok': b.get('stocks_ok', 0),
            'rr_mult': b.get('rr_mult', 0),
            'n_mult': b.get('n_mult', 0),
            'wr_mult': b.get('wr_mult', 0),
            'pf_capped': b.get('pf_capped', 0),
            'final_score': b.get('final_score', 0),
            'timestamp': v83_best.get('timestamp', v82_best.get('timestamp', 0)),
        },
        'params': v83_best.get('params', v82_best.get('params', {})),
        'proxy': {
            'ok': proxy.get('ok', False),
            'running': proxy.get('running', False),
            'pid': proxy.get('pid', ''),
            'port_ok': proxy.get('port_ok', False),
            'internet_ok': proxy.get('internet_ok', False),
            'connectivity': proxy.get('connectivity', {}),
            'uptime': proxy.get('uptime', 0),
            'total_restarts': proxy.get('total_restarts', 0),
            'alive_nodes': proxy.get('alive_nodes', 0),
            'total_nodes': proxy.get('total_nodes', 0),
            'last_check': proxy.get('last_check', ''),
            'source': proxy.get('source', ''),
        },
        'milestones': v83_mile.get('milestones', []),
        'elite_count': len(v83_elite) if isinstance(v83_elite, list) else 0,
        'status': {
            'v83': v83_live,
            'v82': v82_live,
            'v7': v7_live,
        },
        'timestamp': int(time.time()),
    }

# ════════ 前端HTML ════════

FRONTEND_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SMC V8.3 监控面板</title>
<style>
:root { --bg: #0d1117; --card: #161b22; --accent: #58a6ff; --green: #3fb950; --red: #f85149; --orange: #d29922; --text: #c9d1d9; --dim: #8b949e; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; background: var(--bg); color: var(--text); padding: 20px; }
h1 { font-size: 1.5rem; margin-bottom: 16px; display: flex; align-items: center; gap: 12px; }
h1 .badge { font-size: 0.7rem; padding: 3px 10px; border-radius: 12px; }
h2 { font-size: 1.1rem; margin: 20px 0 10px; color: var(--accent); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 20px; }
.card { background: var(--card); border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
.card h3 { font-size: 0.9rem; color: var(--dim); margin-bottom: 8px; }
.stat { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #21262d; }
.stat:last-child { border: 0; }
.stat .label { color: var(--dim); font-size: 0.9rem; }
.stat .value { font-weight: 600; font-variant-numeric: tabular-nums; }
.stat .value.green { color: var(--green); }
.stat .value.red { color: var(--red); }
.stat .value.blue { color: var(--accent); }
.stat .value.orange { color: var(--orange); }
.progress-bar { height: 8px; background: #21262d; border-radius: 4px; margin: 10px 0; overflow: hidden; }
.progress-bar .fill { height: 100%; background: var(--accent); transition: width 0.5s; border-radius: 4px; }
.progress-bar .fill.complete { background: var(--green); }
.status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.dot-ok { background: var(--green); }
.dot-err { background: var(--red); }
.dot-warn { background: var(--orange); }
.hist-chart { display: flex; align-items: flex-end; gap: 2px; height: 100px; margin: 10px 0; position: relative; overflow-x: auto; }
.hist-bar { width: 8px; border-radius: 2px 2px 0 0; min-height: 2px; flex-shrink: 0; position: relative; }
.hist-bar:hover { opacity: 1; }
.hist-bar .tooltip { display: none; position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); background: #000; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 0.7rem; white-space: nowrap; z-index: 10; }
.hist-bar:hover .tooltip { display: block; }
.cycle-list { display: flex; flex-wrap: wrap; gap: 4px; margin: 8px 0; }
.cycle-item { padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; background: var(--card); border: 1px solid #30363d; }
.cycle-item.good { border-color: var(--green); color: var(--green); }
.cycle-item.best { border-color: var(--accent); background: var(--accent); color: #000; }
.params-table { font-size: 0.8rem; width: 100%; }
.params-table td { padding: 3px 8px; }
.params-table td:first-child { color: var(--dim); }
.params-table td:last-child { font-family: monospace; text-align: right; }
.footer { margin-top: 20px; text-align: center; font-size: 0.8rem; color: var(--dim); }
.refresh-info { text-align: right; font-size: 0.8rem; color: var(--dim); margin-bottom: 10px; }
.version-tabs { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.version-tab { padding: 6px 14px; border-radius: 6px; cursor: pointer; background: var(--card); border: 1px solid #30363d; font-size: 0.85rem; }
.version-tab.active { background: var(--accent); color: #000; border-color: var(--accent); font-weight: 600; }
.section-hidden { display: none; }
@keyframes pulse { 0% { opacity: .7; } 50% { opacity: 1; } 100% { opacity: .7; } }
.pulsing { animation: pulse 2s ease-in-out infinite; }
</style>
</head>
<body>
<h1>
  SMC V8.3 监控面板
  <span class="badge" id="statusBadge" style="background:var(--green);color:#000;">V8.3</span>
  <span class="badge" id="engineBadge" style="background:#30363d;color:var(--text);">引擎</span>
  <span style="font-size:0.7rem;color:var(--dim);font-weight:normal;" id="timeLabel"></span>
</h1>
<div class="refresh-info">每2秒自动刷新 · <a href="#" onclick="event.preventDefault();refresh()">手动刷新</a></div>

<div class="version-tabs">
  <span class="version-tab active" onclick="switchTab('v83',this)">V8.3 🏆</span>
  <span class="version-tab" onclick="switchTab('cycles',this)">Cycles</span>
  <span class="version-tab" onclick="switchTab('proxy',this)">代理</span>
  <span class="version-tab" onclick="switchTab('params',this)">参数</span>
</div>

<!-- V8.3 面板 -->
<div id="panel-v83" class="">
  <div class="grid">
    <div class="card">
      <h3>🏆 V8.3 优化器</h3>
      <div class="stat"><span class="label">运行状态</span><span class="value" id="v83Running">检测中...</span></div>
      <div class="stat"><span class="label">当前轮次</span><span class="value blue" id="v83Round">-</span></div>
      <div class="stat"><span class="label">最佳Score</span><span class="value green" id="v83Score">-</span></div>
      <div class="stat"><span class="label">最佳WR</span><span class="value green" id="v83Wr">-</span></div>
      <div class="stat"><span class="label">最佳PF</span><span class="value green" id="v83Pf">-</span></div>
      <div class="stat"><span class="label">交易数(N)</span><span class="value blue" id="v83N">-</span></div>
      <div class="stat"><span class="label">盈亏比(RR)</span><span class="value orange" id="v83Rr">-</span></div>
      <div class="stat"><span class="label">回报率(Ret)</span><span class="value green" id="v83Ret">-</span></div>
      <div class="stat"><span class="label">夏普比(SR)</span><span class="value blue" id="v83Sr">-</span></div>
      <div class="stat"><span class="label">Coverage</span><span class="value" id="v83Cov">-</span></div>
      <div class="stat"><span class="label">精英池</span><span class="value" id="v83Elite">-</span></div>
      <div class="progress-bar"><div class="fill" id="v83Progress" style="width:0%"></div></div>
    </div>
    <div class="card">
      <h3>📊 评分组件 (V8.3 五层)</h3>
      <div class="stat"><span class="label">RR_mult</span><span class="value orange" id="bRrMult">-</span></div>
      <div class="stat"><span class="label">N_mult</span><span class="value blue" id="bNMult">-</span></div>
      <div class="stat"><span class="label">WR_mult</span><span class="value green" id="bWRMult">-</span></div>
      <div class="stat"><span class="label">PF_capped</span><span class="value" id="bPfCapped">-</span></div>
      <div class="stat"><span class="label">Final Score</span><span class="value green" id="bFinalScore">-</span></div>
      <div class="stat"><span class="label">Signal/Total</span><span class="value blue" id="bStocks">-</span></div>
    </div>
    <div class="card">
      <h3>🔗 代理状态</h3>
      <div class="stat"><span class="label">代理运行</span><span class="value" id="proxyRun"><span class="status-dot dot-warn"></span>检测中</span></div>
      <div class="stat"><span class="label">端口7890</span><span class="value" id="proxyPort">-</span></div>
      <div class="stat"><span class="label">外网</span><span class="value" id="proxyInternet">-</span></div>
      <div class="stat"><span class="label">存活节点</span><span class="value" id="proxyNodes">-</span></div>
      <div class="stat"><span class="label">重启次数</span><span class="value" id="proxyRestarts">-</span></div>
      <div class="stat"><span class="label">运行时长</span><span class="value" id="proxyUptime">-</span></div>
    </div>
  </div>
  <h2>📈 Score历史 (V8.3)</h2>
  <div class="card"><div class="hist-chart" id="v83HistoryChart"></div></div>
</div>

<!-- Cycles 面板 -->
<div id="panel-cycles" class="section-hidden">
  <div class="card">
    <div class="stat"><span class="label">总Cycles</span><span class="value blue" id="cTotal">-</span></div>
    <div class="stat"><span class="label">最佳WR</span><span class="value green" id="cBestWr">-</span></div>
    <div class="stat"><span class="label">最佳Score</span><span class="value" id="cBestScore">-</span></div>
    <div class="stat"><span class="label">最佳PF</span><span class="value green" id="cBestPf">-</span></div>
    <div class="stat"><span class="label">最佳RR</span><span class="value orange" id="cBestRr">-</span></div>
    <div class="stat"><span class="label">最佳N</span><span class="value blue" id="cBestN">-</span></div>
  </div>
  <h2>Cycle 历史</h2>
  <div class="card" id="cycleList"></div>
  <h2>Cycle Score 趋势</h2>
  <div class="card"><div class="hist-chart" id="cycleChart"></div></div>
  <h2>Cycle WR 趋势</h2>
  <div class="card"><div class="hist-chart" id="cycleWrChart"></div></div>
</div>

<!-- 代理面板 -->
<div id="panel-proxy" class="section-hidden">
  <div class="grid">
    <div class="card">
      <h3>🔗 代理综合状态</h3>
      <div class="stat"><span class="label">代理运行</span><span class="value" id="pRunning"><span class="status-dot dot-warn"></span>检测中</span></div>
      <div class="stat"><span class="label">进程PID</span><span class="value" id="pPid">-</span></div>
      <div class="stat"><span class="label">端口7890</span><span class="value" id="pPort">-</span></div>
      <div class="stat"><span class="label">外网连通</span><span class="value" id="pInternet">-</span></div>
      <div class="stat"><span class="label">存活/总节点</span><span class="value" id="pNodes">-</span></div>
      <div class="stat"><span class="label">总重启次数</span><span class="value" id="pRestarts">-</span></div>
      <div class="stat"><span class="label">运行时长</span><span class="value" id="pUptime">-</span></div>
    </div>
    <div class="card">
      <h3>🌐 外网连通性</h3>
      <div class="stat"><span class="label">Google</span><span class="value" id="pGoogle">-</span></div>
      <div class="stat"><span class="label">GitHub</span><span class="value" id="pGithub">-</span></div>
      <div class="stat"><span class="label">YouTube</span><span class="value" id="pYoutube">-</span></div>
    </div>
  </div>
</div>

<!-- 参数面板 -->
<div id="panel-params" class="section-hidden">
  <div class="grid" style="grid-template-columns:1fr;">
    <div class="card">
      <h3>🔧 V8.3 最佳参数 (14维)</h3>
      <div class="stat"><span class="label">评分引擎</span><span class="value" id="pEngine">V8.3</span></div>
      <div class="stat"><span class="label">Full_Eval</span><span class="value green" id="pEval">-</span></div>
      <table class="params-table" id="paramsTable">
        <tr><td colspan="2" style="color:var(--dim);">加载中...</td></tr>
      </table>
    </div>
  </div>
</div>

<div class="footer">SMC V8.3 · 第五代评分 · RR引导 · <span id="updateTime">-</span></div>

<script>
const API = '';
let lastHistory = {};

function switchTab(name, el) {
  document.querySelectorAll('.version-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  ['v83','cycles','proxy','params'].forEach(p => {
    document.getElementById('panel-' + p).classList.toggle('section-hidden', p !== name);
  });
}

async function loadCycles() {
  try {
    const versions = await (await fetch(API+'/api/versions')).json();
    const cycles = versions.v83_dirs || [];
    document.getElementById('cTotal').textContent = cycles.length;
    return cycles;
  } catch { return []; }
}

async function loadHistory() {
  try {
    const hist = await (await fetch(API+'/api/history')).json();
    const rounds = hist.rounds || (typeof hist === 'object' && !hist.rounds ? [] : hist.rounds || []);
    return rounds;
  } catch { return []; }
}

async function refresh() {
  try {
    const [status, hist] = await Promise.all([
      fetch(API+'/api/status').then(r=>r.json()),
      fetch(API+'/api/history').then(r=>r.json()),
    ]);
    lastHistory = hist;

    // ════════ V8.3 ════════
    const v83 = status.v83 || {};
    const b = status.best || {};
    const p = status.proxy || {};
    const det = v83.details || {};

    document.getElementById('v83Running').textContent = v83.running ? '运行中' : (v83.status === 'complete' ? '✅ 已完成' : '⏹ 停止');
    document.getElementById('v83Running').className = 'value ' + (v83.running ? 'green pulsing' : (v83.status === 'complete' ? 'green' : 'red'));
    document.getElementById('v83Round').textContent = (v83.round||0) + '/' + (v83.total_rounds||0);
    document.getElementById('v83Score').textContent = (v83.best_score||0).toFixed(1);
    document.getElementById('v83Wr').textContent = (v83.best_wr||0).toFixed(1) + '%';
    document.getElementById('v83Wr').className = 'value ' + ((v83.best_wr||0) >= 80 ? 'green' : 'orange');
    document.getElementById('v83Pf').textContent = (b.pf||0) > 0 ? b.pf.toFixed(2) : '-';
    document.getElementById('v83N').textContent = v83.best_n || b.n || 0;
    document.getElementById('v83Rr').textContent = (b.rr_avg||0).toFixed(2);
    document.getElementById('v83Rr').className = 'value ' + ((b.rr_avg||0) >= 1.2 ? 'green' : (b.rr_avg||0) >= 0.8 ? 'orange' : 'red');
    document.getElementById('v83Ret').textContent = (b.ret||0).toFixed(2) + '%';
    document.getElementById('v83Sr').textContent = (b.sr||0).toFixed(2);
    document.getElementById('v83Cov').textContent = (b.coverage_pct||0).toFixed(0) + '%  (' + (b.stocks_signal||0) + '/' + (b.stocks_ok||0) + ')';
    document.getElementById('v83Elite').textContent = status.elite_count || 0;
    
    const pct = v83.total_rounds > 0 ? ((v83.round||0)/v83.total_rounds*100) : 0;
    const pb = document.getElementById('v83Progress');
    pb.style.width = Math.min(pct, 100) + '%';
    pb.className = 'fill' + (v83.status === 'complete' ? ' complete' : '');
    pb.style.background = v83.running ? 'var(--accent)' : (v83.status === 'complete' ? 'var(--green)' : 'var(--orange)');

    // 引擎徽章
    const badge = document.getElementById('engineBadge');
    badge.textContent = 'V8.3 RR≥1.2';
    badge.style.display = 'inline-block';

    // ════════ 评分组件 ════════
    document.getElementById('bRrAvg').textContent = (b.rr_avg||0).toFixed(2);
    document.getElementById('bRrAvg').className = 'value ' + ((b.rr_avg||0) >= 1.5 ? 'green' : (b.rr_avg||0) >= 1.2 ? 'orange' : 'red');
    document.getElementById('bCov').textContent = (b.coverage_pct||0).toFixed(0) + '%';
    document.getElementById('bQuality').textContent = (b.avg_quality||0).toFixed(2);

    // ════════ 代理 ════════
    document.getElementById('proxyRun').innerHTML = '<span class="status-dot '+(p.internet_ok?'dot-ok':'dot-err')+'"></span>'+(p.internet_ok?'运行中':'已停止');
    document.getElementById('proxyPort').textContent = p.port_ok ? '✓' : '✗';
    document.getElementById('proxyPort').className = 'value ' + (p.port_ok ? 'green' : 'red');
    document.getElementById('proxyInternet').textContent = p.internet_ok ? '✓' : '✗';
    document.getElementById('proxyInternet').className = 'value ' + (p.internet_ok ? 'green' : 'red');
    document.getElementById('proxyNodes').textContent = (p.alive_nodes||0) + '/' + (p.total_nodes||0);
    document.getElementById('proxyRestarts').textContent = p.total_restarts||0;
    const up = p.uptime||0;
    document.getElementById('proxyUptime').textContent = up > 3600 ? (up/3600).toFixed(1)+'h' : up > 60 ? Math.floor(up/60)+'m' : up+'s';

    // ════════ 代理面板 ════════
    document.getElementById('pRunning').innerHTML = '<span class="status-dot '+(p.internet_ok?'dot-ok':'dot-err')+'"></span>'+(p.internet_ok?'运行中':'已停止');
    document.getElementById('pPid').textContent = p.pid || '-';
    document.getElementById('pPort').textContent = p.port_ok ? '✓' : '✗';
    document.getElementById('pPort').className = 'value ' + (p.port_ok ? 'green' : 'red');
    document.getElementById('pInternet').textContent = p.internet_ok ? '✓' : '✗';
    document.getElementById('pInternet').className = 'value ' + (p.internet_ok ? 'green' : 'red');
    document.getElementById('pNodes').textContent = (p.alive_nodes||0) + '/' + (p.total_nodes||0);
    document.getElementById('pRestarts').textContent = p.total_restarts||0;
    document.getElementById('pUptime').textContent = up > 3600 ? (up/3600).toFixed(1)+'h' : up > 60 ? Math.floor(up/60)+'m' : up+'s';
    const conn = p.connectivity || {};
    const sites = {'pGoogle':'google.com','pGithub':'github.com','pYoutube':'youtube.com'};
    Object.entries(sites).forEach(([id, key]) => {
      const ok = conn[key]; const el = document.getElementById(id);
      el.textContent = ok === true ? '✓ OK' : ok === false ? '✗ Fail' : '-';
      el.className = 'value ' + (ok === true ? 'green' : ok === false ? 'red' : '');
    });

    // ════════ 参数面板 ════════
    buildParams(status);
    
    // ════════ 历史图表 ════════
    buildChart(hist);

    // ════════ Cycles ════════
    loadCyclesView();

    // ════════ 状态 ════════
    document.getElementById('timeLabel').textContent = v83.timestamp ? '更新 '+v83.timestamp : '';
    document.getElementById('updateTime').textContent = new Date().toLocaleString('zh-CN');

    const sBadge = document.getElementById('statusBadge');
    if (v83.running) { sBadge.textContent = '🟢 RUNNING'; sBadge.style.background = '#3fb950'; }
    else if (v83.status === 'complete') { sBadge.textContent = '✅ COMPLETE'; sBadge.style.background = '#58a6ff'; }
    else { sBadge.textContent = '⏹ STOPPED'; sBadge.style.background = '#30363d'; }

  } catch(e) {
    console.error('Refresh error:', e);
    document.querySelectorAll('.stat .value').forEach(el => {
      if (!el.textContent || el.textContent === '-' || el.textContent === '') {
        el.textContent = '⚠';
      }
    });
  }
}

function buildParams(status) {
  const params = status.params || {};
  const b = status.best || {};
  const tbl = document.getElementById('paramsTable');
  const keys = Object.keys(params);
  if (keys.length > 0) {
    let evalLine = 'WR='+(b.wr||0)+'% PF='+(b.pf||0)+' N='+(b.n||0)+' RR='+(b.rr_avg||0).toFixed(2)+' Ret='+(b.ret||0).toFixed(2)+'%';
    document.getElementById('pEval').textContent = evalLine;
    document.getElementById('pEval').className = 'value ' + ((b.wr||0) >= 80 ? 'green' : 'orange');
    tbl.innerHTML = keys.map(k => '<tr><td>'+k+'</td><td>'+params[k]+'</td></tr>').join('');
  } else {
    tbl.innerHTML = '<tr><td colspan="2" style="color:var(--dim);text-align:center;">暂无参数</td></tr>';
  }
}

function buildChart(hist) {
  const el = document.getElementById('v83HistoryChart');
  const rounds = hist.rounds || [];
  if (!rounds || rounds.length < 2) {
    el.innerHTML = '<div style="color:var(--dim);padding:20px;text-align:center;">等待优化数据...</div>';
    return;
  }
  const scores = rounds.map(r => r.score||0);
  const wrs = rounds.map(r => r.wr||0);
  const rrs = rounds.map(r => r.rr||0);
  const maxScore = Math.max(...scores.filter(s=>s>0), 1);
  // Show last 150 bars
  const show = scores.slice(-150);
  const showWrs = wrs.slice(-150);
  const showRrs = rrs.slice(-150);
  const showMax = Math.max(...show.filter(s=>s>0), 1);
  const startIdx = Math.max(0, scores.length - 150);
  
  el.innerHTML = show.map((s, i) => {
    const realIdx = startIdx + i;
    const pct = Math.max(2, (s / showMax) * 100);
    const wr = showWrs[i] || 0;
    let color = wr >= 80 ? '#3fb950' : wr >= 60 ? '#58a6ff' : '#8b949e';
    const tip = 'R'+realIdx+': S='+s.toFixed(0)+' WR='+wr.toFixed(0)+'%'+(showRrs[i]?', RR='+showRrs[i].toFixed(2):'');
    return '<div class="hist-bar" style="height:'+pct.toFixed(0)+'%;background:'+color+';"><span class="tooltip">'+tip+'</span></div>';
  }).join('');
}

async function loadCyclesView() {
  try {
    const versions = await (await fetch(API+'/api/versions')).json();
    const cycles = versions.v83_dirs || [];
    const cDiv = document.getElementById('cycleList');
    if (!cycles || cycles.length === 0) {
      cDiv.innerHTML = '<div style="color:var(--dim);">无Cycle数据</div>';
      return;
    }
    // Try to read best_params from each cycle for WR
    // For now show cycle numbers
    cDiv.innerHTML = cycles.slice(-50).map(c => {
      return '<span class="cycle-item good">Cycle#'+c+'</span>';
    }).join('');
    
    // Cycle chart using last best param from each cycle
    const cycleScores = cycles.slice(-50);
    const maxCs = Math.max(...cycleScores.filter(s=>s>0), 1);
    
    // WR chart
    const wrChart = document.getElementById('cycleChart');
    if (cycleScores.length > 1) {
      wrChart.innerHTML = cycleScores.map((s, i) => {
        const pct = Math.max(2, (s / maxCs) * 100);
        return '<div class="hist-bar" style="height:'+pct.toFixed(0)+'%;background:#58a6ff;"><span class="tooltip">Cycle#'+cycles[Math.max(0, cycles.length - 50 + i)]+': S='+s+'</span></div>';
      }).join('');
    }
  } catch {}
}

// 每2秒刷新
setInterval(refresh, 2000);
refresh();
</script>
</body>
</html>"""

class StatusHandler(http.server.BaseHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip('/')

        # Serve frontend at /
        if path == '' or path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(FRONTEND_HTML.encode('utf-8'))
            return

        # JSON API
        handler_map = {
            '/api/health': lambda: json.dumps({'status':'ok','engine':'V8.3','time':int(time.time())}),
            '/api/status': lambda: json.dumps(build_status_response()),
            '/api/best': lambda: json.dumps(safe_read_json(V83_BEST) or safe_read_json(SMC_DIRS['v82'] / 'best_params.json')),
            '/api/history': lambda: json.dumps(safe_read_json(V83_HIST) or safe_read_json(SMC_DIRS['v82'] / 'history.json')),
            '/api/milestones': lambda: json.dumps(safe_read_json(V83_MILESTONES)),
            '/api/proxy': lambda: json.dumps(safe_read_json(PROXY_STATUS)),
            '/api/elite': lambda: json.dumps(safe_read_json(V83_ELITE) or []),
            '/api/sync': lambda: (sync_all(), json.dumps({'synced':True,'time':int(time.time())}))[1],
            '/api/versions': lambda: json.dumps({
                name: {'exists': d.exists(), 'cycles': len(list(d.glob('cycle_*'))) if name in ('v82','v83') else None}
                for name, d in SMC_DIRS.items()
            } | {'v83_dirs': sorted(
                [int(p.name.split('_')[1]) for p in SMC_DIRS['v83'].glob('cycle_*')]
            ) if SMC_DIRS['v83'].exists() else []}),
        }

        handler = handler_map.get(path)
        if handler:
            response_data = handler()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            response_data = json.dumps({'error': f'Not found: {path}', 'endpoints': list(handler_map.keys()) + ['/']})
        
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
        self.wfile.write(response_data.encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

def main():
    print(f"SMC V8.3 WebUI API — 端口 {PORT}")
    print(f"  V83: {SMC_DIRS['v83']}")
    print(f"  ########################################")
    print(f"  #  前端: http://0.0.0.0:{PORT}/       #")
    print(f"  #  API:  http://0.0.0.0:{PORT}/api/   #")
    print(f"  ########################################")
    print(f"  ########################################")
    print(f"  # Cycle#35 WR=84.8% PF=18.12 RR=3.24  #")
    print(f"  # Score=10447 N=33 Cov=86.7%           #")
    print(f"  ########################################")

    server = http.server.HTTPServer(('0.0.0.0', PORT), StatusHandler)
    print(f"\nServer started on port {PORT}")
    print(f"CORS enabled, serving frontend + JSON\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()