#!/usr/bin/env python3
"""
V6.1 → V6.2 全自动迭代循环
============================
策略:
1. 用V6.1最佳参数初始化
2. 跑GA搜索(30代)找新参数
3. 全量验证(2710只)
4. 记录结果，与历史最佳比较
5. 如果WR>85%或比上次好>2%，接受新参数
6. 重复直到100轮完成
"""
import sys, os, json, time, shutil, copy, random, math
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from pathlib import Path
from collections import defaultdict

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v6'
OPT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OPT_DIR / 'auto_iter_log.json'

# Load V6.1 candidates (stocks with WR>=80%)
V61_SIGNALS = json.loads((OPT_DIR / 'v62_signals_full.json').read_text())
CANDIDATE_CODES = list(V61_SIGNALS.get('results', V61_SIGNALS).keys())[:200]

# Current best params (GA V3)
BEST_PARAMS = {'fvg_th': 0.11, 'score_th': 1.5, 'sl_mult': 3.86, 'tp_mult': 0.43, 'min_sigs': 4}
BEST_SCORE = {'wr': 95.8, 'n': 11509, 'pf': 3.7}

from smc_engine_v62 import single_stock_scan_v62

def evaluate_quick(params, stocks, n=80):
    """Quick evaluation on n stocks"""
    split = int(n * 0.6)
    is_stocks = stocks[:split]
    oos_stocks = stocks[split:split+40]
    
    results = {}
    for label, stks in [('is', is_stocks), ('oos', oos_stocks)]:
        total = 0; wins = 0; win_pnl = 0; loss_pnl = 0
        for code in stks:
            trades = single_stock_scan_v62(code, params)
            for t in trades:
                total += 1
                if t['pnl'] > 0:
                    wins += 1; win_pnl += t['pnl']
                else:
                    loss_pnl += abs(t['pnl'])
        wr = wins/total*100 if total else 0
        pf = win_pnl/loss_pnl if loss_pnl else (0 if win_pnl else 0)
        results[label] = {'wr': round(wr,1), 'n': total, 'pf': round(pf,2)}
    
    # Score: WR * 0.6 + PF*5 * 0.2 + n/10 * 0.2 - overfit_penalty
    is_score = results['is']['wr'] * 0.6 + min(results['is']['pf'], 10) * 3
    oos_score = results['oos']['wr'] * 0.4 + min(results['oos']['pf'], 10) * 2
    overfit = abs(results['is']['wr'] - results['oos']['wr']) * 0.5
    min_n = min(results['is']['n'], results['oos']['n'])
    n_bonus = min(15, min_n / 10)
    
    score = max(0, is_score + oos_score - overfit + n_bonus)
    
    return score, results

# Main iteration loop
def run_auto_iter(target_iterations=100):
    """Main auto-iteration loop"""
    
    # Load history from previous runs
    if LOG_FILE.exists():
        history = json.loads(LOG_FILE.read_text())
    else:
        history = []
    
    iteration = len(history)
    best_score_so_far = max([h.get('score', 0) for h in history]) if history else 0
    
    current_params = dict(BEST_PARAMS)
    
    while iteration < target_iterations:
        iteration += 1
        t0 = time.time()
        
        # Every 10 iterations, try random perturbation for exploration
        if iteration % 10 == 0:
            # Random big jump
            p = dict(BEST_PARAMS)
            for k in p:
                if k == 'fvg_th':
                    p[k] = round(random.uniform(0.05, 0.5), 2)
                elif k == 'score_th':
                    p[k] = round(random.uniform(0.5, 4.5), 1)
                elif k in ('sl_mult', 'tp_mult'):
                    p[k] = round(max(0.5, p[k] + random.gauss(0, 1.0)), 2)
                elif k == 'min_sigs':
                    p[k] = random.choice([1, 2, 3, 4])
            current_params = p
        else:
            # Small mutation around best
            p = dict(BEST_PARAMS)
            key = random.choice(list(p.keys()))
            if key == 'fvg_th':
                p[key] = round(max(0.05, min(0.5, p[key] + random.gauss(0, 0.05))), 2)
            elif key == 'score_th':
                p[key] = round(max(0.5, min(5.0, p[key] + random.gauss(0, 0.3))), 1)
            elif key in ('sl_mult', 'tp_mult'):
                p[key] = round(max(0.5, min(6.0, p[key] + random.gauss(0, 0.3))), 2)
            elif key == 'min_sigs':
                p[key] = random.choice([max(1, min(4, p[key] + random.choice([-1, 0, 1])))])
            current_params = p
        
        # Evaluate
        score, results = evaluate_quick(current_params, CANDIDATE_CODES, n=80)
        
        entry = {
            'iter': iteration,
            'score': round(score, 1),
            'params': current_params,
            'is': results['is'],
            'oos': results['oos'],
            'time_s': round(time.time() - t0, 1),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        history.append(entry)
        
        # Check if best
        if score > best_score_so_far:
            best_score_so_far = score
            BEST_PARAMS.update(current_params)
            BEST_SCORE.update(results)
            
            signature = f"★ NEW BEST ★"
            json.dump(BEST_PARAMS, open(OPT_DIR / 'best_params_v6.json', 'w'), indent=2)
            json.dump(entry, open(OPT_DIR / f'iter_best_{iteration:04d}.json', 'w'), indent=2)
        else:
            signature = ""
        
        # Log
        is_entry = entry['is']
        oos_entry = entry['oos']
        
        print(f"Iter {iteration:03d}/{target_iterations}: score={score:5.1f} "
              f"IS:WR={is_entry['wr']:5.1f}% n={is_entry['n']:3d} PF={is_entry['pf']:5.2f} "
              f"OOS:WR={oos_entry['wr']:5.1f}% n={oos_entry['n']:3d} PF={oos_entry['pf']:5.2f} "
              f"diff={abs(is_entry['wr']-oos_entry['wr']):.1f}% "
              f"{signature}")
        
        # Save progress every 5 iters
        if iteration % 5 == 0:
            json.dump(history[-50:], open(LOG_FILE, 'w'), indent=2)
    
    # Final save
    json.dump(history, open(LOG_FILE, 'w'), indent=2)
    
    print(f"\n{'='*60}")
    print(f"Completed {target_iterations} iterations")
    print(f"Best params: {BEST_PARAMS}")
    print(f"Best results: IS={BEST_SCORE}")

if __name__ == '__main__':
    run_auto_iter(150)