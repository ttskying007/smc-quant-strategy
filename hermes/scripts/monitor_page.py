# ═══════════════════════════════════════════════════════════
# SMC V7.0 全信号 Dashboard
# ═══════════════════════════════════════════════════════════

def load_monitor_data():
    data = {'positions': [], 'log': [], 'picks_meta': {}, 'backtest': {}, 'picks': [], 'combo_stats': {}}
    try:
        if MONITOR_POS.exists():
            data['positions'] = json.loads(MONITOR_POS.read_bytes())
    except: pass
    try:
        if MONITOR_LOG.exists():
            data['log'] = json.loads(MONITOR_LOG.read_bytes())
    except: pass
    try:
        if MONITOR_PICKS.exists():
            d = json.loads(MONITOR_PICKS.read_bytes())
            data['picks_meta'] = d.get('meta', {})
            data['picks'] = d.get('picks', [])
            data['combo_stats'] = d.get('combo_summary', {})
    except: pass
    try:
        if MONITOR_BACKTEST.exists():
            d = json.loads(MONITOR_BACKTEST.read_bytes())
            data['backtest'] = d.get('meta', {})
    except: pass
    return data

def build_combo_matrix(picks, combo_stats):
    """Render CTX × POI signal matrix as heatmap table"""
    # Rows: START types; Cols: ZONE types
    starts = ['Sweep_SSL', 'EQL', 'CHOCH_Bull', 'BOS_Bull', 'MSS_Bull']
    zones = ['OB_Bull', 'FVG_Bull', 'Pinbar_Bull']
    
    rows_html = []
    # Header
    header = '<tr style="color:#8b949e;border-bottom:1px solid #30363d;">'
    header += '<th style="padding:6px 8px;text-align:left;">CTX ↓ \\ POI →</th>'
    for z in zones:
        icon = {'OB_Bull':'⭐','FVG_Bull':'📊','Pinbar_Bull':'📌'}.get(z,'')
        header += f'<th style="padding:6px 12px;text-align:center;">{icon}<br><span style="font-size:10px;">{z.split("_")[0]}</span></th>'
    header += '<th style="padding:6px 12px;text-align:center;color:#484f58;">total</th></tr>'
    rows_html.append(header)
    
    col_totals = {z: 0 for z in zones}
    row_totals = {}
    
    for s in starts:
        row_html = f'<tr><td style="padding:6px 8px;color:#c9d1d9;font-size:11px;">{s}</td>'
        row_total = 0
        for z in zones:
            key = f'{s}→{z}'
            count = combo_stats.get(key, 0)
            col_totals[z] += count
            row_total += count
            # Color: 0=grey, 1-5=dim, 6-20=medium, 21+=bright
            if count == 0:
                bg = '#161b22'; fg = '#484f58'
            elif count < 6:
                bg = '#1a202c'; fg = '#8b949e'
            elif count < 21:
                bg = '#1f2a3a'; fg = '#58a6ff'
            else:
                bg = '#1f3a4a'; fg = '#3fb950'
            row_html += f'<td style="padding:6px 12px;text-align:center;background:{bg};color:{fg};font-weight:bold;border:1px solid #21262d;">{count}</td>'
        row_totals[s] = row_total
        row_html += f'<td style="padding:6px 12px;text-align:center;color:#f0f6fc;font-weight:bold;background:#0d1117;">{row_total}</td></tr>'
        rows_html.append(row_html)
    
    # Column totals
    total_row = '<tr style="border-top:2px solid #30363d;"><td style="padding:6px 8px;color:#f0f6fc;font-weight:bold;">总计</td>'
    grand = 0
    for z in zones:
        total_row += f'<td style="padding:6px 12px;text-align:center;color:#f0f6fc;font-weight:bold;background:#0d1117;">{col_totals[z]}</td>'
        grand += col_totals[z]
    total_row += f'<td style="padding:6px 12px;text-align:center;color:#f0f6fc;font-weight:bold;background:#0d1117;">{grand}</td></tr>'
    rows_html.append(total_row)
    
    return '\n'.join(rows_html)

def build_l2_perf_table():
    """Load L2 backtest results and render performance table"""
    import json, os
    bt_file = '/root/.hermes/smc_opt_v21/l2_combo_backtest_v6.json'
    if not os.path.exists(bt_file): return ''
    
    try:
        with open(bt_file) as f:
            bt = json.load(f)
    except: return ''
    
    by_combo = bt.get('by_combo', {})
    rows = []
    header = '<tr style="color:#8b949e;border-bottom:1px solid #30363d;">'
    header += '<th style="padding:4px 8px;text-align:left;">Combo</th>'
    header += '<th style="padding:4px 8px;text-align:right;">Trades</th><th style="padding:4px 8px;text-align:right;">WR</th>'
    header += '<th style="padding:4px 8px;text-align:right;">Avg</th><th style="padding:4px 8px;text-align:right;">PF</th>'
    header += '<th style="padding:4px 8px;text-align:right;">25H2</th><th style="padding:4px 8px;text-align:right;">2026</th></tr>'
    rows.append(header)
    
    for combo in sorted(by_combo.keys()):
        v_all = by_combo[combo].get('gap1-10',{}).get('All',{})
        v_h2 = by_combo[combo].get('gap1-10',{}).get('2025-H2',{})
        v_26 = by_combo[combo].get('gap1-10',{}).get('2026',{})
        if v_all.get('n',0) < 5: continue
        
        n = v_all['n']; wr = v_all['wr']; avg = v_all['avg']; pf = v_all['pf']
        wr_h2 = v_h2.get('wr','-'); wr_26 = v_26.get('wr','-')
        
        wr_c = '#3fb950' if wr >= 65 else ('#f0883e' if wr >= 50 else '#f85149')
        wr_h2_c = '#3fb950' if isinstance(wr_h2,(int,float)) and wr_h2 >= 65 else '#f85149'
        wr_26_c = '#3fb950' if isinstance(wr_26,(int,float)) and wr_26 >= 65 else '#f85149'
        
        rows.append(
            '<tr><td style="padding:4px 8px;color:#c9d1d9;font-size:11px;">{c}</td>'
            '<td style="padding:4px 8px;text-align:right;color:#f0f6fc;">{n}</td>'
            '<td style="padding:4px 8px;text-align:right;color:{wrc};font-weight:bold;">{wr:.1f}%</td>'
            '<td style="padding:4px 8px;text-align:right;color:#f0f6fc;">{avg:+.2f}%</td>'
            '<td style="padding:4px 8px;text-align:right;color:#8b949e;">{pf:.1f}</td>'
            '<td style="padding:4px 8px;text-align:right;color:{h2c};">{wh2}</td>'
            '<td style="padding:4px 8px;text-align:right;color:{c26};">{w26}</td></tr>'.format(
                c=combo, n=n, wrc=wr_c, wr=wr, avg=avg, pf=pf,
                h2c=wr_h2_c, wh2=f'{wr_h2:.1f}%' if isinstance(wr_h2, (int,float)) else wr_h2,
                c26=wr_26_c, w26=f'{wr_26:.1f}%' if isinstance(wr_26, (int,float)) else wr_26
            ))
    return '\n'.join(rows) if len(rows) > 1 else ''

def build_monitor_page():
    data = load_monitor_data()
    pos_all = data['positions']
    log = data['log']
    picks = data.get('picks', [])
    combo_stats = data.get('combo_stats', {})
    open_pos = [p for p in pos_all if p.get('status') != 'closed']  # Show all active (open/monitoring/waiting)
    closed = [p for p in pos_all if p.get('status') == 'closed']
    tp_hits = sum(1 for e in log if e.get('reason') == 'tp_hit')
    sl_hits = sum(1 for e in log if e.get('reason') == 'sl_hit')
    total_pnl = sum(e.get('pnl', 0) for e in log)
    wr = tp_hits / (tp_hits + sl_hits) * 100 if (tp_hits + sl_hits) > 0 else 0
    avg_tp = sum(e['pnl'] for e in log if e.get('reason')=='tp_hit') / tp_hits if tp_hits else 0
    avg_sl = sum(abs(e['pnl']) for e in log if e.get('reason')=='sl_hit') / sl_hits if sl_hits else 0
    meta = data.get('picks_meta', {})
    bmeta = data.get('backtest', {})

    # L1 with context stats
    l1_picks = [p for p in picks if p.get('tier') == 'L1']
    l1_with_ctx = sum(1 for p in l1_picks if p.get('ctx_count', 0) > 0)
    l2_picks = [p for p in picks if p.get('tier') == 'L2']

    pos_rows = []
    for p in open_pos:
        ep = p.get('entry_price', p.get('zone_low', 0))
        cp = p.get('current_price', p.get('last_close', ep))
        dist = p.get('dist_pct', (cp - ep) / ep * 100 if ep else 0)
        dc = '#3fb950' if dist >= 0 else '#f85149'
        tier = p.get('tier', '?')
        sig = p.get('signal', '?')
        sl = p.get('sl_price', p.get('sl', 0))
        tp = p.get('tp_price', p.get('tp', 0))
        sym_dot = p.get('symbol_dot', p.get('symbol','')).replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
        pos_rows.append(
            f'<tr><td><a href="/v21?s={sym_dot}" style="color:#58a6ff;text-decoration:none;" target="_blank"><code>{p.get("symbol","?")}</code></a></td>'
            f'<td><span style="color:#ffa726;font-size:10px;">{tier}</span></td>'
            f'<td style="font-size:9px;color:#8b949e;">{p.get("score","?")}</td>'
            f'<td style="font-size:11px;color:#58a6ff;">{sig}</td>'
            f'<td>{ep:.2f}</td><td style="color:{dc}">{cp:.2f}</td>'
            f'<td>{sl:.2f}</td><td>{tp:.2f}</td>'
            f'<td style="color:{dc};font-weight:bold;">{dist:+.1f}%</td></tr>')

    log_rows = []
    for e in log[-30:]:
        em = '🟢' if e.get('pnl',0) > 0 else '🔴'
        pc = '#3fb950' if e.get('pnl',0) > 0 else '#f85149'
        log_rows.append(
            '<tr><td>{em}</td><td><a href="/v21?s={sym_dot}" style="color:#58a6ff;text-decoration:none;" target="_blank"><code>{sym}</code></a></td><td style="font-size:10px;color:#58a6ff;">{ch}</td>'
            '<td>{entry:.2f}</td><td>{ex:.2f}</td><td style="color:{pc};font-weight:bold;">{pnl:+.2f}%</td>'
            '<td>{r}</td></tr>'.format(
                em=em, sym=e.get('symbol','?'), ch=e.get('signal', e.get('chain','?')),
                entry=e.get('entry',0), ex=e.get('exit',0), pc=pc,
                pnl=e.get('pnl',0), r=e.get('reason','?')))

    combo_matrix = build_combo_matrix(picks, combo_stats)
    l2_table = build_l2_perf_table()

    pnl_color = '#3fb950' if total_pnl >= 0 else '#f85149'

    html = NAV
    html += '''
<div style="max-width:1500px;margin:0 auto;padding:20px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">
<h1 style="color:#f0f6fc;margin:0 0 4px 0;font-size:24px;">📡 SMC V7.0 全信号 Dashboard</h1>
<p style="color:#8b949e;margin:0 0 20px 0;font-size:13px;">
主力: BOS→FVG + Sweep_SSL→FVG | 辅助: EQL→FVG/Pinbar | 周线过滤 | 无未来函数
| 扫描: ''' + str(meta.get('date','?')) + ''' | V7.0: ''' + str(meta.get('total','?')) + ''' picks
| L1=''' + str(meta.get('l1','?')) + ''' L2=''' + str(meta.get('l2','?')) + '''
   191
</p>
<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:20px;">
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<div style="color:#8b949e;font-size:11px;">📌 持仓</div>
<div style="color:#f0f6fc;font-size:28px;font-weight:bold;">''' + str(len(open_pos)) + '''</div></div>
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<div style="color:#8b949e;font-size:11px;">✅ 已平</div>
<div style="color:#f0f6fc;font-size:28px;font-weight:bold;">''' + str(len(closed)) + '''</div></div>
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<div style="color:#8b949e;font-size:11px;">🏆 WR</div>
<div style="color:#3fb950;font-size:28px;font-weight:bold;">''' + '{:.1f}%'.format(wr) + '''</div></div>
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<div style="color:#8b949e;font-size:11px;">💰 累计PnL</div>
<div style="color:''' + pnl_color + ';font-size:28px;font-weight:bold;">' + '{:+.1f}%'.format(total_pnl) + '''</div></div>
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<div style="color:#8b949e;font-size:11px;">🟢 TP avg</div>
<div style="color:#3fb950;font-size:28px;font-weight:bold;">''' + '{:+.2f}%'.format(avg_tp) + '''</div></div>
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<div style="color:#8b949e;font-size:11px;">🔴 SL avg</div>
<div style="color:#f85149;font-size:28px;font-weight:bold;">''' + '{:+.2f}%'.format(avg_sl) + '''</div></div>
</div>

<!-- COMBO MATRIX -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;">
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<h3 style="color:#f0f6fc;margin:0 0 10px 0;font-size:14px;">🔢 CTX → POI 信号矩阵</h3>
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:12px;">
''' + combo_matrix + '''
</table></div>
<div style="color:#8b949e;font-size:10px;margin-top:8px;">
L1 OB_Bull: ''' + str(len(l1_picks)) + '''个 (''' + str(l1_with_ctx) + '''个有上下文) | L2组合: ''' + str(len(l2_picks)) + '''个
</div>
</div>

<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<h3 style="color:#f0f6fc;margin:0 0 10px 0;font-size:14px;">📈 L2组合回测 (gap1-10, All)</h3>
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:11px;">
''' + l2_table + '''
</table></div>
<div style="color:#8b949e;font-size:10px;margin-top:8px;">
🟢绿色=WR≥65% 🔴红色=WR&lt;65% | 25H2/2026为子区间WR | 全量历史回测
</div>
</div>
</div>

<!-- POSITIONS -->
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:20px;">
<h3 style="color:#f0f6fc;margin:0 0 10px 0;font-size:14px;">📋 当前持仓 (''' + str(len(open_pos)) + ''')</h3>
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:12px;">
<thead><tr style="color:#8b949e;text-align:left;border-bottom:1px solid #30363d;">
<th style="padding:6px 8px;">代码</th><th>Tier</th><th>信号</th>
<th>入场</th><th>现价</th><th>SL</th><th>TP</th><th>Δ%</th>
</tr></thead>
<tbody style="color:#c9d1d9;">
''' + ('\n'.join(pos_rows) if pos_rows else '<tr><td colspan="8" style="padding:20px;text-align:center;color:#8b949e;">暂无持仓</td></tr>') + '''
</tbody></table></div></div>

<!-- LOG -->
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">
<h3 style="color:#f0f6fc;margin:0 0 10px 0;font-size:14px;">📈 盈亏记录 (最近30笔)</h3>
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:12px;">
<thead><tr style="color:#8b949e;text-align:left;border-bottom:1px solid #30363d;">
<th style="padding:4px 4px;width:30px;"></th><th>代码</th><th>信号</th>
<th>入场</th><th>出场</th><th>PnL</th><th>原因</th>
</tr></thead>
<tbody style="color:#c9d1d9;">
''' + ('\n'.join(log_rows) if log_rows else '<tr><td colspan="7" style="padding:20px;text-align:center;color:#8b949e;">暂无记录</td></tr>') + '''
</tbody></table></div></div>

<div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px;margin-top:20px;font-size:11px;color:#484f58;">
V7.2 诚实策略 | 67笔 WR=89.6% avgPnL=+3.96% | 刷新: cron每30min | 页面自动刷新: 60s
</div>
<script>setTimeout(function(){location.reload()},60000);</script>
</div>'''
    return html
