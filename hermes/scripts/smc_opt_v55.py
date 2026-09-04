#!/usr/bin/env python3
"""
SMC V5.5 全自动优化器 — 高波动专用
=====================================
只优化 ATR >= 2% 的高/中波动股票 (跳过低波动)

评分函数:
  WR * 0.3 + min(40, PF*6) * 0.3 + min(30, Ret) * 0.2 + min(10, N) * 0.1 + Bonus(WR>85%+3, PF>5+5, PF>8+3)

参数: 20维 (高/中/低3层各5个 + 5个全局)
"""

import sys, json, time, math, random, os
from pathlib import Path

sys.path.insert(0, str(Path.home() / '.hermes' / 'scripts'))
from smc_v55 import PARAM_DEFS, backtest_all, score_trades, load_bars, get_vol

LOG_DIR = Path.home() / '.hermes' / 'smc_opt_v55'
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ════════ 高/中波动股票 ════════

HIGH_VOL_STOCKS = [
    '300231.SZ', '002415.SZ', '300750.SZ', '688981.SH',
    '300059.SZ', '002230.SZ', '002594.SZ', '300124.SZ',
    '600030.SH', '601318.SH',
]

def default_params():
    return {k: PARAM_DEFS[k]['default'] for k in PARAM_DEFS}

def randomize(cur=None, temp=0.3):
    p = {}
    for k, d in PARAM_DEFS.items():
        if cur and random.random() > 0.12:
            delta = (d['max']-d['min']) * temp * random.gauss(0, 0.25)
            val = cur.get(k, d['default']) + delta
        else:
            val = d['min'] + random.random() * (d['max']-d['min'])
        val = max(d['min'], min(d['max'], val))
        if d.get('step', 1) >= 1:
            val = round(val / d['step']) * d['step']
        else:
            val = round(val, 2)
        p[k] = val
    return p

def crossover(p1, p2):
    child = {}
    for k, d in PARAM_DEFS.items():
        child[k] = p1.get(k, d['default']) if random.random() < 0.5 else p2.get(k, d['default'])
        if random.random() < 0.08:
            child[k] = d['min'] + random.random() * (d['max']-d['min'])
            if d.get('step',1) >= 1:
                child[k] = round(child[k]/d['step'])*d['step']
            else:
                child[k] = round(child[k], 2)
    return child

def evaluate(fp, stocks=None, max_s=12):
    """评估一组参数"""
    if stocks is None:
        stocks = HIGH_VOL_STOCKS[:max_s]
    all_trades = []
    stocks_ok = 0; stocks_sig = 0
    for sym in stocks:
        try:
            bars = load_bars(sym)
            if not bars or len(bars) < 60: continue
            vol = get_vol(bars)
            # 只取高/中波动
            if vol['atr_pct'] < 1.5: continue
            stocks_ok += 1
            tr = backtest_all(bars, fp)
            if tr:
                stocks_sig += 1
                all_trades.extend(tr)
        except:
            continue
    if not all_trades:
        return {'score':0,'wr':0,'pf':0,'n':0,'ret':0,'stocks_ok':stocks_ok,'stocks_sig':0}
    s = score_trades(all_trades)
    s['stocks_ok'] = stocks_ok
    s['stocks_sig'] = stocks_sig
    return s


def run_opt(n_rounds=150):
    """主优化循环"""
    
    bp = default_params()
    ds = evaluate(bp, max_s=8)
    best_score = ds['score']
    best_eval = ds
    
    top_k = [(best_score, bp.copy())]
    cur = bp.copy()
    temp = 0.4
    no_imp = 0
    history = [{'r':0,'score':best_score,'wr':ds.get('wr',0),'pf':ds.get('pf',0),'n':ds.get('n',0)}]
    
    print(f"[R000] Baseline: Score={best_score:.1f} WR={ds.get('wr',0):.1f}% PF={ds.get('pf',0):.2f} N={ds.get('n',0)} Sig={ds.get('stocks_sig',0)}")
    
    t0 = time.time()
    
    for rnd in range(n_rounds):
        r = rnd + 1
        
        # 自适应温度
        if r < 40: temp = max(0.5, 0.6 * math.exp(-r/50))
        elif r < 80: temp = 0.25
        elif r < 120: temp = 0.12
        else: temp = 0.06
        
        if no_imp > 12 and r % 5 == 0:
            temp = min(0.6, temp * 4)
            no_imp = 0
        
        # 多策略
        cands = [randomize(cur, temp) for _ in range(3)]
        if r > 15 and len(top_k) >= 2:
            cands.append(randomize(random.choice(top_k)[1], temp*1.5))
        if len(top_k) >= 2:
            cands.append(crossover(random.choice(top_k)[1], random.choice(top_k)[1]))
        cands.append(bp.copy())
        
        best_c = None
        best_cs = -1
        best_ce = None
        
        for p in cands:
            s = evaluate(p, max_s=8)
            if s['score'] > best_cs:
                best_cs = s['score']
                best_c = p.copy()
                best_ce = s
        
        if best_cs <= 0:
            best_c = bp.copy()
            best_cs = best_score
            best_ce = best_eval
        
        if best_cs > best_score:
            best_score = best_cs
            bp = best_c.copy()
            best_eval = best_ce
            no_imp = 0
            top_k.append((best_score, bp.copy()))
            top_k.sort(key=lambda x:-x[0])
            top_k = top_k[:10]
            
            full = evaluate(bp, max_s=len(HIGH_VOL_STOCKS))
            print(f"[R{r:03d}] ★ Score={best_score:.1f} WR={full.get('wr',0):.1f}% PF={full.get('pf',0):.2f} N={full.get('n',0)} Ret={full.get('ret',0):.1f}% Sig={full.get('stocks_sig',0)}")
        else:
            no_imp += 1
        
        # cur update
        if r % 4 == 0: cur = bp.copy()
        elif best_c: cur = best_c.copy()
        else: cur = randomize(bp, 0.2)
        
        history.append({'r':r,'score':best_score,'wr':best_eval.get('wr',0),'pf':best_eval.get('pf',0),'n':best_eval.get('n',0),'ret':best_eval.get('ret',0)})
        
        if r % 15 == 0:
            now = time.strftime('%H:%M:%S')
            el = time.time() - t0
            print(f"[{now} R{r:03d}/{n_rounds}] Best={best_score:.1f} Temp={temp:.2f} NoImp={no_imp} {el:.0f}s")
            
            json.dump({
                'best_score':best_score,'best_params':bp,'best_eval':best_eval,
                'current_round':r,'history':history[-75:],
                'top_k': [(s,p) for s,p in top_k[:5]],
            }, open(LOG_DIR / f'ckpt_{r:03d}.json', 'w'), indent=2)
    
    # Final
    el = time.time() - t0
    full = evaluate(bp, max_s=len(HIGH_VOL_STOCKS))
    
    print(f"\n{'='*60}")
    print(f"V5.5 DONE: {n_rounds}r in {el:.0f}s ({el/max(1,n_rounds):.1f}s/r)")
    print(f"Best Score: {best_score:.1f}")
    print("Params:")
    for k,v in bp.items(): print(f"  {k}: {v}")
    print("Final Eval:")
    for k in ['score','wr','pf','n','ret','n_wins','n_losses','stocks_sig']:
        if k in full: print(f"  {k}: {full[k]}")
    
    json.dump({'best_score':best_score,'best_params':bp,'final_eval':full,
               'history':history,'elapsed':el}, open(LOG_DIR / 'final.json', 'w'), indent=2)
    return bp, full


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('-n', type=int, default=150)
    p.add_argument('--quick', '-q', action='store_true')
    args = p.parse_args()
    
    print(f"=== V5.5 Optimizer (High Vol) | {args.n} rounds | {len(PARAM_DEFS)} dims ===")
    print(f"Stocks: {len(HIGH_VOL_STOCKS)} high/med volatility")
    
    if args.quick:
        s = evaluate(default_params(), max_s=8)
        for k in ['score','wr','pf','n','ret','stocks_sig','stocks_ok']:
            print(f"  {k}: {s.get(k,0)}")
        exit(0)
    
    bp, fs = run_opt(args.n)