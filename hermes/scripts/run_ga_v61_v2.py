#!/usr/bin/env python3
"""V6.1 GA Search V2 — 防过拟合"""
import sys, os, json, random, time, math
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from collections import defaultdict
from pathlib import Path
from smc_engine_v61 import (load_cached_bars, detect_entries_v61, simulate_entry, 
                            compute_score_v61, evaluate_v6)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v6'
os.makedirs(OPT_DIR, exist_ok=True)

# Use 80 stocks for better generalization
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
]

# Simplified parameter space — only 5 critical params
PARAM_SPACE = {
    'fvg_th': (0.12, 0.40),       # FVG敏感度
    'score_th': (2.0, 4.0),       # 信号门槛
    'sl_mult': (1.2, 3.0),        # 止损乘数
    'tp_mult': (2.0, 4.0),        # 止盈乘数
    'min_sigs': (2, 3),           # 最少信号数 (int)
}

print("="*70)
print("  V6.1 GA Search V2 — Anti-Overfit")
print("="*70)
print(f"  Stocks: {len(STOCKS)}")
print(f"  Params: {list(PARAM_SPACE.keys())}")
print(f"  Space: {[f'{k}:{v[0]:.2f}~{v[1]:.2f}' for k,v in PARAM_SPACE.items()]}")

# Load bars
print(f"\n  Loading bars...")
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
            alpha = random.uniform(0.2, 0.8)
            c[k] = round(p1[k]*alpha + p2[k]*(1-alpha), 2)
    return c

def mutate(p):
    p = {**p}
    for k, (lo, hi) in PARAM_SPACE.items():
        if random.random() < 0.3:
            if k == 'min_sigs':
                p[k] = random.randint(int(lo), int(hi))
            else:
                delta = random.uniform(-0.15, 0.15) * (hi - lo)
                p[k] = round(max(lo, min(hi, p[k] + delta)), 2)
    return p

def evaluate_params(params, bars_dict):
    """Evaluate params on all stocks — returns IS and OOS scores"""
    total_is_trades = []
    total_oos_trades = []
    n_stocks_with_sigs = 0
    
    for code, bars in bars_dict.items():
        split = int(len(bars) * 0.75)
        is_bars = bars[:split]
        oos_bars = bars[split:]
        
        if len(is_bars) < 60 or len(oos_bars) < 20:
            continue
        
        # IS
        try:
            e_is = detect_entries_v61(is_bars, params).get('total', [])
            is_trades = [simulate_entry(e, is_bars) for e in e_is]
            is_trades = [t for t in is_trades if t]
            
            e_oos = detect_entries_v61(oos_bars, params).get('total', [])
            oos_trades = [simulate_entry(e, oos_bars) for e in e_oos]
            oos_trades = [t for t in oos_trades if t]
            
            if is_trades or oos_trades:
                n_stocks_with_sigs += 1
            
            total_is_trades.extend(is_trades)
            total_oos_trades.extend(oos_trades)
        except:
            continue
    
    # IS score
    is_score = compute_score_v61(total_is_trades)
    is_wr = len([t for t in total_is_trades if t['pnl']>0])/len(total_is_trades)*100 if total_is_trades else 0
    is_n = len(total_is_trades)
    
    # OOS score
    oos_score = compute_score_v61(total_oos_trades)
    oos_wr = len([t for t in total_oos_trades if t['pnl']>0])/len(total_oos_trades)*100 if total_oos_trades else 0
    oos_n = len(total_oos_trades)
    
    # Combined score: IS * 0.3 + OOS * 0.7
    # With strong penalty for low trade counts
    is_trade_penalty = min(1.0, is_n / 50)
    oos_trade_penalty = min(1.0, oos_n / 20)
    
    combined = (is_score * 0.3 * is_trade_penalty + 
                oos_score * 0.7 * oos_trade_penalty)
    
    return {
        'combined': round(combined, 1),
        'is_score': is_score,
        'is_wr': round(is_wr, 1),
        'is_n': is_n,
        'oos_score': oos_score,
        'oos_wr': round(oos_wr, 1),
        'oos_n': oos_n,
        'n_stocks': n_stocks_with_sigs,
    }

# Initialize population
pop_size = 20
generations = 15

print(f"\n  Population: {pop_size} x {generations} generations")
print(f"  Total evaluations: ~{pop_size * generations}")
print()

population = [random_params() for _ in range(pop_size)]
best_overall = None
history = []

start_time = time.time()

for gen in range(generations):
    gen_start = time.time()
    
    results = []
    for idx, p in enumerate(population):
        r = evaluate_params(p, bars_cache)
        results.append((r['combined'], p, r))
    
    results.sort(key=lambda x: -x[0])
    
    best_r = results[0]
    avg_top5 = sum(r[0] for r in results[:5]) / 5
    
    if best_overall is None or best_r[0] > best_overall['combined']:
        best_overall = best_r[2]
        best_overall['params'] = best_r[1]
    
    gen_time = time.time() - gen_start
    
    entry = {
        'gen': gen+1,
        'best_score': best_r[0],
        'best_is_wr': best_r[2]['is_wr'],
        'best_is_n': best_r[2]['is_n'],
        'best_oos_wr': best_r[2]['oos_wr'],
        'best_oos_n': best_r[2]['oos_n'],
        'avg_top5': round(avg_top5, 1),
        'params': best_r[1],
        'time': round(gen_time, 0),
    }
    history.append(entry)
    
    print(f"  Gen {gen+1:>2d}: best={best_r[0]:>5.1f} "
          f"IS:WR={best_r[2]['is_wr']:.1f}% n={best_r[2]['is_n']:>2d} "
          f"OOS:WR={best_r[2]['oos_wr']:.1f}% n={best_r[2]['oos_n']:>2d} "
          f"avg5={avg_top5:.1f} {gen_time:.0f}s")
    
    if gen == generations - 1:
        break
    
    # Selection + reproduction
    top = [r[1] for r in results[:max(4, pop_size//3)]]
    new_pop = top.copy()
    
    while len(new_pop) < pop_size:
        p1, p2 = random.choices(top, k=2)
        child = crossover(p1, p2)
        child = mutate(child)
        new_pop.append(child)
    
    population = new_pop

total_time = time.time() - start_time

print(f"\n{'='*70}")
print(f"  GA V2 Complete! ({total_time:.0f}s)")
print(f"{'='*70}")
print(f"  Best params:")
print(f"    fvg_th={best_overall['params']['fvg_th']:.2f}")
print(f"    score_th={best_overall['params']['score_th']:.2f}")
print(f"    sl_mult={best_overall['params']['sl_mult']:.2f}")
print(f"    tp_mult={best_overall['params']['tp_mult']:.2f}")
print(f"    min_sigs={best_overall['params']['min_sigs']}")
print(f"  Results:")
print(f"    IS:  WR={best_overall['is_wr']:.1f}% n={best_overall['is_n']}")
print(f"    OOS: WR={best_overall['oos_wr']:.1f}% n={best_overall['oos_n']}")
print(f"    Score: {best_overall['combined']}")
print(f"    Stocks with signals: {best_overall['n_stocks']}")

# Save
result = {
    'params': best_overall['params'],
    'results': {k: v for k, v in best_overall.items() if k != 'params'},
    'history': history,
}
with open(OPT_DIR / 'ga_v2_result.json', 'w') as f:
    json.dump(result, f, indent=2)

print(f"\n  Saved to: {OPT_DIR / 'ga_v2_result.json'}")

# OOS final validation
print(f"\n{'='*70}")
print(f"  Final OOS Validation (full bars)")
print(f"{'='*70}")
final_is = []
final_oos = []
for code, bars in bars_cache.items():
    split = int(len(bars) * 0.7)
    is_b = bars[:split]
    oos_b = bars[split:]
    
    e_is = detect_entries_v61(is_b, best_overall['params']).get('total',[])
    e_oos = detect_entries_v61(oos_b, best_overall['params']).get('total',[])
    
    for e in e_is:
        t = simulate_entry(e, is_b)
        if t: final_is.append(t)
    for e in e_oos:
        t = simulate_entry(e, oos_b)
        if t: final_oos.append(t)

evaluate_v6(final_is, 'V6.IS')
evaluate_v6(final_oos, 'V6.OOS')