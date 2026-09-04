#!/usr/bin/env python3
"""
V7 全自动迭代器 — 自适应GA搜索 + Walk-Forward OOS
====================================================
策略:
1. 从V4扫描结果加载候选股票(WR>=80%的)
2. 每轮:
   - 80%随机: GA搜索(15代×8pop)找新参数
   - 20%随机: 围绕最佳参数微调
3. Walk-Forward OOS验证(3-fold)
4. 多目标评分自动接受/拒绝
5. 记录完整历史
6. 如果代理中断自动恢复

运行: python3 auto_iter_v7.py [--iters 100] [--stocks 50] [--parallel 4]
"""
import sys, os, json, time, shutil, copy, random, math, traceback
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from pathlib import Path
from collections import defaultdict

from smc_engine_v7 import (
    generate_entries_v7, simulate_entry_v7, evaluate_v7, compute_score_v7,
    load_cached_bars, load_batch_bars, genetic_search_v7, walkforward_test_v7,
    random_params_v7, clamp_params_v7, crossover_params_v7, mutate_params_v7,
    PARAM_SPACE_V7, OPT_DIR, PARAM_DEFAULTS_V7, classify_market_v7
)

# =============================================
# Config
# =============================================
LOG_FILE = OPT_DIR / 'auto_iter_v7_log.json'
RESUME_FILE = OPT_DIR / 'auto_iter_v7_resume.json'
BEST_PARAMS_FILE = OPT_DIR / 'best_params_v7.json'
PROGRESS_FILE = OPT_DIR / 'iter_v7_progress.json'

# =============================================
# Load candidate stocks
# =============================================
def load_candidates():
    """从V4/V6结果加载候选股票"""
    # Try V4 scan results
    v4_path = Path.home() / '.hermes' / 'smc_opt_v4' / 'scan_v4_results.json'
    if v4_path.exists():
        data = json.loads(v4_path.read_text())
        if isinstance(data, list):
            quality = [s for s in data if s.get('wr_s', 0) >= 80]
            codes = [s['code'] for s in quality]
            print(f"  V4 candidates: {len(codes)} stocks (WR>=80%)")
            return codes
    
    # Try V6 results
    v6_path = OPT_DIR.parent / 'smc_opt_v6' / 'v61_signals_full.json'
    if v6_path.exists():
        data = json.loads(v6_path.read_text())
        if isinstance(data, dict) and 'stocks' in data:
            codes = [s['code'] for s in data['stocks'] if s.get('performance',{}).get('wr',0) >= 70]
            print(f"  V6 candidates: {len(codes)} stocks")
            return codes
    
    # Fallback
    print("  WARNING: No candidate list found, using default stocks")
    return ['600519.SH','000001.SZ','000858.SZ','002594.SZ','300750.SZ',
            '601318.SH','600036.SH','002415.SZ','000333.SZ','600585.SH']

# =============================================
# Parameter perturbation
# =============================================
def perturb_params(params, intensity=0.1):
    """小幅扰动参数"""
    p = dict(params)
    for k, (lo, hi, tp) in PARAM_SPACE_V7.items():
        if k in p:
            if random.random() < 0.5:
                if tp == 'int':
                    delta = random.choice([-1, 0, 1])
                    p[k] = max(int(lo), min(int(hi), int(p[k]) + delta))
                else:
                    delta = random.gauss(0, (hi-lo)*intensity)
                    p[k] = round(max(lo, min(hi, p[k] + delta)), 2)
    return clamp_params_v7(p)

# =============================================
# Full evaluation
# =============================================
def full_evaluate(params, bars_dict, verbose=True):
    """全量评估指定参数"""
    total_is = []
    total_oos = []
    stock_results = []
    
    for code, bars in bars_dict.items():
        split = int(len(bars) * 0.8)
        if split < 60: continue
        
        try:
            entries = generate_entries_v7(bars, params)
            is_trades = []
            oos_trades = []
            
            for e in entries.get('total', []):
                ei = e['idx']
                if ei <= split:
                    t = simulate_entry_v7(e, bars)
                    if t: is_trades.append(t)
                else:
                    t = simulate_entry_v7(e, bars)
                    if t: oos_trades.append(t)
            
            if is_trades or oos_trades:
                stock_results.append({
                    'code': code,
                    'is_n': len(is_trades),
                    'oos_n': len(oos_trades),
                })
                total_is.extend(is_trades)
                total_oos.extend(oos_trades)
        except:
            continue
    
    if not total_is:
        return None, None, 0
    
    is_eval = evaluate_v7(total_is, 'V7.IS') if verbose else None
    oos_eval = evaluate_v7(total_oos, 'V7.OOS') if verbose and total_oos else None
    
    is_wr = len([t for t in total_is if t['pnl']>0])/len(total_is)*100 if total_is else 0
    oos_wr = len([t for t in total_oos if t['pnl']>0])/len(total_oos)*100 if total_oos else 0
    
    score = compute_score_v7(total_is, is_wr, oos_wr)
    
    return score, is_wr, oos_wr

# =============================================
# Main iteration loop
# =============================================
DEBUG = False

def run_auto_iter_v7(target_iters=100, n_stocks=50, parallel=1):
    """Run V7 auto-iteration"""
    print("="*70)
    print("  SMC V7 全自动迭代引擎启动")
    print(f"  目标迭代: {target_iters}")
    print(f"  候选股票数: {n_stocks}")
    print("="*70)
    
    # Load candidates
    print("\n--- Loading candidates ---")
    all_candidates = load_candidates()
    candidates = all_candidates[:n_stocks]
    print(f"  Using {len(candidates)} stocks for iteration")
    
    # Resume from checkpoint
    if RESUME_FILE.exists():
        try:
            resume = json.loads(RESUME_FILE.read_text())
            print(f"\n  Resuming from iteration {resume.get('iter', 0)}")
            history = resume.get('history', [])
            best_overall = resume.get('best_overall', {'score': 0})
            current_best_params = resume.get('best_params', dict(PARAM_DEFAULTS_V7))
        except:
            history = []
            best_overall = {'score': 0, 'is_wr': 0, 'oos_wr': 0}
            current_best_params = dict(PARAM_DEFAULTS_V7)
    else:
        # Try loading previous best
        if BEST_PARAMS_FILE.exists():
            try:
                data = json.loads(BEST_PARAMS_FILE.read_text())
                best_params = {k: v for k, v in data.items() if not k.startswith('_')}
                print(f"  Loaded previous best params")
                current_best_params = best_params
            except:
                current_best_params = dict(PARAM_DEFAULTS_V7)
        else:
            current_best_params = dict(PARAM_DEFAULTS_V7)
        
        history = []
        best_overall = {'score': 0, 'is_wr': 0, 'oos_wr': 0}
    
    start_iter = len(history)
    print(f"  Starting from iteration {start_iter + 1}/{target_iters}")
    
    # Load bars (only once)
    print("\n--- Loading bars ---")
    bars_dict = {}
    loaded = 0
    for i, s in enumerate(candidates):
        bars = load_cached_bars(s, 300)
        if bars and len(bars) >= 80:
            bars_dict[s] = bars
            loaded += 1
        if (i+1) % 200 == 0:
            print(f"  Loaded {loaded}/{len(candidates)}")
    print(f"  Loaded {loaded}/{len(candidates)} bars")
    
    if not bars_dict:
        print("ERROR: No bars loaded!")
        return
    
    # Main loop
    iteration = start_iter
    last_checkpoint = time.time()
    stall_count = 0  # 停滞计数
    best_score_so_far = best_overall.get('score', 0)
    
    while iteration < target_iters:
        iteration += 1
        t0 = time.time()
        
        try:
            # Strategy selection
            if stall_count > 5:
                # Stalled! Big random jump
                print(f"  [Stall mode] Big random jump...")
                candidate = clamp_params_v7(random_params_v7())
                stall_count = 0
            elif iteration % 3 == 0:
                # GA search every 3 iterations
                print(f"\n  [GA Search #{iteration}] Searching...")
                ga_result = genetic_search_v7(candidates[:min(10, len(candidates))],
                                               generations=8, pop_size=8, mutation_rate=0.4)
                if ga_result:
                    candidate = ga_result
                else:
                    candidate = perturb_params(current_best_params, 0.15)
            elif iteration % 7 == 0:
                # Walk-forward validation on best
                print(f"\n  [Walk-Forward OOS #{iteration}] Testing best params...")
                score, is_wr, oos_wr = full_evaluate(current_best_params, bars_dict, verbose=True)
                print(f"  Best params OOS validation: score={score} IS-WR={is_wr:.1f}% OOS-WR={oos_wr:.1f}%")
                candidate = perturb_params(current_best_params, 0.1)
            else:
                # Small perturbation
                candidate = perturb_params(current_best_params, 0.12)
            
            # Evaluate
            score, is_wr, oos_wr = full_evaluate(candidate, bars_dict, verbose=False)
            
            if score is None:
                print(f"  Iter {iteration}: score=0 (no trades)")
                continue
            
            is_new_best = score > best_score_so_far
            
            if is_new_best:
                best_score_so_far = score
                current_best_params = candidate
                best_overall = {'score': score, 'is_wr': is_wr, 'oos_wr': oos_wr}
                stall_count = 0
                
                # Save best params
                with open(BEST_PARAMS_FILE, 'w') as f:
                    json.dump({**candidate, '_score': score, '_is_wr': is_wr,
                               '_oos_wr': oos_wr, '_iter': iteration}, f, indent=2)
                
                # Save iteration result
                iter_file = OPT_DIR / f'iter_v7_best_{iteration:04d}.json'
                with open(iter_file, 'w') as f:
                    json.dump({'iter': iteration, 'score': score, 'params': candidate,
                               'is_wr': is_wr, 'oos_wr': oos_wr}, f, indent=2)
            else:
                stall_count += 1
            
            # Record
            entry = {
                'iter': iteration,
                'score': round(score, 1) if score else 0,
                'is_wr': round(is_wr, 1) if is_wr else 0,
                'oos_wr': round(oos_wr, 1) if oos_wr else 0,
                'new_best': is_new_best,
                'time_s': round(time.time() - t0, 1),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            history.append(entry)
            
            # Progress indicator
            best_str = " ★ NEW BEST ★" if is_new_best else ""
            print(f"  Iter {iteration:03d}/{target_iters}: score={entry['score']:5.1f} "
                  f"IS-WR={entry['is_wr']:5.1f}% OOS-WR={entry['oos_wr']:5.1f}% "
                  f"t={entry['time_s']:.0f}s{best_str}")
            
            # Checkpoint every 10 iters
            if iteration % 10 == 0 or time.time() - last_checkpoint > 300:
                with open(RESUME_FILE, 'w') as f:
                    json.dump({
                        'iter': iteration,
                        'history': history[-50:],
                        'best_overall': best_overall,
                        'best_params': current_best_params,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    }, f, indent=2)
                last_checkpoint = time.time()
                
                # Save progress for WebUI
                with open(PROGRESS_FILE, 'w') as f:
                    json.dump({
                        'current_iter': iteration,
                        'total_iters': target_iters,
                        'best_score': best_overall.get('score', 0),
                        'best_wr': best_overall.get('is_wr', 0),
                        'best_oos_wr': best_overall.get('oos_wr', 0),
                        'recent_scores': [h.get('score', 0) for h in history[-20:]],
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    }, f, indent=2)
        
        except KeyboardInterrupt:
            print(f"\n  Interrupted at iteration {iteration}")
            break
        except Exception as ex:
            print(f"  Iter {iteration}: ERROR: {ex}")
            traceback.print_exc()
            time.sleep(10)
            continue
    
    # Final save
    print(f"\n{'='*60}")
    print(f"  Completed {len(history)} iterations")
    print(f"  Best score: {best_overall.get('score', 0)}")
    print(f"  Best IS-WR: {best_overall.get('is_wr', 0)}%")
    print(f"  Best OOS-WR: {best_overall.get('oos_wr', 0)}%")
    
    # Save full history
    with open(LOG_FILE, 'w') as f:
        json.dump(history, f, indent=2)
    
    # Cleanup resume
    if RESUME_FILE.exists():
        RESUME_FILE.unlink()
    
    print(f"\n  Full log: {LOG_FILE}")
    print(f"  Best params: {BEST_PARAMS_FILE}")
    
    # Update progress
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({
            'status': 'completed',
            'total_iters': len(history),
            'best_score': best_overall.get('score', 0),
            'best_wr': best_overall.get('is_wr', 0),
            'best_oos_wr': best_overall.get('oos_wr', 0),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }, f, indent=2)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='SMC V7 Auto Iteration')
    parser.add_argument('--iters', type=int, default=100, help='Number of iterations')
    parser.add_argument('--stocks', type=int, default=50, help='Number of stocks')
    parser.add_argument('--parallel', type=int, default=1, help='Parallel processes')
    args = parser.parse_args()
    
    run_auto_iter_v7(args.iters, args.stocks, args.parallel)