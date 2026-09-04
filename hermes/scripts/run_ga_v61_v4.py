#!/usr/bin/env python3
"""
V6.1 GA Search V4 — 更优约束参数搜索
=====================================
V3的问题: tp_mult=0.43 < sl_mult=3.86, 逻辑上不合理
V4修复: 强制 sl_mult <= tp_mult (止损<=止盈)
同时加入交易量目标: 优化 score = WR * wt + PF * wpf + (n/500) * wn
"""
import sys, os, json, random, time, math, copy
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from collections import defaultdict
from pathlib import Path

from smc_engine_v61 import detect_entries_v61, simulate_entry, load_cached_bars

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v6'
OPT_DIR.mkdir(parents=True, exist_ok=True)

# === PARAM SPACE V4 ===
# V3 fix: sl_mult range capped, tp_mult MUST be >= sl_mult + 0.5
PARAM_RANGES = {
    'fvg_th': (0.05, 0.5),
    'score_th': (0.5, 5.0),
    'sl_mult': (0.5, 4.0),          # Stop loss multiplier
    'tp_mult': (1.0, 6.0),          # Take profit multiplier - always >= sl
    'min_sigs': [1, 2, 3, 4],       # Minimum signals to trigger
}

# Fixed constraint: tp >= sl + 0.5 minimum difference
MIN_TP_SL_DIFF = 0.5

# Use stocks with WR>=80% from V4 scan
V4_RESULTS = json.load(open(str(OPT_DIR / 'scan_v4_stats.json')))
CANDIDATE_CODES = [s['code'] for s in V4_RESULTS if s.get('wr', 0) >= 80][:160]

def rand_param():
    """Generate random params respecting constraint tp >= sl + MIN_DIFF"""
    p = {}
    for k, v in PARAM_RANGES.items():
        if isinstance(v, list):
            p[k] = random.choice(v)
        else:
            p[k] = round(random.uniform(v[0], v[1]), 2)
    # Enforce: tp must be >= sl + 0.5
    p['tp_mult'] = max(p['tp_mult'], p['sl_mult'] + MIN_TP_SL_DIFF)
    return p

def mutate(p):
    p = copy.deepcopy(p)
    key = random.choice(list(PARAM_RANGES.keys()))
    v = PARAM_RANGES[key]
    if isinstance(v, list):
        choices = [x for x in v if x != p[key]]
        p[key] = random.choice(choices) if choices else p[key]
    else:
        stdev = (v[1] - v[0]) * 0.15
        val = p[key] + random.gauss(0, stdev)
        p[key] = round(max(v[0], min(v[1], val)), 2)
    # Re-enforce constraint
    p['tp_mult'] = max(p['tp_mult'], p['sl_mult'] + MIN_TP_SL_DIFF)
    return p

def crossover(p1, p2):
    p = {}
    for k in PARAM_RANGES:
        p[k] = random.choice([p1[k], p2[k]])
    p['tp_mult'] = max(p['tp_mult'], p['sl_mult'] + MIN_TP_SL_DIFF)
    return p

def evaluate(params, stocks):
    """Evaluate param set on 60% of stocks (IS), returns score and full results"""
    split = int(len(stocks) * 0.6)
    is_stocks = stocks[:split]
    oos_stocks = stocks[split:]
    
    # IS evaluation
    total_trades = 0
    wins = 0
    total_pnl = 0
    win_pnl = 0
    loss_pnl = 0
    
    for code in is_stocks:
        bars = load_cached_bars(code, 300)
        if not bars or len(bars) < 100:
            continue
        entries = detect_entries_v61(bars, params)
        total_sigs = entries.get('total', [])
        if total_sigs:
            for e in total_sigs:
                t = simulate_entry(e, bars)
                if t:
                    total_trades += 1
                    if t.get('pnl', 0) > 0:
                        wins += 1
                        win_pnl += t['pnl']
                    else:
                        loss_pnl += abs(t['pnl'])
                    total_pnl += t.get('pnl', 0)
    
    is_wr = wins/total_trades*100 if total_trades > 0 else 0
    is_n = total_trades
    is_pf = win_pnl/loss_pnl if loss_pnl > 0 else (999 if win_pnl > 0 else 0)
    
    # OOS evaluation
    total_trades2 = 0
    wins2 = 0
    win_pnl2 = 0
    loss_pnl2 = 0
    
    for code in oos_stocks:
        bars = load_cached_bars(code, 300)
        if not bars or len(bars) < 100:
            continue
        entries = detect_entries_v61(bars, params)
        total_sigs = entries.get('total', [])
        if total_sigs:
            for e in total_sigs:
                t = simulate_entry(e, bars)
                if t:
                    total_trades2 += 1
                    if t.get('pnl', 0) > 0:
                        wins2 += 1
                        win_pnl2 += t['pnl']
                    else:
                        loss_pnl2 += abs(t['pnl'])
    
    oos_wr = wins2/total_trades2*100 if total_trades2 > 0 else 0
    oos_n = total_trades2
    oos_pf = win_pnl2/loss_pnl2 if loss_pnl2 > 0 else (999 if win_pnl2 > 0 else 0)
    
    # Multi-objective score: WR > 80% heavily rewarded, trade count matters
    wr_bonus = 20 if is_wr >= 80 else (is_wr - 50) * 0.5
    n_bonus = min(20, is_n / 20)
    pf_bonus = min(10, is_pf * 5) if is_pf < 999 else 0
    
    # OOS matching
    oos_penalty = abs(is_wr - oos_wr) * 0.3
    
    # Minimum trade penalty
    min_trade_penalty = max(0, (30 - is_n) * 2) if is_n < 30 else 0
    
    score = max(0, wr_bonus + n_bonus + pf_bonus - oos_penalty - min_trade_penalty)
    
    return {
        'score': round(score, 1),
        'is_wr': round(is_wr, 1),
        'is_n': is_n,
        'is_pf': round(is_pf, 2),
        'oos_wr': round(oos_wr, 1),
        'oos_n': oos_n,
        'oos_pf': round(oos_pf, 2),
    }

def genetic_search(generations=25, pop_size=28, stocks=None):
    if stocks is None:
        stocks = CANDIDATE_CODES
    
    # Initialize
    population = [rand_param() for _ in range(pop_size)]
    best_score = 0
    best_params = None
    best_results = None
    history = []
    
    print(f"GA V4: {generations}gen x {pop_size}pop x {len(stocks)}stocks")
    print(f"Constraint: tp >= sl + {MIN_TP_SL_DIFF}")
    print()
    
    for gen in range(1, generations + 1):
        t0 = time.time()
        
        # Evaluate
        scored = []
        for params in population:
            r = evaluate(params, stocks)
            scored.append((r['score'], params, r))
        
        scored.sort(key=lambda x: -x[0])
        
        best = scored[0]
        if best[0] > best_score:
            best_score = best[0]
            best_params = best[1]
            best_results = best[2]
        
        history.append({
            'gen': gen,
            'score': best[0],
            'is_wr': best[2]['is_wr'],
            'is_n': best[2]['is_n'],
            'oos_wr': best[2]['oos_wr'],
            'oos_n': best[2]['oos_n'],
            'avg_top5': round(sum(s[0] for s in scored[:5]) / 5, 1),
            'params': best[1],
        })
        
        elapsed = time.time() - t0
        print(f"  Gen {gen:>2}: score={best[0]:>5.1f} IS:WR={best[2]['is_wr']:.1f}% n={best[2]['is_n']} OOS:WR={best[2]['oos_wr']:.1f}% n={best[2]['oos_n']} avg5={history[-1]['avg_top5']:.1f} {elapsed:.0f}s")
        
        # Selection + crossover + mutation
        top = scored[:pop_size // 3]
        new_pop = [p[1] for p in top]  # Elites
        
        while len(new_pop) < pop_size:
            if random.random() < 0.6:
                p1 = random.choice(top)[1]
                p2 = random.choice(top)[1]
                child = crossover(p1, p2)
            else:
                child = mutate(random.choice(top)[1])
            new_pop.append(child)
        
        population = new_pop
    
    print()
    print(f"  Best: WR={best_results['is_wr']}% IS n={best_results['is_n']} PF={best_results['is_pf']}")
    print(f"  OOS: WR={best_results['oos_wr']}% n={best_results['oos_n']} PF={best_results['oos_pf']}")
    print(f"  Params: {best_params}")
    
    result = {
        'params': best_params,
        'results': best_results,
        'history': history,
    }
    
    with open(str(OPT_DIR / 'ga_v4_result.json'), 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n  Saved to {OPT_DIR / 'ga_v4_result.json'}")
    
    return result

if __name__ == '__main__':
    result = genetic_search(generations=25, pop_size=28)
    
    # Save best params to be used by gen_v61_signals
    best = result['params']
    params_path = OPT_DIR / 'best_params_v6.json'
    json.dump(best, open(str(params_path), 'w'))
    print(f"\n  Best params saved to {params_path}")
    
    # Full validation on all 154 stocks
    print(f"\n  Full validation ({len(CANDIDATE_CODES)} stocks)...")
    total_trades = 0
    wins = 0
    win_pnl = 0
    loss_pnl = 0
    for code in CANDIDATE_CODES:
        bars = load_cached_bars(code, 300)
        if not bars or len(bars) < 100:
            continue
        entries = detect_entries_v61(bars, best)
        total_sigs = entries.get('total', [])
        for e in total_sigs:
            t = simulate_entry(e, bars)
            if t:
                total_trades += 1
                if t.get('pnl', 0) > 0:
                    wins += 1
                    win_pnl += t['pnl']
                else:
                    loss_pnl += abs(t['pnl'])
    wr = wins/total_trades*100 if total_trades else 0
    pf = win_pnl/loss_pnl if loss_pnl else 999
    print(f"  Full: {total_trades}t WR={wr:.1f}% PF={pf:.2f}")