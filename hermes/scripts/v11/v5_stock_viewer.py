#!/usr/bin/env python3
"""
V5 个股K线查看器 — V45引擎实时回测 + V2风格信号绘制
=====================================================
功能:
  - V45实时回测(单只~50ms)
  - 14种信号全检测 + 编号圆圈(FVG/OB/Sweep/CHOCH/MSS等)
  - FVG/OB/BPR等信号区域填充
  - Sweep/CHOCH/MSS等信号线
  - 入场点(三角) + 出场点(菱形) + SL线(虚线)
  - 组合信号标签(FVG→OB→SWP)
  - 信号过滤开关
  - 交易明细表格
"""
import json, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.v45_engine import load_ohlcv, backtest_stock_v45
from v11.signals_v11 import detect_all_signals_v11

CACHE_DIR = Path('/root/.hermes/kline_cache')

# ── Signal style definitions (matches V2) ──
SIG_STYLE = {
    'FVG_Bull':  {'fill': 'rgba(156,39,176,0.2)','stroke': 'rgba(156,39,176,0.6)','label': 'FVG','z': 2},
    'FVG_Bear':  {'fill': 'rgba(233,30,99,0.2)','stroke': 'rgba(233,30,99,0.6)','label': 'FVG','z': 2},
    'IFVG_Bull': {'fill': 'rgba(138,43,226,0.2)','stroke': 'rgba(138,43,226,0.6)','label': 'IFVG','z': 2},
    'IFVG_Bear': {'fill': 'rgba(138,43,226,0.2)','stroke': 'rgba(138,43,226,0.6)','label': 'IFVG','z': 2},
    'OB_Bull':   {'fill': 'rgba(33,150,243,0.15)','stroke': 'rgba(33,150,243,0.5)','label': 'OB','z': 3},
    'OB_Bear':   {'fill': 'rgba(244,67,54,0.15)','stroke': 'rgba(244,67,54,0.5)','label': 'OB','z': 3},
    'BPR_Bull':  {'fill': 'rgba(0,150,136,0.15)','stroke': 'rgba(0,150,136,0.5)','label': 'BPR','z': 3},
    'BPR_Bear':  {'fill': 'rgba(0,150,136,0.15)','stroke': 'rgba(0,150,136,0.5)','label': 'BPR','z': 3},
    'SweepDown': {'stroke': '#FFEB3B','type':'dashed','width':2,'label':'Sweep','z':4},
    'SweepUp':   {'stroke': '#FF9800','type':'dashed','width':2,'label':'Sweep','z':4},
    'CHOCH_Bull':{'stroke': '#00BCD4','type':'solid','width':2,'label':'CHOCH','z':5},
    'CHOCH_Bear':{'stroke': '#E91E63','type':'solid','width':2,'label':'CHOCH','z':5},
    'MSS_Bull':  {'stroke': '#4FC3F7','type':'dashed','width':2,'label':'MSS','z':5},
    'MSS_Bear':  {'stroke': '#4FC3F7','type':'dashed','width':2,'label':'MSS','z':5},
    'OTE_Bull':  {'fill': 'rgba(76,175,80,0.15)','stroke':'rgba(76,175,80,0.5)','label':'OTE','z':1},
    'OTE_Bear':  {'fill': 'rgba(76,175,80,0.15)','stroke':'rgba(76,175,80,0.5)','label':'OTE','z':1},
    'EQL_High':  {'stroke': '#B0BEC5','type':'solid','width':1,'label':'EQL','z':3},
    'EQL_Low':   {'stroke': '#B0BEC5','type':'solid','width':1,'label':'EQL','z':3},
    'PO3_Acc':   {'fill': 'rgba(33,150,243,0.12)','stroke':'rgba(33,150,243,0.4)','label':'PO3-A','z':3},
    'PO3_Man':   {'fill': 'rgba(244,67,54,0.12)','stroke':'rgba(244,67,54,0.4)','label':'PO3-M','z':3},
    'PO3_DIS':   {'fill': 'rgba(76,175,80,0.12)','stroke':'rgba(76,175,80,0.4)','label':'PO3-D','z':3},
    'LiquidityVoid': {'stroke':'#9E9E9E','type':'dashed','width':1,'label':'LV','z':2},
    'Rejection_Resistance': {'fill':'rgba(255,152,0,0.12)','stroke':'rgba(255,152,0,0.4)','label':'RB','z':3},
    'Rejection_Support': {'fill':'rgba(76,175,80,0.12)','stroke':'rgba(76,175,80,0.4)','label':'RB','z':3},
    'BreakerBlock_Bull': {'fill':'rgba(156,39,176,0.12)','stroke':'rgba(156,39,176,0.4)','label':'BRK','z':3},
    'BreakerBlock_Bear': {'fill':'rgba(156,39,176,0.12)','stroke':'rgba(156,39,176,0.4)','label':'BRK','z':3},
}

SIG_FAMILY = {
    'FVG_Bull':'fvg','FVG_Bear':'fvg','IFVG_Bull':'ifvg','IFVG_Bear':'ifvg',
    'OB_Bull':'ob','OB_Bear':'ob','BPR_Bull':'bpr','BPR_Bear':'bpr',
    'SweepDown':'sweep','SweepUp':'sweep',
    'CHOCH_Bull':'choch','CHOCH_Bear':'choch',
    'MSS_Bull':'mss','MSS_Bear':'mss',
    'OTE_Bull':'ote','OTE_Bear':'ote',
    'EQL_High':'eql','EQL_Low':'eql',
    'PO3_Acc':'po3','PO3_Man':'po3','PO3_DIS':'po3',
    'LiquidityVoid':'lv','Rejection_Resistance':'rb','Rejection_Support':'rb',
    'BreakerBlock_Bull':'brk','BreakerBlock_Bear':'brk',
}

SIG_MAP = {
    'fvg':'fvg','ifvg':'ifvg','ob':'ob','sweep':'sweep',
    'choch':'choch','mss':'mss','ote':'ote','eql':'eql',
    'po3':'po3','lv':'lv','rb':'rb','brk':'brk','bpr':'bpr',
}

def fmt_date(d):
    s = str(d).strip()
    if len(s) >= 10 and s[4]=='-' and s[7]=='-': return s[:10]
    if len(s)==8 and s.isdigit(): return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    if len(s)>=12 and s.isdigit(): return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return s

def short_label(t):
    return SIG_STYLE.get(t,{}).get('label',t[:4])

def build_v5_html(symbol):
    ohlcv = load_ohlcv(symbol)
    if not ohlcv:
        return f'<p style="color:#f85149;padding:20px">No data: {symbol}</p>'

    # Add formatted dates
    for b in ohlcv:
        if 'date' not in b and 't' in b:
            b['date'] = str(b['t'])
        b['_date'] = fmt_date(b.get('date',b.get('t','')))[:10]

    # V45 backtest
    result = backtest_stock_v45(ohlcv, symbol)
    if not result:
        return f'<p style="color:#8b949e;padding:20px">No trades: {symbol}</p>'

    trades = result['trades']
    perf = result['perf']

    # ── Detect all 14 signals (for visualization) ──
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
    signals_result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_sigs = signals_result.get('all', [])

    # Number signals sequentially
    sig_counter = 0
    numbered_sigs = []
    for sig in all_sigs:
        sig_counter += 1
        sig['seq'] = sig_counter
        numbered_sigs.append(sig)

    dates = [str(b.get('date',b.get('t',''))) for b in ohlcv]
    dates_short = [str(b.get('_date','')) for b in ohlcv]
    ohlcv_data = [[b['o'],b['c'],b['l'],b['h']] for b in ohlcv]
    max_idx = len(dates) - 1

    # ── Build signal visual markers ──
    mark_areas, mark_lines, mark_points = [], [], []

    for sig in numbered_sigs:
        stype = sig['type']
        style = SIG_STYLE.get(stype, {})
        family = SIG_FAMILY.get(stype, 'other')
        seq = sig['seq']
        label = style.get('label', stype[:4])
        sname = f"{seq}{label}"
        idx = sig['idx']
        if idx < 0 or idx >= len(dates):
            continue
        sig_date = dates_short[idx] if idx < len(dates_short) else ''
        sig_upper = sig.get('upper', 0)
        sig_lower = sig.get('lower', 0)
        sig_price = sig.get('price', 0)
        sig_strength = sig.get('strength', 0)
        sig_conf = sig.get('confidence', 0)
        sig_dir = sig.get('direction', 'neutral')

        tt = (f'Signal #{seq}: {stype}<br/>Date: {sig_date}<br/>Direction: {sig_dir}<br/>'
              f'Strength: {sig_strength:.1f}<br/>Confidence: {sig_conf:.2f}')
        if sig_upper > 0 and sig_lower > 0:
            tt += f'<br/>Range: {sig_lower:.2f} - {sig_upper:.2f}'
        if sig_price > 0:
            tt += f'<br/>Price: {sig_price:.2f}'

        # Signal area (FVG/OB/BPR/OTE/PO3/BRK/RB)
        if 'fill' in style:
            upper = sig.get('upper', 0)
            lower = sig.get('lower', 0)
            if upper > 0 and lower > 0 and upper != lower:
                end_x = dates[min(idx + 10, max_idx)]
                mark_areas.append({
                    'family': family, 'signal': stype, 'seq': seq,
                    '_tooltip': tt,
                    'data': [
                        {'xAxis': dates[idx], 'yAxis': lower,
                         'itemStyle': {'color': style['fill'],
                                       'borderColor': style['stroke'],
                                       'borderWidth': 1 if upper-lower>0.01 else 0,
                                       'opacity': 0.8}},
                        {'xAxis': end_x, 'yAxis': upper}
                    ]
                })

        # Signal line (Sweep/CHOCH/MSS/EQL/LV)
        if 'stroke' in style and 'fill' not in style:
            price = sig.get('price', 0)
            if price == 0:
                price = sig.get('upper', 0)
            if price <= 0:
                continue
            end_x = dates[min(idx + 20, max_idx)]
            mark_lines.append({
                'signal': stype, 'family': family, 'seq': seq,
                '_tooltip': tt,
                '_pair': [
                    {'xAxis': dates[idx], 'yAxis': price},
                    {'xAxis': end_x, 'yAxis': price}
                ],
                'lineStyle': {
                    'color': style['stroke'],
                    'type': style.get('type', 'dashed'),
                    'width': style.get('width', 1),
                    'opacity': 0.6
                },
                'label': {
                    'show': True, 'formatter': sname,
                    'color': style['stroke'], 'fontSize': 9, 'position': 'start'
                }
            })

        # Signal point (numbered circle)
        price = sig.get('price', sig.get('upper', 0))
        if price > 0:
            color_map = {
                'FVG_Bull':'#9C27B0','FVG_Bear':'#E91E63','OB_Bull':'#2196F3','OB_Bear':'#F44336',
                'SweepDown':'#FFEB3B','SweepUp':'#FF9800','CHOCH_Bull':'#00BCD4','CHOCH_Bear':'#E91E63',
                'MSS_Bull':'#4FC3F7','MSS_Bear':'#4FC3F7','EQL_High':'#B0BEC5','EQL_Low':'#B0BEC5',
                'OTE_Bull':'#4CAF50','OTE_Bear':'#4CAF50','PO3_Acc':'#2196F3','PO3_Man':'#F44336',
                'PO3_DIS':'#4CAF50','LiquidityVoid':'#9E9E9E','Rejection_Resistance':'#FF9800',
                'Rejection_Support':'#FF9800','BreakerBlock_Bull':'#9C27B0','BreakerBlock_Bear':'#9C27B0',
                'IFVG_Bull':'#7B1FA2','IFVG_Bear':'#7B1FA2','BPR_Bull':'#009688','BPR_Bear':'#009688',
            }
            color = color_map.get(stype, '#888')
            mark_points.append({
                'signal': stype, 'family': family, 'seq': seq,
                'name': sname,
                'coord': [dates[idx], price],
                'value': str(seq),
                '_tooltip': tt,
                'symbol': 'circle', 'symbolSize': 8,
                'itemStyle': {'color': color, 'borderColor': '#fff', 'borderWidth': 1},
                'label': {
                    'show': True, 'formatter': str(seq),
                    'color': '#fff', 'fontSize': 8,
                    'fontWeight': 'bold', 'position': 'right'
                }
            })

    # ── Build trade markers ──
    entry_pts, exit_pts, sl_pts = [], [], []
    trade_sigs_html_list = []

    for i, t in enumerate(trades):
        entry_idx = t['entry_idx']
        entry_price = t['entry_price']

        # Combo signal labels (like V2: nearby signals within 5 bars)
        nearby = [s for s in numbered_sigs if abs(s['idx'] - entry_idx) <= 5]
        ct = list(dict.fromkeys(s['type'] for s in nearby[:5]))
        cs = []
        for c in ct:
            base = short_label(c)
            cs.append(base)
        combo = '→'.join(cs) if cs else f'E{i+1}'

        entry_pts.append({
            'idx': entry_idx, 'price': entry_price,
            'won': t['won'], 'rr': t.get('rr', 0),
            'pnl': t.get('pnl_pct', 0), 'num': i+1,
            'combo': combo,
        })
        exit_pts.append({
            'idx': t['exit_idx'], 'price': t['exit_price'],
            'pnl': t.get('pnl_pct', 0),
        })
        sl_pts.append({
            'entry_idx': entry_idx, 'sl': t['sl'],
        })

        # HTML trade row with signal tags
        nearby_tags = [s for s in numbered_sigs if abs(s['idx'] - entry_idx) <= 5][:6]
        sigs_html = ''.join(
            f'<span class="signals sig-{SIG_MAP.get(s["type"].split("_")[0].lower(),"fvg")}">'
            f'{s["seq"]}{short_label(s["type"])}</span>'
            for s in nearby_tags
        )
        trade_sigs_html_list.append(sigs_html)

    # ── Stock list ──
    all_symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                         for f in CACHE_DIR.glob('*_daily_300.json')])
    stock_options = ''.join(
        f'<option value="{s}"{" selected" if s==symbol else ""}>{s}</option>'
        for s in all_symbols
    )

    total_pnl = sum(t['pnl_pct'] for t in trades)
    wins = sum(1 for t in trades if t['won'])

    # ── Build trade rows ──
    trade_rows = []
    for i, t in enumerate(trades):
        pnl_c = 'win' if t.get('pnl_pct',0) > 0 else 'loss'
        wl_c = 'win' if t['won'] else 'loss'
        wl_t = 'W' if t['won'] else 'L'
        rr = t.get('rr', 0)
        hold = t.get('hold_bars', 0)
        sl_type = t.get('sl_type', '?')
        entry_type = t.get('entry_type', '?')
        trade_rows.append(
            f'<tr>'
            f'<td>{i+1}</td>'
            f'<td class="date">{dates[t["entry_idx"]]}</td>'
            f'<td class="date">{dates[t["exit_idx"]]}</td>'
            f'<td>{hold}</td>'
            f'<td>{t["entry_price"]:.2f}</td>'
            f'<td>{t["exit_price"]:.2f}</td>'
            f'<td class="num">{t["sl"]:.2f}</td>'
            f'<td><span class="tag-{sl_type}">{sl_type}</span></td>'
            f'<td><span class="entry-tag">{entry_type}</span></td>'
            f'<td class="{pnl_c}">{t["pnl_pct"]:+.2f}%</td>'
            f'<td class="{wl_c}">{wl_t}</td>'
            f'<td class="num">{rr:.1f}x</td>'
            f'<td class="signal-cell">{trade_sigs_html_list[i]}</td>'
            f'</tr>'
        )
    rows_html = ''.join(trade_rows)

    # ── Serialize for JS ──
    dates_j = json.dumps(dates)
    ohlcv_j = json.dumps(ohlcv_data)
    entry_j = json.dumps(entry_pts)
    exit_j = json.dumps(exit_pts)
    sl_j = json.dumps(sl_pts)
    areas_j = json.dumps(mark_areas)
    lines_j = json.dumps(mark_lines)
    points_j = json.dumps(mark_points)
    sym_j = json.dumps(symbol)
    stocks_j = json.dumps(all_symbols)

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>{symbol} V5</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}
.header{{background:#161b22;padding:15px 20px;border-bottom:1px solid #30363d}}
.header h1{{color:#00d4aa;font-size:20px}}
.header .sub{{color:#8b949e;font-size:12px;margin-top:4px}}
.controls{{background:#161b22;padding:10px 20px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.controls select{{padding:6px 10px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;font-size:13px;min-width:180px}}
.controls .btn{{padding:6px 14px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}}
.controls .btn:hover{{background:#2ea043}}
.controls .btn-secondary{{background:#21262d;color:#c9d1d9}}
.controls .btn-secondary:hover{{background:#30363d}}
.controls .stats{{display:flex;gap:16px;font-size:12px}}
.controls .stat{{text-align:center}}
.controls .stat .val{{font-weight:bold;font-size:15px}}
.controls .stat .lbl{{color:#8b949e;font-size:10px}}
.win{{color:#3fb950}} .loss{{color:#f85149}} .blue{{color:#58a6ff}} .num{{text-align:right}}
#chart{{width:100%;height:520px}}
.filters{{background:#161b22;padding:8px 20px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px}}
.filters label{{display:flex;align-items:center;gap:4px;cursor:pointer;padding:3px 8px;border-radius:4px;background:#0d1117;border:1px solid #30363d}}
.filters input{{margin:0}}
.detail{{padding:16px;max-width:1400px;margin:0 auto}}
.summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:12px 0}}
.skpi{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px;text-align:center}}
.skpi .v{{font-size:20px;font-weight:bold}}
.skpi .l{{font-size:11px;color:#8b949e;margin-top:2px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:#161b22;padding:6px 8px;text-align:left;color:#8b949e;font-weight:600;border-bottom:2px solid #30363d;position:sticky;top:0;white-space:nowrap}}
td{{padding:5px 8px;border-bottom:1px solid #21262d;white-space:nowrap}}
tr:hover{{background:#161b22}}
.date{{font-size:10px;color:#8b949e}}.signal-cell{{max-width:200px;overflow:hidden}}
.signals{{display:inline-block;padding:2px 4px;border-radius:3px;font-size:10px;margin:0 1px}}
.sig-fvg{{background:#9C27B044;color:#CE93D8}}.sig-ifvg{{background:#7B1FA244;color:#CE93D8}}
.sig-ob{{background:#2196F344;color:#90CAF9}}.sig-sweep{{background:#FF980044;color:#FFCC80}}
.sig-choch{{background:#00BCD444;color:#80DEEA}}.sig-mss{{background:#4FC3F744;color:#B3E5FC}}
.sig-ote{{background:#4CAF5044;color:#A5D6A7}}.sig-eql{{background:#B0BEC544;color:#CFD8DC}}
.sig-po3{{background:#7C4DFF44;color:#B388FF}}.sig-lv{{background:#9E9E9E44;color:#BDBDBD}}
.sig-rb{{background:#FF980044;color:#FFCC80}}.sig-brk{{background:#9C27B044;color:#CE93D8}}
.sig-bpr{{background:#00968844;color:#80CBC4}}
.tag-adaptive{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;background:#1f6feb22;color:#58a6ff;border:1px solid #1f6feb44}}
.tag-fvg_lower{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;background:#9C27B022;color:#CE93D8;border:1px solid #9C27B044}}
.tag-ob_lower{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;background:#2196F322;color:#90CAF9;border:1px solid #2196F344}}
.tag-swing_low{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;background:#d2992222;color:#d29922;border:1px solid #d2992244}}
.entry-tag{{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;background:#23863622;color:#3fb950;border:1px solid #23863644}}
.search-wrap{{position:relative;display:inline-block}}
.search-wrap input{{padding:6px 10px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;font-size:13px;width:200px}}
.search-wrap .dropdown{{position:absolute;top:100%;left:0;right:0;background:#161b22;border:1px solid #30363d;border-top:none;border-radius:0 0 6px 6px;max-height:300px;overflow-y:auto;z-index:1000;display:none}}
.search-wrap .dropdown div{{padding:6px 12px;cursor:pointer;font-size:13px;color:#c9d1d9}}
.search-wrap .dropdown div:hover{{background:#1f6feb33}}
</style>
<script src="/echarts.min.js"></script></head><body>

<div class="header">
  <h1>{symbol} V5 交易分析 <span style="color:#8b949e;font-size:13px;font-weight:normal">| V45 实时回测</span></h1>
  <div class="sub">
    {len(trades)}笔交易 | WR={perf['win_rate']}% |
    RR={perf['avg_rr']}x | PF={perf['profit_factor']} |
    总P&L={total_pnl:+.2f}% | 信号: {len(numbered_sigs)}
  </div>
</div>

<div class="controls">
  <div class="search-wrap">
    <input type="text" id="stockSearch" placeholder="Search stock..." autocomplete="off">
    <div class="dropdown" id="searchDropdown"></div>
  </div>
  <select name="s" onchange="goStock(this.value)">
    {stock_options}
  </select>
  <div class="stats">
    <div class="stat"><div class="val win">{perf['win_rate']}%</div><div class="lbl">胜率</div></div>
    <div class="stat"><div class="val blue">{perf['avg_rr']}x</div><div class="lbl">盈亏比</div></div>
    <div class="stat"><div class="val">{perf['profit_factor']}</div><div class="lbl">PF</div></div>
    <div class="stat"><div class="val">{perf['avg_pnl']:+.2f}%</div><div class="lbl">均利</div></div>
    <div class="stat"><div class="val">{len(trades)}</div><div class="lbl">交易数</div></div>
  </div>
</div>

<div class="filters">
  <span style="color:#8b949e;font-weight:bold;">信号过滤:</span>
  <label><input type="checkbox" class="sig-filter" data-family="fvg" checked> FVG</label>
  <label><input type="checkbox" class="sig-filter" data-family="ifvg" checked> IFVG</label>
  <label><input type="checkbox" class="sig-filter" data-family="ob" checked> OB</label>
  <label><input type="checkbox" class="sig-filter" data-family="bpr" checked> BPR</label>
  <label><input type="checkbox" class="sig-filter" data-family="sweep" checked> Sweep</label>
  <label><input type="checkbox" class="sig-filter" data-family="choch" checked> CHOCH</label>
  <label><input type="checkbox" class="sig-filter" data-family="mss" checked> MSS</label>
  <label><input type="checkbox" class="sig-filter" data-family="ote" checked> OTE</label>
  <label><input type="checkbox" class="sig-filter" data-family="eql" checked> EQL</label>
  <label><input type="checkbox" class="sig-filter" data-family="po3" checked> PO3</label>
  <label><input type="checkbox" class="sig-filter" data-family="lv" checked> LV</label>
  <label><input type="checkbox" class="sig-filter" data-family="rb" checked> RB</label>
  <label><input type="checkbox" class="sig-filter" data-family="brk" checked> BRK</label>
  <button class="btn btn-secondary" style="padding:3px 10px;font-size:11px;" onclick="document.querySelectorAll('.sig-filter').forEach(c=>c.checked=true);applyFilters();">All</button>
  <button class="btn btn-secondary" style="padding:3px 10px;font-size:11px;" onclick="document.querySelectorAll('.sig-filter').forEach(c=>c.checked=false);applyFilters();">None</button>
</div>

<div id="chart"></div>

<div class="detail">
<div class="summary-grid">
  <div class="skpi"><div class="v win">{perf['win_rate']}%</div><div class="l">胜率</div></div>
  <div class="skpi"><div class="v blue">{perf['avg_rr']:.2f}x</div><div class="l">平均RR</div></div>
  <div class="skpi"><div class="v">{perf['profit_factor']}</div><div class="l">Profit Factor</div></div>
  <div class="skpi"><div class="v">{total_pnl:+.2f}%</div><div class="l">总P&L</div></div>
  <div class="skpi"><div class="v">{wins}/{len(trades)-wins}</div><div class="l">W/L</div></div>
  <div class="skpi"><div class="v">{perf.get('vol_class','?')}</div><div class="l">波动率</div></div>
</div>

<h2>交易明细 <span style="color:#8b949e;font-size:12px;font-weight:normal">({len(trades)}笔)</span></h2>
<div style="overflow-x:auto;">
<table>
<tr>
  <th>#</th><th>入场日</th><th>出场日</th><th>持</th>
  <th>入场价</th><th>出场价</th><th>SL</th><th>SL类型</th>
  <th>入口</th><th>P&L%</th><th>W/L</th><th>RR</th><th>信号组合</th>
</tr>
{rows_html}
</table>
</div>
</div>

<script>
function goStock(s){{window.location.href='/v5_stock?s='+encodeURIComponent(s);}}
var dom=document.getElementById('chart');var chart=echarts.init(dom,'dark');
var dates={dates_j};var ohlcvData={ohlcv_j};
var entryPts={entry_j};var exitPts={exit_j};var slLines={sl_j};
var markAreas={areas_j};var markLines={lines_j};var markPoints={points_j};
var currentSymbol={sym_j};var allStocks={stocks_j};

function getActiveFamilies(){{var a={{}};document.querySelectorAll('.sig-filter').forEach(function(c){{a[c.dataset.family]=c.checked;}});return a;}}

function getSeriesOptions(){{var a=getActiveFamilies();
var fa=markAreas.filter(function(m){{return a[m.family]}}).map(function(m){{return m.data}});
var fl=markLines.filter(function(m){{return a[m.family]}}).map(function(m){{return m._pair||m}});
var fp=markPoints.filter(function(m){{return a[m.family]}});

var em=[];entryPts.forEach(function(e){{em.push({{name:'E'+e.num,coord:[dates[e.idx],e.price],value:e.combo||'E'+e.num,itemStyle:{{color:e.won?'#3fb950':'#f85149'}},symbol:'pin',symbolSize:32,label:{{show:true,formatter:e.combo||('E'+e.num),fontSize:9,color:'#fff',position:'top'}}}});}});
var xm=[];exitPts.forEach(function(e){{xm.push({{coord:[dates[e.idx],e.price],value:e.pnl.toFixed(1)+'%',itemStyle:{{color:e.pnl>0?'#79c0ff':'#d29922'}},symbol:'diamond',symbolSize:16}});}});
var sm=[];slLines.forEach(function(sl){{sm.push({{yAxis:sl.sl,lineStyle:{{color:'#d29922',type:'dashed',width:1,opacity:0.6}},label:{{show:true,formatter:'SL '+sl.sl.toFixed(2),color:'#d29922',fontSize:10}}}});}});

return[{{name:'K线',type:'candlestick',data:ohlcvData,itemStyle:{{color:'#f85149',color0:'#3fb950',borderColor:'#f85149',borderColor0:'#3fb950'}},
markPoint:{{data:fp.concat(em),symbol:'pin',symbolSize:30,label:{{show:true,formatter:function(p){{return p.name}},fontSize:9,color:'#fff'}}}},
markArea:{{silent:false,data:fa,emphasis:{{itemStyle:{{opacity:0.5}}}}}},
markLine:{{silent:false,data:fl.concat(sm),emphasis:{{lineStyle:{{width:2}}}}}}}}];}}

function applyFilters(){{chart.setOption({{series:getSeriesOptions()}});}}
window.applyFilters=applyFilters;

document.getElementById('stockSearch').addEventListener('input',function(){{var q=this.value.trim().toUpperCase();var dd=document.getElementById('searchDropdown');
if(q.length<2){{dd.style.display='none';return;}}
var r=[];for(var i=0;i<allStocks.length;i++){{var s=allStocks[i];var c=s.split('.')[0];if(c===q)r.push(s);}}
if(r.length===0){{for(var i=0;i<allStocks.length;i++){{var s=allStocks[i];if(s.indexOf(q)>=0)r.push(s);}}}}
r=r.slice(0,20);if(r.length===0){{dd.style.display='none';return;}}
dd.innerHTML='';r.forEach(function(s){{var d=document.createElement('div');d.textContent=s;d.addEventListener('click',function(){{goStock(s);}});dd.appendChild(d);}});dd.style.display='block';}});

chart.setOption({{animation:false,backgroundColor:'#0d1117',
tooltip:{{trigger:'axis',axisPointer:{{type:'cross'}},
formatter:function(params){{var p=params[0];if(!p)return'';var d=p.axisValue;var vals=p.data;
if(Array.isArray(p.data)&&p.data.length>=4){{return d+'<br/>O: '+p.data[0].toFixed(2)+'<br/>H: '+p.data[3].toFixed(2)+'<br/>L: '+p.data[2].toFixed(2)+'<br/>C: '+p.data[1].toFixed(2);}}return d;}}}},
dataZoom:[{{type:'inside',start:0,end:100}},{{type:'slider',start:0,end:100,bottom:10,height:25,borderColor:'#30363d',backgroundColor:'#161b22'}}],
grid:{{left:'5%',right:'5%',bottom:'15%',top:'5%'}},
xAxis:{{type:'category',data:dates,axisLine:{{lineStyle:{{color:'#30363d'}}}},axisLabel:{{rotate:45,fontSize:10,interval:30,color:'#8b949e'}},splitLine:{{show:false}}}},
yAxis:{{scale:true,splitLine:{{lineStyle:{{color:'#21262d',type:'dashed'}}}},axisLabel:{{color:'#8b949e',fontSize:11}}}},
series:[{{name:'K线',type:'candlestick',data:ohlcvData,itemStyle:{{color:'#f85149',color0:'#3fb950',borderColor:'#f85149',borderColor0:'#3fb950'}},markPoint:{{data:[],symbol:'pin',symbolSize:30,label:{{show:true}}}},markArea:{{silent:false,data:[]}},markLine:{{silent:false,data:[]}}}}]}});
setTimeout(applyFilters,100);
document.querySelectorAll('.sig-filter').forEach(function(cb){{cb.addEventListener('change',applyFilters);}});
window.addEventListener('resize',function(){{chart.resize();}});
</script></body></html>'''
