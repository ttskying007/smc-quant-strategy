#!/usr/bin/env python3
"""
SMC Engine V6.1 — 高效共振引擎 (Fixed)
=========================================
V6.0问题修复:
  1. detect_fvg_v6 产生大量重复FVG (每个bar产生3个不同窗口的FVG)
  2. 只处理最后25个FVG，但前800个都是早期的，导致miss
  3. 去重不够严格，同方向5根K线内只保留1个
  4. 入口检测逻辑过于复杂

V6.1改进:
  1. 先按时间筛选，只看最近30根K线内的FVG
  2. 多窗口FVG -> 合并为加权得分 (不再生成多个entry)
  3. 简化评分系统
"""
import math, json, time, os, sys, random
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}
KLINE_CACHE = Path.home() / '.hermes' / 'kline_cache'
OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v6'
os.makedirs(OPT_DIR, exist_ok=True)

# =============================================
# 数据获取
# =============================================
def fetch_hubble(url, timeout=20):
    import urllib.request
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
    req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()

def get_klines(symbol, interval='daily', limit=500):
    import json
    url = f"{HUBBLE_BASE}/api/v2/cnstock/stocks?symbol={symbol}&interval={interval}&limit={limit}"
    raw = json.loads(fetch_hubble(url))
    data = raw.get('data', raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        return []
    bars = []
    for k in data:
        if isinstance(k, dict):
            bars.append({
                't': str(k.get('time',k.get('t',''))),
                'o': float(k.get('open',k.get('o',0))),
                'h': float(k.get('high',k.get('h',0))),
                'l': float(k.get('low',k.get('l',0))),
                'c': float(k.get('close',k.get('c',0))),
                'v': float(k.get('volume',k.get('vol',k.get('v',0)))),
            })
        elif isinstance(k, list) and len(k)>=5:
            bars.append({'t':str(k[0]),'o':float(k[1]),'h':float(k[2]),
                         'l':float(k[3]),'c':float(k[4]),
                         'v':float(k[5]) if len(k)>5 else 0})
    if len(bars)>=2 and bars[0]['t'] > bars[1]['t']:
        bars.reverse()
    return bars

def load_cached_bars(symbol, limit=300):
    cache_key = f"{symbol}_daily_{limit}".replace('.','_').replace('-','_')
    cache_path = KLINE_CACHE / f"{cache_key}.json"
    if cache_path.exists() and os.path.getsize(cache_path) > 100:
        try:
            with open(cache_path) as f:
                data = json.load(f)
                # Support both list format and dict-with-keys format
                if isinstance(data, list) and len(data) >= 100:
                    return data
                if isinstance(data, dict) and 'time' in data and len(data['time']) >= 100:
                    # Convert dict format to list of tuples
                    l = []
                    for i in range(len(data['time'])):
                        l.append([data['time'][i], data['open'][i], data['high'][i],
                                  data['low'][i], data['close'][i], data['vol'][i]])
                    return l
        except:
            pass
    return get_klines(symbol, 'daily', limit)

# =============================================
# 工具函数
# =============================================
def calc_atr(klines, period=14):
    if len(klines) < period:
        return abs(klines[-1]['h']-klines[-1]['l']) if klines else 0
    trs = []
    for i in range(-period, 0):
        tr = max(klines[i]['h']-klines[i]['l'],
                 abs(klines[i]['h']-klines[i-1]['c']),
                 abs(klines[i]['l']-klines[i-1]['c']))
        trs.append(tr)
    return sum(trs)/len(trs)

def calc_vol_ratio(bars, idx, lookback=20):
    if idx < lookback:
        return 1.0
    recent_vols = [b['v'] for b in bars[idx-lookback:idx]]
    avg_v = sum(recent_vols) / len(recent_vols) if recent_vols else 1
    current_v = bars[idx]['v'] if idx < len(bars) else avg_v
    return current_v / avg_v if avg_v > 0 else 1.0

def calc_ema(values, period):
    if len(values) < period:
        return sum(values)/len(values)
    k = 2/(period+1)
    ema = values[0]
    for v in values[1:]:
        ema = v*k + ema*(1-k)
    return ema

def calc_rsi(klines, period=14):
    if len(klines) < period+1:
        return 50
    closes = [k['c'] for k in klines]
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i]-closes[i-1]
        if diff > 0: gains.append(diff); losses.append(0)
        else: gains.append(0); losses.append(abs(diff))
    avg_g = sum(gains[-period:])/period
    avg_l = sum(losses[-period:])/period
    if avg_l == 0: return 100
    return 100 - 100/(1+avg_g/avg_l)

def detect_swing_highs(klines, left=2, right=2):
    return [(i, klines[i]['h']) for i in range(left, len(klines)-right)
            if klines[i]['h'] == max(klines[j]['h'] for j in range(i-left, i+right+1))]

def detect_swing_lows(klines, left=2, right=2):
    return [(i, klines[i]['l']) for i in range(left, len(klines)-right)
            if klines[i]['l'] == min(klines[j]['l'] for j in range(i-left, i+right+1))]

# =============================================
# 市场状态
# =============================================
def classify_market_state(bars):
    if len(bars) < 50:
        return 'unknown', 'unknown', 'unknown'
    atr = calc_atr(bars)
    avg_price = sum((bars[i]['h']+bars[i]['l'])/2 for i in range(-20, 0))/20
    atr_pct = atr/avg_price*100 if avg_price > 0 else 0
    
    if atr_pct < 0.8: vol = 'very_low'
    elif atr_pct < 1.5: vol = 'low'
    elif atr_pct < 2.5: vol = 'medium'
    elif atr_pct < 4.0: vol = 'high'
    else: vol = 'very_high'
    
    closes = [k['c'] for k in bars[-30:]]
    x_bar = len(closes)/2
    y_bar = sum(closes)/len(closes)
    num = sum((i-x_bar)*(c-y_bar) for i,c in enumerate(closes))
    dn = sum((i-x_bar)**2 for i in range(len(closes)))
    dd = sum((c-y_bar)**2 for c in closes)
    r2 = (num**2/(dn*dd)) if dn*dd > 0 else 0
    trend = 'strong' if r2 > 0.6 else 'weak' if r2 > 0.3 else 'range'
    
    recent_v = sum(k['v'] for k in bars[-30:])/30
    old_v = sum(k['v'] for k in bars[-60:-30])/30 if len(bars) >= 60 else recent_v
    vr = recent_v/old_v if old_v > 0 else 1.0
    vol_active = 'high' if vr > 1.5 else 'low' if vr < 0.7 else 'normal'
    
    return vol, trend, vol_active

# =============================================
# FVG检测 (V6.1 - 高效)
# =============================================
def detect_fvg_standard_v6(bars, threshold=0.25):
    """标准FVG 3K"""
    if len(bars) < 3:
        return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:])/max(1, min(30, len(bars)))
    if avg_r == 0:
        return []
    results = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        bd = abs(c['c']-c['o'])
        if c['c'] > c['o']:
            top = min(p['h'], n['h'])
            bot = max(p['l'], n['l'])
            if top > bot and (top-bot) > avg_r*threshold:
                str_ = 1
                if bd > (top-bot)*2: str_ += 1
                if (top-bot) > avg_r*0.5: str_ += 1
                results.append({'type':'BullFVG','direction':'long',
                    'top':top,'bottom':bot,'mid':(top+bot)/2,'strength':min(4,str_),
                    'index':i,'width':top-bot})
        elif c['c'] < c['o']:
            top = max(p['h'], n['h'])
            bot = min(p['l'], n['l'])
            if top > bot and (top-bot) > avg_r*threshold:
                str_ = 1
                if bd > (top-bot)*2: str_ += 1
                if (top-bot) > avg_r*0.5: str_ += 1
                results.append({'type':'BearFVG','direction':'short',
                    'top':top,'bottom':bot,'mid':(top+bot)/2,'strength':min(4,str_),
                    'index':i,'width':top-bot})
    return results

def detect_sweep_v6(bars, lookback=12, wick_min=1.5):
    if len(bars) < lookback+3:
        return []
    avg_body = sum(abs(k['c']-k['o']) for k in bars[-30:])/max(1, min(30, len(bars)))
    if avg_body == 0:
        return []
    signals = []
    for i in range(lookback, len(bars)):
        c = bars[i]
        body = abs(c['c']-c['o'])
        if body < avg_body*0.3:
            continue
        seg = bars[i-lookback:i]
        hh = max(k['h'] for k in seg)
        ll = min(k['l'] for k in seg)
        # BSL
        if c['h'] > hh and c['c'] < hh:
            wick_abs = c['h'] - max(c['c'],c['o'])
            wr = wick_abs/body if body > 0 else 999
            vol_r = calc_vol_ratio(bars, i)
            if wr >= wick_min:
                signals.append({'type':'BSLSweep','direction':'short','level':hh,
                    'wick_ratio':round(wr,2),'wick_abs':round(wick_abs,2),
                    'vol_ratio':round(vol_r,2),'index':i,'score_bonus':0.5 if vol_r>1.2 else 0})
        # SSL
        if c['l'] < ll and c['c'] > ll:
            wick_abs = min(c['c'],c['o']) - c['l']
            wr = wick_abs/body if body > 0 else 999
            vol_r = calc_vol_ratio(bars, i)
            if wr >= wick_min:
                signals.append({'type':'SSLSweep','direction':'long','level':ll,
                    'wick_ratio':round(wr,2),'wick_abs':round(wick_abs,2),
                    'vol_ratio':round(vol_r,2),'index':i,'score_bonus':0.5 if vol_r>1.2 else 0})
    return signals

def detect_choch_v6(bars, lookback=30):
    if len(bars) < 20:
        return {'detected':False}
    seg = bars[-lookback:] if len(bars) > lookback else bars
    ph = detect_swing_highs(seg)
    pl = detect_swing_lows(seg)
    result = {'detected':False}
    if len(ph) >= 3 and len(pl) >= 3:
        rpl = [(i,v) for i,v in pl[-5:]]
        rph = [(i,v) for i,v in ph[-5:]]
        if len(rpl) >= 3:
            vals = [v for _,v in rpl[-3:]]
            if vals[0] > vals[1] > vals[2]:
                shs = sorted([v for _,v in ph if rpl[-1][0] < _], reverse=True)
                if shs and seg[-1]['c'] > shs[0]:
                    result = {'detected':True,'direction':'long','break_level':shs[0],'type':'LL+Break'}
        if len(rph) >= 3:
            vals = [v for _,v in rph[-3:]]
            if vals[0] < vals[1] < vals[2]:
                sls = sorted([v for _,v in pl if rph[-1][0] < _])
                if sls and seg[-1]['c'] < sls[0]:
                    result = {'detected':True,'direction':'short','break_level':sls[0],'type':'HH+Break'}
    return result

def detect_ob_v6(bars, fvg_list=None):
    if len(bars) < 10:
        return []
    avg_body = sum(abs(bars[i]['c']-bars[i]['o']) for i in range(max(0,len(bars)-30),len(bars)))/min(30,max(1,len(bars)))
    if avg_body == 0: return []
    signals = []
    for i in range(4, len(bars)-2):
        pre = bars[i-4:i]
        c = bars[i]
        bd = abs(c['c']-c['o'])
        mh = max(k['h'] for k in pre)
        ml = min(k['l'] for k in pre)
        vol_r = calc_vol_ratio(bars, i)
        if bars[i+1]['c'] > mh and c['c'] < c['o'] and bd > avg_body*0.7:
            top = round(max(c['o'],c['c']),4)
            bot = round(min(c['o'],c['c']),4)
            has_fvg = any(f['direction']=='long' and top>f['bottom'] and bot<f['top'] for f in fvg_list) if fvg_list else False
            signals.append({'type':'BullOB','direction':'long','top':top,'bottom':bot,'index':i,
                'overlap_fvg':has_fvg,'vol_confirm':vol_r>1.3,'score_bonus':(1 if has_fvg else 0)+(0.5 if vol_r>1.3 else 0)})
        if bars[i+1]['l'] < ml and c['c'] > c['o'] and bd > avg_body*0.7:
            top = round(max(c['o'],c['c']),4)
            bot = round(min(c['o'],c['c']),4)
            has_fvg = any(f['direction']=='short' and top>f['bottom'] and bot<f['top'] for f in fvg_list) if fvg_list else False
            signals.append({'type':'BearOB','direction':'short','top':top,'bottom':bot,'index':i,
                'overlap_fvg':has_fvg,'vol_confirm':vol_r>1.3,'score_bonus':(1 if has_fvg else 0)+(0.5 if vol_r>1.3 else 0)})
    return signals

def calc_bpr_v6(fvg_list, lookback=20):
    if not fvg_list or len(fvg_list) < 2:
        return []
    recent = [f for f in fvg_list if f['index'] >= max(f['index'] for f in fvg_list) - lookback]
    if len(recent) < 2: return []
    bull = sorted([f for f in recent if f['direction']=='long'], key=lambda x:-x.get('strength',1))[:4]
    bear = sorted([f for f in recent if f['direction']=='short'], key=lambda x:-x.get('strength',1))[:4]
    if not bull or not bear: return []
    merged = []
    for b1 in bull:
        for b2 in bear:
            top = min(b1['top'],b2['top'])
            bot = max(b1['bottom'],b2['bottom'])
            if top > bot:
                merged.append({'top':round(top,4),'bottom':round(bot,4),'mid':round((top+bot)/2,4),
                    'index':max(b1['index'],b2['index']),'width':round(top-bot,4)})
    merged.sort(key=lambda x:-x['width'])
    dedup = []
    for b in merged:
        if not any(abs(b['index']-m['index'])<=3 or (b['top']>m['bottom'] and b['bottom']<m['top']) for m in dedup):
            dedup.append(b)
    return dedup[:3]

# =============================================
# V6.1 核心入口
# =============================================
def get_params_from_state(vol, trend, active):
    """基于市场状态生成优化参数"""
    p = {'fvg_th':0.25,'score_th':2.5,'sl_mult':2.0,'tp_mult':2.5,
         'min_sigs':2,'wick_min':2.0,'score_strict':4.0,'sl_strict':1.5,'tp_strict':3.0,'min_sigs_strict':3}
    if vol in ('very_high','high'):
        p['fvg_th'] = 0.35; p['score_th'] = 3.0; p['sl_mult'] = 2.5; p['score_strict'] = 4.5
    elif vol == 'medium':
        p['fvg_th'] = 0.25; p['sl_mult'] = 2.0
    elif vol == 'low':
        p['fvg_th'] = 0.18; p['score_th'] = 2.0; p['sl_mult'] = 1.5; p['score_strict'] = 3.5
    else:
        p['fvg_th'] = 0.15; p['score_th'] = 1.8; p['sl_mult'] = 1.2; p['score_strict'] = 3.0
    if trend == 'strong':
        p['score_th'] = max(1.5, p['score_th']-0.5); p['tp_mult'] += 0.5
    elif trend == 'range':
        p['score_th'] += 0.3; p['min_sigs'] = 3; p['wick_min'] = 2.5
    if active == 'high':
        p['sl_mult'] = max(1.0, p['sl_mult']-0.3)
    return p

def score_fvg_signal(direction, bars, idx, fvg, sw, ob, choch, bpr):
    score = 1.0 + fvg.get('strength',1)*0.3
    sigs = [f"FVG{fvg.get('strength',1)}"]
    found = {'fvg':True}
    last_idx = len(bars)-1
    age = last_idx-idx
    tw = max(0.4, 1.0-age/35.0)
    
    if sw:
        best = max(sw, key=lambda s: s.get('wick_ratio',0))
        wr = best.get('wick_ratio',0)
        sw_score = min(2.0, 0.5+wr*0.3) + best.get('score_bonus',0)
        score += sw_score; found['sw']=True; sigs.append(f"SW({wr:.1f})")
    if ob:
        bonus = sum(o.get('score_bonus',0) for o in ob)/max(1,len(ob))
        score += 0.8 + bonus; found['ob']=True; sigs.append('OB')
    if choch.get('detected') and choch['direction']==direction:
        score += 1.5; found['ch']=True; sigs.append('CH')
    if bpr:
        score += 0.8; found['bpr']=True; sigs.append('BPR')
    # MS
    recent = bars[max(0,idx-10):idx+1]
    bv = sum(1 for k in recent if k['c'] > k['o'])
    sv = sum(1 for k in recent if k['c'] < k['o'])
    if (direction=='long' and bv>sv) or (direction=='short' and sv>bv):
        score += 0.5; found['ms']=True; sigs.append('MS')
    # vol confirm
    ci = min(idx+1, last_idx)
    if ci < len(bars) and ci > 0:
        vr = calc_vol_ratio(bars, ci)
        if vr > 1.3:
            score += 0.5; found['vol']=True; sigs.append(f"V{vr:.1f}")
    score *= tw
    n_sig = sum(1 for v in found.values() if v)
    return round(score,2), sigs, n_sig

def detect_entries_v61(bars, params=None):
    """
    V6.1 高效入口
    只检查最近40根K线中的FVG
    """
    results = {'bronze':[],'silver':[],'gold':[],'total':[]}
    if len(bars) < 60:
        return results
    
    vol, trend, active = classify_market_state(bars)
    sp = get_params_from_state(vol, trend, active)
    if params:
        sp.update(params)
    
    last_idx = len(bars)-1
    
    # 只看最近40根K线
    look_start = max(0, last_idx - 50)
    bars_seg = bars[look_start:last_idx+1]
    
    # FVG
    fvg_all = detect_fvg_standard_v6(bars, sp.get('fvg_th',0.25))
    
    # 只关注最后40根的FVG
    fvg_recent = [f for f in fvg_all if f['index'] >= last_idx - 40]
    
    if not fvg_recent:
        return results
    
    # Sweep
    sweep_list = detect_sweep_v6(bars, 12, sp.get('wick_min',2.0))
    sweep_recent = [s for s in sweep_list if s['index'] >= last_idx - 45]
    
    # OB
    ob_list = detect_ob_v6(bars, fvg_all)
    ob_recent = [o for o in ob_list if o['index'] >= last_idx - 45]
    
    # CHOCH
    choch = detect_choch_v6(bars)
    
    # BPR
    bpr_list = calc_bpr_v6(fvg_all, 20)
    bpr_recent = [b for b in bpr_list if b['index'] >= last_idx - 50]
    
    sc_th = sp.get('score_th', 2.5)
    sc_silver = max(3.0, sc_th + 0.5)
    sc_gold = sp.get('score_strict', 4.0)
    sl_m = sp.get('sl_mult', 2.0)
    tp_m = sp.get('tp_mult', 2.5)
    sl_s = sp.get('sl_strict', 1.5)
    tp_s = sp.get('tp_strict', 3.0)
    min_s = sp.get('min_sigs', 2)
    min_s3 = sp.get('min_sigs_strict', 3)
    
    for fvg in fvg_recent:
        i = fvg.get('index', 0)
        if i < 3 or i >= last_idx-2:
            continue
        
        direction = fvg['direction']
        
        sw = [s for s in sweep_recent if s['direction']==direction and -3 <= i-s.get('index',0) <= 20]
        ob = [o for o in ob_recent if o['direction']==direction and abs(o.get('index',0)-i) <= 10]
        bpr = [b for b in bpr_recent if abs(b.get('index',0)-i) <= 12]
        
        score, sigs, n_sig = score_fvg_signal(direction, bars, i, fvg, sw, ob, choch, bpr)
        
        if score < 1.5:
            continue
        
        atr = calc_atr(bars[:i+5])
        ep = fvg['mid']
        
        # Bronze (所有>=score_th)
        if score >= sc_th and n_sig >= min_s:
            entry = {'idx':min(i+1,last_idx-1),'dir':'L' if direction=='long' else 'S',
                     'fvg_idx':i,'sigs':sigs,'sc':round(score,2),'n_sig':n_sig}
            if direction == 'long':
                entry['ep']=round(ep,4); entry['sl']=round(ep-atr*max(0.5,sl_m),4); entry['tp']=round(ep+atr*max(1.0,tp_m),4)
            else:
                entry['ep']=round(ep,4); entry['sl']=round(ep+atr*max(0.5,sl_m),4); entry['tp']=round(ep-atr*max(1.0,tp_m),4)
            results['bronze'].append(entry)
            results['total'].append({**entry,'level':'bronze'})
        
        # Silver
        if score >= sc_silver and n_sig >= min(min_s+1, min_s+1):
            entry = {'idx':min(i+1,last_idx-1),'dir':'L' if direction=='long' else 'S',
                     'fvg_idx':i,'sigs':sigs,'sc':round(score,2),'n_sig':n_sig}
            sl_mid = (sl_m+sl_s)/2/0.8; tp_mid = (tp_m+tp_s)/2/0.8
            if direction == 'long':
                entry['ep']=round(ep,4); entry['sl']=round(ep-atr*max(0.5,sl_mid),4); entry['tp']=round(ep+atr*max(1.0,tp_mid),4)
            else:
                entry['ep']=round(ep,4); entry['sl']=round(ep+atr*max(0.5,sl_mid),4); entry['tp']=round(ep-atr*max(1.0,tp_mid),4)
            results['silver'].append(entry)
            if not any(abs(e['idx']-entry['idx'])<=3 for e in results['total']):
                results['total'].append({**entry,'level':'silver'})
        
        # Gold
        if score >= sc_gold and n_sig >= min_s3:
            entry = {'idx':min(i+1,last_idx-1),'dir':'L' if direction=='long' else 'S',
                     'fvg_idx':i,'sigs':sigs,'sc':round(score,2),'n_sig':n_sig}
            if direction == 'long':
                entry['ep']=round(ep,4); entry['sl']=round(ep-atr*max(0.5,sl_s),4); entry['tp']=round(ep+atr*max(1.5,tp_s),4)
            else:
                entry['ep']=round(ep,4); entry['sl']=round(ep+atr*max(0.5,sl_s),4); entry['tp']=round(ep-atr*max(1.5,tp_s),4)
            results['gold'].append(entry)
            if not any(abs(e['idx']-entry['idx'])<=3 for e in results['total']):
                results['total'].append({**entry,'level':'gold'})
    
    # 去重: 5根K线内同方向保留score最高的
    for ch in results:
        e = results[ch]
        if not e: continue
        e.sort(key=lambda x: -x.get('sc',0))
        dedup = []
        for x in e:
            if not any(abs(x['idx']-y['idx'])<=5 and x['dir']==y['dir'] for y in dedup):
                dedup.append(x)
        results[ch] = dedup
    
    return results

# =============================================
# 模拟/回测
# =============================================
def simulate_entry(e, bars):
    ei = e.get('idx',0)
    if ei >= len(bars): return None
    d = e.get('dir','L')
    ep = e.get('ep',0)
    sl = e.get('sl',0)
    tp = e.get('tp',0)
    if not all([ep, sl, tp]): return None
    for j in range(ei, len(bars)):
        b = bars[j]
        if d == 'L':
            if b['l'] <= sl: return {'pnl':(sl-ep)/ep,'reason':'sl','bars':j-ei+1,'ret':(sl-ep)/ep*100}
            if b['h'] >= tp: return {'pnl':(tp-ep)/ep,'reason':'tp','bars':j-ei+1,'ret':(tp-ep)/ep*100}
        else:
            if b['h'] >= sl: return {'pnl':(ep-sl)/ep,'reason':'sl','bars':j-ei+1,'ret':(ep-sl)/ep*100}
            if b['l'] <= tp: return {'pnl':(ep-tp)/ep,'reason':'tp','bars':j-ei+1,'ret':(ep-tp)/ep*100}
    last = bars[-1]['c']
    pnl = (last-ep)/ep if d=='L' else (ep-last)/ep
    return {'pnl':pnl,'reason':'eod','bars':len(bars)-ei+1,'ret':pnl*100}

def backtest_v61(bars, mode='total', params=None):
    if not isinstance(bars,list) or len(bars) < 60: return []
    entries = detect_entries_v61(bars, params)
    result = entries.get(mode, [])
    if not result: return []
    trades = []
    for e in result:
        t = simulate_entry(e, bars)
        if t: trades.append(t)
    return trades

def evaluate_v6(trades, name='V6'):
    n = len(trades)
    if n == 0: return {'n':0,'wr':0.0,'pf':0.0,'sr':0.0,'ret':0.0}
    wins = [t for t in trades if t['pnl']>0]
    losses = [t for t in trades if t['pnl']<=0]
    wr = len(wins)/n*100
    ret = sum(t['pnl'] for t in trades)*100
    avg = sum(t['pnl'] for t in trades)/n
    std = math.sqrt(sum((p['pnl']-avg)**2 for p in trades)/n) if n>1 else 0.001
    sr = (avg/std)*math.sqrt(252) if std>0 else 0
    win_sum = sum(t['pnl'] for t in wins) if wins else 0
    loss_sum = abs(sum(t['pnl'] for t in losses)) if losses else 0
    pf = (win_sum/loss_sum) if loss_sum>0 else (999 if win_sum>0 else 0)
    print(f"  {name:>15}: {n:>4d}t WR={wr:>5.1f}% PF={pf:>7.2f} SR={sr:>5.2f} Ret={ret:>+7.2f}%")
    return {'n':n,'wr':round(wr,1),'pf':round(pf,3),'sr':round(sr,3),'ret':round(ret,2)}

def compute_score_v61(trades):
    n = len(trades)
    if n < 3: return 0
    wins = [t for t in trades if t['pnl']>0]
    losses = [t for t in trades if t['pnl']<=0]
    wr = len(wins)/n*100
    win_sum = sum(t['pnl'] for t in wins) if wins else 0
    loss_sum = abs(sum(t['pnl'] for t in losses)) if losses else 0
    pf = (win_sum/loss_sum) if loss_sum>0 else 999
    avg_r = sum(t['pnl'] for t in trades)/n
    std = math.sqrt(sum((t['pnl']-avg_r)**2 for t in trades)/n) if n>1 else 0.001
    sr = (avg_r/std)*math.sqrt(252) if std>0 else 0
    n_pen = min(1.0, n/30) if n<30 else 1.0
    pf_cap = min(5.0, pf)
    sc = (wr/100)*50 + sr*20 + pf_cap*30
    sc *= n_pen
    if pf<1.0: sc*=0.2
    if wr<40: sc*=0.3
    return round(sc,1)

# =============================================
# 全自动迭代系统
# =============================================

def genetic_search(symbols, base_params, generations=30, pop_size=15, mutation_rate=0.3):
    """
    遗传算法参数搜索
    param_space: {(key, (low, high, type))} type: linear/log/choice
    """
    param_space = {
        'fvg_th': (0.10, 0.45, 'linear'),
        'score_th': (1.5, 4.5, 'linear'),
        'sl_mult': (1.0, 3.5, 'linear'),
        'tp_mult': (1.5, 4.5, 'linear'),
        'min_sigs': (2, 4, 'int'),
        'wick_min': (1.0, 3.5, 'linear'),
        'sl_strict': (0.8, 2.5, 'linear'),
        'tp_strict': (2.0, 5.0, 'linear'),
        'score_gold': (3.0, 5.5, 'linear'),
    }
    
    # Load bars for all symbols
    print(f"\nLoading bars for {len(symbols)} symbols...")
    all_bars = {}
    loaded = 0
    for s in symbols:
        bars = load_cached_bars(s, 300)
        if bars and len(bars) >= 100:
            all_bars[s] = bars
            loaded += 1
    print(f"Loaded {loaded}/{len(symbols)}")
    
    if not all_bars:
        print("ERROR: No bars loaded!")
        return None
    
    def random_params():
        p = {k: v for k, v in base_params.items()}
        for k, (lo, hi, tp) in param_space.items():
            if tp == 'int':
                p[k] = random.randint(int(lo), int(hi))
            else:
                p[k] = round(random.uniform(lo, hi), 2)
        return p
    
    def crossover(p1, p2):
        child = {}
        for k in p1:
            if k == 'min_sigs':
                child[k] = random.choice([p1[k], p2[k]])
            else:
                blend = round(p1[k]*random.uniform(0.3,0.7)+p2[k]*(1-random.uniform(0.3,0.7)), 2)
                child[k] = blend
        return child
    
    def mutate(p):
        p = {**p}
        for k, (lo, hi, tp) in param_space.items():
            if random.random() < mutation_rate:
                if tp == 'int':
                    p[k] = random.randint(int(lo), int(hi))
                else:
                    p[k] = round(random.uniform(lo, hi), 2)
        return p
    
    def clamp(p):
        for k, (lo, hi, tp) in param_space.items():
            if k in p:
                p[k] = max(lo, min(hi, p[k]))
                if tp == 'int':
                    p[k] = int(round(p[k]))
        return p
    
    def fitness(params):
        total_trades = []
        total_score = 0
        n_stocks = 0
        for code, bars in all_bars.items():
            # 80/20 split for OOS validation
            split = int(len(bars) * 0.8)
            if split < 60:
                continue
            is_bars = bars[:split]  # In-sample
            
            try:
                entries = detect_entries_v61(is_bars, params)
                all_e = entries.get('total', [])
                trades = []
                for e in all_e:
                    t = simulate_entry(e, is_bars)
                    if t: trades.append(t)
                if trades:
                    sc = compute_score_v61(trades)
                    total_score += sc
                    total_trades.extend(trades)
                    n_stocks += 1
            except:
                continue
        
        if not total_trades:
            return 0, n_stocks, 0, 0
        
        score = compute_score_v61(total_trades)
        wr = len([t for t in total_trades if t['pnl']>0])/len(total_trades)*100 if total_trades else 0
        return score, n_stocks, len(total_trades), wr
    
    # Initialize population
    print(f"\n{'='*70}")
    print(f"  GA Search: {generations} gen x {pop_size} pop")
    print(f"{'='*70}")
    
    population = [clamp(random_params()) for _ in range(pop_size)]
    best_overall = {'params': None, 'score': 0, 'n': 0, 'wr': 0, 'gen': 0}
    
    start_time = time.time()
    
    for gen in range(generations):
        gen_start = time.time()
        
        # Evaluate
        scored = []
        for idx, p in enumerate(population):
            sc, ns, nt, wr = fitness(p)
            scored.append((sc, p, ns, nt, wr))
        
        scored.sort(key=lambda x: -x[0])
        
        best_sc, best_p, best_ns, best_nt, best_wr = scored[0]
        avg_sc = sum(s[0] for s in scored[:max(1,len(scored)//2)]) / max(1, len(scored)//2)
        
        if best_sc > best_overall['score']:
            best_overall = {'params': best_p, 'score': best_sc, 'n': best_nt,
                           'wr': best_wr, 'gen': gen+1}
        
        gen_time = time.time() - gen_start
        
        print(f"  Gen {gen+1:>2d}/{generations}: best={best_sc:.1f} WR={best_wr:.1f}% "
              f"n={best_nt} avg={avg_sc:.1f} {gen_time:.0f}s")
        
        if gen == generations - 1:
            break
        
        # Selection
        top = scored[:max(3, pop_size//3)]
        
        # Reproduction: crossover top + random
        new_pop = [t[1] for t in top]
        
        while len(new_pop) < pop_size:
            if len(top) >= 2:
                p1, p2 = random.choices(top, k=2)
                child = crossover(p1[1], p2[1])
            else:
                child = random_params()
            child = mutate(child)
            child = clamp(child)
            new_pop.append(child)
        
        population = new_pop
    
    total_time = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"  GA Complete! Time: {total_time:.0f}s")
    print(f"  Best score: {best_overall['score']:.1f}")
    print(f"  Best WR: {best_overall['wr']:.1f}%")
    print(f"  Best trades: {best_overall['n']}")
    print(f"  Best gen: {best_overall['gen']}")
    print(f"  Best params: {json.dumps(best_overall['params'], indent=2)}")
    
    # OOS validation
    print(f"\n{'='*70}")
    print(f"  OOS Validation")
    print(f"{'='*70}")
    is_trades = []
    oos_trades = []
    for code, bars in all_bars.items():
        split = int(len(bars) * 0.8)
        if split < 60: continue
        is_b = bars[:split]
        oos_b = bars[split:]
        
        e_is = detect_entries_v61(is_b, best_overall['params']).get('total',[])
        e_oos = detect_entries_v61(oos_b, best_overall['params']).get('total',[])
        
        for e in e_is:
            t = simulate_entry(e, is_b)
            if t: is_trades.append(t)
        for e in e_oos:
            t = simulate_entry(e, oos_b)
            if t: oos_trades.append(t)
    
    print(f"  IS:")
    evaluate_v6(is_trades, 'V6.IS')
    print(f"  OOS:")
    evaluate_v6(oos_trades, 'V6.OOS')
    
    # Save best params
    param_file = OPT_DIR / 'best_params_v61.json'
    with open(param_file, 'w') as f:
        json.dump({**best_overall['params'], '_score': best_overall['score'],
                   '_wr': best_overall['wr'], '_n': best_overall['n']}, f, indent=2)
    print(f"\n  Saved to: {param_file}")
    
    return best_overall['params']

# =============================================
# 主入口
# =============================================
if __name__ == '__main__':
    print("="*70)
    print("  SMC Engine V6.1 — 多策略共振")
    print("="*70)
    
    test_stocks = ['600519.SH','000001.SZ','000858.SZ','600036.SH',
                   '002594.SZ','300750.SZ','601318.SH','600887.SH',
                   '000002.SZ','600585.SH','688981.SH','002415.SZ',
                   '603259.SH','000333.SZ','002475.SZ','300124.SZ',
                   '002230.SZ','600690.SH']
    
    total_trades = {'bronze':[],'silver':[],'gold':[],'total':[]}
    
    print(f"\n--- V6.1 Test ({len(test_stocks)} stocks) ---")
    start = time.time()
    
    for code in test_stocks:
        try:
            bars = get_klines(code, 'daily', 300)
            if len(bars) < 100:
                continue
            
            vol, trend, vol_act = classify_market_state(bars)
            entries = detect_entries_v61(bars)
            
            for mode in ['bronze','silver','gold','total']:
                et = entries.get(mode, [])
                if et:
                    trades = []
                    for e in et:
                        t = simulate_entry(e, bars)
                        if t: trades.append(t)
                    if trades:
                        total_trades[mode].extend(trades)
            
            has_signals = any(len(entries.get(m,[]))>0 for m in ['bronze','silver','gold'])
            if has_signals:
                all_sigs = sum(len(entries.get(m,[])) for m in ['bronze','silver','gold','total'])
                # Dedup count
                unique_total = len(entries.get('total',[]))
                print(f"  {code}: {vol}/{trend}/{vol_act} -> {unique_total} sigs")
        except Exception as e:
            print(f"  {code}: ERROR {e}")
    
    elapsed = time.time()-start
    print(f"\n{'='*70}")
    print(f"  V6.1 综合 ({elapsed:.0f}s)")
    print(f"{'='*70}")
    for mode in ['bronze','silver','gold','total']:
        tt = total_trades.get(mode,[])
        if tt:
            evaluate_v6(tt, f'V6.{mode}')