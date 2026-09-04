#!/usr/bin/env python3
"""
SMC Scanner — 可独立运行的 SMC 信号扫描脚本

用法:
  python3 scripts/smc_scanner.py --market cn --symbols 000001.SZ,600519.SH --interval daily
  python3 scripts/smc_scanner.py --market crypto --symbols BTCUSDT,ETHUSDT --exchange binance
  python3 scripts/smc_scanner.py --market us --symbols AAPL,TSLA,MSFT
"""

import json, sys, math, urllib.request, argparse

BASE = "http://43.167.234.49:3101"
HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# ─── FVG 检测 ───────────────────────────────────────────
def detect_fvg(klines):
    fvg_signals = []
    if len(klines) < 3:
        return fvg_signals

    avg_range = sum(abs(k['h'] - k['l']) for k in klines[-30:]) / 30 if len(klines) >= 30 else sum(abs(k['h'] - k['l']) for k in klines) / max(1, len(klines))

    for i in range(1, len(klines) - 1):
        prev, curr, nxt = klines[i-1], klines[i], klines[i+1]
        body_size = abs(curr['c'] - curr['o'])

        if curr['c'] > curr['o']:  # 阳线 → Bullish FVG
            gap_top = min(prev['h'], nxt['h'])
            gap_bot = max(prev['l'], nxt['l'])
            if gap_top > gap_bot and gap_top - gap_bot > avg_range * 0.15:
                strength = 1
                if body_size > (gap_top - gap_bot) * 2:
                    strength += 1
                if (gap_top - gap_bot) > avg_range * 0.5:
                    strength += 1
                fvg_signals.append({
                    'type': 'Bullish FVG', 'direction': 'long',
                    'top': round(gap_top, 4), 'bottom': round(gap_bot, 4),
                    'mid': round((gap_top + gap_bot) / 2, 4),
                    'strength': strength, 'index': i,
                    'width': round(gap_top - gap_bot, 4)
                })
        elif curr['c'] < curr['o']:  # 阴线 → Bearish FVG
            gap_top = max(prev['h'], nxt['h'])
            gap_bot = min(prev['l'], nxt['l'])
            if gap_top > gap_bot and gap_top - gap_bot > avg_range * 0.15:
                strength = 1
                if body_size > (gap_top - gap_bot) * 2:
                    strength += 1
                if (gap_top - gap_bot) > avg_range * 0.5:
                    strength += 1
                fvg_signals.append({
                    'type': 'Bearish FVG', 'direction': 'short',
                    'top': round(gap_top, 4), 'bottom': round(gap_bot, 4),
                    'mid': round((gap_top + gap_bot) / 2, 4),
                    'strength': strength, 'index': i,
                    'width': round(gap_top - gap_bot, 4)
                })
    return fvg_signals


# ─── 流动性猎杀检测 ─────────────────────────────────────
def find_pivots(klines, left=3, right=3):
    highs, lows = [], []
    for i in range(left, len(klines) - right):
        candidates_high = [klines[j]['h'] for j in range(i-left, i+right+1) if 0 <= j < len(klines)]
        if klines[i]['h'] == max(candidates_high):
            highs.append((i, klines[i]['h']))

        candidates_low = [klines[j]['l'] for j in range(i-left, i+right+1) if 0 <= j < len(klines)]
        if klines[i]['l'] == min(candidates_low):
            lows.append((i, klines[i]['l']))
    return highs, lows


def detect_liquidity_sweep(klines, lookback=15):
    signals = []
    if len(klines) < lookback + 3:
        return signals

    for i in range(lookback, len(klines)):
        curr = klines[i]
        high_level = max(k['h'] for k in klines[i-lookback:i])
        low_level = min(k['l'] for k in klines[i-lookback:i])
        body = abs(curr['c'] - curr['o'])
        if body == 0:
            continue

        # BSL Sweep: 突破前高后回落
        if curr['h'] > high_level and curr['c'] < high_level:
            wick_top = curr['h'] - max(curr['c'], curr['o'])
            ratio = wick_top / body
            if ratio >= 1.5:
                signals.append({
                    'type': 'BSL Sweep', 'direction': 'short',
                    'level': round(high_level, 4), 'swept_high': round(curr['h'], 4),
                    'wick_ratio': round(ratio, 2), 'index': i
                })

        # SSL Sweep: 跌破前低后反弹
        if curr['l'] < low_level and curr['c'] > low_level:
            wick_bot = min(curr['c'], curr['o']) - curr['l']
            ratio = wick_bot / body
            if ratio >= 1.5:
                signals.append({
                    'type': 'SSL Sweep', 'direction': 'long',
                    'level': round(low_level, 4), 'swept_low': round(curr['l'], 4),
                    'wick_ratio': round(ratio, 2), 'index': i
                })
    return signals


# ─── IFVG ───────────────────────────────────────────
def detect_ifvg(klines):
    if len(klines) < 4: return []
    avg_r = sum(abs(k['h']-k['l']) for k in klines[-30:])/30 if len(klines)>=30 else 0
    if avg_r == 0: return []
    s = []
    for i in range(2, len(klines)-2):
        c = klines[i]; n1, n2 = klines[i+1], klines[i+2]; bd = abs(c['c']-c['o'])
        gt = max(n1['h'], n2['h']); gb = min(n1['l'], n2['l'])
        if not (gt > gb and gt-gb > avg_r*0.15): continue
        st = 1 + (1 if bd > (gt-gb)*2 else 0)
        s.append({'type': 'IFVG Bullish' if c['c']>c['o'] else 'IFVG Bearish',
                  'direction': 'long' if c['c']>c['o'] else 'short',
                  'top': gt, 'bottom': gb, 'mid': (gt+gb)/2, 'strength': min(3,st), 'index': i})
    return s


# ─── CHOCH V2 (宽松版) ─────────────────────────────
def detect_choch_v2(klines, lb=15):
    if len(klines) < 8: return {'detected': False}
    seg = klines[-lb:] if len(klines)>lb else klines
    f5, l3 = seg[:5], seg[-3:]
    f5h, f5l = max(k['h'] for k in f5), min(k['l'] for k in f5)
    l3h, l3l = max(k['h'] for k in l3), min(k['l'] for k in l3)
    if f5[-1]['c'] < f5[0]['c'] and l3h > f5h:
        return {'detected': True, 'direction': 'long', 'method': 'trend_rev', 'level': f5h}
    if f5[-1]['c'] > f5[0]['c'] and l3l < f5l:
        return {'detected': True, 'direction': 'short', 'method': 'trend_rev', 'level': f5l}
    return {'detected': False}


# ─── PD Array ─────────────────────────────────────
def detect_pd_array(klines, fvg_list=None, ob_list=None):
    if fvg_list is None: fvg_list = detect_fvg(klines)
    if ob_list is None: ob_list = detect_order_blocks(klines)
    arr = []
    for o in ob_list:
        if o['index'] > len(klines)-25:
            arr.append({'type':'OB','dir':o['direction'],'top':o['top'],'bottom':o['bottom'],'priority':1})
    for f in fvg_list:
        if f['index'] > len(klines)-25:
            arr.append({'type':'FVG','dir':f['direction'],'top':f['top'],'bottom':f['bottom'],'strength':f['strength'],'priority':2})
    seg = klines[-30:]; sh = max(k['h'] for k in seg); sl = min(k['l'] for k in seg); r = sh-sl
    if r > 0:
        arr.append({'type':'Discount','dir':'long','top':round(sl+r*0.618,2),'bottom':round(sl+r*0.79,2),'priority':3})
        arr.append({'type':'Premium','dir':'short','top':round(sh-r*0.382,2),'bottom':round(sh-r*0.618,2),'priority':3})
    arr.sort(key=lambda x: x.get('priority',99))
    return arr


# ─── FVG Stack ────────────────────────────────────
def detect_fvg_stack(klines, fvg_list=None):
    if fvg_list is None: fvg_list = detect_fvg(klines)
    if len(fvg_list) < 2: return []
    stacks = []
    for i in range(len(fvg_list)):
        for j in range(i+1, len(fvg_list)):
            f1, f2 = fvg_list[i], fvg_list[j]
            if abs(f1['index']-f2['index'])<=5 and f1['top']>=f2['bottom'] and f2['top']>=f1['bottom']:
                stacks.append({'top': max(f1['top'],f2['top']), 'bottom': min(f1['bottom'],f2['bottom']),
                               'dir': f1['direction'], 'strength': f1['strength']+f2['strength'], 'count': 2})
    merged = []
    for s in stacks:
        if not any(abs(s['top']-m['top'])<0.5 and s['dir']==m['dir'] for m in merged): merged.append(s)
    return merged


# ─── Equal HL ─────────────────────────────────────
def detect_equal_hl(klines, tol=0.02):
    if len(klines) < 15: return []
    seg = klines[-30:] if len(klines)>30 else klines
    ph, pl = [], []
    for i in range(2, len(seg)-2):
        if seg[i]['h'] == max(seg[j]['h'] for j in range(i-2,i+3) if 0<=j<len(seg)): ph.append(seg[i]['h'])
        if seg[i]['l'] == min(seg[j]['l'] for j in range(i-2,i+3) if 0<=j<len(seg)): pl.append(seg[i]['l'])
    r = []
    for i in range(len(ph)):
        for j in range(i+1, len(ph)):
            if abs(ph[i]-ph[j])/ph[i] < tol: r.append({'type':'EQ High','dir':'short','level':max(ph[i],ph[j]),'strength':2})
    for i in range(len(pl)):
        for j in range(i+1, len(pl)):
            if abs(pl[i]-pl[j])/pl[i] < tol: r.append({'type':'EQ Low','dir':'long','level':min(pl[i],pl[j]),'strength':2})
    return r


# ─── Volume Spread ────────────────────────────────
def detect_volume_spread(klines):
    if len(klines) < 20: return {}
    seg = klines[-20:]
    rv = sum(k['v'] for k in seg[-5:])/5; pv = sum(k['v'] for k in seg[-10:-5])/5
    vr = rv/pv if pv > 0 else 1; rh = max(k['h'] for k in seg[-5:]); rl = min(k['l'] for k in seg[-5:])
    ph = max(k['h'] for k in seg[-10:-5]); pl = min(k['l'] for k in seg[-10:-5])
    r = {'vol_ratio': round(vr,2), 'divergence': False, 'confirmation': False}
    if rh > ph and vr < 0.7: r['divergence']=True; r['type']='bearish_div'; r['strength']=2 if vr<0.5 else 1
    if rl < pl and vr < 0.7: r['divergence']=True; r['type']='bullish_div'; r['strength']=2 if vr<0.5 else 1
    if vr > 1.5 and (rh > ph or rl < pl): r['confirmation']=True; r['strength']=2 if vr>2.0 else 1
    return r


# ─── Killzone ─────────────────────────────────────
def detect_killzone():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc); et = now - timedelta(hours=4)
    h = et.hour; zones = []
    if 20 <= h or h < 1: zones.append('Asian')
    if 2 <= h < 5: zones.append('London')
    if 7 <= h < 10 or (h == 10 and et.minute < 30): zones.append('NY_AM')
    if h == 10: zones.append('SilverBullet')
    if 13 <= h < 16: zones.append('NY_Close')
    return {'in_killzone': len(zones)>0, 'primary_zone': zones[-1] if zones else None,
            'is_weekend': now.weekday()>=5, 'et_time': et.strftime('%H:%M')}
def detect_market_structure(klines, lookback=15):
    pivot_highs, pivot_lows = find_pivots(klines[-lookback:], left=2, right=2)

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return {'trend': 'unknown', 'direction': None, 'bos': False, 'choch': False}

    h_vals = [h for _, h in pivot_highs[-3:]]
    l_vals = [l for _, l in pivot_lows[-3:]]

    trend = 'unknown'
    direction = None
    if len(h_vals) >= 3 and len(l_vals) >= 3:
        if h_vals[-1] > h_vals[-2] and l_vals[-1] > l_vals[-2]:
            trend = 'uptrend'; direction = 'long'
        elif h_vals[-1] < h_vals[-2] and l_vals[-1] < l_vals[-2]:
            trend = 'downtrend'; direction = 'short'

    current = klines[-1]
    bos = False
    if trend == 'uptrend' and len(h_vals) >= 2:
        bos = current['h'] > h_vals[-2] 
    elif trend == 'downtrend' and len(l_vals) >= 2:
        bos = current['l'] < l_vals[-2]

    choch = False; choch_type = None
    if len(l_vals) >= 3 and l_vals[-1] < l_vals[-2] < l_vals[-3] and current['c'] > h_vals[-1] if h_vals else False:
        choch = True; choch_type = 'Bullish CHOCH'; direction = 'long'
    elif len(h_vals) >= 3 and h_vals[-1] > h_vals[-2] > h_vals[-3] and current['c'] < l_vals[-1] if l_vals else False:
        choch = True; choch_type = 'Bearish CHOCH'; direction = 'short'

    return {
        'trend': trend, 'direction': direction,
        'bos': bos, 'choch': choch, 'choch_type': choch_type,
        'pivot_highs': [round(h, 4) for _, h in pivot_highs[-5:]],
        'pivot_lows': [round(l, 4) for _, l in pivot_lows[-5:]]
    }


# ─── Order Block 检测 ──────────────────────────────────
def detect_order_blocks(klines):
    signals = []
    if len(klines) < 10:
        return signals

    avg_body = sum(abs(klines[i]['c'] - klines[i]['o']) for i in range(max(0, len(klines)-30), len(klines))) / min(30, len(klines))

    for i in range(4, len(klines) - 2):
        seg_before = klines[i-4:i]
        seg_after = klines[i+1:i+3]

        # Bullish OB: 下降中最后一根阴线后价格突破
        max_high = max(k['h'] for k in seg_before)
        if klines[i+1]['c'] > max_high and klines[i]['c'] < klines[i]['o']:
            body = abs(klines[i]['c'] - klines[i]['o'])
            if body > avg_body * 0.5:
                signals.append({
                    'type': 'Bullish OB', 'direction': 'long',
                    'top': round(max(klines[i]['o'], klines[i]['c']), 4),
                    'bottom': round(min(klines[i]['o'], klines[i]['c']), 4),
                    'index': i
                })

        # Bearish OB: 上升中最后一根阳线后价格下跌
        min_low = min(k['l'] for k in seg_before)
        if klines[i+1]['l'] < min_low and klines[i]['c'] > klines[i]['o']:
            body = abs(klines[i]['c'] - klines[i]['o'])
            if body > avg_body * 0.5:
                signals.append({
                    'type': 'Bearish OB', 'direction': 'short',
                    'top': round(max(klines[i]['o'], klines[i]['c']), 4),
                    'bottom': round(min(klines[i]['o'], klines[i]['c']), 4),
                    'index': i
                })
    return signals


# ─── 综合评分 ────────────────────────────────────────────
def score_signal(fvg_list, ob_list, sweep_list, structure, current_price):
    score = 0
    details = {}

    if fvg_list:
        best = max(fvg_list, key=lambda x: x['strength'])
        fvg_pts = 8 + best['strength'] * 5
        score += fvg_pts
        details['fvg'] = f"+{fvg_pts} ({best['type']}, strength={best['strength']})"

    if ob_list:
        ob_pts = min(15, len(ob_list) * 8)
        score += ob_pts
        details['ob'] = f"+{ob_pts} ({len(ob_list)}×OB)"

    if sweep_list:
        sw = sweep_list[-1]
        sw_pts = min(20, int(sw['wick_ratio'] * 8))
        score += sw_pts
        details['sweep'] = f"+{sw_pts} ({sw['type']}, ratio={sw['wick_ratio']})"

    if structure.get('choch'):
        choch_pts = 20
        score += choch_pts
        details['choch'] = f"+{choch_pts} ({structure['choch_type']})"

    if structure.get('trend') in ('uptrend', 'downtrend'):
        trend_pts = 10
        score += trend_pts
        details['trend'] = f"+{trend_pts} ({structure['trend']})"

    return min(100, score), details


# ─── 数据获取 ──────────────────────────────────────────
def fetch_data(market, symbol, interval='daily', limit=200, exchange='binance'):
    api_map = {
        'cn': f"cnstock/stocks?symbol={symbol}&interval={interval}&limit={limit}",
        'hk': f"hksstock/stocks?symbol={symbol}&interval={interval}&limit={limit}",
        'us': f"usstock/stocks?symbol={symbol}&limit={limit}",
        'crypto': f"crypto/klines?exchange={exchange}&symbol={symbol}&interval={interval}&limit={limit}"
    }
    endpoint = api_map.get(market)
    if not endpoint:
        raise ValueError(f"未知市场: {market}")

    url = f"{BASE}/api/v2/{endpoint}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.loads(resp.read())

    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and 'data' in raw:
        return raw['data']
    return raw


def normalize_klines(raw, market):
    """统一K线格式为 {o, h, l, c, v}"""
    bars = []
    if isinstance(raw, dict):
        raw = [raw]
    for k in raw:
        if isinstance(k, dict):
            bars.append({
                'o': float(k.get('open', k.get('o', 0))),
                'h': float(k.get('high', k.get('h', 0))),
                'l': float(k.get('low', k.get('l', 0))),
                'c': float(k.get('close', k.get('c', 0))),
                'v': float(k.get('volume', k.get('vol', k.get('v', 0)))),
                't': k.get('time', k.get('t', ''))
            })
        elif isinstance(k, list) and len(k) >= 5:
            bars.append({'o': float(k[1]), 'h': float(k[2]), 'l': float(k[3]), 'c': float(k[4]), 'v': float(k[5]) if len(k) > 5 else 0, 't': k[0]})
    return bars


# ─── 主扫描逻辑 ────────────────────────────────────────
def scan_symbol(market, symbol, interval='daily', limit=200, exchange='binance'):
    try:
        raw = fetch_data(market, symbol, interval, limit, exchange)
        klines = normalize_klines(raw, market)
        if len(klines) < 30:
            return None

        fvg = detect_fvg(klines)
        ob = detect_order_blocks(klines)
        sweep = detect_liquidity_sweep(klines)
        structure = detect_market_structure(klines)
        current_price = klines[-1]['c']

        score, details = score_signal(fvg, ob, sweep, structure, current_price)

        return {
            'symbol': symbol,
            'price': round(current_price, 4),
            'score': score,
            'details': details,
            'fvg_count': len(fvg),
            'ob_count': len(ob),
            'sweep_count': len(sweep),
            'structure': structure['trend'],
            'has_choch': structure['choch'],
            'choch_type': structure['choch_type'],
            'direction': structure['direction']
        }
    except Exception as e:
        return {'symbol': symbol, 'error': str(e)}


def print_report(results, market, interval):
    results = [r for r in results if r and 'error' not in r]
    results.sort(key=lambda x: x['score'], reverse=True)

    print(f"\n{'═'*60}")
    print(f"  SMC 信号扫描报告 | {market.upper()} | {interval}")
    print(f"{'═'*60}")

    if not results:
        print("\n❌ 未检测到有效信号")
        return

    print(f"\n扫描标的数: {len(results)}")
    print(f"有信号: {len([r for r in results if r['score'] >= 40])}")
    print()

    grade_color = {5: '🟢', 4: '🟢', 3: '🟡', 2: '🟠', 1: '🔴'}
    for i, r in enumerate(results[:10]):
        stars = min(5, r['score'] // 20 + 1)
        grade = grade_color.get(stars, '⚪')
        signal_type = ''
        if r['has_choch']:
            signal_type = f" {r['choch_type']}"

        print(f" {i+1}. {grade} {r['symbol']} 评分 {r['score']}/100 {'⭐'*stars}")
        print(f"    价格: {r['price']} | 趋势: {r['structure']}{signal_type}")
        print(f"    FVG: {r['fvg_count']}个 | OB: {r['ob_count']}个 | Sweep: {r['sweep_count']}个")
        if r['details']:
            detail_str = ' | '.join(r['details'].values())
            print(f"    {detail_str}")
        print()


def main():
    parser = argparse.ArgumentParser(description='SMC 信号扫描器')
    parser.add_argument('--market', choices=['cn', 'hk', 'us', 'crypto'], default='cn')
    parser.add_argument('--symbols', default='000001.SZ,600519.SH')
    parser.add_argument('--interval', default='daily')
    parser.add_argument('--exchange', default='binance')
    parser.add_argument('--limit', type=int, default=200)
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(',')]
    results = []

    for sym in symbols:
        result = scan_symbol(args.market, sym, args.interval, args.limit, args.exchange)
        results.append(result)

    print_report(results, args.market, args.interval)


if __name__ == '__main__':
    main()