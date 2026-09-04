#!/usr/bin/env python3
"""
SMC V2 Interactive WebUI — 13种SMC信号全量K线查看器
=====================================================
功能:
  - 3291只股票下拉选择
  - 日K线 红涨绿跌
  - 全部13种SMC信号在K线上绘制
  - 信号编号 + 代码标记
  - 信号组合入场描述
  - SL/TP线 (基于SMC结构)
  - 信号时序评分显示
  - 筛选/切换开关
  - dataZoom缩放
  - 多周期趋势 (周线)
  - 信号tooltip
  - 股票搜索自动完成
  - 信号组合筛选
  - 60min多时间框架叠加
"""
import json, sys, traceback
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.klines_60min import get_60min_kline

CACHE = Path('/root/.hermes/kline_cache')
CACHE_60M = Path('/root/.hermes/kline_cache_60min')
V28_FULL = '/root/.hermes/smc_opt_v28/v28_full_merged.json'

DATA = json.load(open(V28_FULL))
STOCKS = DATA['stocks']
TRADES = DATA['all_trades']

symbol_offset = 0
SYM_MAP = {}
for s in STOCKS:
    n = s['n_trades']
    SYM_MAP[s['symbol']] = {
        'data': s,
        'trades': TRADES[symbol_offset:symbol_offset+n],
    }
    symbol_offset += n

# ─── Signal color / rendering config ───────────────────────────────
SIG_STYLE = {
    # FVG: semi-transparent rectangles
    'FVG_Bull':   {'fill': 'rgba(156,39,176,0.2)',  'stroke': 'rgba(156,39,176,0.6)',  'label': 'FVG', 'z': 2},
    'FVG_Bear':   {'fill': 'rgba(233,30,99,0.2)',   'stroke': 'rgba(233,30,99,0.6)',   'label': 'FVG', 'z': 2},
    # IFVG: violet semi-transparent
    'IFVG_Bull':  {'fill': 'rgba(138,43,226,0.2)',  'stroke': 'rgba(138,43,226,0.6)',  'label': 'IFVG', 'z': 2},
    'IFVG_Bear':  {'fill': 'rgba(138,43,226,0.2)',  'stroke': 'rgba(138,43,226,0.6)',  'label': 'IFVG', 'z': 2},
    # OB: blue/red semi-transparent
    'OB_Bull':    {'fill': 'rgba(33,150,243,0.15)', 'stroke': 'rgba(33,150,243,0.5)',  'label': 'OB', 'z': 3},
    'OB_Bear':    {'fill': 'rgba(244,67,54,0.15)',  'stroke': 'rgba(244,67,54,0.5)',   'label': 'OB', 'z': 3},
    # BPR: teal semi-transparent
    'BPR_Bull':   {'fill': 'rgba(0,150,136,0.15)',  'stroke': 'rgba(0,150,136,0.5)',   'label': 'BPR', 'z': 3},
    'BPR_Bear':   {'fill': 'rgba(0,150,136,0.15)',  'stroke': 'rgba(0,150,136,0.5)',   'label': 'BPR', 'z': 3},
    # Sweep: dashed horizontal lines
    'SweepDown':  {'stroke': '#FFEB3B', 'type': 'dashed', 'width': 2, 'label': 'Sweep', 'z': 4},
    'SweepUp':    {'stroke': '#FF9800', 'type': 'dashed', 'width': 2, 'label': 'Sweep', 'z': 4},
    # CHOCH: vertical/angled lines
    'CHOCH_Bull': {'stroke': '#00BCD4', 'type': 'solid',  'width': 2, 'label': 'CHOCH', 'z': 5},
    'CHOCH_Bear': {'stroke': '#E91E63', 'type': 'solid',  'width': 2, 'label': 'CHOCH', 'z': 5},
    # MSS: light blue dashed
    'MSS_Bull':   {'stroke': '#4FC3F7', 'type': 'dashed', 'width': 2, 'label': 'MSS', 'z': 5},
    'MSS_Bear':   {'stroke': '#4FC3F7', 'type': 'dashed', 'width': 2, 'label': 'MSS', 'z': 5},
    # OTE: fib zone rectangle
    'OTE_Bull':   {'fill': 'rgba(76,175,80,0.15)',  'stroke': 'rgba(76,175,80,0.5)',   'label': 'OTE', 'z': 1},
    'OTE_Bear':   {'fill': 'rgba(76,175,80,0.15)',  'stroke': 'rgba(76,175,80,0.5)',   'label': 'OTE', 'z': 1},
    # EQL: gray horizontal lines
    'EQL_High':   {'stroke': '#B0BEC5', 'type': 'solid',  'width': 1, 'label': 'EQL', 'z': 3},
    'EQL_Low':    {'stroke': '#B0BEC5', 'type': 'solid',  'width': 1, 'label': 'EQL', 'z': 3},
    # PO3 phases
    'PO3_Acc':    {'fill': 'rgba(33,150,243,0.12)', 'stroke': 'rgba(33,150,243,0.4)',  'label': 'PO3-A', 'z': 3},
    'PO3_Man':    {'fill': 'rgba(244,67,54,0.12)',  'stroke': 'rgba(244,67,54,0.4)',   'label': 'PO3-M', 'z': 3},
    'PO3_DIS':    {'fill': 'rgba(76,175,80,0.12)',  'stroke': 'rgba(76,175,80,0.4)',   'label': 'PO3-D', 'z': 3},
    # LiquidityVoid / RejectionBlock: subtle markers
    'LiquidityVoid': {'stroke': '#9E9E9E', 'type': 'dashed', 'width': 1, 'label': 'LV', 'z': 2},
    'Rejection_Resistance': {'fill': 'rgba(255,152,0,0.12)', 'stroke': 'rgba(255,152,0,0.4)',  'label': 'RB', 'z': 3},
    'Rejection_Support':    {'fill': 'rgba(76,175,80,0.12)', 'stroke': 'rgba(76,175,80,0.4)',   'label': 'RB', 'z': 3},
    'BreakerBlock_Bull':    {'fill': 'rgba(156,39,176,0.12)', 'stroke': 'rgba(156,39,176,0.4)', 'label': 'BRK', 'z': 3},
    'BreakerBlock_Bear':    {'fill': 'rgba(156,39,176,0.12)', 'stroke': 'rgba(156,39,176,0.4)', 'label': 'BRK', 'z': 3},
}

# Map signal type to its base family for filter toggles
SIG_FAMILY = {
    'FVG_Bull': 'fvg', 'FVG_Bear': 'fvg',
    'IFVG_Bull': 'ifvg', 'IFVG_Bear': 'ifvg',
    'OB_Bull': 'ob', 'OB_Bear': 'ob',
    'BPR_Bull': 'bpr', 'BPR_Bear': 'bpr',
    'SweepDown': 'sweep', 'SweepUp': 'sweep',
    'CHOCH_Bull': 'choch', 'CHOCH_Bear': 'choch',
    'MSS_Bull': 'mss', 'MSS_Bear': 'mss',
    'OTE_Bull': 'ote', 'OTE_Bear': 'ote',
    'EQL_High': 'eql', 'EQL_Low': 'eql',
    'PO3_Acc': 'po3', 'PO3_Man': 'po3', 'PO3_DIS': 'po3',
    'LiquidityVoid': 'lv',
    'Rejection_Resistance': 'rb',
    'Rejection_Support': 'rb',
    'BreakerBlock_Bull': 'brk',
    'BreakerBlock_Bear': 'brk',
}


def format_date(d):
    """Format date to YYYY-MM-DD string from various input formats."""
    s = str(d).strip()
    # Already YYYY-MM-DD
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    # YYYYMMDD
    if len(s) == 8 and s.isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    # YYYYMMDDHHMM
    if len(s) >= 12 and s.isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return s


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_daily_300.json"
    fpath = CACHE / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
        bar['_date'] = format_date(bar.get('date', bar.get('t', '')))[:10]
    return data


def load_60min_ohlcv(symbol):
    """Load 60min kline data."""
    fname = f"{symbol.replace('.','_')}_60min_200.json"
    fpath = CACHE_60M / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
        bar['_date'] = format_date(bar.get('date', bar.get('t', '')))[:10]
    return data


def short_sig_label(t):
    """Return short label for a signal type."""
    return SIG_STYLE.get(t, {}).get('label', t[:4])


# ─── Helper: compute SL, TP from signals around entry ──────────────
def compute_sl_tp_from_signals(signals, entry_idx, entry_price, direction):
    """Compute SL/TP based on SMC structure."""
    sl = None
    tp = None
    lookback = 20
    for sig in signals:
        if sig['idx'] >= entry_idx or sig['idx'] < entry_idx - lookback:
            continue
        if direction == 'bull':
            if sig['type'] in ('SweepDown',) and sig.get('lower', 0) > 0:
                sl_candidate = sig.get('lower', sig.get('price', 0))
                if sl is None or sl_candidate < sl:
                    sl = sl_candidate
            if sig['type'] in ('EQL_Low',) and sig.get('lower', 0) > 0:
                sl_candidate = sig.get('lower', sig.get('price', 0))
                if sl is None or sl_candidate < sl:
                    sl = sl_candidate
            if sig['type'] in ('FVG_Bull', 'IFVG_Bull', 'OB_Bull') and sig.get('upper', 0) > entry_price:
                tp_candidate = sig['upper']
                if tp is None or tp_candidate > tp:
                    tp = tp_candidate
        else:
            if sig['type'] in ('SweepUp',) and sig.get('upper', 0) > 0:
                sl_candidate = sig.get('upper', sig.get('price', 0))
                if sl is None or sl_candidate > sl:
                    sl = sl_candidate
            if sig['type'] in ('EQL_High',) and sig.get('upper', 0) > 0:
                sl_candidate = sig.get('upper', sig.get('price', 0))
                if sl is None or sl_candidate > sl:
                    sl = sl_candidate
            if sig['type'] in ('FVG_Bear', 'IFVG_Bear', 'OB_Bear') and sig.get('lower', 0) < entry_price:
                tp_candidate = sig['lower']
                if tp is None or tp_candidate < tp:
                    tp = tp_candidate
    if sl is None:
        sl = entry_price * (0.98 if direction == 'bull' else 1.02)
    if tp is None:
        tp = entry_price * (1.05 if direction == 'bull' else 0.95)
    return sl, tp


def build_html(symbol):
    ohlcv = load_ohlcv(symbol)
    if not ohlcv:
        return '<p>No data for ' + symbol + '</p>'
    info = SYM_MAP.get(symbol)
    trades = info['trades'] if info else []
    stock = info['data'] if info else {}

    # ── Run V11 signal detection ──
    try:
        result = detect_all_signals_v11(ohlcv)
        all_signals = result.get('all', [])
        stats = result.get('stats', {})
    except Exception as e:
        all_signals = []
        stats = {}
        print(f"Signal detection error for {symbol}: {e}")

    dates = [str(b.get('date', b.get('t', ''))) for b in ohlcv]
    dates_short = [str(b.get('_date', format_date(b.get('date', b.get('t', ''))))[:10]) for b in ohlcv]
    ohlcv_data = [[b['o'], b['c'], b['l'], b['h']] for b in ohlcv]

    # ── Number signals sequentially ──
    sig_counter = 0
    numbered_signals = []
    for sig in all_signals:
        sig_counter += 1
        sig['seq'] = sig_counter
        numbered_signals.append(sig)
    n_signals = len(numbered_signals)
    max_idx = len(dates) - 1

    # ── Build signal markAreas (rectangles) and markLines ──
    mark_areas = []
    mark_lines = []
    mark_points = []

    for sig in numbered_signals:
        stype = sig['type']
        style = SIG_STYLE.get(stype, {})
        family = SIG_FAMILY.get(stype, 'other')
        seq = sig['seq']
        label = style.get('label', stype[:4])
        sname = f"{seq}{label}"
        idx = sig['idx']
        if idx < 0 or idx >= len(dates):
            continue

        # Build tooltip text for this signal
        sig_date = dates_short[idx] if idx < len(dates_short) else ''
        sig_upper = sig.get('upper', 0)
        sig_lower = sig.get('lower', 0)
        sig_price = sig.get('price', 0)
        sig_strength = sig.get('strength', 0)
        sig_conf = sig.get('confidence', 0)
        sig_dir = sig.get('direction', 'neutral')
        tooltip_parts = [
            f'Signal #{seq}: {stype}',
            f'Date: {sig_date}',
            f'Direction: {sig_dir}',
            f'Strength: {sig_strength:.1f}',
            f'Confidence: {sig_conf:.2f}',
        ]
        if sig_upper > 0 and sig_lower > 0:
            tooltip_parts.append(f'Range: {sig_lower:.2f} - {sig_upper:.2f}')
        if sig_price > 0:
            tooltip_parts.append(f'Price: {sig_price:.2f}')
        tooltip_text = '<br/>'.join(tooltip_parts)

        # ── Rectangle signals (FVG, IFVG, OB, BPR, OTE, PO3, RB, BRK) ──
        if 'fill' in style:
            upper = sig.get('upper', 0)
            lower = sig.get('lower', 0)
            if upper > 0 and lower > 0 and upper != lower:
                end_x = dates[min(idx+10, max_idx)]
                mark_areas.append({
                    'family': family,
                    'signal': stype,
                    'seq': seq,
                    '_tooltip': tooltip_text,
                    'data': [
                        {
                            'xAxis': dates[idx],
                            'yAxis': lower,
                            'itemStyle': {
                                'color': style['fill'],
                                'borderColor': style['stroke'],
                                'borderWidth': 1 if upper - lower > 0.01 else 0,
                                'opacity': 0.8,
                            },
                        },
                        {'xAxis': end_x, 'yAxis': upper},
                    ]
                })

        # ── All line signals → horizontal dashed segments, ~20 bars rightward ──
        if 'stroke' in style and 'fill' not in style:
            price = sig.get('price', 0)
            if price == 0:
                price = sig.get('upper', 0)
            if price <= 0:
                continue

            end_x = dates[min(idx+20, max_idx)]
            dash_type = style.get('type', 'dashed')
            line_color = style['stroke']
            line_width = style.get('width', 1)
            opacity = 0.6

            mark_lines.append({
                'signal': stype,
                'family': family,
                'seq': seq,
                '_tooltip': tooltip_text,
                '_pair': [
                    {'xAxis': dates[idx], 'yAxis': price},
                    {'xAxis': end_x, 'yAxis': price}
                ],
                'lineStyle': {
                    'color': line_color,
                    'type': dash_type,
                    'width': line_width,
                    'opacity': opacity,
                },
                'label': {
                    'show': True,
                    'formatter': sname,
                    'color': line_color,
                    'fontSize': 9,
                    'position': 'start',
                },
            })

        # ── Mark points for all signals (numbered markers) ──
        price = sig.get('price', sig.get('upper', 0))
        if price > 0:
            sym = 'circle'
            size = 8
            color = style.get('stroke', '#888')
            if stype.startswith('FVG_Bull'): color = '#9C27B0'
            elif stype.startswith('FVG_Bear'): color = '#E91E63'
            elif stype.startswith('OB_Bull'): color = '#2196F3'
            elif stype.startswith('OB_Bear'): color = '#F44336'
            elif stype.startswith('Sweep'): color = '#FFEB3B' if 'Down' in stype else '#FF9800'
            elif stype.startswith('CHOCH_Bull'): color = '#00BCD4'
            elif stype.startswith('CHOCH_Bear'): color = '#E91E63'
            elif stype.startswith('MSS'): color = '#4FC3F7'
            elif stype.startswith('EQL'): color = '#B0BEC5'
            elif stype.startswith('OTE'): color = '#4CAF50'
            elif stype.startswith('Rejection'): color = '#FF9800'
            elif stype.startswith('Breaker'): color = '#9C27B0'
            elif stype.startswith('Liquidity'): color = '#9E9E9E'

            mark_points.append({
                'signal': stype,
                'family': family,
                'seq': seq,
                'name': sname,
                'coord': [dates[idx], price],
                'value': f'{seq}',
                '_tooltip': tooltip_text,
                'symbol': sym,
                'symbolSize': size,
                'itemStyle': {'color': color, 'borderColor': '#fff', 'borderWidth': 1},
                'label': {
                    'show': True,
                    'formatter': f'{seq}',
                    'color': '#fff',
                    'fontSize': 8,
                    'fontWeight': 'bold',
                    'position': 'right',
                },
            })

    # ── Build entry/exit markers from trades ──
    entry_points = []
    exit_points = []
    sl_tp_lines = []
    entry_signal_labels = []

    for i, t in enumerate(trades):
        entry_idx = t['entry_idx']
        entry_price = t['entry_price']
        direction = 'bull'
        nearby_signals = [s for s in numbered_signals
                          if abs(s['idx'] - entry_idx) <= 5 and
                          ((direction == 'bull' and s['direction'] == 'bull') or
                           (direction == 'bear' and s['direction'] == 'bear') or
                           s.get('direction') in ('neutral', None))]
        combo_types = list(dict.fromkeys(s['type'] for s in nearby_signals[:5]))
        combo_short = []
        for ct in combo_types:
            base = short_sig_label(ct)
            combo_short.append(base)
        combo_str = f"E{i+1}: {'→'.join(combo_short)}" if combo_short else f"E{i+1}"

        sl_price = t.get('sl', 0)
        tp_price = t.get('tp', 0)
        if sl_price == 0:
            sl_price, _ = compute_sl_tp_from_signals(numbered_signals, entry_idx, entry_price, direction)

        entry_points.append({
            'idx': t['entry_idx'], 'price': t['entry_price'],
            'won': t['won'], 'rr': t['rr'], 'pnl': t['pnl_pct'],
            'num': i+1, 'combo': combo_str,
        })
        exit_points.append({
            'idx': t['exit_idx'], 'price': t['exit_price'],
            'won': t['won'], 'rr': t['rr'], 'pnl': t['pnl_pct'],
            'num': i+1,
        })
        sl_tp_lines.append({
            'entry_idx': t['entry_idx'],
            'exit_idx': t['exit_idx'],
            'sl': sl_price,
        })

    # ── Weekly trend ──
    weekly = []
    for i in range(0, len(ohlcv), 5):
        chunk = ohlcv[i:i+5]
        if not chunk: continue
        weekly.append({
            'o': chunk[0]['o'], 'h': max(b['h'] for b in chunk),
            'l': min(b['l'] for b in chunk), 'c': chunk[-1]['c'],
            'start_date': str(chunk[0].get('date', chunk[0].get('t', ''))),
        })

    total_pnl = sum(t['pnl_pct'] for t in trades) if trades else 0

    # Build stock list for search autocomplete
    stock_list_json = json.dumps(sorted(SYM_MAP.keys()))

    # ── HTML ──
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{symbol} SMC Signal Viewer V2</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1117; color:#c9d1d9; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
.header {{ background:#161b22; padding:15px 20px; border-bottom:1px solid #30363d; }}
.header h1 {{ font-size:22px; color:#f0f6fc; }}
.header .sub {{ color:#8b949e; font-size:13px; margin-top:4px; }}
.controls {{ background:#161b22; padding:12px 20px; border-bottom:1px solid #30363d; display:flex; align-items:center; gap:15px; flex-wrap:wrap; }}
.controls select {{ padding:8px 12px; background:#0d1117; color:#c9d1d9; border:1px solid #30363d; border-radius:6px; font-size:14px; min-width:200px; }}
.controls select:focus {{ outline:none; border-color:#58a6ff; }}
.controls .btn {{ padding:8px 16px; background:#238636; color:#fff; border:none; border-radius:6px; cursor:pointer; font-size:14px; }}
.controls .btn:hover {{ background:#2ea043; }}
.controls .btn-danger {{ background:#da3633; }}
.controls .btn-danger:hover {{ background:#f85149; }}
.controls .btn-secondary {{ background:#21262d; color:#c9d1d9; }}
.controls .btn-secondary:hover {{ background:#30363d; }}
.controls .stats {{ display:flex; gap:20px; font-size:13px; flex-wrap:wrap; }}
.controls .stat {{ text-align:center; }}
.controls .stat .val {{ font-weight:bold; font-size:16px; }}
.controls .stat .lbl {{ color:#8b949e; font-size:11px; }}
.win {{ color:#3fb950; }} .loss {{ color:#f85149; }}
#chart {{ width:100%; height:600px; }}
.filters {{ background:#161b22; padding:8px 20px; border-bottom:1px solid #30363d; display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:12px; }}
.filters label {{ display:flex; align-items:center; gap:4px; cursor:pointer; padding:3px 8px; border-radius:4px; background:#0d1117; border:1px solid #30363d; }}
.filters label:hover {{ border-color:#58a6ff; }}
.filters input {{ margin:0; }}
.detail {{ padding:20px; max-width:1400px; margin:0 auto; }}
.detail h2 {{ font-size:16px; margin-bottom:10px; color:#f0f6fc; }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th {{ background:#161b22; padding:10px 8px; text-align:left; color:#8b949e; font-weight:600; border-bottom:2px solid #30363d; position:sticky; top:0; }}
td {{ padding:8px; border-bottom:1px solid #21262d; }}
tr:hover {{ background:#161b22; }}
tr.loss td {{ color:inherit; }}
.signals {{ display:inline-block; padding:2px 4px; border-radius:3px; font-size:10px; margin:0 1px; }}
.sig-fvg {{ background:#9C27B044; color:#CE93D8; }}
.sig-ifvg {{ background:#7B1FA244; color:#CE93D8; }}
.sig-ob {{ background:#2196F344; color:#90CAF9; }}
.sig-sweep {{ background:#FF980044; color:#FFCC80; }}
.sig-choch {{ background:#00BCD444; color:#80DEEA; }}
.sig-mss {{ background:#4FC3F744; color:#B3E5FC; }}
.sig-ote {{ background:#4CAF5044; color:#A5D6A7; }}
.sig-eql {{ background:#B0BEC544; color:#CFD8DC; }}
.sig-po3 {{ background:#7C4DFF44; color:#B388FF; }}
.sig-lv {{ background:#9E9E9E44; color:#BDBDBD; }}
.sig-rb {{ background:#FF980044; color:#FFCC80; }}
.sig-brk {{ background:#9C27B044; color:#CE93D8; }}
.tag {{ display:inline-block; padding:2px 6px; border-radius:4px; font-size:11px; }}
.tag-swing {{ background:#1f6feb22; color:#58a6ff; border:1px solid #1f6feb44; }}
.tag-fixed {{ background:#8b949e22; color:#8b949e; border:1px solid #8b949e44; }}
/* Stock search autocomplete */
.search-wrap {{ position:relative; display:inline-block; }}
.search-wrap input {{ padding:8px 12px; background:#0d1117; color:#c9d1d9; border:1px solid #30363d; border-radius:6px; font-size:14px; width:220px; }}
.search-wrap input:focus {{ outline:none; border-color:#58a6ff; }}
.search-wrap .dropdown {{ position:absolute; top:100%; left:0; right:0; background:#161b22; border:1px solid #30363d; border-top:none; border-radius:0 0 6px 6px; max-height:300px; overflow-y:auto; z-index:1000; display:none; }}
.search-wrap .dropdown div {{ padding:6px 12px; cursor:pointer; font-size:13px; color:#c9d1d9; }}
.search-wrap .dropdown div:hover {{ background:#1f6feb33; }}
.search-wrap .dropdown div.selected {{ background:#1f6feb44; }}
/* Toggle switches */
.toggle-wrap {{ display:flex; align-items:center; gap:6px; }}
.toggle-wrap input[type="checkbox"] {{ accent-color:#58a6ff; }}
</style>
<script src="/echarts.min.js"></script>
</head><body>

<div class="header">
  <h1>{symbol} SMC Viewersignal V2</h1>
  <div class="sub">
    {len(trades)} trades | WR={stock.get('win_rate','?')}% |
    RR={stock.get('avg_rr','?'):.1f}x |
    PF={stock.get('profit_factor','?')} |
    Total P&L={total_pnl:+.2f}% |
    Signals: {len(numbered_signals)} total |
    Phase={stock.get('phase','?')}
  </div>
</div>

<div class="controls">
  <form method="get" style="display:flex;align-items:center;gap:10px;">
    <div class="search-wrap">
      <input type="text" id="stockSearch" placeholder="Search stock code/name..." autocomplete="off">
      <div class="dropdown" id="searchDropdown"></div>
    </div>
    <select name="s" id="stockSelect" onchange="this.form.submit()">
"""
    for sym in sorted(SYM_MAP.keys()):
        d = SYM_MAP[sym]['data']
        sel = ' selected' if sym == symbol else ''
        html += f'      <option value="{sym}"{sel}>{sym} ({d["n_trades"]}t WR={d["win_rate"]}%)</option>\n'

    html += """    </select>
    <input type="submit" class="btn" value="View">
  </form>
  <div class="stats">
    <div class="stat"><div class="val win">{wr_label}</div><div class="lbl">Win Rate</div></div>
    <div class="stat"><div class="val">{rr_label}</div><div class="lbl">RR</div></div>
    <div class="stat"><div class="val">{pf_label}</div><div class="lbl">PF</div></div>
  </div>
</div>

<!-- Multi-row filters: combo filter + signal type filters + 60min toggle -->
<div class="filters" style="padding:8px 20px; border-bottom:1px solid #30363d; display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:12px; background:#161b22;">
  <span style="color:#8b949e;font-weight:bold;">Signal Combo:</span>
  <label><input type="radio" name="comboFilter" value="all" checked onchange="applyComboFilter()"> All</label>
  <label><input type="radio" name="comboFilter" value="sweep_fvg" onchange="applyComboFilter()"> Sweep→FVG</label>
  <label><input type="radio" name="comboFilter" value="fvg_only" onchange="applyComboFilter()"> FVG only</label>
  <label><input type="radio" name="comboFilter" value="sweep_only" onchange="applyComboFilter()"> Sweep only</label>
  <label><input type="radio" name="comboFilter" value="choch_mss" onchange="applyComboFilter()"> CHOCH/MSS</label>
  <label><input type="radio" name="comboFilter" value="custom" onchange="applyComboFilter()"> Custom</label>
  <span style="color:#30363d;width:1px;height:20px;border-left:1px solid #30363d;"></span>
  <label class="toggle-wrap"><input type="checkbox" id="show60min" onchange="toggle60min()"> Show 60min</label>
  <label class="toggle-wrap"><input type="checkbox" id="showWeekly" onchange="applyFilters()"> Weekly</label>
</div>

<div class="filters" id="filters">
  <span style="color:#8b949e;font-weight:bold;">Signal Types:</span>
  <label><input type="checkbox" class="sig-filter" data-family="fvg" checked> FVG</label>
  <label><input type="checkbox" class="sig-filter" data-family="ifvg" checked> IFVG</label>
  <label><input type="checkbox" class="sig-filter" data-family="ob" checked> OB</label>
  <label><input type="checkbox" class="sig-filter" data-family="sweep" checked> Sweep</label>
  <label><input type="checkbox" class="sig-filter" data-family="choch" checked> CHOCH</label>
  <label><input type="checkbox" class="sig-filter" data-family="mss" checked> MSS</label>
  <label><input type="checkbox" class="sig-filter" data-family="ote" checked> OTE</label>
  <label><input type="checkbox" class="sig-filter" data-family="eql" checked> EQL</label>
  <label><input type="checkbox" class="sig-filter" data-family="po3" checked> PO3</label>
  <label><input type="checkbox" class="sig-filter" data-family="bpr" checked> BPR</label>
  <label><input type="checkbox" class="sig-filter" data-family="lv" checked> LV</label>
  <label><input type="checkbox" class="sig-filter" data-family="rb" checked> RB</label>
  <label><input type="checkbox" class="sig-filter" data-family="brk" checked> BRK</label>
  <button class="btn btn-secondary" style="padding:3px 10px;font-size:11px;" onclick="document.querySelectorAll('.sig-filter').forEach(c=>c.checked=true);applyFilters();">All</button>
  <button class="btn btn-secondary" style="padding:3px 10px;font-size:11px;" onclick="document.querySelectorAll('.sig-filter').forEach(c=>c.checked=false);applyFilters();">None</button>
  <button class="btn btn-danger" style="padding:3px 10px;font-size:11px;" onclick="chart.dispatchAction({type:'dataZoom',start:0,end:100})" title="Reset Zoom">Reset Zoom</button>
</div>

<div id="chart"></div>

<div class="detail">
<h2>Trade Details</h2>
<div style="overflow-x:auto;">
<table>
<tr>
  <th>#</th><th>Entry</th><th>Exit</th><th>Hold</th>
  <th>Entry Px</th><th>Exit Px</th><th>SL</th><th>Type</th>
  <th>Signals at Entry</th><th>P&L%</th><th>W/L</th><th>RR</th>
</tr>
"""
    # Replace stats placeholders
    wr = stock.get('win_rate', '?')
    rr_val = stock.get('avg_rr', '?')
    pf = stock.get('profit_factor', '?')
    html = html.replace('{wr_label}', f'{wr:.1f}%' if isinstance(wr, (int, float)) else str(wr))
    html = html.replace('{rr_label}', f'{rr_val:.1f}x' if isinstance(rr_val, (int, float)) else str(rr_val))
    html = html.replace('{pf_label}', f'{pf:.0f}' if isinstance(pf, (int, float)) else str(pf))
    for i, t in enumerate(trades):
        cls = 'loss' if not t['won'] else ''
        rr = t.get('rr', 0)
        rr_cls = 'rrbad' if rr < 2.0 else 'rrgood'

        entry_idx = t['entry_idx']
        nearby = [s for s in numbered_signals if abs(s['idx'] - entry_idx) <= 5]
        seen_types = []
        sig_html = ''
        for s in nearby[:6]:
            st = s['type']
            base = st.split('_')[0].lower()
            if base not in seen_types:
                seen_types.append(base)
                sc = short_sig_label(st)
                cls_map = {'fvg':'sig-fvg','ifvg':'sig-ifvg','ob':'sig-ob','sweep':'sig-sweep',
                           'choch':'sig-choch','mss':'sig-mss','ote':'sig-ote','eql':'sig-eql',
                           'po3':'sig-po3','lv':'sig-lv','rb':'sig-rb','brk':'sig-brk','bpr':'sig-ob'}
                sc_cls = cls_map.get(base, 'sig-fvg')
                sig_html += f'<span class="signals {sc_cls}">{s["seq"]}{sc}</span>'

        html += f'<tr class="{cls}">'
        html += f'<td>{i+1}</td>'
        html += f'<td>{dates[t["entry_idx"]]}</td>'
        html += f'<td>{dates[t["exit_idx"]]}</td>'
        html += f'<td>{t.get("hold_bars", 0)}d</td>'
        html += f'<td>{t["entry_price"]:.2f}</td>'
        html += f'<td>{t["exit_price"]:.2f}</td>'
        html += f'<td>{t["sl"]:.2f}</td>'
        sl_type = t.get('sl_type', '?')
        html += f'<td><span class="tag tag-{sl_type}">{sl_type}</span></td>'
        html += f'<td>{sig_html}</td>'
        pnl = t['pnl_pct']
        html += f'<td class="{"win" if pnl>0 else "loss"}">{pnl:+.2f}%</td>'
        html += f'<td class="{"win" if t["won"] else "loss"}">{"W" if t["won"] else "L"}</td>'
        html += f'<td class="{rr_cls}">{rr:.1f}x</td>'
        html += '</tr>\n'

    html += """</table>
</div>
</div>

<script>
var dom = document.getElementById('chart');
var chart = echarts.init(dom, 'dark');

var dates = """ + json.dumps(dates) + """;
var datesShort = """ + json.dumps(dates_short) + """;
var ohlcvData = """ + json.dumps(ohlcv_data) + """;
var entryPts = """ + json.dumps(entry_points) + """;
var exitPts = """ + json.dumps(exit_points) + """;
var slLines = """ + json.dumps(sl_tp_lines) + """;
var markAreas = """ + json.dumps(mark_areas) + """;
var markLines = """ + json.dumps(mark_lines) + """;
var markPoints = """ + json.dumps(mark_points) + """;
var currentSymbol = """ + json.dumps(symbol) + """;

// Build K-line series
var entryMarkPoints = [];
entryPts.forEach(function(e) {
    entryMarkPoints.push({
        name: 'E' + e.num,
        coord: [dates[e.idx], e.price],
        value: e.combo || 'E' + e.num,
        itemStyle: { color: e.won ? '#3fb950' : '#f85149' },
        symbol: 'pin', symbolSize: 32,
        label: {
            show: true,
            formatter: e.combo ? '{b}' : 'E' + e.num,
            fontSize: 9, color: '#fff',
            position: 'top',
        },
    });
});

var exitMarkPoints = [];
exitPts.forEach(function(e) {
    exitMarkPoints.push({
        name: 'X' + e.num,
        coord: [dates[e.idx], e.price],
        value: e.pnl.toFixed(1) + '%',
        itemStyle: { color: e.pnl > 0 ? '#79c0ff' : '#d29922' },
        symbol: 'diamond', symbolSize: 16,
    });
});

var slMarkLines = [];
slLines.forEach(function(sl) {
    slMarkLines.push({
        yAxis: sl.sl,
        lineStyle: { color: '#d29922', type: 'dashed', width: 1, opacity: 0.6 },
        label: { show: true, formatter: 'SL ' + sl.sl.toFixed(2), color: '#d29922', fontSize: 10 },
    });
});

// 60min signal data (lazy loaded)
var sixtyMinAreas = [];
var sixtyMinLines = [];
var sixtyMinPoints = [];
var sixtyMinLoaded = false;

// Tooltip formatter for signal markArea/markLine
function signalTooltipFormatter(params) {
    if (!params || params.length === 0) return '';
    // Check if this is a mark component
    var p = params[0];
    if (p.componentType === 'markArea' || p.componentType === 'markLine' || p.componentType === 'markPoint') {
        if (p.data && p.data._tooltip) return p.data._tooltip;
        if (p.data && p.data.name) return p.data.name;
        return '';
    }
    // Regular candlestick tooltip
    if (Array.isArray(p.data) && p.data.length >= 4) {
        return (p.axisValue || p.name || '') +
               '<br/>O: ' + p.data[0].toFixed(2) +
               '<br/>H: ' + p.data[3].toFixed(2) +
               '<br/>L: ' + p.data[2].toFixed(2) +
               '<br/>C: ' + p.data[1].toFixed(2);
    }
    return p.axisValue || p.name || '';
}

// Filtered markAreas, markLines, markPoints
function getActiveFamilies() {
    var active = {};
    document.querySelectorAll('.sig-filter').forEach(function(cb) {
        active[cb.dataset.family] = cb.checked;
    });
    return active;
}

function getComboFilter() {
    var radios = document.getElementsByName('comboFilter');
    for (var i = 0; i < radios.length; i++) {
        if (radios[i].checked) return radios[i].value;
    }
    return 'all';
}

function applyComboFilter() {
    var combo = getComboFilter();
    var allCbs = document.querySelectorAll('.sig-filter');
    if (combo === 'all') {
        allCbs.forEach(function(cb) { cb.checked = true; });
    } else if (combo === 'sweep_fvg') {
        allCbs.forEach(function(cb) { cb.checked = ['sweep','fvg'].includes(cb.dataset.family); });
    } else if (combo === 'fvg_only') {
        allCbs.forEach(function(cb) { cb.checked = ['fvg','ifvg'].includes(cb.dataset.family); });
    } else if (combo === 'sweep_only') {
        allCbs.forEach(function(cb) { cb.checked = cb.dataset.family === 'sweep'; });
    } else if (combo === 'choch_mss') {
        allCbs.forEach(function(cb) { cb.checked = ['choch','mss'].includes(cb.dataset.family); });
    }
    // 'custom' leaves checkboxes as-is
    applyFilters();
}

function getSeriesOptions() {
    var active = getActiveFamilies();
    var showWeekly = document.getElementById('showWeekly') && document.getElementById('showWeekly').checked;

    var filteredAreas = markAreas.filter(function(m) { return active[m.family]; }).map(function(m) { return m.data; });
    var filteredLines = markLines.filter(function(m) { return active[m.family]; }).map(function(m) { return m._pair || m; });
    var filteredPoints = markPoints.filter(function(m) { return active[m.family]; });

    // Add 60min signals if visible
    if (document.getElementById('show60min') && document.getElementById('show60min').checked && sixtyMinLoaded) {
        var sixtyAreas = sixtyMinAreas.filter(function(m) { return active[m.family]; }).map(function(m) { return m.data; });
        var sixtyLines = sixtyMinLines.filter(function(m) { return active[m.family]; }).map(function(m) { return m._pair || m; });
        var sixtyPoints = sixtyMinPoints.filter(function(m) { return active[m.family]; });
        filteredAreas = filteredAreas.concat(sixtyAreas);
        filteredLines = filteredLines.concat(sixtyLines);
        filteredPoints = filteredPoints.concat(sixtyPoints);
    }

    var series = [{
        name: 'K线', type: 'candlestick',
        data: ohlcvData,
        itemStyle: {
            color: '#f85149', color0: '#3fb950',
            borderColor: '#f85149', borderColor0: '#3fb950',
        },
        markPoint: {
            data: filteredPoints.concat(entryMarkPoints),
            symbol: 'pin', symbolSize: 30,
            label: { show: true, formatter: function(p) { return p.name; }, fontSize: 9, color: '#fff' },
        },
        markArea: {
            silent: false,
            data: filteredAreas,
            emphasis: { itemStyle: { opacity: 0.5 } },
        },
        markLine: {
            silent: false,
            data: filteredLines.concat(slMarkLines),
            emphasis: { lineStyle: { width: 2 } },
        },
    }];

    // Weekly candlestick overlay
    if (showWeekly && weeklyBars && weeklyBars.length > 0) {
        // Map weekly to daily xAxis using start_date
        var weeklyData = [];
        var weeklyDates = weeklyBars.map(function(w) { return w.start_date; });
        // For each daily date, find the corresponding weekly bar
        dates.forEach(function(d, i) {
            var wIdx = -1;
            for (var j = weeklyBars.length - 1; j >= 0; j--) {
                if (d >= weeklyBars[j].start_date && (j === weeklyBars.length - 1 || d < weeklyBars[j+1].start_date)) {
                    wIdx = j;
                    break;
                }
            }
            if (wIdx >= 0) {
                weeklyData.push([weeklyBars[wIdx].o, weeklyBars[wIdx].c, weeklyBars[wIdx].l, weeklyBars[wIdx].h]);
            } else {
                weeklyData.push(ohlcvData[i]);
            }
        });

        series.push({
            name: 'Weekly MA',
            type: 'candlestick',
            data: weeklyData,
            itemStyle: {
                color: 'rgba(88,166,255,0.3)', color0: 'rgba(88,166,255,0.3)',
                borderColor: '#58a6ff', borderColor0: '#58a6ff',
                borderWidth: 1,
            },
            z: 0,
        });
    }

    return series;
}

function applyFilters() {
    var series = getSeriesOptions();
    chart.setOption({
        series: series,
    });
}

window.applyFilters = applyFilters;
window.applyComboFilter = applyComboFilter;

// Load 60min signals
function toggle60min() {
    var cb = document.getElementById('show60min');
    if (!cb.checked) {
        applyFilters();
        return;
    }
    if (!sixtyMinLoaded) {
        fetch('/api/signals_60min?code=' + encodeURIComponent(currentSymbol))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                sixtyMinAreas = data.areas || [];
                sixtyMinLines = data.lines || [];
                sixtyMinPoints = data.points || [];
                sixtyMinLoaded = true;
                applyFilters();
            })
            .catch(function(err) {
                console.error('60min load error:', err);
                sixtyMinLoaded = true; // prevent retry
                applyFilters();
            });
    } else {
        applyFilters();
    }
}

// ── Stock search autocomplete ──
var allStocks = """ + stock_list_json + """;

document.addEventListener('DOMContentLoaded', function() {
    var input = document.getElementById('stockSearch');
    var dropdown = document.getElementById('searchDropdown');

    input.addEventListener('input', function() {
        var q = input.value.trim().toUpperCase();
        if (q.length < 2) {
            dropdown.style.display = 'none';
            return;
        }
        var results = [];
        // First pass: exact code matches
        for (var i = 0; i < allStocks.length; i++) {
            var sym = allStocks[i];
            var code = sym.split('.')[0];
            if (code === q) {
                results.push(sym);
            }
        }
        // Second pass: code prefix matches
        if (results.length === 0) {
            for (var i = 0; i < allStocks.length; i++) {
                var sym = allStocks[i];
                var code = sym.split('.')[0];
                if (code.startsWith(q)) {
                    results.push(sym);
                }
            }
        }
        // Third pass: partial match
        if (results.length === 0) {
            for (var i = 0; i < allStocks.length; i++) {
                var sym = allStocks[i];
                if (sym.indexOf(q) >= 0) {
                    results.push(sym);
                }
            }
        }
        // Limit
        results = results.slice(0, 20);

        if (results.length === 0) {
            dropdown.style.display = 'none';
            return;
        }

        dropdown.innerHTML = '';
        results.forEach(function(sym) {
            var div = document.createElement('div');
            div.textContent = sym;
            div.addEventListener('click', function() {
                window.location.href = '/?s=' + encodeURIComponent(sym);
            });
            dropdown.appendChild(div);
        });
        dropdown.style.display = 'block';
    });

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            var visible = dropdown.style.display === 'block';
            if (visible && dropdown.firstChild) {
                dropdown.firstChild.click();
            } else {
                // Try to submit with typed value as symbol
                var q = input.value.trim();
                if (q) {
                    window.location.href = '/?s=' + encodeURIComponent(q);
                }
            }
        }
        if (e.key === 'Escape') {
            dropdown.style.display = 'none';
        }
    });

    document.addEventListener('click', function(e) {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
});

// Initial render
chart.setOption({
    animation: false,
    backgroundColor: '#0d1117',
    tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: signalTooltipFormatter,
    },
    dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { type: 'slider', start: 0, end: 100, bottom: 10, height: 25,
          borderColor: '#30363d', backgroundColor: '#161b22',
          dataBackground: { lineStyle: { color: '#58a6ff88' }, areaStyle: { color: '#58a6ff22' } },
          selectedDataBackground: { lineStyle: { color: '#58a6ff' }, areaStyle: { color: '#58a6ff44' } },
        }
    ],
    grid: { left: '5%', right: '5%', bottom: '15%', top: '5%' },
    xAxis: {
        type: 'category', data: dates,
        axisLine: { lineStyle: { color: '#30363d' } },
        axisLabel: { rotate: 45, fontSize: 10, interval: 30, color: '#8b949e' },
        splitLine: { show: false },
    },
    yAxis: {
        scale: true,
        splitLine: { lineStyle: { color: '#21262d', type: 'dashed' } },
        axisLabel: { color: '#8b949e', fontSize: 11 },
    },
    series: [
        {
            name: 'K线', type: 'candlestick',
            data: ohlcvData,
            itemStyle: {
                color: '#f85149', color0: '#3fb950',
                borderColor: '#f85149', borderColor0: '#3fb950',
            },
            markPoint: {
                data: [],
                symbol: 'pin', symbolSize: 30,
                label: { show: true, formatter: function(p) { return p.name; }, fontSize: 9, color: '#fff' },
            },
            markArea: {
                silent: false,
                data: [],
            },
            markLine: {
                silent: false,
                data: [],
            },
        },
    ],
});

// Apply filters after initial render
setTimeout(applyFilters, 100);

// Filter change handlers
document.querySelectorAll('.sig-filter').forEach(function(cb) {
    cb.addEventListener('change', applyFilters);
});

window.addEventListener('resize', function() { chart.resize(); });
</script>
</body></html>"""
    return html


# ─── 60min signal detection ───────────────────────────────────────
def build_60min_signals(symbol):
    """Detect signals on 60min data and map to daily xAxis dates."""
    ohlcv_60m = load_60min_ohlcv(symbol)
    if not ohlcv_60m:
        return {'areas': [], 'lines': [], 'points': []}

    # Run signal detection on 60min data
    try:
        result = detect_all_signals_v11(ohlcv_60m, tf='60min')
        all_signals = result.get('all', [])
    except Exception as e:
        print(f"60min signal detection error for {symbol}: {e}")
        return {'areas': [], 'lines': [], 'points': []}

    if not all_signals:
        return {'areas': [], 'lines': [], 'points': []}

    # Load daily data to get matching dates
    daily = load_ohlcv(symbol)
    if not daily:
        return {'areas': [], 'lines': [], 'points': []}

    # Build date-to-daily-index mapping using _date (YYYY-MM-DD)
    daily_date_map = {}
    for i, b in enumerate(daily):
        d = b.get('_date', format_date(b.get('date', b.get('t', ''))))[:10]
        daily_date_map[d] = i

    daily_dates = [str(b.get('date', b.get('t', ''))) for b in daily]
    max_idx = len(daily_dates) - 1

    areas = []
    lines = []
    points = []
    sig_counter = 0

    for sig in all_signals:
        # Get the date from 60min bar
        sig_date_60m = format_date(sig.get('date', ''))[:10]
        if not sig_date_60m or sig_date_60m not in daily_date_map:
            # Try using the bar index from ohlcv_60m
            bar_idx = sig.get('idx', 0)
            if bar_idx < len(ohlcv_60m):
                sig_date_60m = ohlcv_60m[bar_idx].get('_date', '')
                sig_date_60m = sig_date_60m[:10]
            if not sig_date_60m or sig_date_60m not in daily_date_map:
                continue

        daily_idx = daily_date_map[sig_date_60m]
        sig_counter += 1

        stype = sig['type']
        style = SIG_STYLE.get(stype, {})
        family = SIG_FAMILY.get(stype, 'other')
        label = style.get('label', stype[:4])
        sname = f"60m-{sig_counter}{label}"

        # Use lighter/more transparent styles for 60min
        fill_color = 'rgba(255,255,255,0.08)'
        stroke_color = 'rgba(255,255,255,0.3)'
        if 'fill' in style:
            fill_color = style['fill'].replace('0.2', '0.08').replace('0.15', '0.06').replace('0.12', '0.05')
            stroke_color = style['stroke']

        # ── Rectangle signals ──
        if 'fill' in style:
            upper = sig.get('upper', 0)
            lower = sig.get('lower', 0)
            if upper > 0 and lower > 0 and upper != lower:
                end_x = daily_dates[min(daily_idx+5, max_idx)]
                areas.append({
                    'family': family,
                    'signal': stype,
                    'seq': sig_counter,
                    'data': [
                        {
                            'xAxis': daily_dates[daily_idx],
                            'yAxis': lower,
                            'itemStyle': {
                                'color': fill_color,
                                'borderColor': stroke_color,
                                'borderWidth': 1 if upper - lower > 0.01 else 0,
                                'borderType': 'dashed',
                                'opacity': 0.5,
                            },
                        },
                        {'xAxis': end_x, 'yAxis': upper},
                    ]
                })

        # ── Line signals ──
        if 'stroke' in style and 'fill' not in style:
            price = sig.get('price', 0)
            if price == 0:
                price = sig.get('upper', 0)
            if price <= 0:
                continue

            end_x = daily_dates[min(daily_idx+10, max_idx)]
            dash_type = style.get('type', 'dashed')
            line_color = style.get('stroke', '#888')
            opacity = 0.3

            lines.append({
                'signal': stype,
                'family': family,
                'seq': sig_counter,
                '_pair': [
                    {'xAxis': daily_dates[daily_idx], 'yAxis': price},
                    {'xAxis': end_x, 'yAxis': price}
                ],
                'lineStyle': {
                    'color': line_color,
                    'type': dash_type,
                    'width': 1,
                    'opacity': opacity,
                },
                'label': {
                    'show': True,
                    'formatter': sname,
                    'color': line_color,
                    'fontSize': 8,
                    'position': 'start',
                },
            })

        # ── Points ──
        price = sig.get('price', sig.get('upper', 0))
        if price > 0:
            points.append({
                'signal': stype,
                'family': family,
                'seq': sig_counter,
                'name': sname,
                'coord': [daily_dates[daily_idx], price],
                'value': f'60m-{sig_counter}',
                'symbol': 'circle',
                'symbolSize': 5,
                'itemStyle': {'color': 'rgba(255,255,255,0.4)', 'borderColor': 'rgba(255,255,255,0.2)', 'borderWidth': 1},
                'label': {
                    'show': False,
                },
            })

    return {'areas': areas, 'lines': lines, 'points': points}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/echarts.min.js':
            self.send_response(200)
            self.send_header('Content-type', 'application/javascript')
            self.end_headers()
            self.wfile.write(open('/tmp/echarts.min.js', 'rb').read())
            return

        if parsed.path == '/api/signals_60min':
            params = parse_qs(parsed.query)
            code = params.get('code', ['000001.SZ'])[0]
            try:
                result = build_60min_signals(code)
                body = json.dumps(result).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        params = parse_qs(parsed.query)
        symbol = params.get('s', ['000001.SZ'])[0]

        try:
            html = build_html(symbol)
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            tb = traceback.format_exc()
            self.wfile.write(f'<pre>{tb}</pre>'.encode('utf-8'))


if __name__ == '__main__':
    port = 8896
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'SMC Viewer V2: http://localhost:{port}')
    print(f'Updated: dataZoom + signal tooltips + stock search + combo filter + 60min overlay')
    server.serve_forever()
