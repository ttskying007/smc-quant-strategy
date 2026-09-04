#!/usr/bin/env python3
# SMC V11 — Per-Stock / Per-Phase / Per-TF Parameter Optimizer
"""
V11优化器 — 三维参数空间搜索

V11 vs V8.4优化的核心区别:
1. 每股独立: 不是找40只股票的全局最优, 而是每只股票自己的最优
2. 每阶段独立: 趋势/震荡/波动阶段各有独立参数
3. 每周期独立: 日线/4H/1H各有独立参数
4. 基于自适应: 从自适应参数开始, 局部搜索微调
5. 增量优化: 先跑全量回测, 再识别表现差的股票单独优化

搜索策略:
  Phase 1: 自适应默认 → 全量回测 (基线)
  Phase 2: 识别表现差的股票 → 单独参数搜索
  Phase 3: 每股X次迭代局部搜索 (模拟退火)
  Phase 4: 保存每股票最优参数
  Phase 5: 验证: 用优化后的参数全量回测

优化目标:
  score = WR^2.0 * RR * sqrt(min(N, 50)) * min(3, PF)
"""

import json, math, random, time, logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

log = logging.getLogger('smc_v11.optimizer')

OUTPUT_DIR = Path.home() / '.hermes' / 'smc_opt_v11'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
# Scoring function
# ═══════════════════════════════════════════════════════════════════════

def calc_opt_score(stats: Dict) -> float:
    """优化目标评分
    
    V11评分 (继承V8.4 WR优先):
      score = (WR/100)^2.0 * sqrt(min(N, 50)) * min(3, PF) * min(2.5, RR)
    """
    wr = stats.get('win_rate', 0)
    rr = stats.get('avg_rr', 0)
    pf = stats.get('profit_factor', 0)
    n = stats.get('n_trades', 0)
    
    if n < 5:
        return 0
    if rr < 1.2 and n >= 3:
        return 0
    
    score = (wr / 100) ** 2.0 * math.sqrt(min(n, 50)) * min(3, pf) * min(2.5, rr)
    
    # N惩罚
    if n < 8:
        return 0
    elif n < 15:
        score *= max(0.3, n / 15)
    
    return score


# ═══════════════════════════════════════════════════════════════════════
# Parameter ranges for optimization
# ═══════════════════════════════════════════════════════════════════════

OPT_PARAM_RANGES = {
    'sl_pct': {
        'lo': 0.3, 'hi': 4.0, 'step': 0.3, 'mutate': 0.3,
        'adaptive_base': True,  # 从自适应值开始
    },
    'tp_pct': {
        'lo': 1.0, 'hi': 6.0, 'step': 0.5, 'mutate': 0.5,
        'adaptive_base': True,
    },
    'score_min': {
        'lo': 0.5, 'hi': 7.0, 'step': 0.5, 'mutate': 0.5,
        'adaptive_base': True,
    },
    'fvg_min_width': {
        'lo': 0.0001, 'hi': 0.02, 'step': 0.0005, 'mutate': 0.002,
        'adaptive_base': True,
    },
    'sweep_wick_ratio': {
        'lo': 1.5, 'hi': 6.0, 'step': 0.3, 'mutate': 0.5,
        'adaptive_base': True,
    },
    'ob_strength_min': {
        'lo': 0.3, 'hi': 2.5, 'step': 0.2, 'mutate': 0.3,
        'adaptive_base': True,
    },
    'sweep_lookback': {
        'lo': 5, 'hi': 25, 'step': 1, 'mutate': 2,
        'adaptive_base': True,
    },
    'max_trades': {
        'lo': 2, 'hi': 15, 'step': 1, 'mutate': 2,
        'adaptive_base': True,
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Single-stock parameter optimization
# ═══════════════════════════════════════════════════════════════════════

def optimize_single_stock(
    ohlcv: List[Dict],
    symbol: str,
    tf: str = 'daily',
    iterations: int = 100,
    seed_params: Dict = None,
) -> Dict:
    """单股票参数优化 — 局部搜索
    
    从自适应种子开始, 做迭代次局部爬山搜索。
    
    Returns:
        {
            'best_params': {...},
            'best_score': float,
            'best_stats': {...},
            'history': [每轮],
            'improvement': 相对种子提升%
        }
    """
    from .adaptive_params import calc_stock_params, detect_market_phase
    from .backtest_v11 import backtest_single_stock_v11
    
    # 自适应种子
    if seed_params is None:
        phase = detect_market_phase(ohlcv)
        seed_params = calc_stock_params(ohlcv, symbol=symbol, phase=phase, tf=tf)
    
    # 种子评分
    seed_result = backtest_single_stock_v11(ohlcv, symbol=symbol, params=seed_params, tf=tf)
    seed_stats = seed_result.get('stats', {})
    seed_score = calc_opt_score(seed_stats) if seed_stats else 0
    
    best_params = dict(seed_params)
    best_score = seed_score
    best_stats = dict(seed_stats)
    history = [{
        'iteration': 0,
        'score': round(seed_score, 2),
        'wr': seed_stats.get('win_rate', 0),
        'rr': seed_stats.get('avg_rr', 0),
        'n': seed_stats.get('n_trades', 0),
        'pf': seed_stats.get('profit_factor', 0),
        'params': best_params.copy(),
    }]
    
    log.info(f"Opt {symbol}: Seed score={seed_score:.2f} WR={seed_stats.get('win_rate','?')}% "
             f"RR={seed_stats.get('avg_rr','?')} N={seed_stats.get('n_trades','?')}")
    
    # 迭代搜索
    current_params = dict(seed_params)
    current_score = seed_score
    temperature = 0.5  # SA初始温度
    
    for iteration in range(1, iterations + 1):
        # 1. 产生新参数 (从当前或最优扰动)
        if random.random() < 0.7:
            candidate = _mutate_params(current_params, temperature)
        else:
            candidate = _mutate_params(best_params, temperature * 0.5)
        
        # 2. 回测
        bt_result = backtest_single_stock_v11(ohlcv, symbol=symbol, params=candidate, tf=tf)
        bt_stats = bt_result.get('stats', {})
        bt_score = calc_opt_score(bt_stats) if bt_stats else 0
        
        # 3. 接受/拒绝
        accept = False
        if bt_score > current_score:
            accept = True
        else:
            # SA概率接受
            delta = bt_score - current_score
            if delta < 0 and temperature > 0.01:
                prob = math.exp(delta / (temperature * max(seed_score, 1)))
                if random.random() < prob:
                    accept = True
        
        if accept:
            current_params = dict(candidate)
            current_score = bt_score
        
        # 更新最优
        if bt_score > best_score:
            best_params = dict(candidate)
            best_score = bt_score
            best_stats = dict(bt_stats)
            
            log.info(f"  [{iteration}/{iterations}] NEW BEST: score={bt_score:.2f} "
                     f"WR={bt_stats.get('win_rate',0)}% RR={bt_stats.get('avg_rr',0)}x "
                     f"N={bt_stats.get('n_trades',0)}")
        
        # 记录历史(每10轮)
        if iteration % 10 == 0 or iteration == iterations:
            history.append({
                'iteration': iteration,
                'score': round(bt_score, 2),
                'wr': bt_stats.get('win_rate', 0),
                'rr': bt_stats.get('avg_rr', 0),
                'n': bt_stats.get('n_trades', 0),
                'pf': bt_stats.get('profit_factor', 0),
                'accepted': accept,
            })
        
        # 降温
        temperature = max(0.01, temperature * 0.97)
    
    improvement = ((best_score - seed_score) / max(seed_score, 0.1) * 100) if seed_score > 0 else 0
    
    result = {
        'symbol': symbol,
        'tf': tf,
        'best_params': best_params,
        'best_score': round(best_score, 2),
        'best_stats': {
            'wr': best_stats.get('win_rate', 0),
            'rr': best_stats.get('avg_rr', 0),
            'n': best_stats.get('n_trades', 0),
            'pf': best_stats.get('profit_factor', 0),
        },
        'seed_score': round(seed_score, 2),
        'seed_stats': {
            'wr': seed_stats.get('win_rate', 0),
            'rr': seed_stats.get('avg_rr', 0),
            'n': seed_stats.get('n_trades', 0),
            'pf': seed_stats.get('profit_factor', 0),
        },
        'improvement_pct': round(improvement, 1),
        'history': history,
    }
    
    log.info(f"==> {symbol} optimized: {seed_score:.2f} → {best_score:.2f} "
             f"({improvement:+.1f}%)")
    
    return result


def _mutate_params(params: Dict, temperature: float) -> Dict:
    """对参数做随机扰动"""
    new_params = dict(params)
    n_mutations = max(1, int(random.gauss(2, 1)))  # 1-3个参数扰动
    
    keys = list(OPT_PARAM_RANGES.keys())
    chosen = random.sample(keys, min(n_mutations, len(keys)))
    
    for key in chosen:
        if key not in new_params:
            continue
        
        ranges = OPT_PARAM_RANGES[key]
        lo = ranges['lo']
        hi = ranges['hi']
        step = ranges['step']
        mutate = ranges.get('mutate', step)
        
        # 随机扰动
        current = new_params[key]
        delta = random.uniform(-mutate, mutate) * (0.5 + temperature)
        new_val = current + delta
        
        # 限制范围
        new_val = max(lo, min(hi, new_val))
        
        # Step对齐
        if step >= 1:
            new_val = round(new_val)
        else:
            new_val = round(new_val * (1 / step)) / (1 / step) * step + 0  # 避免-0
        
        new_params[key] = new_val
    
    return new_params


# ═══════════════════════════════════════════════════════════════════════
# Batch optimization
# ═══════════════════════════════════════════════════════════════════════

def batch_optimize_v11(
    symbol_list: List[str],
    tf: str = 'daily',
    iters_per_stock: int = 50,
    label: str = 'batch_opt',
    on_progress=None,
) -> Dict:
    """批量优化 — 每只股票独立搜索
    
    Args:
        symbol_list: 股票列表
        tf: 时间框架
        iters_per_stock: 每只股票迭代次数
        label: 标签
        on_progress: 回调
    
    Returns:
        {
            'per_stock': {symbol: opt_result},
            'summary': 汇总,
            'best_improvements': [...],
        }
    """
    from .rate_limiter import get_limiter
    from .tf_data import fetch_single_tf
    
    limiter = get_limiter(max_rps=3, max_concurrent=2)  # 优化时保守限流
    
    results = {}
    total = len(symbol_list)
    
    for i, symbol in enumerate(symbol_list):
        ohlcv = fetch_single_tf(symbol, interval=tf, bars=300, limiter=limiter)
        
        if not ohlcv or len(ohlcv) < 60:
            log.warning(f"{symbol}: insufficient data, skipping")
            if on_progress:
                on_progress(i + 1, total, symbol, None)
            continue
        
        # 优化
        opt_result = optimize_single_stock(ohlcv, symbol, tf, iters_per_stock)
        results[symbol] = opt_result
        
        if on_progress:
            on_progress(i + 1, total, symbol, opt_result)
        
        # 每5个保存中间结果
        if (i + 1) % 5 == 0:
            save_optimizer_state(results, label)
        
        # 批次延迟
        time.sleep(0.5)
        
        # 每10个长休息
        if (i + 1) % 10 == 0 and i + 1 < total:
            log.info(f"Long pause after {i+1} stocks...")
            time.sleep(3)
    
    # 保存最终结果
    save_optimizer_state(results, label)
    
    # 汇总
    improved = [r for r in results.values() if r.get('improvement_pct', 0) > 0]
    degraded = [r for r in results.values() if r.get('improvement_pct', 0) < -10]
    
    summary = {
        'n_total': total,
        'n_completed': len(results),
        'n_improved': len(improved),
        'n_degraded': len(degraded),
        'avg_improvement': round(
            sum(r.get('improvement_pct', 0) for r in results.values()) / len(results)
            if results else 0, 1
        ),
        'avg_wr': round(
            sum(r['best_stats']['wr'] for r in results.values()) / len(results)
            if results else 0, 1
        ),
        'avg_rr': round(
            sum(r['best_stats']['rr'] for r in results.values()) / len(results)
            if results else 0, 1
        ),
    }
    
    # 最佳改进
    ranked = sorted(
        results.values(),
        key=lambda r: r.get('improvement_pct', 0),
        reverse=True
    )
    
    return {
        'per_stock': results,
        'summary': summary,
        'best_improvements': [
            {
                'symbol': r['symbol'],
                'improvement': r.get('improvement_pct', 0),
                'seed_wr': r['seed_stats']['wr'],
                'best_wr': r['best_stats']['wr'],
            }
            for r in ranked[:10]
        ],
        'label': label,
    }


# ═══════════════════════════════════════════════════════════════════════
# State management
# ═══════════════════════════════════════════════════════════════════════

def save_optimizer_state(results: Dict, label: str):
    """保存优化中间状态"""
    # 保存每股票参数
    per_stock_params = {}
    for symbol, opt in results.items():
        per_stock_params[symbol] = {
            'params': opt.get('best_params'),
            'stats': opt.get('best_stats'),
            'score': opt.get('best_score'),
            'improvement': opt.get('improvement_pct'),
        }
    
    path = OUTPUT_DIR / f'per_stock_params_{label}.json'
    path.write_text(json.dumps(per_stock_params, ensure_ascii=False, indent=2))
    log.info(f"Per-stock params saved: {len(per_stock_params)} stocks")


def load_optimizer_state(label: str) -> Dict:
    """加载已保存的优化状态"""
    path = OUTPUT_DIR / f'per_stock_params_{label}.json'
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception as e:
            log.warning(f"Failed to load state: {e}")
    return {}


# ═══════════════════════════════════════════════════════════════════════
# Validation: run batch backtest with optimized params
# ═══════════════════════════════════════════════════════════════════════

def validate_optimized(
    symbol_list: List[str],
    optimized_params: Dict,  # {symbol: {params: {...}, ...}}
    tf: str = 'daily',
    label: str = 'validated',
) -> Dict:
    """用优化后的参数进行全量回测验证"""
    from .rate_limiter import get_limiter
    from .tf_data import fetch_single_tf
    from .backtest_v11 import backtest_single_stock_v11
    
    limiter = get_limiter(max_rps=3, max_concurrent=2)
    
    results = {}
    total = len(symbol_list)
    
    for i, symbol in enumerate(symbol_list):
        ohlcv = fetch_single_tf(symbol, interval=tf, bars=300, limiter=limiter)
        if not ohlcv or len(ohlcv) < 60:
            continue
        
        stock_params = optimized_params.get(symbol, {}).get('params', None)
        if not stock_params:
            continue
        
        bt = backtest_single_stock_v11(ohlcv, symbol=symbol, params=stock_params, tf=tf)
        results[symbol] = bt
        
        if (i + 1) % 10 == 0:
            log.info(f"[{i+1}/{total}] {symbol}: WR={bt.get('stats',{}).get('win_rate','?')}%")
    
    # 汇总
    all_stats = [r['stats'] for r in results.values() if r.get('stats')]
    total_trades = sum(s.get('n_trades', 0) for s in all_stats)
    total_wins = sum(s.get('n_wins', 0) for s in all_stats)
    overall_wr = total_wins / total_trades * 100 if total_trades > 0 else 0
    avg_rr = sum(s.get('avg_rr', 0) for s in all_stats) / len(all_stats) if all_stats else 0
    
    return {
        'overall': {
            'n_symbols': len(results),
            'n_trades': total_trades,
            'win_rate': round(overall_wr, 1),
            'avg_rr': round(avg_rr, 2),
            'label': label,
        },
        'per_symbol': results,
    }
