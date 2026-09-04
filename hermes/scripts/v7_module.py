#!/usr/bin/env python3
"""V7 Module — Unified K-Line + All SMC Signals + V467 Trades + TP/SL Viewer"""
import json
from pathlib import Path
from collections import defaultdict

DIRS = {
    'V465': '/root/.hermes/smc_opt_v465',
    'V466': '/root/.hermes/smc_opt_v466',
    'V467': '/root/.hermes/smc_opt_v467',
    'V469': '/root/.hermes/smc_opt_v469',
    'V470': '/root/.hermes/smc_opt_v470',
    'V473': '/root/.hermes/smc_opt_v473',
}
CACHE = Path('/root/.hermes/kline_cache')
CACHE_60M = Path('/root/.hermes/kline_cache_60min')

# ── Trade maps: build at import time ──
TRADE_MAPS = {}
for ver in ['V465', 'V466', 'V467', 'V469', 'V470', 'V473']:
    vdir = DIRS[ver]
    sf = Path(f'{vdir}/{ver.lower()}_full_stocks.json')
    m = {}
    if sf.exists():
        stocks = json.loads(sf.read_bytes())
        if ver == 'V466':
            tf = Path(f'{vdir}/{ver.lower()}_full.json')
            trades = json.loads(tf.read_bytes()) if tf.exists() else []
        elif ver == 'V469':
            # V469 uses trade_map (symbol -> list of trades)
            tf = Path(f'{vdir}/{ver.lower()}_trade_map.json')
            if tf.exists():
                m = json.loads(tf.read_bytes())
            TRADE_MAPS[ver] = m
            continue
        else:
            tf = Path(f'{vdir}/{ver.lower()}_full_trades.json')
            trades = json.loads(tf.read_bytes()) if tf.exists() else []
        offset = 0
        for sr in stocks:
            n = sr['n_trades']
            m[sr['symbol']] = trades[offset:offset+n]
            offset += n
    TRADE_MAPS[ver] = m

# ── Signal styles (same as V2) ──
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
    'MSS_Bull':'mss','MSS_Bear':'mss','OTE_Bull':'ote','OTE_Bear':'ote',
    'EQL_High':'eql','EQL_Low':'eql','PO3_Acc':'po3','PO3_Man':'po3','PO3_DIS':'po3',
    'LiquidityVoid':'lv','Rejection_Resistance':'rb','Rejection_Support':'rb',
    'BreakerBlock_Bull':'brk','BreakerBlock_Bear':'brk',
}
FAMILY_COLORS = {
    'fvg':'#9C27B0','ifvg':'#7B1FA2','ob':'#2196F3','sweep':'#FF9800',
    'choch':'#00BCD4','mss':'#4FC3F7','ote':'#4CAF50','eql':'#B0BEC5',
    'po3':'#7C4DFF','bpr':'#009688','lv':'#9E9E9E','rb':'#FF9800','brk':'#9C27B0',
}
SHORT_LABEL = {k: v['label'] for k, v in SIG_STYLE.items()}

def fmt_date(d):
    s = str(d).strip()
    if len(s) >= 10 and s[4]=='-' and s[7]=='-': return s[:10]
    if len(s)==8 and s.isdigit(): return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    if len(s)>=12 and s.isdigit(): return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return s

def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_daily_300.json"
    fp = CACHE / fname
    if not fp.exists(): return None
    data = json.loads(fp.read_text())
    for b in data:
        if 'date' not in b and 't' in b: b['date'] = str(b['t'])
        b['_date'] = fmt_date(b.get('date',b.get('t','')))[:10]
    return data

def load_60m(symbol):
    fname = f"{symbol.replace('.','_')}_60min_200.json"
    fp = CACHE_60M / fname
    if not fp.exists(): return None
    data = json.loads(fp.read_text())
    for b in data:
        if 'date' not in b and 't' in b: b['date'] = str(b['t'])
        b['_date'] = fmt_date(b.get('date',b.get('t','')))[:10]
    return data

def build_v7(symbol, nav='', version='V467'):
    """Unified K-Line + All Signals + V467/V468 Trades + TP/SL"""
    ohlcv = load_ohlcv(symbol)
    if not ohlcv:
        return f'{nav}<div style="padding:20px;color:#8b949e;">No daily data for {symbol}</div>'

    # Load 60min data for trade mapping
    ohlcv_60m = load_60m(symbol)

    # Detect signals on daily
    from v11.signals_v11 import detect_all_signals_v11
    try:
        result = detect_all_signals_v11(ohlcv)
        all_sigs = result.get('all', [])
    except:
        all_sigs = []

    # Look up trades
    v467_trades = []
    v467_stock_info = None
    if version == 'V468':
        try:
            from v11.v468_engine import backtest_stock_v45, load_ohlcv as _60load
            ohlcv_data = _60load(symbol)
            if ohlcv_data:
                bt_result = backtest_stock_v45(ohlcv_data, symbol)
                if bt_result:
                    v467_trades = bt_result['trades']
                    p = bt_result['perf']
                    v467_stock_info = p
        except:
            import traceback; traceback.print_exc()
    if version == 'V469':
        try:
            from v11.v469_final import backtest_stock_v45, load_ohlcv as _60load
            ohlcv_data = _60load(symbol)
            if ohlcv_data:
                bt_result = backtest_stock_v45(ohlcv_data, symbol)
                if bt_result:
                    v467_trades = bt_result['trades']
                    p = bt_result['perf']
                    v467_stock_info = p
        except:
            import traceback; traceback.print_exc()
    if version == 'V470':
        try:
            from v11.v470_engine import backtest_stock_v45, load_ohlcv as _60load
            ohlcv_data = _60load(symbol)
            if ohlcv_data:
                bt_result = backtest_stock_v45(ohlcv_data, symbol)
                if bt_result:
                    v467_trades = bt_result['trades']
                    p = bt_result['perf']
                    v467_stock_info = p
        except:
            import traceback; traceback.print_exc()
    for ver in ['V470', 'V469', 'V467', 'V466', 'V465']:
        m = TRADE_MAPS.get(ver, {})
        if symbol in m:
            v467_trades = m[symbol]
            break

    # Build date indices
    dates = [str(b.get('date', b.get('t', ''))) for b in ohlcv]
    dates_short = [b['_date'] for b in ohlcv]
    ohlcv_data = [[b['o'], b['c'], b['l'], b['h']] for b in ohlcv]
    max_idx = len(dates) - 1

    # Build date->index map for trade mapping
    date_to_idx = {dates_short[i]: i for i in range(len(dates_short))}

    # Build date->daily_idx map from 60min data
    trade_date_map = {}
    if ohlcv_60m:
        for ti, tb in enumerate(ohlcv_60m):
            d = tb['_date']
            if d in date_to_idx and d not in trade_date_map:
                trade_date_map[d] = date_to_idx[d]

    # ── Build signal markers ──
    sig_counter = 0
    numbered_sigs = []
    sig_areas, sig_lines, sig_points = [], [], []

    for sig in all_sigs:
        sig_counter += 1
        sig['seq'] = sig_counter
        numbered_sigs.append(sig)

        stype = sig['type']
        style = SIG_STYLE.get(stype, {})
        family = SIG_FAMILY.get(stype, 'other')
        seq = sig['seq']
        label = style.get('label', stype[:4])
        sname = f"{seq}{label}"
        idx = sig['idx']
        if idx < 0 or idx >= len(dates): continue

        sig_date = dates_short[idx] if idx < len(dates_short) else ''
        sig_upper = sig.get('upper', 0)
        sig_lower = sig.get('lower', 0)
        sig_price = sig.get('price', 0)
        sig_strength = sig.get('strength', 0)
        sig_conf = sig.get('confidence', 0)
        sig_dir = sig.get('direction', 'neutral')
        tt = f'Signal #{seq}: {stype}<br/>Date: {sig_date}<br/>Dir: {sig_dir}<br/>Str: {sig_strength:.1f}<br/>Conf: {sig_conf:.2f}'
        if sig_upper > 0 and sig_lower > 0:
            tt += f'<br/>Range: {sig_lower:.2f} - {sig_upper:.2f}'
        if sig_price > 0:
            tt += f'<br/>Price: {sig_price:.2f}'

        # Area signals (FVG/IFVG/OB/BPR/OTE/PO3/Rejection/BreakerBlock)
        if 'fill' in style and sig_upper > 0 and sig_lower > 0 and sig_upper != sig_lower:
            end_x = dates[min(idx + 10, max_idx)]
            sig_areas.append({
                'family': family, 'signal': stype, 'seq': seq,
                'data': [
                    {'xAxis': dates[idx], 'yAxis': sig_lower,
                     'itemStyle': {'color': style['fill'], 'borderColor': style['stroke'],
                                   'borderWidth': 1, 'opacity': 0.7}},
                    {'xAxis': end_x, 'yAxis': sig_upper}
                ]
            })

        # Line signals (Sweep/CHOCH/MSS/EQL/LiquidityVoid)
        if 'stroke' in style and 'fill' not in style:
            price = sig_price or sig_upper or 0
            if price <= 0: continue
            end_x = dates[min(idx + 20, max_idx)]
            sig_lines.append({
                'signal': stype, 'family': family, 'seq': seq,
                '_pair': [
                    {'xAxis': dates[idx], 'yAxis': price},
                    {'xAxis': end_x, 'yAxis': price}
                ],
                'lineStyle': {'color': style['stroke'], 'type': style.get('type', 'dashed'),
                              'width': style.get('width', 1), 'opacity': 0.6},
                'label': {'show': True, 'formatter': sname,
                          'color': style['stroke'], 'fontSize': 9, 'position': 'start'}
            })

        # Point markers (all signals)
        price = sig_price or sig_upper or 0
        if price > 0:
            c_map = {
                'FVG_Bull':'#9C27B0','FVG_Bear':'#E91E63','OB_Bull':'#2196F3','OB_Bear':'#F44336',
                'SweepDown':'#FFEB3B','SweepUp':'#FF9800','CHOCH_Bull':'#00BCD4','CHOCH_Bear':'#E91E63',
                'MSS_Bull':'#4FC3F7','MSS_Bear':'#4FC3F7','EQL_High':'#B0BEC5','EQL_Low':'#B0BEC5',
                'OTE_Bull':'#4CAF50','OTE_Bear':'#4CAF50','PO3_Acc':'#2196F3','PO3_Man':'#F44336',
                'PO3_DIS':'#4CAF50','LiquidityVoid':'#9E9E9E','Rejection_Resistance':'#FF9800',
                'Rejection_Support':'#FF9800','BreakerBlock_Bull':'#9C27B0','BreakerBlock_Bear':'#9C27B0',
                'IFVG_Bull':'#7B1FA2','IFVG_Bear':'#7B1FA2','BPR_Bull':'#009688','BPR_Bear':'#009688',
            }
            color = c_map.get(stype, '#888')
            sig_points.append({
                'signal': stype, 'family': family, 'seq': seq, 'name': sname,
                'coord': [dates[idx], price], 'value': f'{seq}',
                'symbol': 'circle', 'symbolSize': 8,
                'itemStyle': {'color': color, 'borderColor': '#fff', 'borderWidth': 1},
                'label': {'show': True, 'formatter': f'{seq}', 'color': '#fff',
                          'fontSize': 8, 'fontWeight': 'bold', 'position': 'right'}
            })

    # ── Build trade markers (V467) ──
    entry_markers, exit_markers, sl_markers, tp_markers = [], [], [], []

    for ti, t in enumerate(v467_trades):
        # Map 60min trade entry/exit to daily chart by date
        entry_daily_idx = None
        exit_daily_idx = None
        
        if ohlcv_60m:
            entry_60m_idx = t['entry_idx']
            if entry_60m_idx < len(ohlcv_60m):
                entry_date = ohlcv_60m[entry_60m_idx]['_date']
                entry_daily_idx = date_to_idx.get(entry_date)
            
            exit_60m_idx = t['exit_idx']
            if exit_60m_idx < len(ohlcv_60m):
                exit_date = ohlcv_60m[exit_60m_idx]['_date']
                exit_daily_idx = date_to_idx.get(exit_date)

        # Fallback: use entry_idx/exit_idx directly (for V466 daily trades)
        if entry_daily_idx is None:
            entry_daily_idx = t['entry_idx'] if t['entry_idx'] < len(dates) else None
        if exit_daily_idx is None:
            exit_daily_idx = t['exit_idx'] if t['exit_idx'] < len(dates) else None

        if entry_daily_idx is None:
            continue

        entry_price = t['entry_price']
        exit_price = t['exit_price']
        sl_price = t.get('sl', 0)
        rr = t.get('rr', 0)
        pnl = t.get('pnl_pct', 0)
        won = t.get('won', False)
        entry_type = t.get('entry_type', '')
        hold_bars = t.get('hold_bars', 0)
        tp_pct = t.get('tp_pct', 0)
        sl_pct = t.get('sl_pct', 0)
        signal_type = t.get('signal_type', '')
        exit_method = t.get('exit_method', '')
        signal_grade = t.get('signal_grade', '')  # V469
        grade_color = {'A': '#FFD700', 'B': '#C0C0C0', 'C': '#CD7F32'}.get(signal_grade, '#888')

        # Signal combo: find nearby signals
        nearby = [s for s in numbered_sigs if abs(s['idx'] - entry_daily_idx) <= 5][:5]
        combo_parts = []
        for ns in nearby:
            base = SHORT_LABEL.get(ns['type'], ns['type'][:4])
            combo_parts.append(base)
        unique_combo = []
        seen = set()
        for c in combo_parts:
            if c not in seen:
                seen.add(c)
                unique_combo.append(c)
        combo = '→'.join(unique_combo) if unique_combo else entry_type or f'T{ti+1}'
        trade_label = combo

        # Tooltip
        tt_parts = [
            f'Trade #{ti+1}',
            f'Entry: {dates_short[entry_daily_idx] if entry_daily_idx < len(dates_short) else "?"}',
            f'Price: {entry_price:.2f} → {exit_price:.2f}',
            f'P&L: {pnl:+.2f}% | RR: {rr:.1f}x',
            f'Hold: {hold_bars} bars | {("WON" if won else "LOST")}',
            f'Type: {entry_type} | Signal: {signal_type}',
            f'Exit: {exit_method}',
            f'SL: {sl_price:.2f} ({sl_pct:.2f}%) | TP: {tp_pct:.1f}%',
        ]
        if signal_grade:
            tt_parts.append(f'Grade: {signal_grade}')
        trade_tt = '<br/>'.join(tt_parts)

        # Entry pin (color by grade for V469)
        entry_color = grade_color if signal_grade else ('#3fb950' if won else '#f85149')
        entry_markers.append({
            'name': trade_label,
            'coord': [dates[entry_daily_idx], entry_price],
            'value': trade_label,
            '_tt': trade_tt,
            'itemStyle': {'color': entry_color},
            'symbol': 'pin',
            'symbolSize': 34,
            'label': {
                'show': True, 'formatter': trade_label,
                'fontSize': 9, 'color': '#fff', 'position': 'top',
                'fontWeight': 'bold'
            }
        })

        # Exit diamond (only if exit_daily_idx available)
        if exit_daily_idx is not None and exit_daily_idx < len(dates):
            exit_markers.append({
                'coord': [dates[exit_daily_idx], exit_price],
                'value': f'{pnl:+.1f}%\n{rr:.1f}x',
                '_tt': trade_tt,
                'itemStyle': {'color': '#79c0ff' if pnl > 0 else '#d29922'},
                'symbol': 'diamond',
                'symbolSize': 18,
                'label': {
                    'show': True, 'formatter': f'{pnl:+.1f}%',
                    'fontSize': 9, 'color': '#79c0ff' if pnl > 0 else '#d29922',
                    'position': 'bottom'
                }
            })

        # SL line (dashed)
        if sl_price > 0:
            end_x = dates[min(entry_daily_idx + 10, max_idx)]
            sl_markers.append({
                '_pair': [
                    {'xAxis': dates[entry_daily_idx], 'yAxis': sl_price},
                    {'xAxis': end_x, 'yAxis': sl_price}
                ],
                'lineStyle': {
                    'color': '#d29922', 'type': 'dashed', 'width': 1, 'opacity': 0.7
                },
                'label': {
                    'show': True, 'formatter': f'SL {sl_price:.2f} ({sl_pct:.2f}%)',
                    'color': '#d29922', 'fontSize': 9, 'position': 'start'
                }
            })

        # TP line (dashed, above entry for bull)
        tp_price = entry_price * (1 + tp_pct/100) if tp_pct > 0 else 0
        if tp_price > 0 and tp_price > entry_price:
            end_x = dates[min(entry_daily_idx + 10, max_idx)]
            tp_markers.append({
                '_pair': [
                    {'xAxis': dates[entry_daily_idx], 'yAxis': tp_price},
                    {'xAxis': end_x, 'yAxis': tp_price}
                ],
                'lineStyle': {
                    'color': '#3fb950', 'type': 'dashed', 'width': 1, 'opacity': 0.5
                },
                'label': {
                    'show': True, 'formatter': f'TP {tp_price:.2f} ({tp_pct:.1f}%)',
                    'color': '#3fb950', 'fontSize': 9, 'position': 'end'
                }
            })

    # ── Stock search list ──
    all_stocks = sorted(TRADE_MAPS.get('V467', {}).keys())

    # ── 60min signal data for toggle ──
    sig_60m_areas, sig_60m_lines, sig_60m_points = [], [], []
    if ohlcv_60m:
        try:
            result_60m = detect_all_signals_v11(ohlcv_60m, tf='60min')
            sigs_60m = result_60m.get('all', [])
            sc = 0
            for sig in sigs_60m:
                sd = fmt_date(sig.get('date', ''))[:10]
                if sd not in date_to_idx:
                    bi = sig.get('idx', 0)
                    if bi < len(ohlcv_60m):
                        sd = ohlcv_60m[bi]['_date']
                    if sd not in date_to_idx:
                        continue
                di = date_to_idx[sd]
                sc += 1
                stype = sig['type']
                style = SIG_STYLE.get(stype, {})
                family = SIG_FAMILY.get(stype, 'other')
                sname = f"60m-{sc}{style.get('label', stype[:4])}"

                if 'fill' in style:
                    upper = sig.get('upper', 0)
                    lower = sig.get('lower', 0)
                    if upper > 0 and lower > 0 and upper != lower:
                        sig_60m_areas.append({
                            'family': family, 'data': [
                                {'xAxis': dates[di], 'yAxis': lower,
                                 'itemStyle': {'color': style.get('fill','rgba(255,255,255,0.08)')
                                               .replace('0.2','0.08').replace('0.15','0.06'),
                                               'borderColor': style.get('stroke','rgba(255,255,255,0.3)'),
                                               'borderWidth': 1, 'borderType': 'dashed', 'opacity': 0.5}},
                                {'xAxis': dates[min(di+5, max_idx)], 'yAxis': upper}
                            ]
                        })

                if 'stroke' in style and 'fill' not in style:
                    price = sig.get('price', sig.get('upper', 0))
                    if price > 0:
                        sig_60m_lines.append({
                            'family': family,
                            '_pair': [
                                {'xAxis': dates[di], 'yAxis': price},
                                {'xAxis': dates[min(di+10, max_idx)], 'yAxis': price}
                            ],
                            'lineStyle': {'color': style.get('stroke','#888'), 'type': style.get('type','dashed'),
                                          'width': 1, 'opacity': 0.3},
                            'label': {'show': True, 'formatter': sname, 'color': style.get('stroke','#888'),
                                      'fontSize': 8, 'position': 'start'}
                        })

                price = sig.get('price', sig.get('upper', 0))
                if price > 0:
                    sig_60m_points.append({
                        'family': family, 'name': sname, 'coord': [dates[di], price], 'value': f'60m-{sc}',
                        'symbol': 'circle', 'symbolSize': 5,
                        'itemStyle': {'color': 'rgba(255,255,255,0.4)', 'borderColor': 'rgba(255,255,255,0.2)',
                                      'borderWidth': 1},
                        'label': {'show': False}
                    })
        except:
            pass

    # ── Trade detail table ──
    trade_rows = []
    for ti, t in enumerate(v467_trades):
        entry_d = ''
        exit_d = ''
        if ohlcv_60m:
            ei = t['entry_idx']
            xi = t['exit_idx']
            if ei < len(ohlcv_60m): entry_d = ohlcv_60m[ei]['_date']
            if xi < len(ohlcv_60m): exit_d = ohlcv_60m[xi]['_date']
        
        nearby = []
        for ns in numbered_sigs:
            if entry_d and ns.get('_date'):
                if abs(ns['idx'] - date_to_idx.get(entry_d, 0)) <= 5:
                    nearby.append(ns)
            elif abs(ns['idx'] - t['entry_idx']) <= 5:
                nearby.append(ns)
        nearby = nearby[:5]

        sigs_html = ''
        sig_map_lookup = {'fvg':'fvg','ifvg':'ifvg','ob':'ob','sweep':'sweep','choch':'choch',
                          'mss':'mss','ote':'ote','eql':'eql','po3':'po3','lv':'lv','rb':'rb','brk':'brk'}
        for ns in nearby:
            fam = SIG_FAMILY.get(ns['type'], 'fvg')
            sl = SHORT_LABEL.get(ns['type'], ns['type'][:4])
            cls = sig_map_lookup.get(fam, 'fvg')
            sigs_html += f'<span class="sig sig-{cls}">{ns["seq"]}{sl}</span>'

        pnl_c = 'win' if t.get('pnl_pct', 0) > 0 else 'loss'
        wl_c = 'win' if t['won'] else 'loss'
        wl_t = 'W' if t['won'] else 'L'
        sl_v = t.get('sl', 0)
        sl_s = f'{sl_v:.2f}' if sl_v else '-'

        trade_rows.append(
            f'<tr><td>{ti+1}</td>'
            f'<td>{entry_d}</td><td>{exit_d}</td>'
            f'<td>{t["entry_price"]:.2f}</td><td>{t["exit_price"]:.2f}</td>'
            f'<td>{sigs_html}</td>'
            f'<td>{t.get("entry_type","")}</td>'
            f'<td>{sl_s}</td><td>{t.get("sl_pct",0):.2f}%</td>'
            f'<td>{t.get("tp_pct",0):.1f}%</td>'
            f'<td>{t.get("hold_bars",0)}</td>'
            f'<td>{t.get("exit_method","")}</td>'
            f'<td class="{pnl_c}">{t.get("pnl_pct",0):+.2f}%</td>'
            f'<td class="{wl_c}">{wl_t}</td>'
            f'<td>{t.get("rr",0):.1f}x</td></tr>'
        )
    rows_html = ''.join(trade_rows)

    # Compute stats
    n_trades = len(v467_trades)
    n_wins = sum(1 for t in v467_trades if t['won'])
    wr_pct = n_wins / n_trades * 100 if n_trades else 0
    avg_rr = sum(t['rr'] for t in v467_trades) / n_trades if n_trades else 0

    # JSON serialization
    dates_j = json.dumps(dates, ensure_ascii=False)
    ohlcv_j = json.dumps(ohlcv_data)
    areas_j = json.dumps(sig_areas)
    lines_j = json.dumps(sig_lines)
    points_j = json.dumps(sig_points)
    entry_j = json.dumps(entry_markers, ensure_ascii=False)
    exit_j = json.dumps(exit_markers)
    sl_j = json.dumps(sl_markers)
    tp_j = json.dumps(tp_markers)
    sig60a_j = json.dumps(sig_60m_areas)
    sig60l_j = json.dumps(sig_60m_lines)
    sig60p_j = json.dumps(sig_60m_points)
    stocks_j = json.dumps(all_stocks, ensure_ascii=False)
    sym_j = json.dumps(symbol)

    # Stock options for selector
    stock_options = ''.join(
        f'<option value="{s}"{" selected" if s == symbol else ""}>{s}</option>'
        for s in all_stocks[:200]
    )

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>{symbol} V7 Unified</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:13px}}
.ctrl{{background:#161b22;padding:12px 20px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.ctrl select{{padding:6px 10px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;font-size:13px}}
.ctrl .btn{{padding:6px 14px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}}
h1{{font-size:18px;color:#f0f6fc}} .sub{{color:#8b949e;font-size:12px;margin-top:2px}}
.win{{color:#3fb950}}.loss{{color:#f85149}}
#chart{{width:100%;height:620px}}
.filter{{background:#161b22;padding:6px 20px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:11px}}
.filter label{{display:flex;align-items:center;gap:3px;cursor:pointer;padding:2px 6px;border-radius:3px;background:#0d1117;border:1px solid #30363d;font-size:11px}}
.filter input{{margin:0}}
.filter .tog{{background:#1f6feb33;border-color:#1f6feb66}}
.tbl-wrap{{padding:16px 20px;max-width:100%;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:#161b22;padding:4px 6px;text-align:left;color:#8b949e;font-weight:600;border-bottom:2px solid #30363d;white-space:nowrap;position:sticky;top:0}}
td{{padding:4px 6px;border-bottom:1px solid #21262d;white-space:nowrap}}
tr:hover{{background:#161b22}}
.sig{{display:inline-block;padding:1px 3px;border-radius:2px;font-size:9px;margin:0 1px;font-weight:bold}}
.sig-fvg{{background:#9C27B044;color:#CE93D8}}.sig-ifvg{{background:#7B1FA244;color:#CE93D8}}
.sig-ob{{background:#2196F344;color:#90CAF9}}.sig-sweep{{background:#FF980044;color:#FFCC80}}
.sig-choch{{background:#00BCD444;color:#80DEEA}}.sig-mss{{background:#4FC3F744;color:#B3E5FC}}
.sig-ote{{background:#4CAF5044;color:#A5D6A7}}.sig-eql{{background:#B0BEC544;color:#CFD8DC}}
.sig-po3{{background:#7C4DFF44;color:#B388FF}}.sig-lv{{background:#9E9E9E44;color:#BDBDBD}}
.sig-rb{{background:#FF980044;color:#FFCC80}}.sig-brk{{background:#9C27B044;color:#CE93D8}}.sig-bpr{{background:#00968844;color:#80CBC4}}
.kpi{{display:flex;gap:12px;padding:10px 20px;background:#161b22;border-bottom:1px solid #30363d}}
.kpi-item{{flex:1;text-align:center}}
.kpi-val{{font-size:18px;font-weight:bold}} .kpi-lbl{{color:#8b949e;font-size:10px}}
</style>
<script src="/echarts.min.js"></script></head><body>
{nav}
<div class="ctrl">
<form method="get" style="display:flex;gap:8px;align-items:center;">
<select name="s" onchange="this.form.submit()">{stock_options}</select>
<input type="submit" class="btn" value="View">
</form>
<h1>{symbol}</h1>
<span class="sub">{n_trades} trades | WR={wr_pct:.1f}% | RR={avg_rr:.1f}x | Signals: {len(numbered_sigs)}</span>
</div>
<div class="kpi">
<div class="kpi-item"><div class="kpi-lbl">Trades</div><div class="kpi-val" style="color:#f0f6fc">{n_trades}</div></div>
<div class="kpi-item"><div class="kpi-lbl">WR</div><div class="kpi-val" style="color:#3fb950">{wr_pct:.1f}%</div></div>
<div class="kpi-item"><div class="kpi-lbl">Avg RR</div><div class="kpi-val" style="color:#d2a8ff">{avg_rr:.1f}x</div></div>
<div class="kpi-item"><div class="kpi-lbl">Entry</div><div class="kpi-val" style="color:#58a6ff;font-size:12px">{v467_trades[0].get("entry_type","") if v467_trades else "-"}</div></div>
<div class="kpi-item"><div class="kpi-lbl">Signals</div><div class="kpi-val" style="color:#f0883e;font-size:12px">{len(numbered_sigs)}</div></div>
</div>
<div class="filter">
<span style="color:#8b949e;font-weight:bold;">Signals:</span>
<label><input type="checkbox" class="sf" data-f="fvg" checked> FVG</label>
<label><input type="checkbox" class="sf" data-f="ifvg" checked> IFVG</label>
<label><input type="checkbox" class="sf" data-f="ob" checked> OB</label>
<label><input type="checkbox" class="sf" data-f="sweep" checked> Sweep</label>
<label><input type="checkbox" class="sf" data-f="choch" checked> CHOCH</label>
<label><input type="checkbox" class="sf" data-f="mss" checked> MSS</label>
<label><input type="checkbox" class="sf" data-f="ote" checked> OTE</label>
<label><input type="checkbox" class="sf" data-f="eql" checked> EQL</label>
<label><input type="checkbox" class="sf" data-f="po3" checked> PO3</label>
<label><input type="checkbox" class="sf" data-f="bpr" checked> BPR</label>
<label><input type="checkbox" class="sf" data-f="lv" checked> LV</label>
<label><input type="checkbox" class="sf" data-f="rb" checked> RB</label>
<label><input type="checkbox" class="sf" data-f="brk" checked> BRK</label>
<span style="flex:1"></span>
<label class="tog"><input type="checkbox" id="show60m" onchange="toggle60m()"> 60min Sig</label>
<label class="tog"><input type="checkbox" id="showSL" checked onchange="toggleSL()"> SL</label>
<label class="tog"><input type="checkbox" id="showTP" onchange="toggleTP()"> TP</label>
<button style="padding:2px 8px;background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:3px;cursor:pointer;font-size:10px" onclick="document.querySelectorAll('.sf').forEach(c=>c.checked=true);render();">All</button>
<button style="padding:2px 8px;background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:3px;cursor:pointer;font-size:10px" onclick="document.querySelectorAll('.sf').forEach(c=>c.checked=false);render();">None</button>
</div>
<div id="chart"></div>
<div class="tbl-wrap">
<h2 style="font-size:14px;color:#f0f6fc;margin-bottom:8px;">V467 Trade Details — TP/SL/Signals/Entry Type</h2>
<table><thead><tr>
<th>#</th><th>Entry</th><th>Exit</th><th>E-Price</th><th>X-Price</th><th>Signals</th><th>Type</th><th>SL</th><th>SL%</th><th>TP%</th><th>Hold</th><th>Exit</th><th>P&L</th><th>W/L</th><th>RR</th>
</tr></thead><tbody>{rows_html}</tbody></table></div>
<script>
var dom=document.getElementById("chart");var chart=echarts.init(dom,"dark");
var dates={dates_j};var ohlcvData={ohlcv_j};
var areas={areas_j};var slines={lines_j};var spoints={points_j};
var entries={entry_j};var exits={exit_j};var slMarks={sl_j};var tpMarks={tp_j};
var sig60a={sig60a_j};var sig60l={sig60l_j};var sig60p={sig60p_j};
var currentSymbol={sym_j};
function activeFamilies(){{var a={{}};document.querySelectorAll(".sf").forEach(function(c){{a[c.dataset.f]=c.checked}});return a;}}
function render(){{
var af=activeFamilies();
var fa=areas.filter(function(m){{return af[m.family]}}).map(function(m){{return m.data}});
var fl=slines.filter(function(m){{return af[m.family]}}).map(function(m){{return m._pair||m}});
var fp=spoints.filter(function(m){{return af[m.family]}});
var show60=document.getElementById("show60m");
if(show60&&show60.checked){{
fa=fa.concat(sig60a.filter(function(m){{return af[m.family]}}).map(function(m){{return m.data}}));
fl=fl.concat(sig60l.filter(function(m){{return af[m.family]}}).map(function(m){{return m._pair||m}}));
fp=fp.concat(sig60p.filter(function(m){{return af[m.family]}}));
}}
var em=entries.map(function(e){{return{{name:e.name,coord:e.coord,value:e.value,_tt:e._tt,itemStyle:e.itemStyle,symbol:e.symbol,symbolSize:e.symbolSize,label:e.label}}}});
var xm=exits.map(function(e){{return{{coord:e.coord,value:e.value,_tt:e._tt,itemStyle:e.itemStyle,symbol:e.symbol,symbolSize:e.symbolSize,label:e.label}}}});
var allMarks=fp.concat(em).concat(xm);
var showSL=document.getElementById("showSL");
var showTP=document.getElementById("showTP");
var mlData=fl.slice();
if(showSL&&showSL.checked)mlData=mlData.concat(slMarks.map(function(m){{return m._pair||m}}));
if(showTP&&showTP.checked)mlData=mlData.concat(tpMarks.map(function(m){{return m._pair||m}}));
chart.setOption({{
animation:false,backgroundColor:"#0d1117",
tooltip:{{trigger:"axis",axisPointer:{{type:"cross"}},
formatter:function(params){{
for(var i=0;i<params.length;i++){{
var p=params[i];if(p.componentType==="markPoint"&&p.data&&p.data._tt)return p.data._tt;
if(p.componentType==="markLine"&&p.data&&p.data._tt)return p.data._tt;
}}return false;
}}}},
dataZoom:[{{type:"inside",start:0,end:100}},{{type:"slider",start:0,end:100,bottom:10,height:25,borderColor:"#30363d",backgroundColor:"#161b22"}}],
grid:{{left:"5%",right:"5%",bottom:"15%",top:"5%"}},
xAxis:{{type:"category",data:dates,axisLine:{{lineStyle:{{color:"#30363d"}}}},axisLabel:{{rotate:45,fontSize:10,interval:30,color:"#8b949e"}},splitLine:{{show:false}}}},
yAxis:{{scale:true,splitLine:{{lineStyle:{{color:"#21262d",type:"dashed"}}}},axisLabel:{{color:"#8b949e",fontSize:11}}}},
series:[{{name:"K线",type:"candlestick",data:ohlcvData,
itemStyle:{{color:"#f85149",color0:"#3fb950",borderColor:"#f85149",borderColor0:"#3fb950"}},
markPoint:{{data:allMarks,symbol:"pin",symbolSize:30,
label:{{show:true,formatter:function(p){{return p.name}},fontSize:9,color:"#fff"}}}} ,
markArea:{{silent:false,data:fa,emphasis:{{itemStyle:{{opacity:0.5}}}}}},
markLine:{{silent:false,data:mlData,emphasis:{{lineStyle:{{width:2}}}}}}
}}]
}});}}
function toggle60m(){{render();}}
function toggleSL(){{render();}}
function toggleTP(){{render();}}
chart.setOption({{animation:false,backgroundColor:"#0d1117",
tooltip:{{trigger:"axis",axisPointer:{{type:"cross"}}}},
dataZoom:[{{type:"inside",start:0,end:100}},{{type:"slider",start:0,end:100,bottom:10,height:25,borderColor:"#30363d",backgroundColor:"#161b22"}}],
grid:{{left:"5%",right:"5%",bottom:"15%",top:"5%"}},
xAxis:{{type:"category",data:dates,axisLine:{{lineStyle:{{color:"#30363d"}}}},axisLabel:{{rotate:45,fontSize:10,interval:30,color:"#8b949e"}},splitLine:{{show:false}}}},
yAxis:{{scale:true,splitLine:{{lineStyle:{{color:"#21262d",type:"dashed"}}}},axisLabel:{{color:"#8b949e",fontSize:11}}}},
series:[{{name:"K线",type:"candlestick",data:ohlcvData,
itemStyle:{{color:"#f85149",color0:"#3fb950",borderColor:"#f85149",borderColor0:"#3fb950"}},
markPoint:{{data:[],symbol:"pin",symbolSize:30,label:{{show:true}}}},
markArea:{{silent:false,data:[]}},
markLine:{{silent:false,data:[]}}
}}]
}});
setTimeout(render,50);
document.querySelectorAll(".sf").forEach(function(cb){{cb.addEventListener("change",render);}});
window.addEventListener("resize",function(){{chart.resize()}});
</script></body></html>'''
