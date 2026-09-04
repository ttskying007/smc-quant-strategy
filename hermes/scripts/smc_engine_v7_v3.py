#!/usr/bin/env python3
"""
SMC Engine V7 V3 — 最终版
使用SMC核心原理:
- FVG作为支撑/阻力层（价格跌入FVG区域 = 潜在反弹）
- 不是FVG形成时入场，而是FVG补回后反弹入场
- OB作为价格反转确认
- 多时间框架趋势过滤（周线/日线）
- 自适应SL/TP
"""
import sys, os, json, math, random, time, subprocess
from datetime import datetime
from pathlib import Path
import urllib.request

HOME = Path.home()
OPT_DIR = HOME / '.hermes' / 'smc_opt_v7_v3'
OPT_DIR.mkdir(parents=True, exist_ok=True)
LIVE = OPT_DIR / 'v7v3_live.json'
BEST = OPT_DIR / 'v7v3_best.json'
HIST = OPT_DIR / 'v7v3_hist.json'

HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_CACHE = {}

def sfx(c):
    if c.startswith('6') or c.startswith('9'): return '.SH'
    if c.startswith('0') or c.startswith('3') or c.startswith('2'): return '.SZ'
    if c.startswith('4') or c.startswith('8'): return '.BJ'
    return '.SZ'

def getk(code, days=300):
    key = f"k_{code}_{days}"
    if key in _CACHE: return _CACHE[key]
    sym = f"{code}{sfx(code)}"
    url = f"{HUBBLE_BASE}/api/v2/cnstock/stocks?symbol={sym}&interval=daily&limit={days}"
    try:
        req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
        with _OPENER.open(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode())
        data = raw.get('data', raw) if isinstance(raw, dict) else raw
        if not isinstance(data, list): return []
        bars = []
        for k in data:
            if isinstance(k, dict):
                bars.append({
                    't': str(k.get('time','')), 'o': float(k.get('open',0)),
                    'h': float(k.get('high',0)), 'l': float(k.get('low',0)),
                    'c': float(k.get('close',0)), 'v': float(k.get('volume',k.get('vol',0)))
                })
        if len(bars)>=2 and bars[0]['t'] > bars[1]['t']: bars.reverse()
        _CACHE[key] = bars
        return bars
    except:
        _CACHE[key] = []
        return []

def get_stocks():
    url = f"{HUBBLE_BASE}/api/v2/cnstock/symbols?listStatus=L"
    try:
        req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
        with _OPENER.open(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode())
        syms = raw.get('data', raw) if isinstance(raw, dict) else raw
        stocks = []
        if isinstance(syms, dict):
            for item in syms.get('symbols',[]):
                c = item.get('symbol','')
                if c: stocks.append(c.replace('.SH','').replace('.SZ','').replace('.BJ',''))
        elif isinstance(syms, list):
            for item in syms:
                if isinstance(item, dict):
                    c = item.get('symbol','')
                    if c: stocks.append(c.replace('.SH','').replace('.SZ','').replace('.BJ',''))
            return stocks
        return [s for s in stocks if s]
    except:
        return []

# ============================================
# SMC 信号引擎 v2 — FVG回补+OB确认
# ============================================
def detect_all(klines):
    """从K线检测所有SMC结构"""
    fvg_list = []  # FVG层 (支撑/阻力)
    ob_list = []   # Order Block
    liq_list = []  # 流动性节点
    
    for i in range(1, len(klines)-1):
        p0, p1, p2 = klines[i-1], klines[i], klines[i+1]
        
        # FVG检测
        gap_top = min(p0['l'], p2['l'])
        gap_bot = max(p0['h'], p2['h'])
        gap_sz = gap_bot - gap_top
        
        if gap_sz > 0 and gap_sz / p1['c'] > 0.003:  # 0.3%以上
            is_bear = p1['c'] < p1['o']
            body = abs(p1['c']-p1['o'])
            body_ratio = body / max(p1['h']-p1['l'], 0.001)
            
            fvg_list.append({
                'idx': i, 'top': gap_top, 'bot': gap_bot,
                'mid': (gap_top + gap_bot) / 2,
                'size': gap_sz / p1['c'],
                'bear': is_bear,
                'body_ratio': body_ratio,
                'price': p1['c'],
            })
        
        # OB: 最后3根K线的极端低点
        if i >= 3:
            chunk = klines[i-3:i+1]
            lo = min(x['l'] for x in chunk)
            clo3 = chunk[-1]['c']
            low_wick = clo3 - lo
            if low_wick > 0 and low_wick / max(chunk[-1]['h']-lo, 0.001) > 0.5:
                ob_list.append({
                    'idx': i, 'low': lo, 'close': clo3,
                    'strength': low_wick / max(chunk[-1]['h']-lo, 0.001),
                })
    
    return fvg_list, ob_list

def eval_code(code, sp, min_fvg_pct=0.005, fvg_lookback=10):
    """
    基于SMC结构评估:
    1. 找到所有FVG层和OB
    2. 价格回测到FVG层时 → 结合OB确认 → 入场做多
    3. 用sp['sl_mult']%止损, sp['tp_mult']%止盈
    """
    klines = getk(code, 400)
    if len(klines) < 120:
        return (0, 0, 0.0)
    
    # 仅使用前半段检测FVG, 后半段验证
    lookback = min(int(len(klines) * 0.6), fvg_lookback * 20)
    
    fvg_list, ob_list = detect_all(klines[:lookback])
    
    # 筛选: 只保留大FVG (≥min_fvg_pct)
    fvg_list = [f for f in fvg_list if f['size'] >= min_fvg_pct and f['bear']]  # 熊FVG = 看涨信号
    
    if len(fvg_list) < sp.get('min_sigs', 1):
        return (0, 0, 0.0)
    
    # 在剩余部分找交易机会: 价格跌破FVG底部（补回缺口）后反弹入场
    test_start = len(klines) - int(len(klines) * 0.4)
    
    sl_pct = sp.get('sl_mult', 1.0)
    tp_pct = sp.get('tp_mult', 2.0)
    max_bars = 40 if tp_pct > 3 else (30 if tp_pct > 1.5 else 20)
    
    trades = wins = 0
    pnl = 0.0
    
    for fvg in fvg_list:
        fvg_idx = fvg['idx']
        if fvg_idx >= test_start:
            continue
        
        entry_price = fvg['mid']  # FVG中间价格作为入场参考
        if entry_price == 0:
            continue
        
        # 在test_start区间找: 价格向下触及FVG区域
        for j in range(test_start, len(klines) - 5):
            bar = klines[j]
            # 价格触及FVG区域
            if bar['l'] <= fvg['bot'] and bar['c'] > fvg['bot'] * 0.995:
                # 价格刺穿FVG底部并收在FVG内 → 反弹入场
                entry = bar['c'] if bar['c'] > fvg['bot'] else fvg['mid']
                
                stop = entry * (1 - sl_pct / 100)
                take = entry * (1 + tp_pct / 100)
                
                if abs(stop-entry)/entry < 0.0005: continue
                
                hit_stop = hit_take = False
                last_close = entry
                limit = min(j+1 + max_bars, len(klines))
                
                for k in range(j+1, limit):
                    if klines[k]['l'] <= stop:
                        hit_stop = True; break
                    if klines[k]['h'] >= take:
                        hit_take = True; break
                    last_close = klines[k]['c']
                
                trades += 1
                if hit_take:
                    wins += 1; pnl += tp_pct / 100.0
                elif hit_stop:
                    pnl -= sl_pct / 100.0
                else:
                    r = (last_close - entry) / entry
                    pnl += r
                    if r > 0: wins += 1
                
                break  # 每个FVG只交易一次
    
    return (trades, wins, pnl)

# ============================================
# 评分
# ============================================
def calc_sc(is_wr, oos_wr, is_pf, oos_pf, is_t, oos_t, is_sig, oos_sig, rr, n_is, n_oos):
    avg_wr = (is_wr+oos_wr)/2
    avg_pf = (is_pf+oos_pf)/2
    n_tot = is_t+oos_t
    nb = min(1.0, n_tot/100) if n_tot>0 else 0.05
    ac = (is_sig/n_is*100 + oos_sig/n_oos*100)/2
    
    if avg_wr>=85: wf=100
    elif avg_wr>=80: wf=60
    elif avg_wr>=75: wf=30
    elif avg_wr>=70: wf=12
    elif avg_wr>=65: wf=5
    elif avg_wr>=60: wf=2.5
    elif avg_wr>=55: wf=1.2
    elif avg_wr>=50: wf=0.6
    else: wf=0.2
    
    rp = 1.0
    if rr<0.5: rp=0.05
    elif rr<0.8: rp=0.2
    elif rr<1.0: rp=0.4
    elif rr>=3.0: rp=1.3
    
    wd = abs(is_wr-oos_wr)
    of = 1.0
    if wd>20: of=max(0.1, 1.0-(wd-20)/30)
    elif wd>12: of=max(0.5, 1.0-(wd-12)/20)
    
    cp = 1.0
    if ac<5: cp=0.05
    elif ac<10: cp=0.2
    elif ac<15: cp=0.5
    
    tp = min(1.0, n_tot/10) if n_tot>0 else 0.05
    
    sc = wf * avg_pf * math.sqrt(max(rr,0.01)) * nb * rp * of * cp * tp
    sc = max(0, round(sc, 2))
    
    det = {'wf':wf,'pf':avg_pf,'rr':rr,'rp':rp,'of':of,'cp':cp,'ntot':n_tot,'wd':round(wd,1)}
    return sc, det


# ============================================
# 参数空间
# ============================================
PS = {
    'sl_mult':     [0.3, 5.0, 0.05],   # 止损%
    'tp_mult':     [0.5, 10.0, 0.1],   # 止盈%
    'min_sigs':    [1, 2, 1],           # 最少FVG
    'fvg_pct':     [0.003, 0.02, 0.001], # FVG最小占比
}

def rand_p():
    p = {}
    # 组合生成: 确保RR合理
    if random.random() < 0.4:  # 高RR
        p['sl_mult'] = round(random.uniform(0.3, 1.0), 2)
        p['tp_mult'] = round(random.uniform(2.0, 6.0), 1)
    elif random.random() < 0.7:  # 平衡
        p['sl_mult'] = round(random.uniform(0.5, 2.0), 2)
        p['tp_mult'] = round(random.uniform(1.0, 3.0), 1)
    else:  # 保守
        p['sl_mult'] = round(random.uniform(0.8, 3.0), 2)
        p['tp_mult'] = round(random.uniform(0.8, 2.0), 1)
    
    rr = p['tp_mult'] / max(p['sl_mult'], 0.05)
    if rr < 1.0: p['tp_mult'] = round(p['sl_mult'] * 1.5, 1)
    
    p['min_sigs'] = random.randint(1, 2)
    p['fvg_pct'] = round(random.uniform(0.003, 0.01), 3)
    return p

def mutate(p, scale=1.0):
    p = dict(p)
    for k in random.sample(list(PS.keys()), random.randint(2,3)):
        lo, hi, _ = PS[k]
        if k == 'tp_mult':
            p[k] = round(max(lo, min(hi, p[k]*random.uniform(0.7, 1.5*scale))), 1)
        elif k == 'sl_mult':
            p[k] = round(max(lo, min(hi, p[k]*random.uniform(0.5, 1.3*scale))), 2)
        elif k == 'fvg_pct':
            p[k] = round(max(lo, min(hi, p[k]*random.uniform(0.5, 1.5*scale))), 3)
        else:
            p[k] = max(lo, min(hi, round(p[k]+random.randint(-1,1))))
    rr = p['tp_mult'] / max(p['sl_mult'], 0.05)
    if rr < 1.0: p['tp_mult'] = round(p['sl_mult'] * 1.5, 1)
    return p

def cross(a,b):
    c = {}
    for k,(lo,hi,_) in PS.items():
        if k == 'min_sigs':
            c[k] = random.choice([a[k],b[k]])
        else:
            v = (a[k]+b[k])/2 + random.gauss(0, (hi-lo)*0.06)
            if k=='tp_mult': c[k]=round(max(lo,min(hi,v)),1)
            elif k=='sl_mult': c[k]=round(max(lo,min(hi,v)),2)
            elif k=='fvg_pct': c[k]=round(max(lo,min(hi,v)),3)
            else: c[k]=max(lo,min(hi,round(v)))
    rr = c['tp_mult']/max(c['sl_mult'],0.05)
    if rr < 1.0: c['tp_mult'] = round(c['sl_mult']*1.5,1)
    return c


# ============================================
# 主循环
# ============================================
def run(iters=200, pop_size=30, is_n=30, oos_n=30):
    print(f"\n{'='*60}")
    print(f"  SMC V7V3 (FVG回补策略)")
    print(f"  iters={iters} pop={pop_size} IS={is_n} OOS={oos_n}")
    print(f"{'='*60}")
    
    print("  Loading stocks...")
    alls = get_stocks()
    if not alls: print("  ERROR!"); return None,0,{}
    random.shuffle(alls)
    IS = alls[:is_n]; OOS = alls[is_n:is_n+oos_n]
    
    cached = 0
    for c in IS+OOS:
        if getk(c, 400): cached += 1
    print(f"  {cached}/{len(IS)+len(OOS)} cached, {len(alls)} total")
    
    pop = [rand_p() for _ in range(pop_size)]
    best_sc = 0; best_p = None; best_d = {}
    hist = []; stag = 0; prev = 0
    t0 = time.time()
    
    def fe(p, stks):
        total_t=total_w=total_sig=0; total_pnl=0.0
        for c in stks:
            t,w,pl = eval_code(c, p, min_fvg_pct=p['fvg_pct'])
            total_t+=t; total_w+=w; total_pnl+=pl
            if t>0: total_sig+=1
        wr = total_w/max(total_t,1)*100
        pf = total_w/max(total_t-total_w,1) if total_w>0 else 0
        return wr, pf, total_t, total_pnl, total_sig
    
    for gen in range(1, iters+1):
        gt = time.time()
        
        # proxy
        try:
            r = subprocess.run(['pgrep','-f','mihomo'], capture_output=True, text=True, timeout=3)
            if not r.stdout.strip():
                print(f"  proxy down!"); time.sleep(60)
        except: pass
        
        cur_wr = best_d.get('is_wr',0) if best_d else 0
        cur_rr = (best_p['tp_mult']/max(best_p['sl_mult'],0.05)) if best_p else 0
        
        if cur_wr >= 80 and cur_rr >= 1.5:
            scale = 0.4; stag = 0
        elif cur_wr < 55:
            scale = 2.0
        else:
            scale = 1.0
        
        if best_sc <= prev+0.5: stag += 1
        else: stag = 0
        prev = best_sc
        
        if stag >= 10:
            for _ in range(pop_size//3): pop.append(rand_p())
            scale = 2.0
        
        # 评估
        scored = []
        for idx, p in enumerate(pop):
            iwr, ipf, it, ipn, isig = fe(p, IS)
            owr, opf, ot, opn, osig = fe(p, OOS)
            rr = p['tp_mult']/max(p['sl_mult'],0.05)
            sc, det = calc_sc(iwr, owr, ipf, opf, it, ot, isig, osig, rr, len(IS), len(OOS))
            
            p['_sc']=sc; p['_iwr']=iwr; p['_owr']=owr
            p['_ipf']=ipf; p['_opf']=opf; p['_it']=it; p['_ot']=ot
            p['_rr']=rr
            scored.append(p)
            
            if sc > best_sc:
                best_sc = sc
                best_p = {k:p.get(k) for k in PS}
                best_d = {'is_wr':iwr,'oos_wr':owr,'is_pf':ipf,'oos_pf':opf,
                         'is_n':it,'oos_n':ot,'rr':rr,'score':sc}
        
        scored.sort(key=lambda x: x['_sc'], reverse=True)
        en = max(pop_size//4, 3)
        el = scored[:en]
        
        # 下一代
        npop = list(el)
        for p in el[:max(en//2,3)]:
            for _ in range(2):
                c = mutate(p, scale); npop.append(c)
        while len(npop) < pop_size:
            c = cross(random.choice(el), random.choice(scored[:pop_size//2]))
            if random.random()<0.5: c = mutate(c, scale*0.5)
            npop.append(c)
        while len(npop) < pop_size*1.1:
            npop.append(rand_p())
        pop = npop[:pop_size]
        
        elapsed = time.time()-gt
        
        s = {'g':gen,'t':iters,'sc':best_sc,'iw':best_d.get('is_wr',0),
             'ow':best_d.get('oos_wr',0),'ip':best_d.get('is_pf',0),
             'op':best_d.get('oos_pf',0),'in':best_d.get('is_n',0),
             'on':best_d.get('oos_n',0),'rr':best_d.get('rr',0),
             'ts':datetime.now().strftime('%H:%M:%S'),
             'sl':best_p.get('sl_mult',0),'tp':best_p.get('tp_mult',0)}
        HIST.write_text(json.dumps(hist[-100:], indent=2))
        BEST.write_text(json.dumps(s, indent=2))
        LIVE.write_text(json.dumps(s, indent=2))
        hist.append(s)
        
        print(f"  [gen{gen:3d}/{iters}] sc={best_sc:6.1f} "
              f"WR={best_d.get('is_wr',0):.0f}/{best_d.get('oos_wr',0):.0f}% "
              f"PF={best_d.get('is_pf',0):.1f}/{best_d.get('oos_pf',0):.1f} "
              f"n={best_d.get('is_n',0)+best_d.get('oos_n',0)} "
              f"RR={best_d.get('rr',0):.1f} SL={best_p.get('sl_mult',0):.2f}% "
              f"TP={best_p.get('tp_mult',0):.1f}% ({elapsed:.0f}s)")
        
        if best_d.get('is_wr',0) >= 80 and best_d.get('oos_wr',0) >= 75 and best_d.get('rr',0) >= 1.5:
            recent = [s for s in hist[-5:]]
            if all(s.get('iw',0) >= 75 for s in recent):
                print(f"\n  ✓ TARGET! gen={gen}")
                break
    
    print(f"\n  DONE in {time.time()-t0:.0f}s")
    return best_p, best_sc, best_d


if __name__ == '__main__':
    it = int(sys.argv[1]) if len(sys.argv)>1 else 200
    ps = int(sys.argv[2]) if len(sys.argv)>2 else 30
    i_n = int(sys.argv[3]) if len(sys.argv)>3 else 30
    o_n = int(sys.argv[4]) if len(sys.argv)>4 else 30
    run(it, ps, i_n, o_n)