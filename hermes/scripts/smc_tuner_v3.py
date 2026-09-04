#!/usr/bin/env python3
"""
V3.2 Engine Parameter Tuner — 对V3.2引擎做超参数优化

关键可调参数:
1. score_threshold: 入场分数门槛 (2.0~4.5, 默认3.0)
2. sl_shrink: 止损收缩系数 (0.5~1.5, 默认1.0)
3. tp_expand: 止盈扩展系数 (0.5~2.0, 默认1.0)
4. min_signals: 最小信号数 (1~3, 默认2)
5. choch_weight: CHOCH加分权重 (1.0~3.0, 默认1.5+)
6. fvg_max_age: FVG最大时效 (15~35, 默认25)
"""
import sys, os, json, random, math, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/skills/trading/smc-engine/scripts')
sys.path.insert(0, '/root/.hermes/scripts')
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_backtest_v2 import fetch_stock_list, fetch_klines, normalize_klines, compute_sharpe

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v3'
OPT_DIR.mkdir(parents=True, exist_ok=True)

# 参数空间
PARAM_SPACE = {
    'score_threshold': {'min': 1.5, 'max': 4.5, 'default': 3.0, 'step': 0.5},
    'sl_shrink': {'min': 0.5, 'max': 1.5, 'default': 1.0, 'step': 0.1},
    'tp_expand': {'min': 0.5, 'max': 2.0, 'default': 1.0, 'step': 0.1},
    'min_signals': {'min': 1, 'max': 3, 'step': 1, 'default': 2},
    'choch_bonus': {'min': 1.0, 'max': 3.0, 'default': 1.5, 'step': 0.2},
    'fvg_max_age': {'min': 15, 'max': 35, 'default': 25, 'step': 2},
    'sweep_dist_pre': {'min': 1, 'max': 5, 'default': 3, 'step': 1},
    'sweep_dist_post': {'min': 5, 'max': 15, 'default': 12, 'step': 1},
    'ob_proximity': {'min': 5, 'max': 15, 'default': 10, 'step': 1},
}

def build_custom_entries(bars, params):
    """V3.2入口检测 + 自定义参数"""
    results = []
    if len(bars) < 50:
        return results
    
    from smc_engine import detect_liquidity_sweep, calc_atr, detect_market_structure, detect_order_blocks
    
    # 多阈值FVG
    fvg_list = detect_fvg_multi(bars)
    # 多回看Sweep
    sweep_list = []
    for lb in [5, 8, 12, 15, 20]:
        for s in detect_liquidity_sweep(bars, lookback=lb):
            s['lb'] = lb
            sweep_list.append(s)
    seen_sw = {}
    for s in sweep_list:
        k = (s['index'], s['direction'])
        if k not in seen_sw or s.get('wick_ratio',0) > seen_sw[k].get('wick_ratio',0):
            seen_sw[k] = s
    sweep_list = list(seen_sw.values())
    
    ob_list = detect_order_blocks(bars)
    
    # 多窗口CHOCH
    from smc_engine import detect_choch_v2
    choch_results = []
    for lb in [8, 12, 15, 20]:
        c = detect_choch_v2(bars, lookback=lb)
        if c.get('detected'):
            choch_results.append(c)
    choch_wide = {'detected': bool(choch_results)}
    if choch_results:
        dirs = [r['direction'] for r in choch_results]
        choch_wide['direction'] = max(set(dirs), key=dirs.count)
    
    ms = detect_market_structure(bars, 15)
    
    if not fvg_list:
        return results
    
    last_idx = len(bars) - 1
    sc_th = params['score_threshold']
    min_sig = params['min_signals']
    ch_bonus = params['choch_bonus']
    mx_age = int(params['fvg_max_age'])
    sw_pre = int(params['sweep_dist_pre'])
    sw_post = int(params['sweep_dist_post'])
    ob_prox = int(params['ob_proximity'])
    sl_sh = params['sl_shrink']
    tp_ex = params['tp_expand']
    
    for fvg in fvg_list[-15:]:
        i = fvg.get('index', 0)
        if i < 3 or i >= last_idx - 2:
            continue
        
        age = last_idx - i
        if age > mx_age:
            continue
        
        direction = fvg['direction']
        tw = max(0.5, 1.0 - age / mx_age * 0.5)
        
        signals = {'fg': True}
        score = 1.0
        
        sw = [s for s in sweep_list if s['direction'] == direction and -sw_pre <= i - s.get('index',0) <= sw_post]
        if sw:
            score += min(2.0, max(sw, key=lambda s: s.get('wick_ratio',0)).get('wick_ratio',1.0) * 0.6)
            signals['sw'] = True
        
        if any(o['direction'] == direction and abs(o.get('index',0)-i) <= ob_prox for o in ob_list):
            score += 1.0
            signals['ob'] = True
        
        if choch_wide.get('detected') and choch_wide['direction'] == direction:
            c_sc = ch_bonus + (choch_results.count({'detected':True}) / 4.0) * 0.5
            score += c_sc
            signals['ch'] = True
        
        if ms.get('direction') == direction:
            score += 0.5
            signals['ms'] = True
        
        if fvg.get('strength',1) >= 2:
            score += 0.5
        
        ci = min(i + 1, last_idx - 1)
        if ci > 0:
            cb = bars[ci]
            if (direction == 'long' and cb['c'] > cb['o']) or (direction == 'short' and cb['c'] < cb['o']):
                score += 0.5
                signals['cf'] = True
        
        score *= tw
        n_sig = sum(1 for v in signals.values() if v)
        
        if score >= sc_th and n_sig >= min_sig:
            atr = calc_atr(bars[:i+5])
            ep = fvg['mid']
            ss = min(1.0, score / 6.0)
            sl_a = (2.0 - ss * 0.8) * sl_sh
            tp_a = (2.5 + ss * 1.0) * tp_ex
            
            if direction == 'long':
                results.append({'ep':i+1,'dir':'L','en':ep,'sl':ep-atr*sl_a,'tp':ep+atr*tp_a,
                                'sig':list(signals.keys()),'sc':round(score,2),'fi':i})
            else:
                results.append({'ep':i+1,'dir':'S','en':ep,'sl':ep+atr*sl_a,'tp':ep-atr*tp_a,
                                'sig':list(signals.keys()),'sc':round(score,2),'fi':i})
    
    return results


def simulate_custom(entries, bars):
    trades = []
    for e in entries:
        ei = e['ep']
        if ei >= len(bars):
            continue
        d, ep, sl, tp = e['dir'], e['en'], e['sl'], e['tp']
        sigs = e['sig']
        
        for j in range(ei, len(bars)):
            b = bars[j]
            if d == 'L':
                if b['l'] <= sl:
                    trades.append({'p':(sl-ep)/ep,'r':'sl','sig':sigs}); break
                if b['h'] >= tp:
                    trades.append({'p':(tp-ep)/ep,'r':'tp','sig':sigs}); break
            else:
                if b['h'] >= sl:
                    trades.append({'p':(ep-sl)/ep,'r':'sl','sig':sigs}); break
                if b['l'] <= tp:
                    trades.append({'p':(ep-tp)/ep,'r':'tp','sig':sigs}); break
        else:
            l = bars[-1]['c']
            trades.append({'p':(l-ep)/ep if d=='L' else (ep-l)/ep,'r':'eod','sig':sigs})
    return trades


def detect_fvg_multi(bars):
    if len(bars) < 3: return []
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / 30 if len(bars) >= 30 else 0
    if avg_r == 0: return []
    all_s = []
    for th in [0.12, 0.20, 0.30, 0.45]:
        start = max(1, len(bars)-35)
        for j in range(start, len(bars)-1):
            p,c,n = bars[j-1],bars[j],bars[j+1]
            bd = abs(c['c']-c['o'])
            if c['c'] > c['o']:
                gt,gb = min(p['h'],n['h']),max(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*th:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    all_s.append({'type':'B','direction':'long','top':gt,'bottom':gb,'mid':(gt+gb)/2,'strength':min(3,st),'index':j})
            elif c['c'] < c['o']:
                gt,gb = max(p['h'],n['h']),min(p['l'],n['l'])
                if gt>gb and gt-gb>avg_r*th:
                    st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                    all_s.append({'type':'S','direction':'short','top':gt,'bottom':gb,'mid':(gt+gb)/2,'strength':min(3,st),'index':j})
    seen = {}
    for s in all_s:
        k = (s['index'], s['direction'])
        if k not in seen or s['strength'] > seen[k]['strength']:
            seen[k] = s
    return list(seen.values())


def score_params(params, stocks, n_stocks=6):
    total = []
    for code, name in stocks[:n_stocks]:
        try:
            bars = normalize_klines(fetch_klines(code, 'daily', 500))
            if len(bars) < 100: continue
            entries = build_custom_entries(bars, params)
            trades = simulate_custom(entries, bars)
            total.extend(trades)
        except: continue
    
    n = len(total)
    if n < 3: return {'score':0,'n':0,'wr':0,'sr':0,'pf':0}
    wins = [t for t in total if t['p']>0]
    losses = [t for t in total if t['p']<=0]
    wr = len(wins)/n*100
    pf = abs(sum(t['p'] for t in wins)/sum(t['p'] for t in losses)) if losses and sum(t['p'] for t in losses)!=0 else 10
    sr = compute_sharpe([t['p'] for t in total], 252)
    ret = sum(t['p'] for t in total)*100
    
    # 评分: WR * 0.7 + Sharpe * 10 + n bonus
    s = wr * 0.7 + min(20, sr * 5) + min(10, n * 0.2)
    if pf < 1.0: s *= 0.3
    
    return {'score':round(s,1),'n':n,'wr':round(wr,1),'sr':round(sr,3),'pf':round(pf,2),'ret':round(ret,1)}


def run():
    print("Loading stocks...")
    all_s = fetch_stock_list()
    stocks = [(s['symbol'],s.get('name','')) for s in all_s if not s.get('symbol','').startswith('*ST')]
    random.seed(42); random.shuffle(stocks)
    print(f"  {len(stocks)} stocks")
    
    best = {'score':0,'wr':0,'sr':0,'params':None,'result':None}
    hist = []
    stag = 0
    
    print(f"\n{'='*70}")
    print(f"  V3.2 Parameter Tuner — WR > 80% Target")
    print(f"{'='*70}")
    
    start = time.time()
    for it in range(1, 151):
        # Generate params
        if it <= 3:  # Random exploration
            p = {k:(random.choice(s['choices']) if 'choices' in s else 
                    round((s['min']+random.random()*(s['max']-s['min']))/s.get('step',1))*s.get('step',1))
                 for k,s in PARAM_SPACE.items()}
        elif stag > 8:  # Big mutation
            p = dict(best['params'])
            for k,s in PARAM_SPACE.items():
                if random.random() < 0.5:
                    if 'step' in s:
                        delta = (s['max']-s['min'])*0.2*random.gauss(0,1)
                        p[k] = max(s['min'],min(s['max'],p[k]+delta))
                        p[k] = round(p[k]/s['step'])*s['step']
        elif random.random() < 0.3:  # Random
            p = {k:(round((s['min']+random.random()*(s['max']-s['min']))/s.get('step',1))*s.get('step',1))
                 for k,s in PARAM_SPACE.items() if 'step' in s}
        else:  # Small mutate
            p = dict(best['params'])
            for k,s in PARAM_SPACE.items():
                if random.random() < 0.2:
                    if 'step' in s:
                        delta = (s['max']-s['min'])*0.05*random.gauss(0,1)
                        p[k] = max(s['min'],min(s['max'],p[k]+delta))
                        p[k] = round(p[k]/s['step'])*s['step']
        
        # Score
        try:
            t0 = time.time()
            r = score_params(p, stocks, 6)
            el = time.time()-t0
            
            is_best = r['score'] > best['score']
            if is_best:
                best['score'] = r['score']; best['wr'] = r['wr']; best['sr'] = r['sr']
                best['params'] = dict(p); best['result'] = r; stag = 0
            else:
                stag += 1
            
            hist.append({'it':it,'score':r['score'],'wr':r['wr'],'sr':r['sr'],
                         'n':r['n'],'params':p})
            
            mk = ' 🏆' if is_best else ''
            print(f"  it {it:>3d} | score={r['score']:>5.1f}{mk} | WR={r['wr']:>4.1f}% | "
                  f"SR={r['sr']:>5.2f} | n={r['n']:>3} | {el:.1f}s")
            
            # Save every iteration
            with open(OPT_DIR / f'iter_{it:04d}.json','w') as f:
                json.dump({'it':it,'score':r['score'],'wr':r['wr'],'sr':r['sr'],
                           'n':r['n'],'params':p,'best_score':best['score'],
                           'best_wr':best['wr']}, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"  it {it:>3d}: ERROR {str(e)[:60]}")
            continue
        
        if it % 20 == 0:
            el2 = time.time()-start
            rate = it/el2
            rem = (150-it)/rate
            print(f"\n  📊 [{it}/150] Rate:{rate:.2f}it/s ETA:{rem/60:.1f}min Best:WR={best['wr']}% SR={best['sr']} Stag:{stag}")
        
        if stag > 20 and it > 40:
            print(f"\n  ⚡ Early stop: stag={stag}")
            break
    
    total = time.time()-start
    print(f"\n{'='*70}")
    print(f"  🏁 Done! {it} iters in {total/60:.1f}min")
    print(f"  Best: WR={best['wr']}% SR={best['sr']}")
    print(f"  Params:")
    for k,v in (best['params'] or {}).items():
        print(f"    {k}: {v}")
    print(f"{'='*70}")
    
    with open(OPT_DIR/'best_params.json','w') as f:
        json.dump({'best_wr':best['wr'],'best_sr':best['sr'],'best_params':best['params'],
                   'best_result':best['result']}, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    run()