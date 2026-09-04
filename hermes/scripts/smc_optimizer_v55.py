#!/usr/bin/env python3
"""
SMC V5.5 Optimizer — 多策略并行搜索
=====================================
核心架构:
  1. 多worker并行: 同时跑3组不同搜索策略
  2. 策略1: 局部搜索 (在当前最优附近微调) 
  3. 策略2: 跳跃搜索 (大范围随机)
  4. 策略3: 遗传交叉 (混合历史最优参数)
  5. 每轮自适应切换策略
  
关键改进:
  - 避免score=0: 用默认参数兜底
  - 多策略保底: 如果所有策略都差, 回退到默认
  - 实时保存: 每10轮保存
"""

import sys, json, time, math, random, os
from pathlib import Path

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))

LOG_DIR = Path.home() / '.hermes' / 'smc_opt_v55'
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ════════ 参数空间 ════════

OPT_PARAMS = [
    # (name, min, max, default, step)
    ('fvg_min_width', 0.10, 0.40, 0.25, 0.02),
    ('sweep_lookback', 8, 25, 15, 1),
    ('sweep_wick_ratio', 1.2, 3.5, 2.0, 0.1),
    ('confirm_range', 1, 4, 2, 1),
    ('min_signal_sources', 1, 3, 1, 1),
    ('max_trades', 3, 12, 6, 1),
    ('min_score_threshold', 0.5, 2.5, 1.0, 0.1),
    ('trail_activation', 0.2, 0.6, 0.35, 0.05),
    ('sl_pct', 2.0, 6.0, 3.0, 0.2),
    ('tp_pct', 4.0, 12.0, 6.0, 0.2),
]

def default_params():
    return {k: v[3] for k, *v in [p for p in OPT_PARAMS]}

def params_to_engine(flat_params, atr_pct):
    """V5.5引擎参数转换 (支持波动率自适应)"""
    p = flat_params.copy()
    # 波动率层: 高波动用更宽的FVG, 低波动用更窄的
    if atr_pct >= 3.0:
        p['fvg_min_width'] = min(p['fvg_min_width'] * 1.3, 0.45)
    elif atr_pct <= 1.5:
        p['fvg_min_width'] = max(p['fvg_min_width'] * 0.7, 0.08)
    return p

def randomize(current=None, temperature=0.4):
    """参数随机化 (带保底)"""
    p = {}
    for name, mn, mx, default, step in OPT_PARAMS:
        if current and random.random() > 0.1:
            delta = (mx - mn) * temperature * random.gauss(0, 0.3)
            val = current.get(name, default) + delta
        else:
            val = mn + random.random() * (mx - mn)
        val = max(mn, min(mx, val))
        if step >= 1:
            val = round(val / step) * step
        else:
            val = round(val, 2)
        p[name] = val
    return p

def crossover(p1, p2):
    """遗传交叉"""
    child = {}
    for name, mn, mx, default, step in OPT_PARAMS:
        if random.random() < 0.5:
            child[name] = p1.get(name, default)
        else:
            child[name] = p2.get(name, default)
        # 10%变异
        if random.random() < 0.1:
            child[name] = mn + random.random() * (mx - mn)
            if step >= 1:
                child[name] = round(child[name] / step) * step
            else:
                child[name] = round(child[name], 2)
    return child


# ════════ 引擎接口 (轻量, 避免import阻塞) ════════

def load_bars(symbol):
    """直接从缓存加载K线"""
    from pathlib import Path as P
    import json
    cache_dir = P.home() / '.hermes' / 'kline_cache'
    # 尝试多格式
    for f in cache_dir.glob(f"{symbol.replace('.','_')}_daily_*.json"):
        try:
            with open(f) as fh:
                return json.load(fh)
        except: pass
    return []

def calc_atr_v2(bars, period=14):
    if len(bars) < period+2: return 0
    trs = []
    for i in range(1, min(period+1, len(bars))):
        tr = max(bars[-i]['h']-bars[-i]['l'],
                 abs(bars[-i]['h']-bars[-i-1]['c']),
                 abs(bars[-i]['l']-bars[-i-1]['c']))
        trs.append(tr)
    return sum(trs)/len(trs) if trs else 0

def quick_vol_profile(bars):
    if len(bars) < 30:
        return {'atr_pct': 0, 'vol_level': 'unknown'}
    atr = calc_atr_v2(bars)
    ap = sum((b['h']+b['l'])/2 for b in bars[-20:]) / 20
    atr_pct = atr / ap * 100 if ap > 0 else 0
    if atr_pct >= 3.0: vl = 'high'
    elif atr_pct >= 1.5: vl = 'medium'
    else: vl = 'low'
    return {'atr_pct': round(atr_pct, 2), 'vol_level': vl}

def quick_backtest(bars, params):
    """极简回测 (内联, 无外部依赖)"""
    if len(bars) < 60: return []
    
    eps = []
    fp = params_to_engine(params, calc_atr_v2(bars))
    fvg_w = fp.get('fvg_min_width', 0.25)
    sl_p = fp.get('sl_pct', 3.0)
    tp_p = fp.get('tp_pct', 6.0)
    lkb = fp.get('sweep_lookback', 15)
    wr = fp.get('sweep_wick_ratio', 2.0)
    min_src = fp.get('min_signal_sources', 1)
    max_tr = fp.get('max_trades', 6)
    min_sc = fp.get('min_score_threshold', 1.0)
    trail = fp.get('trail_activation', 0.35)
    cr = fp.get('confirm_range', 2)
    
    # FVG
    avg_r = sum(abs(k['h']-k['l']) for k in bars[-30:]) / max(1, min(30, len(bars)))
    fvgs = []
    for i in range(1, len(bars)-1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        top = min(p['h'], n['h'])
        bot = max(p['l'], n['l'])
        gap = top - bot
        if gap > avg_r * fvg_w:
            fvgs.append({'dir':'S' if c['c']>c['o'] else 'L', 'idx':i, 'mid':(top+bot)/2,
                         'gap':gap/avg_r, 'strength':min(5, gap/(avg_r*0.15))})
    
    # Sweep
    sweeps = []
    for i in range(lkb+1, len(bars)):
        c = bars[i]
        body = abs(c['c']-c['o'])
        uw = c['h'] - max(c['c'], c['o'])
        lw = min(c['c'], c['o']) - c['l']
        rl = min(bars[j]['l'] for j in range(i-lkb, i))
        rh = max(bars[j]['h'] for j in range(i-lkb, i))
        if body > 0:
            if c['l'] < rl and uw/body >= wr*0.5:
                sweeps.append({'dir':'L','idx':i,'price':c['l']})
            if c['h'] > rh and lw/body >= wr*0.4:
                sweeps.append({'dir':'S','idx':i,'price':c['h']})
    
    if not fvgs:
        return []
    
    for fvg in reversed(fvgs[-20:]):
        idx = fvg['idx']
        dir = fvg['dir']
        ep = round(fvg['mid'], 2)
        
        if idx < 3 or idx >= len(bars)-2:
            continue
        if len(bars) - idx > 30:
            continue
        
        src = ['FVG']
        score = 2.0 + fvg.get('strength', 1) * 0.3
        
        if any(s['dir']==dir and abs(s['idx']-idx)<=8 for s in sweeps):
            src.append('Sweep')
            score *= 1.3
        
        # CHoCH
        seg = bars[-15:]
        ups = sum(1 for i in range(len(seg)-1) if seg[i]['c']<seg[i+1]['c'])
        if (dir=='L' and ups > 8) or (dir=='S' and ups < 7):
            src.append('MS')
            score *= 1.2
        
        if len(src) < min_src:
            continue
        
        if score < min_sc:
            continue
        
        # SL/TP
        sl = round(ep * (1 - sl_p/100), 2) if dir=='L' else round(ep * (1 + sl_p/100), 2)
        tp = round(ep * (1 + tp_p/100), 2) if dir=='L' else round(ep * (1 - tp_p/100), 2)
        rr = abs(tp-ep) / max(0.01, abs(sl-ep))
        if rr < 1.0: continue
        
        eps.append({'dir':dir,'ep':ep,'idx':idx,'sl':sl,'tp':tp,'rr':round(rr,2),
                    'score':round(score,2),'src':src})
    
    # 排序去重
    eps.sort(key=lambda e: -e['score'])
    dedup = []
    for e in eps:
        if not any(abs(e['idx']-d['idx'])<=8 and e['dir']==d['dir'] for d in dedup):
            dedup.append(e)
    eps = dedup[:max_tr]
    
    if not eps:
        return []
    
    # 回测
    trades = []
    for e in eps:
        ei = e['idx']+1
        if ei >= len(bars): continue
        cs = e['sl']
        trail_a = False
        for j in range(ei, len(bars)):
            b = bars[j]
            if e['dir'] == 'L':
                if not trail_a and b['h'] >= e['ep'] + (e['tp']-e['ep'])*trail:
                    trail_a = True
                    cs = e['ep']*1.001
                if b['h'] >= e['tp']:
                    trades.append({'pnl':round((e['tp']-e['ep'])/e['ep'],4), 'src':e['src']})
                    break
                if b['l'] <= cs:
                    trades.append({'pnl':round((cs-e['ep'])/e['ep'],4), 'src':e['src']})
                    break
            else:
                if not trail_a and b['l'] <= e['ep'] - abs(e['tp']-e['ep'])*trail:
                    trail_a = True
                    cs = e['ep']*0.999
                if b['l'] <= e['tp']:
                    trades.append({'pnl':round((e['ep']-e['tp'])/e['ep'],4), 'src':e['src']})
                    break
                if b['h'] >= cs:
                    trades.append({'pnl':round((e['ep']-cs)/e['ep'],4), 'src':e['src']})
                    break
        else:
            l = bars[-1]['c']
            pnl = (l-e['ep'])/e['ep'] if e['dir']=='L' else (e['ep']-l)/e['ep']
            trades.append({'pnl':round(pnl,4), 'src':e['src']})
    
    return trades


# ════════ 评分 ════════

def score_trades(trades):
    n = len(trades)
    if n < 2:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': n, 'ret': 0}
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    wr = len(wins) / n * 100
    tw = sum(t['pnl'] for t in wins)
    tl = sum(abs(t['pnl']) for t in losses)
    pf = tw/tl if tl > 0 else 999
    avg = sum(t['pnl'] for t in trades) / n
    total_ret = sum(t['pnl'] for t in trades) * 100
    score = wr * 0.35 + min(50, pf * 7) * 0.35 + min(30, n * 2) * 0.15 + min(30, total_ret) * 0.15
    return {'score': round(score,1), 'wr': round(wr,1), 'pf': round(pf,2), 'n': n,
            'ret': round(total_ret,2), 'n_wins': len(wins), 'n_losses': n-len(wins)}


# ════════ 测试股票 ════════

TEST_STOCKS = [
    '300231.SZ', '000858.SZ', '600519.SH', '002415.SZ', '300750.SZ',
    '601318.SH', '000333.SZ', '002594.SZ', '688981.SH', '600036.SH',
    '300059.SZ', '600030.SH',
]

def evaluate(flat_params, stocks=None, max_s=10):
    """评估参数"""
    if stocks is None:
        stocks = TEST_STOCKS[:max_s]
    all_trades = []
    stocks_ok = 0
    stocks_sig = 0
    for sym in stocks:
        try:
            bars = load_bars(sym)
            if not bars or len(bars) < 60:
                continue
            stocks_ok += 1
            tr = quick_backtest(bars, flat_params)
            if tr:
                stocks_sig += 1
                all_trades.extend(tr)
        except:
            continue
    if not all_trades:
        return {'score': 0, 'wr': 0, 'pf': 0, 'n': 0, 'stocks_ok': stocks_ok, 'stocks_sig': 0}
    s = score_trades(all_trades)
    s['stocks_ok'] = stocks_ok
    s['stocks_sig'] = stocks_sig
    return s


# ════════ 多策略优化 ════════

def run_optimization(n_rounds=120):
    """全自动多策略优化"""
    
    best_params = default_params()
    default_s = evaluate(best_params, max_s=8)
    best_score = default_s.get('score', 0)
    best_eval = default_s
    best_params = default_params()
    
    history = [{'r': 0, 'score': best_score, 'wr': default_s.get('wr', 0), 'pf': default_s.get('pf', 0), 'n': default_s.get('n', 0), 'sig': default_s.get('stocks_sig', 0)}]
    
    print(f"[R000] Baseline: Score={best_score:.1f} WR={default_s.get('wr',0):.1f}% PF={default_s.get('pf',0):.2f} N={default_s.get('n',0)} Sig={default_s.get('stocks_sig',0)}/{default_s.get('stocks_ok',0)}")
    
    # 保存历史最佳
    top_k = [(best_score, best_params.copy())]
    
    cur_params = default_params().copy()
    temperature = 0.4
    no_improve = 0
    strategy = 'local'
    
    t0 = time.time()
    
    for rnd in range(n_rounds):
        r = rnd + 1
        
        # 自适应温度
        if r < 30:
            temperature = 0.5
        elif r < 60:
            temperature = 0.3
        elif r < 90:
            temperature = 0.15
        else:
            temperature = 0.08
        
        # 扩大搜索
        if no_improve > 10 and r % 5 == 0:
            temperature = 0.6
            strategy = 'jump'
            no_improve = 0
        
        # 多策略并跑
        candidates = []
        
        # 策略1: 局部搜索
        for _ in range(3):
            p = randomize(cur_params, temperature)
            candidates.append(p)
        
        # 策略2: 跳跃 (从最优附近)
        if r > 10 and len(top_k) > 2:
            p = randomize(random.choice(top_k)[1], temperature * 1.5)
            candidates.append(p)
        
        # 策略3: 遗传
        if len(top_k) >= 2:
            p = crossover(random.choice(top_k)[1], random.choice(top_k)[1])
            candidates.append(p)
        
        best_candidate = None
        best_candidate_score = -1
        best_candidate_eval = None
        
        for p in candidates:
            s = evaluate(p, max_s=8)
            if s['score'] > best_candidate_score:
                best_candidate_score = s['score']
                best_candidate = p.copy()
                best_candidate_eval = s
        
        # 保底: 保留当前最优
        if best_candidate_score <= 0:
            best_candidate = best_params.copy()
            best_candidate_score = best_score
            best_candidate_eval = best_eval
        
        # 更新
        if best_candidate_score > best_score:
            best_score = best_candidate_score
            best_params = best_candidate.copy()
            best_eval = best_candidate_eval
            no_improve = 0
            top_k.append((best_score, best_params.copy()))
            top_k.sort(key=lambda x: -x[0])
            top_k = top_k[:10]
            
            print(f"[R{r:03d}] ★ Score={best_score:.1f} WR={best_eval.get('wr',0):.1f}% PF={best_eval.get('pf',0):.2f} N={best_eval.get('n',0)} Sig={best_eval.get('stocks_sig',0)}")
            
            # Full evaluation
            if r % 20 == 0 or r == n_rounds:
                full = evaluate(best_params, max_s=len(TEST_STOCKS))
                print(f"    [Full] Score={full.get('score',0):.1f} WR={full.get('wr',0):.1f}% PF={full.get('pf',0):.2f} N={full.get('n',0)}")
                best_eval = full
        else:
            no_improve += 1
        
        # 更新current params (60%最优, 30%候选, 10%随机)
        if r % 5 == 0:
            cur_params = best_params.copy()
        elif r % 3 == 0 and best_candidate:
            cur_params = best_candidate.copy()
        else:
            cur_params = randomize(best_params, 0.2)
        
        history.append({
            'r': r, 'score': best_score,
            'wr': best_eval.get('wr', 0),
            'pf': best_eval.get('pf', 0),
            'n': best_eval.get('n', 0),
            'sig': best_eval.get('stocks_sig', 0),
        })
        
        # Save progress
        if r % 10 == 0 or r % 5 == 0:
            now = time.strftime('%H:%M:%S')
            elapsed = time.time() - t0
            print(f"[{now} R{r:03d}/{n_rounds}] Best={best_score:.1f} Temp={temperature:.2f} NoImpr={no_improve} {elapsed:.0f}s")
            
            json.dump({
                'best_score': best_score,
                'best_params': best_params,
                'best_eval': best_eval,
                'current_round': r,
                'total_rounds': n_rounds,
                'temperature': temperature,
                'history': history[-50:],
                'top_k': [(s, p) for s, p in top_k[:5]],
                'timestamp': time.time(),
            }, open(LOG_DIR / f'checkpoint_r{r:03d}.json', 'w'), indent=2)
            
            # Also always save current best
            json.dump({
                'best_score': best_score, 'best_params': best_params,
                'best_eval': best_eval, 'current_round': r, 'total_rounds': n_rounds,
                'history': history[-100:],
            }, open(LOG_DIR / 'current_best.json', 'w'))
    
    # Final
    elapsed = time.time() - t0
    full_final = evaluate(best_params, max_s=len(TEST_STOCKS))
    
    print(f"\n{'='*60}")
    print(f"V5.5 COMPLETE: {n_rounds} rounds in {elapsed:.0f}s ({elapsed/max(1,n_rounds):.1f}s/r)")
    print(f"Best Score: {best_score:.1f}")
    print(f"Best Params:")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
    print(f"\nFull Evaluation ({len(TEST_STOCKS)} stocks):")
    for k in ['score','wr','pf','n','n_wins','n_losses','ret','stocks_sig','stocks_ok']:
        if k in full_final:
            print(f"  {k}: {full_final[k]}")
    
    json.dump({
        'best_score': best_score, 'best_params': best_params,
        'final_eval': full_final, 'total_rounds': n_rounds,
        'elapsed': elapsed, 'top_k': [(s,p) for s,p in top_k[:5]],
        'history': history,
    }, open(LOG_DIR / 'final_result.json', 'w'), indent=2)
    
    return best_params, full_final


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--rounds', '-n', type=int, default=120, help='Number of optimization rounds')
    p.add_argument('--quick', '-q', action='store_true', help='Quick test only')
    args = p.parse_args()
    
    print(f"=== SMC V5.5 Opt (Multi-Strategy, {args.rounds} rounds) ===")
    print(f"Parameters: {len(OPT_PARAMS)} dims")
    
    if args.quick:
        print("Quick baseline:")
        s = evaluate(default_params(), max_s=8)
        for k in ['score','wr','pf','n','stocks_sig','stocks_ok']:
            print(f"  {k}: {s.get(k, 0)}")
        exit(0)
    
    bp, fs = run_optimization(n_rounds=args.rounds)