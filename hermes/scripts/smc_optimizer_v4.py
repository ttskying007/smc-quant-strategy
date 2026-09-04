#!/usr/bin/env python3
"""
SMC V4 Optimizer — 全自动迭代优化引擎
========================================
目标: WR>80%, PF>5.0 (V4 strict mode)

核心架构:
  1. 三层参数搜索空间 (18维)
  2. 混合策略: 随机探索→遗传→局部精细搜索
  3. 多股票交叉验证 (12只/轮)
  4. 自适应模式切换 (stagnation处理)
  5. 100-200轮迭代

参数空间:
  - FVG: threshold_std, threshold_wide, merge_max_gap
  - Sweep: lookback, wick_min, body_min_pct
  - Score: loose_th, strict_th, ms_bonus
  - SL/TP: sl_mult, tp_mult, sl_shrink, tp_expand
  - Entry: fvg_max_age, sweep_dist_pre, sweep_dist_post, ob_proximity
  
用法:
  python3 smc_optimizer_v4.py --iterations 200 --stocks 12
  python3 smc_optimizer_v4.py --resume  (从上次最佳继续)
"""

import sys, os, json, random, math, time, copy
from pathlib import Path

SMC_DIR = os.path.expanduser('~/.hermes/scripts')
sys.path.insert(0, SMC_DIR)

for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_engine_v4 import (
    get_klines, get_stock_list, detect_entries_v4,
    backtest_v4, evaluate, get_volatility_profile,
    get_adaptive_params, compute_v4_score
)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v4'
OPT_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════
# 参数空间 (18维)
# ═══════════════════════════════════════════

PARAM_SPACE = {
    # FVG参数 (6维)
    'fvg_threshold_std': {'min': 0.20, 'max': 0.50, 'default': 0.30, 'step': 0.02},
    'fvg_threshold_wide': {'min': 0.10, 'max': 0.30, 'default': 0.18, 'step': 0.02},
    'fvg_merge_gap': {'min': 2, 'max': 5, 'default': 3, 'step': 1},
    'fvg_min_strength': {'min': 1, 'max': 2, 'default': 1, 'step': 1},
    'fvg_max_age': {'min': 20, 'max': 40, 'default': 30, 'step': 2},
    'fvg_scan_depth': {'min': 15, 'max': 25, 'default': 20, 'step': 1},
    
    # Sweep参数 (4维)
    'sweep_lookback': {'min': 10, 'max': 25, 'default': 15, 'step': 1},
    'sweep_wick_min': {'min': 1.5, 'max': 3.0, 'default': 2.0, 'step': 0.1},
    'sweep_body_min': {'min': 0.2, 'max': 0.5, 'default': 0.3, 'step': 0.05},
    'sweep_dist_pre': {'min': 2, 'max': 8, 'default': 5, 'step': 1},
    'sweep_dist_post': {'min': 8, 'max': 20, 'default': 15, 'step': 1},
    
    # Score门槛 (3维)
    'score_loose_th': {'min': 1.5, 'max': 3.5, 'default': 2.5, 'step': 0.1},
    'score_strict_th': {'min': 3.0, 'max': 5.5, 'default': 4.0, 'step': 0.1},
    'strict_min_sigs': {'min': 2, 'max': 4, 'default': 3, 'step': 1},
    
    # SL/TP (4维)
    'sl_mult_base': {'min': 1.0, 'max': 3.0, 'default': 1.8, 'step': 0.1},
    'tp_mult_base': {'min': 1.5, 'max': 4.0, 'default': 2.5, 'step': 0.1},
    'sl_shrink_ratio': {'min': 0.3, 'max': 0.8, 'default': 0.5, 'step': 0.05},
    'tp_expand_ratio': {'min': 0.3, 'max': 0.8, 'default': 0.5, 'step': 0.05},
}

# ═══════════════════════════════════════════
# V4 优化器核心
# ═══════════════════════════════════════════

class V4Optimizer:
    def __init__(self):
        self.history = []
        self.best_score = -1
        self.best_params = None
        self.best_result = None
        self.gen = 0
        self.stagnation = 0
        self.stock_list = []
        self.start_time = time.time()
        self.mode = 'random'  # random → genetic → fine_tune
        self.total_iters = 0
        
    def load_stocks(self):
        """加载并打乱股票列表"""
        all_s = get_stock_list()
        self.stock_list = [(s['symbol'], s.get('name','')) for s in all_s 
                          if not s.get('symbol','').startswith('*ST')]
        random.seed(42)
        random.shuffle(self.stock_list)
        print(f"  Loaded {len(self.stock_list)} stocks")
    
    def random_params(self):
        """随机参数"""
        p = {}
        for k, s in PARAM_SPACE.items():
            if 'step' in s:
                v = s['min'] + random.random() * (s['max'] - s['min'])
                p[k] = round(v / s['step']) * s['step']
                p[k] = max(s['min'], min(s['max'], p[k]))
        return p
    
    def default_params(self):
        """默认参数"""
        return {k: s['default'] for k, s in PARAM_SPACE.items()}
    
    def to_v4_params(self, opt_params):
        """将优化参数转换为V4引擎可用的参数字典"""
        return {
            'fvg_threshold': opt_params.get('fvg_threshold_std', 0.30),
            'score_threshold': opt_params.get('score_loose_th', 2.5),
            'sl_mult': opt_params.get('sl_mult_base', 1.8),
            'tp_mult': opt_params.get('tp_mult_base', 2.5),
        }
    
    def mutate(self, base=None, rate=0.3):
        """变异"""
        p = dict(base or self.best_params or self.default_params())
        for k, s in PARAM_SPACE.items():
            if random.random() < rate:
                if 'step' in s:
                    delta = (s['max'] - s['min']) * 0.15 * random.gauss(0, 1)
                    p[k] = max(s['min'], min(s['max'], p[k] + delta))
                    p[k] = round(p[k] / s['step']) * s['step']
        return p
    
    def crossover(self):
        """交叉遗传"""
        if len(self.history) < 4:
            return self.random_params()
        top = sorted(self.history, key=lambda x: x['score'], reverse=True)[:3]
        p1, p2 = top[0]['params'], top[1]['params']
        child = {}
        for k in PARAM_SPACE:
            child[k] = p1[k] if random.random() < 0.5 else p2[k]
            if random.random() < 0.15:
                s = PARAM_SPACE[k]
                if 'step' in s:
                    delta = (s['max'] - s['min']) * 0.05 * random.gauss(0, 1)
                    child[k] = max(s['min'], min(s['max'], child[k] + delta))
                    child[k] = round(child[k] / s['step']) * s['step']
        return child
    
    def local_search(self, base=None, spread=0.05):
        """局部精细搜索"""
        p = dict(base or self.best_params or self.default_params())
        for k, s in PARAM_SPACE.items():
            if random.random() < 0.3:
                if 'step' in s:
                    delta = (s['max'] - s['min']) * spread * random.gauss(0, 1)
                    p[k] = max(s['min'], min(s['max'], p[k] + delta))
                    p[k] = round(p[k] / s['step']) * s['step']
        return p
    
    def score_params(self, params, n_stocks=12):
        """
        评估一组参数
        
        评分策略: 
        - 主要目标: strict模式 WR>80% 且 PF>5
        - 辅助目标: total模式有足够信号量
        - 使用中位数而非平均数
        """
        stocks = self.stock_list[:n_stocks * 2]
        random.shuffle(stocks)
        stocks = stocks[:n_stocks]
        
        per_stock = []
        errors = 0
        
        for idx, (code, name) in enumerate(stocks):
            try:
                bars = get_klines(code, 'daily', 600)
                if len(bars) < 120:
                    errors += 1
                    continue
                
                # 使用用户参数 + 自适应基础
                vol = get_volatility_profile(bars)
                base_params = get_adaptive_params(vol)
                
                # 合并: 用户参数覆盖自适应
                v4_params = {
                    'fvg_threshold': params['fvg_threshold_std'],
                    'score_threshold': params['score_loose_th'],
                    'sl_mult': params['sl_mult_base'],
                    'tp_mult': params['tp_mult_base'],
                }
                
                # 严格模式回测
                strict_trades = backtest_v4(bars, 'strict', v4_params)
                total_trades = backtest_v4(bars, 'total', v4_params)
                
                n_s = len(strict_trades)
                n_t = len(total_trades)
                
                if n_s > 0:
                    wins_s = [t for t in strict_trades if t['pnl']>0]
                    losses_s = [t for t in strict_trades if t['pnl']<=0]
                    wr_s = len(wins_s)/n_s*100
                    pf_s = abs(sum(t['pnl'] for t in wins_s)/sum(t['pnl'] for t in losses_s)) if losses_s and sum(t['pnl'] for t in losses_s)!=0 else 999
                    avg = sum(t['pnl'] for t in strict_trades)/n_s
                    std = math.sqrt(sum((t['pnl']-avg)**2 for t in strict_trades)/n_s) if n_s>1 else 0.001
                    sr_s = (avg/std)*math.sqrt(252) if std>0 else 0
                    ret_s = sum(t['pnl'] for t in strict_trades)*100
                else:
                    wr_s, pf_s, sr_s, ret_s = 0, 0, 0, 0
                
                if n_t > 0:
                    wins_t = [t for t in total_trades if t['pnl']>0]
                    losses_t = [t for t in total_trades if t['pnl']<=0]
                    wr_t = len(wins_t)/n_t*100
                    pf_t = abs(sum(t['pnl'] for t in wins_t)/sum(t['pnl'] for t in losses_t)) if losses_t and sum(t['pnl'] for t in losses_t)!=0 else 999
                else:
                    wr_t, pf_t = 0, 0
                
                per_stock.append({
                    'code': code,
                    'name': name,
                    'n_s': n_s, 'wr_s': wr_s, 'pf_s': pf_s, 'sr_s': sr_s, 'ret_s': ret_s,
                    'n_t': n_t, 'wr_t': wr_t, 'pf_t': pf_t,
                })
            except Exception as e:
                errors += 1
                continue
        
        if not per_stock:
            return {'score': 0, 'wr_s': 0, 'wr_t': 0, 'n_total': 0, 'per_stock': []}
        
        # ═══ V4评分 (核心!) ═══
        # 只评估有足够交易的股票
        valid_stocks = [s for s in per_stock if s['n_s'] >= 2 or s['n_t'] >= 5]
        if not valid_stocks:
            valid_stocks = [s for s in per_stock if s['n_s'] > 0 or s['n_t'] > 3]
        if not valid_stocks:
            valid_stocks = per_stock
        
        n_valid = len(valid_stocks)
        if n_valid == 0:
            return {'score': 0, 'wr_s': 0, 'wr_t': 0, 'n_total': 0, 'per_stock': per_stock}
        
        # 中位数WR (strict)
        wr_s_list = sorted([s['wr_s'] for s in valid_stocks if s['n_s'] > 0])
        median_wr_s = wr_s_list[len(wr_s_list)//2] if wr_s_list else 0
        
        # 中位数PF (strict)
        pf_s_list = sorted([s['pf_s'] for s in valid_stocks if s['n_s'] > 0])
        median_pf_s = pf_s_list[len(pf_s_list)//2] if pf_s_list else 0
        
        # 中位数Sharpe (strict)
        sr_s_list = sorted([s['sr_s'] for s in valid_stocks if s['n_s'] > 0])
        median_sr_s = sr_s_list[len(sr_s_list)//2] if sr_s_list else 0
        
        # 中位数WR (total)
        wr_t_list = sorted([s['wr_t'] for s in valid_stocks if s['n_t'] > 0])
        median_wr_t = wr_t_list[len(wr_t_list)//2] if wr_t_list else 0
        
        # WR>80%比例 (strict)
        high_wr_ratio = sum(1 for s in valid_stocks if s['n_s'] > 0 and s['wr_s'] >= 80) / max(1, n_valid)
        
        # WR>50%比例 (total)
        good_wr_t_ratio = sum(1 for s in valid_stocks if s['n_t'] > 0 and s['wr_t'] >= 50) / max(1, n_valid)
        
        # 有strict信号的股票比例
        has_strict_ratio = sum(1 for s in valid_stocks if s['n_s'] >= 2) / max(1, n_valid)
        
        # 总strict信号量 (用于覆盖率评分)
        n_strict_total = sum(s['n_s'] for s in valid_stocks)
        
        # ═══ 评分 ═══
        score = 0
        
        # 1. Strict WR (40分)
        if median_wr_s >= 90:
            score += 40
        elif median_wr_s >= 80:
            score += 35
        elif median_wr_s >= 70:
            score += 25
        elif median_wr_s >= 60:
            score += 15
        elif median_wr_s >= 50:
            score += 8
        else:
            score += max(0, median_wr_s * 0.15)
        
        # 2. WR>80%比例 (20分)
        score += min(20, high_wr_ratio * 25)
        
        # 3. Strict Sharpe (15分)
        if median_pf_s >= 5:
            score += 15
        elif median_pf_s >= 3:
            score += 12
        elif median_pf_s >= 2:
            score += 8
        elif median_pf_s >= 1.5:
            score += 5
        elif median_pf_s > 1:
            score += 3
        
        # 4. Total WR (15分)
        if median_wr_t >= 60:
            score += 15
        elif median_wr_t >= 50:
            score += 12
        elif median_wr_t >= 40:
            score += 8
        elif median_wr_t >= 30:
            score += 4
        
        # 5. 信号覆盖率 (15分) - 需要足够信号避免过拟合
        if n_strict_total >= 50 and has_strict_ratio >= 0.4:
            score += 15
        elif n_strict_total >= 30 and has_strict_ratio >= 0.3:
            score += 12
        elif n_strict_total >= 15 and has_strict_ratio >= 0.2:
            score += 8
        elif n_strict_total >= 8 and has_strict_ratio >= 0.1:
            score += 4
        else:
            score += max(1, n_strict_total * 0.3)  # 少量信号也给基础分
        
        # 6. Total good ratio bonus (加分)
        if good_wr_t_ratio >= 0.5:
            score += 5
        elif good_wr_t_ratio >= 0.3:
            score += 3
        
        # PF < 1.0  → 惩罚
        if median_pf_s < 1.0 and median_wr_s > 50:
            score *= 0.3
        
        return {
            'score': round(score, 1),
            'median_wr_s': round(median_wr_s, 1),
            'median_pf_s': round(median_pf_s, 2),
            'median_sr_s': round(median_sr_s, 2),
            'median_wr_t': round(median_wr_t, 1),
            'high_wr_ratio': round(high_wr_ratio, 2),
            'has_strict_ratio': round(has_strict_ratio, 2),
            'good_wr_t_ratio': round(good_wr_t_ratio, 2),
            'n_valid': n_valid,
            'n_strict': sum(s['n_s'] for s in per_stock),
            'n_total': sum(s['n_t'] for s in per_stock),
            'total_stocks': len(stocks) - errors,
            'per_stock': per_stock,
        }
    
    def run(self, iterations=200, n_stocks=12):
        """主运行循环"""
        self.load_stocks()
        
        print(f"\n{'='*70}")
        print(f"  SMC V4 Optimizer")
        print(f"  Iterations: {iterations} | Stocks/iter: {n_stocks}")
        print(f"  Target: Strict WR>80% PF>5.0")
        print(f"  Params: {len(PARAM_SPACE)}D")
        print(f"{'='*70}")
        
        start = time.time()
        
        for i in range(1, iterations + 1):
            self.gen = i
            self.total_iters = i
            
            # ═══ 动态模式切换 ═══
            progress = i / iterations
            
            if progress < 0.1:  # 初期: 大量随机
                if random.random() < 0.3:
                    params = self.default_params()
                else:
                    params = self.random_params()
            elif self.stagnation > 15:  # 停滞: 大幅变异
                params = self.mutate(self.best_params, rate=0.5) if self.best_params else self.random_params()
            elif progress < 0.3:  # 探索期: 随机+交叉
                if random.random() < 0.5:
                    params = self.random_params()
                elif random.random() < 0.5:
                    params = self.crossover()
                else:
                    params = self.mutate(self.best_params, 0.3) if self.best_params else self.random_params()
            elif progress < 0.6:  # 利用期: 遗传+变异
                r = random.random()
                if r < 0.3:
                    params = self.random_params()
                elif r < 0.6:
                    params = self.crossover()
                elif r < 0.8:
                    params = self.mutate(self.best_params, 0.2)
                else:
                    params = self.local_search(self.best_params, 0.03)
            else:  # 精细期: 局部搜索为主
                r = random.random()
                if r < 0.2:
                    params = self.random_params()
                elif r < 0.4:
                    params = self.crossover()
                elif r < 0.7:
                    params = self.mutate(self.best_params, 0.15)
                else:
                    params = self.local_search(self.best_params, 0.02)
            
            # ═══ 评估 ═══
            try:
                t0 = time.time()
                result = self.score_params(params, n_stocks)
                elapsed = time.time() - t0
                
                result['params'] = params
                result['iteration'] = i
                self.history.append(result)
                
                is_best = result['score'] > self.best_score
                if is_best and result['score'] > 0:
                    self.best_score = result['score']
                    self.best_params = dict(params)
                    self.best_result = result
                    self.stagnation = 0
                else:
                    self.stagnation += 1
                
                # 打印
                marker = ' 🏆' if is_best else ''
                score_str = f"score={result['score']:>5.1f}{marker}"
                wr_s = f"WR_s={result.get('median_wr_s',0):>4.1f}"
                pf_s = f"PF_s={result.get('median_pf_s',0):>3.1f}"
                wr_t = f"WR_t={result.get('median_wr_t',0):>4.1f}"
                n_counts = f"nS={result.get('n_strict',0):>2} nT={result.get('n_total',0):>3}"
                hr = f"WR80%={result.get('high_wr_ratio',0):.1%}"
                
                print(f"  iter {i:>4d}/{iterations} | {score_str} | {wr_s} | {pf_s} | {wr_t} | {n_counts} | {hr} | {elapsed:.1f}s")
                
                # 保存每次迭代
                self.save_iteration(i, params, result, is_best)
                
            except Exception as e:
                import traceback
                print(f"  iter {i:>4d}: ERROR {str(e)[:80]}")
                traceback.print_exc()
                continue
            
            # 进度报告
            if i % 20 == 0:
                elapsed = time.time() - start
                rate = i / elapsed
                remaining = (iterations - i) / max(0.01, rate)
                
                best_wr_s = self.best_result.get('median_wr_s', 0) if self.best_result else 0
                best_pf_s = self.best_result.get('median_pf_s', 0) if self.best_result else 0
                
                print(f"\n  📊 [{i}/{iterations}] {elapsed/60:.1f}min | "
                      f"Rate: {rate:.2f}it/s | ETA: {remaining/60:.1f}min | "
                      f"Best: score={self.best_score} WR_s={best_wr_s} PF_s={best_pf_s}")
        
        # ═══ 完成 ═══
        total_elapsed = time.time() - start
        print(f"\n{'='*70}")
        print(f"  🏁 SMC V4 Optimizer Completed!")
        print(f"    Iterations: {self.total_iters}")
        print(f"    Time: {total_elapsed/60:.1f}min")
        print(f"{'='*70}")
        
        if self.best_result:
            print(f"\n  🏆 Best Result:")
            print(f"    Score: {self.best_score}")
            print(f"    Strict WR (median): {self.best_result.get('median_wr_s', 0)}%")
            print(f"    Strict PF: {self.best_result.get('median_pf_s', 0)}")
            print(f"    Strict SR: {self.best_result.get('median_sr_s', 0)}")
            print(f"    Total WR (median): {self.best_result.get('median_wr_t', 0)}%")
            print(f"    WR>80% ratio: {self.best_result.get('high_wr_ratio', 0):.1%}")
            print(f"    N signals (strict): {self.best_result.get('n_strict', 0)}")
            print(f"    N signals (total): {self.best_result.get('n_total', 0)}")
            print(f"\n    Best Params:")
            for k, v in sorted(self.best_params.items()):
                vs = PARAM_SPACE[k]
                default = vs['default']
                flag = ' <<<' if v != default else ''
                print(f"      {k:>25s}: {v:>8.4f}{flag}")
        
        # 保存最终
        self.save_final()
        print(f"\n{'='*70}")
    
    def save_iteration(self, i, params, result, is_best):
        """保存单次迭代"""
        entry = {
            'iteration': i, 'score': result['score'],
            'wr_s': result.get('median_wr_s', 0),
            'pf_s': result.get('median_pf_s', 0),
            'sr_s': result.get('median_sr_s', 0),
            'wr_t': result.get('median_wr_t', 0),
            'n_strict': result.get('n_strict', 0),
            'n_total': result.get('n_total', 0),
            'high_wr_ratio': result.get('high_wr_ratio', 0),
            'params': params,
            'best_score': self.best_score,
            'stagnation': self.stagnation,
        }
        with open(OPT_DIR / f'iter_{i:04d}.json', 'w') as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    
    def save_final(self):
        """保存最终结果"""
        if not self.best_params or not self.best_result:
            return
        
        result = {
            'best_score': self.best_score,
            'best_wr_s': self.best_result.get('median_wr_s', 0),
            'best_pf_s': self.best_result.get('median_pf_s', 0),
            'best_sr_s': self.best_result.get('median_sr_s', 0),
            'best_wr_t': self.best_result.get('median_wr_t', 0),
            'best_high_wr_ratio': self.best_result.get('high_wr_ratio', 0),
            'best_n_strict': self.best_result.get('n_strict', 0),
            'best_n_total': self.best_result.get('n_total', 0),
            'best_params': self.best_params,
            'best_result': self.best_result,
            'total_iters': self.total_iters,
            'total_stocks': self.best_result.get('total_stocks', 0),
        }
        with open(OPT_DIR / 'best_params.json', 'w') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 也保存人类可读的
        with open(OPT_DIR / 'summary.txt', 'w') as f:
            f.write(f"SMC V4 Optimizer Results\n")
            f.write(f"{'='*50}\n")
            f.write(f"Best Score: {self.best_score}\n")
            f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"\nPerformance:\n")
            f.write(f"  Strict WR:  {self.best_result.get('median_wr_s', 0)}%\n")
            f.write(f"  Strict PF:  {self.best_result.get('median_pf_s', 0)}\n")
            f.write(f"  Strict SR:  {self.best_result.get('median_sr_s', 0)}\n")
            f.write(f"  Total WR:   {self.best_result.get('median_wr_t', 0)}%\n")
            f.write(f"  WR>80%:     {self.best_result.get('high_wr_ratio', 0):.1%}\n")
            f.write(f"  N(strict):  {self.best_result.get('n_strict', 0)}\n")
            f.write(f"  N(total):   {self.best_result.get('n_total', 0)}\n")
            f.write(f"\nBest Params:\n")
            for k, v in sorted(self.best_params.items()):
                default = PARAM_SPACE[k]['default']
                diff = ' <<<' if abs(v - default) > 0.01 else ''
                f.write(f"  {k:>25s}: {v:>8.4f}{diff}\n")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='SMC V4 Optimizer')
    parser.add_argument('--iterations', type=int, default=200, help='Iterations (default: 200)')
    parser.add_argument('--stocks', type=int, default=12, help='Stocks per iter (default: 12)')
    parser.add_argument('--resume', action='store_true', help='Resume from best')
    args = parser.parse_args()
    
    opt = V4Optimizer()
    
    if args.resume:
        # 从最佳参数继续
        best_file = OPT_DIR / 'best_params.json'
        if best_file.exists():
            with open(best_file) as f:
                data = json.load(f)
            if data.get('best_params'):
                opt.best_params = data['best_params']
                opt.best_score = data.get('best_score', 0)
                print(f"\n  Resuming from best: score={opt.best_score}")
                print(f"  Continuing for {args.iterations} more iterations")
    
    opt.run(iterations=args.iterations, n_stocks=args.stocks)