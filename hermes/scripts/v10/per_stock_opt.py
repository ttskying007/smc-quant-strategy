#!/usr/bin/env python3
# SMC V10 — Per-Stock Parameter Optimizer
"""
核心创新: 每只股票有独立的最优参数集。

为什么每股票参数不同:
- 茅台(600519): 高价股, ATR%小, 需要更紧的止损, 更宽的FVG敏感度
- 中芯(688981): 科创板高波动, ATR%大, 需要更宽的止损, 更高的确认门槛
- 不同行业的波动特性完全不同

优化策略:
1. 从全局最优参数(来自V8.4的best_params)作为种子
2. 对每只股票运行局部爬山搜索 (100-200次迭代)
3. 每只股票只优化关键参数: sl_pct, tp_pct, score_min, fvg_min_width, sweep_lookback
4. 固定不敏感参数: fvg_merge_dist, confirm_range, ob_strength_min

存储: ~/.hermes/smc_opt_v10/per_stock_params.json
"""

import json, math, random, time, logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v10.per_stock_opt')


# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════

OUTPUT_DIR = Path.home() / '.hermes' / 'smc_opt_v10'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PER_STOCK_FILE = OUTPUT_DIR / 'per_stock_params.json'

# Parameters that get per-stock optimization
PER_STOCK_OPTIMIZABLE = [
    'sl_pct', 'tp_pct', 'score_min', 
    'fvg_min_width', 'sweep_lookback', 'sweep_wick_ratio',
]

# Parameters that stay fixed (from global best)
FIXED_PARAMS = [
    'fvg_merge_dist', 'confirm_range', 'ob_strength_min',
    'min_sources', 'max_trades', 'atr_min_pct', 'atr_max_pct',
    'vol_adapt_sl',
]

# Default global best params (from V8.4 R13)
GLOBAL_BEST = {
    'fvg_min_width': 0.22,
    'fvg_merge_dist': 2,
    'sweep_lookback': 12,
    'sweep_wick_ratio': 4.26,
    'ob_strength_min': 0.97,
    'confirm_range': 2,
    'min_sources': 3,
    'score_min': 3.71,
    'max_trades': 7,
    'atr_min_pct': 3.17,
    'atr_max_pct': 11.55,
    'sl_pct': 1.0,
    'tp_pct': 2.8,
    'vol_adapt_sl': 0.6,
}

# Per-parameter optimization ranges (narrow around global best)
OPTIMIZATION_RANGES = {
    'sl_pct': (-0.5, +0.5),
    'tp_pct': (-1.0, +1.5),
    'score_min': (-1.5, +0.5),
    'fvg_min_width': (-0.10, +0.10),
    'sweep_lookback': (-4, +6),
    'sweep_wick_ratio': (-1.5, +1.0),
}


# ═══════════════════════════════════════════════════════════════════════
# Per-stock optimizer
# ═══════════════════════════════════════════════════════════════════════

def optimize_per_stock(
    symbol: str,
    backtest_fn,          # fn(symbol, params) → {wr, rr_avg, n, pf, ...}
    global_best: Dict = None,
    iterations: int = 150,
    verbose: bool = True,
) -> Dict:
    """Optimize parameters for a single stock via hill climbing.
    
    Strategy: narrow search around global best, because global best
    is already close to the stock-specific optimum.
    
    Args:
        symbol: stock code (e.g. '600519.SH')
        backtest_fn: function(symbol, params) → result_dict
        global_best: starting point parameters
        iterations: number of search iterations
        verbose: print progress
    
    Returns:
        {
            'symbol': symbol,
            'params': best_params_dict,
            'score': best_score,
            'wr': best_wr,
            'rr_avg': best_rr_avg,
            'n': n_trades,
            'pf': profit_factor,
            'history': [iterations],
        }
    """
    if global_best is None:
        global_best = GLOBAL_BEST.copy()
    
    # Initialize with global best
    current_params = dict(global_best)
    best_params = dict(current_params)
    
    # Evaluate baseline
    try:
        baseline = backtest_fn(symbol, current_params)
    except Exception as e:
        log.warning(f"Baseline eval failed for {symbol}: {e}")
        return _empty_stock_result(symbol, current_params)
    
    best_score = _score(baseline)
    best_wr = baseline.get('wr', 0)
    best_rr = baseline.get('rr_avg', 0)
    best_n = baseline.get('n', 0)
    best_pf = baseline.get('pf', 0)
    
    history = [{
        'iter': 0, 'score': best_score, 'wr': best_wr,
        'rr': best_rr, 'n': best_n, 'pf': best_pf,
    }]
    
    # Adaptive mutation rate
    mutation_rate = 0.15
    consecutive_failures = 0
    temperature = 1.0
    
    for iteration in range(1, iterations + 1):
        # Mutate parameters
        candidate = _mutate(current_params, mutation_rate)
        
        # Evaluate
        try:
            result = backtest_fn(symbol, candidate)
        except Exception:
            consecutive_failures += 1
            continue
        
        score = _score(result)
        
        # Accept/reject (simulated annealing)
        delta = score - best_score
        accept = delta > 0 or random.random() < math.exp(delta / (temperature * 0.01))
        
        if accept:
            current_params = dict(candidate)
            
            if score > best_score:
                best_score = score
                best_params = dict(candidate)
                best_wr = result.get('wr', 0)
                best_rr = result.get('rr_avg', 0)
                best_n = result.get('n', 0)
                best_pf = result.get('pf', 0)
                consecutive_failures = 0
                mutation_rate = max(0.05, mutation_rate * 0.95)
            else:
                consecutive_failures += 1
                
            history.append({
                'iter': iteration, 'score': score, 'wr': result.get('wr', 0),
                'rr': result.get('rr_avg', 0), 'n': result.get('n', 0),
                'pf': result.get('pf', 0),
            })
        else:
            consecutive_failures += 1
        
        # Adapt mutation rate
        if consecutive_failures > 15:
            mutation_rate = min(0.3, mutation_rate * 1.5)
            consecutive_failures = 0
            log.debug(f"[{symbol}] Increasing mutation to {mutation_rate:.2f}")
        
        # Cool down
        temperature *= 0.995
        
        if verbose and iteration % 30 == 0:
            log.info(f"[{symbol}] iter {iteration}/{iterations}: "
                     f"score={best_score:.1f} WR={best_wr:.1f}% "
                     f"RR={best_rr:.2f} N={best_n}")
    
    return {
        'symbol': symbol,
        'params': best_params,
        'score': round(best_score, 2),
        'wr': round(best_wr, 1),
        'rr_avg': round(best_rr, 2),
        'n': best_n,
        'pf': round(best_pf, 2),
        'baseline_score': history[0]['score'] if history else 0,
        'improvement': round(best_score - history[0]['score'], 2) if history else 0,
        'history': history[-20:],  # last 20 for compactness
        'total_iters': iterations,
    }


def _mutate(params: Dict, rate: float) -> Dict:
    """Mutate per-stock optimizable parameters within allowed ranges."""
    mutated = dict(params)
    
    for param in PER_STOCK_OPTIMIZABLE:
        if param not in mutated:
            continue
        
        current_val = mutated[param]
        ranges = OPTIMIZATION_RANGES.get(param, (-0.2, +0.2))
        
        # Gaussian mutation within range
        delta = random.gauss(0, abs(ranges[1] - ranges[0]) * rate)
        new_val = current_val + delta
        
        # Clamp to absolute bounds
        abs_bounds = _param_abs_bounds(param)
        new_val = max(abs_bounds[0], min(abs_bounds[1], new_val))
        
        # Also clamp to local range around global
        global_val = GLOBAL_BEST.get(param, current_val)
        local_min = global_val + ranges[0]
        local_max = global_val + ranges[1]
        new_val = max(local_min, min(local_max, new_val))
        
        # Round appropriately
        if param in ('sl_pct', 'tp_pct', 'sweep_wick_ratio'):
            new_val = round(new_val, 1)
        elif param == 'score_min':
            new_val = round(new_val, 2)
        elif param == 'fvg_min_width':
            new_val = round(new_val, 2)
        elif param == 'sweep_lookback':
            new_val = int(round(new_val))
        
        mutated[param] = new_val
    
    return mutated


def _param_abs_bounds(param: str) -> Tuple[float, float]:
    """Absolute bounds for each parameter."""
    bounds = {
        'sl_pct': (0.5, 6.0),
        'tp_pct': (1.0, 18.0),
        'score_min': (0.5, 5.0),
        'fvg_min_width': (0.01, 0.50),
        'sweep_lookback': (3, 30),
        'sweep_wick_ratio': (1.0, 6.0),
    }
    return bounds.get(param, (0, 100))


def _score(result: Dict) -> float:
    """Score a backtest result. Higher = better."""
    wr = result.get('wr', 0)
    n = result.get('n', 0)
    pf = result.get('pf', 0)
    rr = result.get('rr_avg', 0)
    
    if n == 0:
        return -1000
    
    # WR^2.0 priority (same as V8.4 v3)
    score = (wr / 100) ** 2.0 * math.sqrt(min(n, 50)) * min(3, pf) * min(2.5, rr)
    
    # Penalties
    if rr < 1.2 and n >= 3:
        score *= 0.1
    if n < 5:
        score = 0
    elif n < 10:
        score *= max(0.3, n / 10)
    
    return score


def _empty_stock_result(symbol, params):
    return {
        'symbol': symbol,
        'params': params,
        'score': -1000,
        'wr': 0, 'rr_avg': 0, 'n': 0, 'pf': 0,
        'improvement': 0, 'total_iters': 0, 'history': [],
    }


# ═══════════════════════════════════════════════════════════════════════
# Batch optimization
# ═══════════════════════════════════════════════════════════════════════

def batch_optimize(
    stocks: List[str],
    backtest_fn,
    global_best: Dict = None,
    iterations_per_stock: int = 150,
    verbose: bool = True,
) -> Dict[str, Dict]:
    """Run per-stock optimization for a list of stocks.
    
    Returns: {symbol: result_dict, ...}
    """
    results = {}
    total = len(stocks)
    
    log.info(f"Starting per-stock optimization for {total} stocks, {iterations_per_stock} iters each")
    
    for i, symbol in enumerate(stocks):
        log.info(f"[{i+1}/{total}] Optimizing {symbol}...")
        try:
            result = optimize_per_stock(
                symbol, backtest_fn, global_best, iterations_per_stock, verbose
            )
            results[symbol] = result
            log.info(f"[{i+1}/{total}] {symbol}: "
                     f"score={result['score']:.1f} WR={result['wr']:.1f}% "
                     f"RR={result['rr_avg']:.2f} N={result['n']} "
                     f"(improved: {result['improvement']:+.1f})")
        except Exception as e:
            log.error(f"[{i+1}/{total}] {symbol} FAILED: {e}")
            results[symbol] = _empty_stock_result(symbol, global_best or GLOBAL_BEST)
    
    return results


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════

def save_per_stock_params(results: Dict[str, Dict], global_best: Dict = None):
    """Save per-stock optimized parameters to JSON."""
    data = {
        'version': 'v10.0',
        'global_best': global_best or GLOBAL_BEST,
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'stocks': {},
    }
    
    for symbol, result in results.items():
        data['stocks'][symbol] = {
            'params': result.get('params', {}),
            'score': result.get('score', 0),
            'wr': result.get('wr', 0),
            'rr_avg': result.get('rr_avg', 0),
            'n': result.get('n', 0),
            'pf': result.get('pf', 0),
            'improvement': result.get('improvement', 0),
        }
    
    PER_STOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(PER_STOCK_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    log.info(f"Saved {len(results)} stock params to {PER_STOCK_FILE}")
    return PER_STOCK_FILE


def load_per_stock_params() -> Optional[Dict]:
    """Load per-stock optimized parameters."""
    if not PER_STOCK_FILE.exists():
        return None
    
    try:
        with open(PER_STOCK_FILE) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Failed to load per-stock params: {e}")
        return None


def get_params_for_stock(symbol: str, global_best: Dict = None) -> Dict:
    """Get parameters for a specific stock.
    
    Falls back to global best if per-stock params not available.
    """
    data = load_per_stock_params()
    if data and symbol in data.get('stocks', {}):
        return data['stocks'][symbol]['params']
    
    return dict(global_best or GLOBAL_BEST)


# ═══════════════════════════════════════════════════════════════════════
# Statistics
# ═══════════════════════════════════════════════════════════════════════

def compute_per_stock_stats(results: Dict[str, Dict]) -> Dict:
    """Compute statistics across all per-stock optimizations."""
    stocks_with_trades = [r for r in results.values() if r.get('n', 0) > 0]
    
    if not stocks_with_trades:
        return {'error': 'No stocks with trades'}
    
    wr_list = [r['wr'] for r in stocks_with_trades]
    rr_list = [r['rr_avg'] for r in stocks_with_trades]
    n_list = [r['n'] for r in stocks_with_trades]
    
    # Weighted average by N
    total_n = sum(n_list)
    avg_wr = sum(w * n for w, n in zip(wr_list, n_list)) / total_n if total_n > 0 else 0
    avg_rr = sum(r * n for r, n in zip(rr_list, n_list)) / total_n if total_n > 0 else 0
    
    # Per-stock WR improvement
    improvements = [r.get('improvement', 0) for r in stocks_with_trades]
    
    return {
        'total_stocks': len(results),
        'stocks_with_trades': len(stocks_with_trades),
        'total_trades': total_n,
        'avg_wr': round(avg_wr, 1),
        'avg_rr': round(avg_rr, 2),
        'wr_median': round(sorted(wr_list)[len(wr_list)//2], 1),
        'wr_max': round(max(wr_list), 1),
        'wr_min': round(min(wr_list), 1),
        'avg_improvement': round(sum(improvements) / len(improvements), 2) if improvements else 0,
        'improved_count': sum(1 for imp in improvements if imp > 0),
        'unchanged_count': sum(1 for imp in improvements if imp == 0),
    }
