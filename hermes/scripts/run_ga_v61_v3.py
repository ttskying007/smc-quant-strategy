#!/usr/bin/env python3
"""
V6.1 GA Search V3 — 多目标优化
=================================
1. 目标: WR>80% AND trades>50 (per 80 stocks)
2. 更宽参数空间
3. 多目标评分: WR*0.4 + Trades*0.3 + PF*0.3
"""
import sys, os, json, random, time, math
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from pathlib import Path
from smc_engine_v61 import (load_cached_bars, detect_entries_v61, simulate_entry, 
                            compute_score_v61)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v6'
os.makedirs(OPT_DIR, exist_ok=True)

# Bigger stock set
STOCKS = [
    '600519.SH','000001.SZ','000858.SZ','600036.SH','002594.SZ','300750.SZ',
    '601318.SH','600887.SH','000002.SZ','600585.SH','688981.SH','002415.SZ',
    '603259.SH','000333.SZ','002475.SZ','300124.SZ','002230.SZ','600690.SH',
    '000651.SZ','002304.SZ','600030.SH','600104.SH','601088.SH','601166.SH',
    '601288.SH','601328.SH','601398.SH','601628.SH','601857.SH','600900.SH',
    '600276.SH','600309.SH','603288.SH','002714.SZ','300760.SZ','000568.SZ',
    '000725.SZ','002142.SZ','002236.SZ','002352.SZ','300059.SZ','300015.SZ',
    '300274.SZ','300413.SZ','300498.SZ','600809.SH','601012.SH','601899.SH',
    '603986.SH','600028.SH','600016.SH','600019.SH','600048.SH','600050.SH',
    '600085.SH','600150.SH','600196.SH','600406.SH','600438.SH','600570.SH',
    '600588.SH','600660.SH','600745.SH','600795.SH','600893.SH','600941.SH',
    '600958.SH','601006.SH','601111.SH','601117.SH','601225.SH','601238.SH',
    '601390.SH','601555.SH','601668.SH','601688.SH','601766.SH','601800.SH',
    '601808.SH','601818.SH','601878.SH','601881.SH','601985.SH','601989.SH',
    '000063.SZ','000100.SZ','000157.SZ','000166.SZ','000338.SZ','000425.SZ',
    '000538.SZ','000596.SZ','000625.SZ','000661.SZ','000768.SZ','000776.SZ',
    '000786.SZ','000858.SZ','000895.SZ','000938.SZ','000963.SZ','001979.SZ',
    '002007.SZ','002008.SZ','002027.SZ','002044.SZ','002049.SZ','002050.SZ',
    '002129.SZ','002153.SZ','002179.SZ','002180.SZ','002185.SZ','002202.SZ',
    '002241.SZ','002252.SZ','002271.SZ','002311.SZ','002371.SZ','002410.SZ',
    '002414.SZ','002422.SZ','002450.SZ','002460.SZ','002463.SZ','002466.SZ',
    '002493.SZ','002508.SZ','002555.SZ','002558.SZ','002568.SZ','002572.SZ',
    '002595.SZ','002601.SZ','002602.SZ','002607.SZ','002608.SZ','002624.SZ',
    '002625.SZ','002648.SZ','002673.SZ','002709.SZ','002736.SZ','002739.SZ',
    '002773.SZ','002812.SZ','002821.SZ','002837.SZ','002841.SZ','002916.SZ',
    '002920.SZ','002938.SZ','002945.SZ','002950.SZ','002955.SZ','002958.SZ',
]

PARAM_SPACE = {
    'fvg_th': (0.08, 0.40),
    'score_th': (1.5, 4.5),
    'sl_mult': (1.0, 3.5),
    'tp_mult': (1.5, 5.0),
    'min_sigs': (2, 4),
}

print("="*70)
print(f"  V6.1 GA Search V3 — Multi-Objective")
print(f"  {len(STOCKS)} stocks, 5 params")
print("="*70)

# Load bars
bars_cache = {}
loaded = 0
for s in STOCKS:
    b = load_cached_bars(s, 300)
    if b and len(b) >= 100:
        bars_cache[s] = b
        loaded += 1
print(f"  Loaded: {loaded}/{len(STOCKS)}")

def random_params():
    p = {}
    for k, (lo, hi) in PARAM_SPACE.items():
        if k == 'min_sigs':
            p[k] = random.randint(int(lo), int(hi))
        else:
            p[k] = round(random.uniform(lo, hi), 2)
    return p

def crossover(p1, p2):
    c = {}
    for k in p1:
        if k == 'min_sigs':
            c[k] = random.choice([p1[k], p2[k]])
        else:
            c[k] = round(p1[k]*random.uniform(0.2,0.8)+p2[k]*(1-random.uniform(0.2,0.8)), 2)
    return c

def mutate(p):
    p = {**p}
    for k, (lo, hi) in PARAM_SPACE.items():
        if random.random() < 0.3:
            if k == 'min_sigs':
                p[k] = random.randint(int(lo), int(hi))
            else:
                delta = random.uniform(-0.2, 0.2) * (hi - lo)
                p[k] = round(max(lo, min(hi, p[k] + delta)), 2)
    return p

def multi_objective_score(is_wr, is_n, oos_wr, oos_n, is_pf, oos_pf):
    """
    Multi-objective: WR dominance with trade count
    Score = (WR^1.5 / 100) * min(1, n/50) * 100
    """
    oos_part = (oos_wr/100)**1.5 * min(1.0, oos_n/30) * 60
    is_part = (is_wr/100)**1.5 * min(1.0, is_n/50) * 40
    
    # Strong PF boost
    pf_bonus = 0
    for pf, n in [(is_pf, is_n), (oos_pf, oos_n)]:
        if n >= 10:
            pf_bonus += min(pf/5.0, 5.0)
    
    total = oos_part + is_part + pf_bonus
    return round(total, 1)

def evaluate(params):
    total_is_wins = 0
    total_is_trades = 0
    total_is_pnl_win = 0
    total_is_pnl_loss = 0
    total_oos_wins = 0
    total_oos_trades = 0
    total_oos_pnl_win = 0
    total_oos_pnl_loss = 0
    n_stocks = 0
    
    for code, bars in bars_cache.items():
        split = int(len(bars) * 0.7)
        is_bars = bars[:split]
        oos_bars = bars[split:]
        if len(is_bars) < 60 or len(oos_bars) < 20:
            continue
        
        try:
            e_is = detect_entries_v61(is_bars, params).get('total', [])
            e_oos = detect_entries_v61(oos_bars, params).get('total', [])
            
            if not e_is and not e_oos:
                continue
            n_stocks += 1
            
            for e in e_is:
                t = simulate_entry(e, is_bars)
                if t:
                    total_is_trades += 1
                    if t['pnl'] > 0:
                        total_is_wins += 1
                        total_is_pnl_win += t['pnl']
                    else:
                        total_is_pnl_loss += abs(t['pnl'])
            
            for e in e_oos:
                t = simulate_entry(e, oos_bars)
                if t:
                    total_oos_trades += 1
                    if t['pnl'] > 0:
                        total_oos_wins += 1
                        total_oos_pnl_win += t['pnl']
                    else:
                        total_oos_pnl_loss += abs(t['pnl'])
        except:
            continue
    
    is_wr = total_is_wins/total_is_trades*100 if total_is_trades else 0
    oos_wr = total_oos_wins/total_oos_trades*100 if total_oos_trades else 0
    is_pf = total_is_pnl_win/total_is_pnl_loss if total_is_pnl_loss > 0 else (999 if total_is_pnl_win > 0 else 0)
    oos_pf = total_oos_pnl_win/total_oos_pnl_loss if total_oos_pnl_loss > 0 else (999 if total_oos_pnl_win > 0 else 0)
    
    score = multi_objective_score(is_wr, total_is_trades, oos_wr, total_oos_trades, is_pf, oos_pf)
    
    return {
        'score': score,
        'is_wr': round(is_wr, 1),
        'is_n': total_is_trades,
        'is_pf': round(is_pf, 2),
        'oos_wr': round(oos_wr, 1),
        'oos_n': total_oos_trades,
        'oos_pf': round(oos_pf, 2),
        'n_stocks': n_stocks,
    }

pop_size = 24
generations = 20

population = [random_params() for _ in range(pop_size)]
best_overall = None
history = []

start_time = time.time()

for gen in range(generations):
    gen_start = time.time()
    
    results = []
    for idx, p in enumerate(population):
        r = evaluate(p)
        results.append((r['score'], p, r))
    
    results.sort(key=lambda x: -x[0])
    best_r = results[0]
    avg_top = sum(r[0] for r in results[:5])/5
    
    if best_overall is None or best_r[0] > best_overall['score']:
        best_overall = best_r[2]
        best_overall['params'] = best_r[1]
    
    gen_time = time.time() - gen_start
    history.append({
        'gen': gen+1, 'score': best_r[0],
        'is_wr': best_r[2]['is_wr'], 'is_n': best_r[2]['is_n'],
        'oos_wr': best_r[2]['oos_wr'], 'oos_n': best_r[2]['oos_n'],
        'avg_top5': round(avg_top, 1), 'params': best_r[1],
    })
    
    print(f"  Gen {gen+1:>2d}: score={best_r[0]:>5.1f} "
          f"IS:WR={best_r[2]['is_wr']:.1f}% n={best_r[2]['is_n']:>3d} "
          f"OOS:WR={best_r[2]['oos_wr']:.1f}% n={best_r[2]['oos_n']:>2d} "
          f"avg5={avg_top:.1f} {gen_time:.0f}s")
    
    if gen == generations - 1:
        break
    
    # Selection
    top = [r[1] for r in results[:max(5, pop_size//3)]]
    new_pop = top.copy()
    while len(new_pop) < pop_size:
        p1, p2 = random.choices(top, k=2)
        child = crossover(p1, p2)
        child = mutate(child)
        new_pop.append(child)
    population = new_pop

total_time = time.time() - start_time

print(f"\n{'='*70}")
print(f"  GA V3 Complete! ({total_time:.0f}s)")
print(f"{'='*70}")
print(f"  Best params:")
for k, v in best_overall['params'].items():
    print(f"    {k}={v}")
print(f"  IS:    WR={best_overall['is_wr']:.1f}% n={best_overall['is_n']} PF={best_overall['is_pf']:.2f}")
print(f"  OOS:   WR={best_overall['oos_wr']:.1f}% n={best_overall['oos_n']} PF={best_overall['oos_pf']:.2f}")
print(f"  Score: {best_overall['score']}")
print(f"  Stocks: {best_overall['n_stocks']}")

# Save
with open(OPT_DIR / 'ga_v3_result.json', 'w') as f:
    json.dump({'params': best_overall['params'], 'results': 
        {k:v for k,v in best_overall.items() if k!='params'},
        'history': history}, f, indent=2)

# Now full validation with GA V3 params
print(f"\n{'='*70}")
print(f"  Full validation (90 stocks, full bars)")
print(f"{'='*70}")
full_is = []
full_oos = []
for code, bars in bars_cache.items():
    split = int(len(bars) * 0.7)
    is_b = bars[:split]
    oos_b = bars[split:]
    
    e_is = detect_entries_v61(is_b, best_overall['params']).get('total', [])
    e_oos = detect_entries_v61(oos_b, best_overall['params']).get('total', [])
    
    for e in e_is:
        t = simulate_entry(e, is_b)
        if t: full_is.append(t)
    for e in e_oos:
        t = simulate_entry(e, oos_b)
        if t: full_oos.append(t)

from smc_engine_v61 import evaluate_v6
evaluate_v6(full_is, 'V6.IS')
evaluate_v6(full_oos, 'V6.OOS')

# Save as new best
with open(OPT_DIR / 'best_params_v61.json', 'w') as f:
    json.dump(best_overall['params'], f, indent=2)
print(f"\n  Saved new best params")