#!/usr/bin/env python3
# SMC V9 — Advanced Signal Annotation Engine
"""
高级SMC信号标识引擎：生成可视化标注数据供ECharts前端渲染。
包括趋势线(BOS/CHoCH/BSL/SSL/EQL)、区域(OB/FVG/POI/Supply-Demand)、以及买卖点标注。

核心函数: generate_chart_data(ohlcv, signals, trades=None) -> dict
该函数输出可直接被前端消费的标注数据结构。
"""

import math, logging, json
from collections import defaultdict

log = logging.getLogger('smc_v9.annotations')

# ─── 颜色主题 ───────────────────────────────────────────────────────
COLORS = {
    'BOS_Bull': '#3fb950', 'BOS_Bear': '#f85149',
    'CHoCH': '#d29922',
    'BSL': '#58a6ff', 'SSL': '#f0883e', 'EQL': '#8b949e',
    'FVG_Bull': 'rgba(63,185,80,0.20)', 'FVG_Bear': 'rgba(248,81,73,0.20)',
    'OB_Bull': '#3fb950', 'OB_Bear': '#f85149',
    'POI': '#bc8cff',
    'Demand': 'rgba(63,185,80,0.25)', 'Supply': 'rgba(248,81,73,0.25)',
    'Entry_Long': '#3fb950', 'Entry_Short': '#f85149',
    'SL': '#f85149', 'TP': '#3fb950',
}


# ═══════════════════════════════════════════════════════════════════════
# PART 1: 结构识别 — BOS / CHoCH
# ═══════════════════════════════════════════════════════════════════════

def _swing_points(ohlcv, lookback=5):
    """识别摆动高点和低点。"""
    highs = [b['h'] for b in ohlcv]
    lows = [b['l'] for b in ohlcv]
    n = len(ohlcv)

    swing_highs = []
    swing_lows = []
    for i in range(lookback, n - lookback):
        # 摆动高点: 两侧各 lookback 根内的最高
        if highs[i] == max(highs[i - lookback:i + lookback + 1]):
            swing_highs.append({'idx': i, 'price': highs[i]})
        # 摆动低点: 两侧各 lookback 根内的最低
        if lows[i] == min(lows[i - lookback:i + lookback + 1]):
            swing_lows.append({'idx': i, 'price': lows[i]})

    return swing_highs, swing_lows


def detect_structure_breaks(ohlcv, min_pct=0.3):
    """检测BOS(突破结构)和CHoCH(趋势转变)。

    返回: [{'type':'BOS_Bull'/'BOS_Bear'/'CHoCH_Bull'/'CHoCH_Bear', idx, price, strength, label}, ...]
    每条带 label 描述。
    """
    swing_highs, swing_lows = _swing_points(ohlcv)
    results = []

    # ── BOS (Break of Structure) ──
    # BOS_Bull: 价格突破前一个摆动高点
    for i in range(1, len(swing_highs)):
        prev = swing_highs[i - 1]
        curr = swing_highs[i]
        pct_up = (curr['price'] - prev['price']) / prev['price'] * 100
        if pct_up > min_pct:
            strength = min(pct_up / 1.0, 5.0)
            results.append({
                'type': 'BOS_Bull',
                'idx': curr['idx'],
                'price': round(prev['price'], 2),
                'break_price': round(curr['price'], 2),
                'strength': round(strength, 1),
                'label': f'BOS↑ {prev["idx"]}→{curr["idx"]}',
            })

    # BOS_Bear: 价格跌破前一个摆动低点
    for i in range(1, len(swing_lows)):
        prev = swing_lows[i - 1]
        curr = swing_lows[i]
        pct_down = (prev['price'] - curr['price']) / prev['price'] * 100
        if pct_down > min_pct:
            strength = min(pct_down / 1.0, 5.0)
            results.append({
                'type': 'BOS_Bear',
                'idx': curr['idx'],
                'price': round(prev['price'], 2),
                'break_price': round(curr['price'], 2),
                'strength': round(strength, 1),
                'label': f'BOS↓ {prev["idx"]}→{curr["idx"]}',
            })

    # ── CHoCH (Change of Character) ──
    # CHoCH_Bull: 从下降 → 上升 — 出现HH+HL
    if len(swing_lows) >= 4 and len(swing_highs) >= 2:
        # 最后3个摆动低点呈现 Higher Low
        ll = swing_lows[-3:]
        if ll[2]['price'] > ll[1]['price'] > ll[0]['price']:
            strength = min((ll[2]['price'] - ll[0]['price']) / ll[0]['price'] * 50, 5.0)
            results.append({
                'type': 'CHoCH_Bull',
                'idx': ll[2]['idx'],
                'price': round(ll[2]['price'], 2),
                'prev_low': round(ll[0]['price'], 2),
                'strength': round(max(1.0, strength), 1),
                'label': f'CHoCH↑ HL@{ll[2]["idx"]}',
            })

    # CHoCH_Bear: 从上升 → 下降 — 出现LH+LL
    if len(swing_highs) >= 4 and len(swing_lows) >= 2:
        # 摆动低点最后2个: LL
        hh = swing_highs[-3:]
        if hh[2]['price'] < hh[1]['price'] < hh[0]['price']:
            strength = min((hh[0]['price'] - hh[2]['price']) / hh[0]['price'] * 50, 5.0)
            results.append({
                'type': 'CHoCH_Bear',
                'idx': hh[2]['idx'],
                'price': round(hh[2]['price'], 2),
                'prev_high': round(hh[0]['price'], 2),
                'strength': round(max(1.0, strength), 1),
                'label': f'CHoCH↓ LH@{hh[2]["idx"]}',
            })

    return results


# ═══════════════════════════════════════════════════════════════════════
# PART 2: 趋势线 — BSL / SSL / EQL
# ═══════════════════════════════════════════════════════════════════════

def detect_trend_lines(ohlcv):
    """检测BSL(支撑线), SSL(阻力线), EQL(均衡/中枢线).

    返回: {'BSL':[{x1,y1,x2,y2,strength}], 'SSL':[...], 'EQL':[{idx,price}]}
    """
    swing_highs, swing_lows = _swing_points(ohlcv, lookback=3)

    # ── BSL: 连接两个或以上摆动低点 ──
    bsl = []
    for i in range(len(swing_lows)):
        for j in range(i + 1, len(swing_lows)):
            sli, slj = swing_lows[i], swing_lows[j]
            # 后一个低点必须 >= 前一个 (不破)
            if slj['price'] >= sli['price']:
                dist = slj['idx'] - sli['idx']
                if 5 <= dist <= 60:  # 合理距离
                    strength = min(1.0 + (slj['price'] - sli['price']) / sli['price'] * 30, 5.0)
                    bsl.append({
                        'x1': sli['idx'], 'y1': round(sli['price'], 2),
                        'x2': slj['idx'], 'y2': round(slj['price'], 2),
                        'strength': round(strength, 1),
                        'label': f"BSL@{sli['idx']}→@{slj['idx']}",
                    })
    # 最多返回strength最高的3条
    bsl = sorted(bsl, key=lambda x: -x['strength'])[:3]

    # ── SSL: 连接两个或以上摆动高点 ──
    ssl = []
    for i in range(len(swing_highs)):
        for j in range(i + 1, len(swing_highs)):
            shi, shj = swing_highs[i], swing_highs[j]
            if shj['price'] <= shi['price']:
                dist = shj['idx'] - shi['idx']
                if 5 <= dist <= 60:
                    strength = min(1.0 + (shi['price'] - shj['price']) / shi['price'] * 30, 5.0)
                    ssl.append({
                        'x1': shi['idx'], 'y1': round(shi['price'], 2),
                        'x2': shj['idx'], 'y2': round(shj['price'], 2),
                        'strength': round(strength, 1),
                        'label': f"SSL@{shi['idx']}→@{shj['idx']}",
                    })
    ssl = sorted(ssl, key=lambda x: -x['strength'])[:3]

    # ── EQL: 均衡线 — 最近30根的SMA20中枢 ──
    eql = []
    n = len(ohlcv)
    lookback = min(30, max(20, n // 4))
    # 分段EQL
    step = max(1, lookback // 5)
    for i in range(n - lookback, n, step):
        window = ohlcv[max(0, i - 10):i + 10]
        if window:
            centre = sum(b['c'] for b in window) / len(window)

    return {
        'BSL': bsl,
        'SSL': ssl,
        'EQL': eql,
    }


# ═══════════════════════════════════════════════════════════════════════
# PART 3: 兴趣点(POI) — 多信号汇聚区域
# ═══════════════════════════════════════════════════════════════════════

def detect_poi_zones(ohlcv, signals):
    """POI由多重信号汇聚形成.

    规则:
    - FVG + OB 距离 <= 3 → POI (最高)
    - Sweep + FVG 重叠 → POI (高)
    - BPR + OB 重叠 → POI (中)

    返回: [{'type':'POI', idx, upper, lower, sources:[...], strength}, ...]
    """
    # 按类型分组
    fvg = [s for s in signals if s['type'] == 'FVG']
    ob = [s for s in signals if s['type'].startswith('OB_')]
    sweep = [s for s in signals if s['type'].startswith('Sweep')]
    bpr = [s for s in signals if s['type'].startswith('BPR_')]
    msb = [s for s in signals if s['type'].startswith('MSB_')]

    poi_list = []
    used = set()

    for f in fvg:
        for o in ob:
            pair_id = (f['idx'], o['idx'])
            if pair_id not in used and abs(f['idx'] - o['idx']) <= 3:
                upper = max(f.get('upper', 0), o.get('upper', 0))
                lower = min(f.get('lower', 0), o.get('lower', 0))
                if upper > lower:
                    idx = max(f['idx'], o['idx'])
                    strength = 5.0  # FVG+OB = 最强
                    poi_list.append({
                        'type': 'POI',
                        'idx': idx,
                        'upper': round(upper, 2),
                        'lower': round(lower, 2),
                        'sources': ['FVG', f'OB_{o.get("direction", "?")}'],
                        'strength': strength,
                    })
                    used.add(pair_id)

    for s in sweep:
        for f in fvg:
            pair_id = ('sw', s['idx'], f['idx'])
            if pair_id not in used and s['idx'] >= f['idx'] - 3:
                upper = s.get('high', s.get('upper', 0))
                lower = f.get('lower', 0)
                if upper > lower:
                    idx = s['idx']
                    strength = 4.0
                    poi_list.append({
                        'type': 'POI',
                        'idx': idx,
                        'upper': round(upper, 2),
                        'lower': round(lower, 2),
                        'sources': [s['type'], 'FVG'],
                        'strength': strength,
                    })
                    used.add(pair_id)

    for b in bpr:
        for o in ob:
            pair_id = ('bpr', b['idx'], o['idx'])
            if pair_id not in used and abs(b['idx'] - o['idx']) <= 3:
                upper = max(b.get('upper', 0), o.get('upper', 0))
                lower = min(b.get('lower', 0), o.get('lower', 0))
                if upper > lower:
                    idx = max(b['idx'], o['idx'])
                    strength = 3.5
                    poi_list.append({
                        'type': 'POI',
                        'idx': idx,
                        'upper': round(upper, 2),
                        'lower': round(lower, 2),
                        'sources': ['BPR', f'OB_{o.get("direction", "?")}'],
                        'strength': strength,
                    })
                    used.add(pair_id)

    return sorted(poi_list, key=lambda x: -x['strength'])


# ═══════════════════════════════════════════════════════════════════════
# PART 4: Supply / Demand Zone
# ═══════════════════════════════════════════════════════════════════════

def detect_supply_demand(ohlcv, volume_mult=1.5, kbody_pct=1.0):
    """Supply/Demand Zone.

    Supply: 大幅上涨 + 成交量放大 + 大阴线顶部
    Demand: 大幅下跌 + 成交量放大 + 大阳线底部

    返回: [{'type':'Demand'/'Supply', idx, upper, lower, strength, volume_ratio}]
    """
    sd_list = []
    n = len(ohlcv)
    for i in range(20, n):
        bar = ohlcv[i]
        body = abs(bar['c'] - bar['o'])
        wick = bar['h'] - bar['l']
        avg_vol = sum(ohlcv[j]['v'] for j in range(max(0, i - 10), i)) / 10 if i >= 10 else 0

        # 成交量放大
        if avg_vol > 0 and bar['v'] < avg_vol * volume_mult:
            continue

        # 大幅波动 + 成交量放大
        body_pct = body / wick * 100 if wick > 0 else 0
        if body_pct < kbody_pct * 50:
            continue

        # 计算前一波动
        prev_range = max(0.5, abs(ohlcv[i - 1]['h'] - ohlcv[i - 1]['l']))
        vol_ratio = round(bar['v'] / avg_vol, 1) if avg_vol > 0 else 0

        # Demand: 大幅下跌 + 大阳线(close > open) + 成交量放大
        if bar['c'] > bar['o']:
            drop = (bar['o'] - bar['l']) / bar['l'] * 100 if bar['l'] > 0 else 0
            if drop > 0.5 or (body > wick * 0.6 and vol_ratio >= 1.3):
                lower = round(bar['l'] - (bar['h'] - bar['l']) * 0.1, 2)
                upper = round(bar['l'] + body * 0.3, 2)
                strength = min(1.0 + vol_ratio * 0.5 + drop * 0.3, 5.0)
                sd_list.append({
                    'type': 'Demand',
                    'idx': i,
                    'upper': upper,
                    'lower': lower,
                    'strength': round(strength, 1),
                    'volume_ratio': vol_ratio,
                    'price': round(bar['c'], 2),
                })

        # Supply: 大幅上涨 + 大阴线(close < open) + 成交量放大
        elif bar['c'] < bar['o']:
            rise = (bar['h'] - bar['o']) / bar['o'] * 100 if bar['o'] > 0 else 0
            if rise > 0.5 or (body > wick * 0.6 and vol_ratio >= 1.3):
                lower = round(bar['h'] - body * 0.3, 2)
                upper = round(bar['h'] + (bar['h'] - bar['l']) * 0.1, 2)
                strength = min(1.0 + vol_ratio * 0.5 + rise * 0.3, 5.0)
                sd_list.append({
                    'type': 'Supply',
                    'idx': i,
                    'upper': upper,
                    'lower': lower,
                    'strength': round(strength, 1),
                    'volume_ratio': vol_ratio,
                    'price': round(bar['c'], 2),
                })

    # 去重: 同区域内只保留最强
    if sd_list:
        filtered = [sd_list[0]]
        for s in sd_list[1:]:
            last = filtered[-1]
            if abs(s['idx'] - last['idx']) <= 3 and s['type'] == last['type']:
                if s['strength'] > last['strength']:
                    filtered[-1] = s
            else:
                filtered.append(s)
        sd_list = filtered

    return sd_list


# ═══════════════════════════════════════════════════════════════════════
# PART 5: 买卖点 → ECharts entry/exit 格式
# ═══════════════════════════════════════════════════════════════════════

def signals_to_entry_exits(signals, trades=None, params=None):
    """将信号和回测交易转化为ECharts entry/exit标记。

    params 包含 sl_pct, tp_pct, score_min 等.

    返回: [{'idx', entry', 'sl', 'tp', 'ret', 'direction', 'signal_type', ...}, ...]
    """
    if not params:
        params = {'sl_pct': 1.0, 'tp_pct': 3.0}
    sl_pct = params.get('sl_pct', 1.0) / 100
    tp_pct = params.get('tp_pct', 3.0) / 100

    entries = []
    used_indices = set()

    # 优先从trade数据中提取entry/exit
    if trades:
        for t in trades:
            entry = entries[-1] if entries else {}
            idx = t.get('idx', 0)
            entry = {
                'idx': idx,
                'entry': round(t.get('entry', t.get('price', 0)), 2),
                'exit': round(t.get('exit', 0), 2),
                'sl': round(t.get('sl', 0), 2),      # 如果有
                'tp': round(t.get('tp', 0), 2),
                'ret': round(t.get('ret', 0), 2),
                'direction': t.get('direction', 'long'),
                'signal_type': t.get('signal_type', '?'),
                'win': t.get('win', t.get('ret', 0) > 0),
                'rr': round(t.get('rr', 0), 2),
                'reason': t.get('reason', t.get('signal_type', 'SMC信号')),
            }
            entries.append(entry)

    # 如果没有回测数据，从signals合成entry (价格=signal price, SL/TP通过估算)
    if not entries and signals:
        for s in signals[:10]:  # 最多10个
            idx = s.get('idx', 0)
            direction = s.get('direction', 'bull')
            price = s.get('price', s.get('upper', s.get('break_level', s.get('lower', 0))))
            if price > 0 and idx not in used_indices:
                used_indices.add(idx)
                if direction == 'bull':
                    sl = round(price * (1 - sl_pct), 2)
                    tp = round(price * (1 + tp_pct), 2)
                else:
                    sl = round(price * (1 + sl_pct), 2)
                    tp = round(price * (1 - tp_pct), 2)

                entries.append({
                    'idx': idx,
                    'entry': price,
                    'sl': sl,
                    'tp': tp,
                    'direction': direction,
                    'signal_type': s['type'],
                    'reason': f'{s["type"]} @{idx}',
                })

    return entries


# ═══════════════════════════════════════════════════════════════════════
# PART 6: ECharts数据整合
# ═══════════════════════════════════════════════════════════════════════

def calc_atr_pct(ohlcv, period=14):
    """简易ATR计算(百分比)。"""
    if not ohlcv or len(ohlcv) < period + 1:
        return 0
    trs = []
    for i in range(1, min(period + 1, len(ohlcv))):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i - 1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if trs:
        avg_tr = sum(trs) / len(trs)
        return round(avg_tr / ohlcv[-1]['c'] * 100, 2)
    return 0


def _render_lines_dict(trend_type, lines_dict, color_fn):
    """将BSL/SSL转为前端可消费的line mark数据。"""
    result = []
    lines = lines_dict.get(trend_type, [])
    for i, l in enumerate(lines):
        result.append({
            'id': f'{trend_type}_{i}',
            'type': trend_type,
            'x1': l['x1'], 'y1': l['y1'],
            'x2': l['x2'], 'y2': l['y2'],
            'strength': l.get('strength', 1.0),
            'label': l.get('label', f'{trend_type}_{i}'),
            'color': color_fn(trend_type),
            'lineStyle': 'dashed' if 'BSL' in trend_type or 'SSL' in trend_type else 'solid',
        })
    return result


def _render_eql_lines(lines):
    """EQL均衡线 → ECharts markLine data. [{xAxis, yAxis, ...}]"""
    return [{'type': 'EQL', 'x': l['idx'], 'y': l['price'],
             'label': f'EQL@{l["price"]:.0f}', 'color': COLORS['EQL']} for l in lines]


def _zones_to_mark_area(zones, color_base, label_prefix):
    """将zone[]转为ECharts markArea格式.

    ECharts markArea: [{xAxis: start, yAxis: y1}, {xAxis: end, yAxis: y2}]
    但我们传给前端原始数据，前端用 custom series 或 graphic 来绘制矩形.
    这里返回 [{type, xAxis, yAxis_start, yAxis_end, ...}]
    """
    area = []
    for z in zones:
        # ECharts markArea needs paired data items
        color = color_base
        if 'direction' in z and z['direction'] == 'bull':
            color = COLORS.get('OB_Bull', color)
        elif 'direction' in z and z['direction'] == 'bear':
            color = COLORS.get('OB_Bear', color)

        area.append({
            'type': z.get('type', 'ZONE'),
            'idx': z.get('idx', 0),
            'upper': z.get('upper', z.get('price', 0)),
            'lower': z.get('lower', z.get('price', 0)),
            'strength': z.get('strength', 1.0),
            'direction': z.get('direction', ''),
            'color': color,
            'label': label_prefix,
            'sources': z.get('sources', []),
        })
    return area


def generate_chart_data(ohlcv, signals, trades=None, params=None):
    """完整的前端ECharts标注数据.

    Args:
        ohlcv: K线数据, [{'o','h','l','c','v'}, ...]
        signals: 从smc_signals.detect_all_signals() 的输出
        trades: (可选) 从smc_backtest.evaluate_trades() 的输出trades
        params: (可选) 参数

    Returns:
        dict: 前端可直接消费的数据
    """
    if ohlcv is None:
        ohlcv = []

    result = {
        'ohlcv': ohlcv,
        'current_price': ohlcv[-1]['c'] if ohlcv else 0,
        'atr_pct': calc_atr_pct(ohlcv) if ohlcv else 0,
    }

    # ── 1. 趋势线 (BOS/CHoCH) ──
    try:
        structures = detect_structure_breaks(ohlcv)
    except Exception as e:
        log.warning(f"detect_structure_breaks failed: {e}")
        structures = []
    result['structures'] = structures

    # ── 2. 趋势线 (BSL/SSL/EQL) ──
    try:
        trend_lines = detect_trend_lines(ohlcv)
    except Exception as e:
        log.warning(f"detect_trend_lines failed: {e}")
        trend_lines = {'BSL': [], 'SSL': [], 'EQL': []}
    result['trend_lines'] = {
        'BSL': _render_lines_dict('BSL', trend_lines, lambda t: COLORS['BSL']),
        'SSL': _render_lines_dict('SSL', trend_lines, lambda t: COLORS['SSL']),
        'EQL': trend_lines.get('EQL', []),
    }

    # ── 3. 信号区域 (FVG, IFVG, OB) ──
    zones_fvg = [s for s in signals if s['type'] == 'FVG']
    zones_ob = [s for s in signals if s['type'].startswith('OB_')]
    zones_bpr = [s for s in signals if s['type'].startswith('BPR_')]
    zones_msb = [s for s in signals if s['type'].startswith('MSB_')]
    zones_sweep = [s for s in signals if s['type'].startswith('Sweep')]

    result['zones'] = {
        'FVG': _zones_to_mark_area(zones_fvg, COLORS['FVG_Bull'], 'FVG'),
        'OB': _zones_to_mark_area(zones_ob, COLORS['OB_Bull'], 'OB'),
        'BPR': _zones_to_mark_area(zones_bpr, COLORS['EQL'], 'BPR'),
        'MSB': _zones_to_mark_area(zones_msb, COLORS['CHoCH'], 'MSB'),
        'Sweep': _zones_to_mark_area(zones_sweep, COLORS['POI'], 'Sweep'),
    }

    # ── 4. POI ──
    try:
        pois = detect_poi_zones(ohlcv, signals)
    except Exception as e:
        log.warning(f"detect_poi_zones failed: {e}")
        pois = []
    result['poi'] = _zones_to_mark_area(pois, COLORS['POI'], 'POI')

    # ── 5. Supply/Demand ──
    try:
        sd = detect_supply_demand(ohlcv)
    except Exception as e:
        log.warning(f"detect_supply_demand failed: {e}")
        sd = []
    result['supply_demand'] = _zones_to_mark_area(sd, COLORS['Demand'], 'S-D')

    # ── 6. Entry/Exit (买卖点) ──
    result['entries'] = signals_to_entry_exits(signals, trades, params)

    # ── 7. Summary: 统计每种标注的数量 ──
    summary = {}
    if structures:
        for s in structures:
            summary[s['type']] = summary.get(s['type'], 0) + 1
    for k, v in result['zones'].items():
        summary[k] = summary.get(k, 0) + len(v)
    summary['POI'] = len(pois)
    summary['Supply/Demand'] = len(sd)
    summary['Entry'] = len(result['entries'])
    result['annotation_summary'] = summary

    return result


# ─── 快捷测试 ──────────────────────────────────────────────────────
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    print("=== SMC Annotations Module ===")
    print("Functions:", [n for n in dir() if n.startswith(('detect_', 'generate_', '_swing', '_zones', '_render', 'signals_to'))])
    print("Colors:", json.dumps(COLORS, indent=2))