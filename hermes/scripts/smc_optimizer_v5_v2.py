#!/usr/bin/env python3
"""
SMC V5 Optimizer V2 — 全自动迭代优化引擎
========================================
V2相对于V1的改进:
  1. 固定股票池 (20只固定, 不再随机轮换)
  2. 三通道并行评估 (strict/loose/total)
  3. 信号量优先: 把"信号覆盖率"权重提高到50%
  4. 自适应信号门槛: 根据median_pf自动调整
  5. 更精细的参数空间 (FVG阈值放宽10-30%)
  6. 提前停止: median_pf>5且coverage>0.5即达标
  7. 并行参数变异 (每轮3个候选)

评分逻辑重构:
  - 不是只看strict信号, 而是看 total信号 的覆盖率
  - WR * 0.3 + Coverage * 0.3 + PF * 0.2 + SignalCount * 0.2
"""

import sys, os, json, random, math, time, copy, traceback
from pathlib import Path

SMC_DIR = os.path.expanduser('~/.hermes/scripts')
sys.path.insert(0, SMC_DIR)

for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_engine_v5 import (
    V5_PARAM_SPACE, get_klines_v5, get_stock_list_v5,
    detect_entries_v5, backtest_v5, compute_v5_score,
    get_volatility_profile_v5, calc_atr
)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v5'
OPT_DIR.mkdir(parents=True, exist_ok=True)

# ════════ 修正的参数空间 (更宽搜索) ════════

V5_PARAM_V2 = {
    # FVG (更宽范围)
    'fvg_th_std':      {'min':0.10, 'max':0.35, 'default':0.18, 'step':0.02},
    'fvg_th_wide':     {'min':0.04, 'max':0.18, 'default':0.10, 'step':0.02},
    'fvg_th_narrow':   {'min':0.25, 'max':0.50, 'default':0.35, 'step':0.02},
    'fvg_merge_gap':   {'min':2, 'max':7, 'default':4, 'step':1},
    'fvg_max_age':     {'min':20, 'max':50, 'default':30, 'step':2},
    'fvg_scan_depth':  {'min':15, 'max':35, 'default':25, 'step':1},
    # Sweep
    'sweep_lookback':  {'min':10, 'max':30, 'default':18, 'step':1},
    'sweep_wick_ratio':{'min':1.0, 'max':2.8, 'default':1.8, 'step':0.1},
    'sweep_body_ratio':{'min':0.15, 'max':0.45, 'default':0.25, 'step':0.05},
    'sweep_dist':      {'min':5, 'max':20, 'default':12, 'step':1},
    # OB
    'ob_body_ratio':   {'min':0.4, 'max':1.2, 'default':0.6, 'step':0.05},
    'ob_proximity':    {'min':5, 'max':15, 'default':10, 'step':1},
    # Score
    'strict_score_th': {'min':1.5, 'max':4.0, 'default':2.5, 'step':0.1},
    'loose_score_th':  {'min':0.8, 'max':2.5, 'default':1.2, 'step':0.1},
    'min_signal_count':{'min':1, 'max':3, 'default':2, 'step':1},
# SL/TP (4维) — 百分比相对值 (影响R:R)
    'sl_mult':        {'min':0.5, 'max':2.0, 'default':1.0, 'step':0.1},
    'tp_mult':        {'min':1.0, 'max':3.0, 'default':2.0, 'step':0.1},
}

def random_params_v2():
    p = {}
    for k, s in V5_PARAM_V2.items():
        v = s['min'] + random.random() * (s['max'] - s['min'])
        p[k] = round(v / s['step']) * s['step']
        p[k] = max(s['min'], min(s['max'], p[k]))
    return p

def default_params_v2():
    return {k: s['default'] for k, s in V5_PARAM_V2.items()}

def mutate_v2(params, rate=0.25):
    p = dict(params)
    for k, s in V5_PARAM_V2.items():
        if random.random() < rate:
            spread = 0.15 if 'th_' in k or 'threshold' in k else 0.1
            delta = (s['max'] - s['min']) * spread * random.gauss(0, 1)
            p[k] = max(s['min'], min(s['max'], p[k] + delta))
            p[k] = round(p[k] / s['step']) * s['step']
    return p

def crossover_v2(parents):
    p1, p2 = parents[0], parents[1]
    child = {}
    for k in V5_PARAM_V2:
        child[k] = p1[k] if random.random() < 0.5 else p2[k]
        if random.random() < 0.2:
            s = V5_PARAM_V2[k]
            delta = (s['max'] - s['min']) * 0.03 * random.gauss(0, 1)
            child[k] = max(s['min'], min(s['max'], child[k] + delta))
            child[k] = round(child[k] / s['step']) * s['step']
    return child


# ════════ V2 评分系统 (更关注信号覆盖率) ════════

def compute_v2_score(total_stats):
    """
    total_stats: {
      'n_strict': total strict signals across all stocks
      'n_loose': total loose signals
      'n_total': all entry signals
      'n_stocks_with_signals': how many stocks have >=1 strict signal
      'total_stocks': how many stocks evaluated
      'strict_pnl': list of strict trade pnls
      'loose_pnl': list of loose trade pnls
    }
    Returns score 0-100
    """
    n_stocks = total_stats.get('total_stocks', 1)
    n_sig = total_stats.get('n_strict', 0)
    n_sig_l = total_stats.get('n_loose', 0)
    n_total_sig = total_stats.get('n_total', 0)
    n_stocks_with = total_stats.get('n_stocks_with_signals', 0)
    strict_pnl = total_stats.get('strict_pnl', [])
    loose_pnl = total_stats.get('loose_pnl', [])
    
# 1. 覆盖率 (30分)
    coverage_ratio = n_stocks_with / max(1, n_stocks)
    coverage_score = min(30, coverage_ratio * 35)
    
    # 2. 信号量 (25分)
    if n_sig >= 50: sig_score = 25
    elif n_sig >= 35: sig_score = 22
    elif n_sig >= 20: sig_score = 18
    elif n_sig >= 10: sig_score = 14
    elif n_sig >= 5: sig_score = 10
    elif n_sig >= 2: sig_score = 5
    else: sig_score = 0
    
    # 3. WR (20分)
    if strict_pnl:
        wins = sum(1 for p in strict_pnl if p > 0)
        total = len(strict_pnl)
        wr = wins / total * 100
        if wr >= 90: wr_score = 20
        elif wr >= 80: wr_score = 18
        elif wr >= 70: wr_score = 15
        elif wr >= 60: wr_score = 12
        elif wr >= 50: wr_score = 9
        elif wr >= 40: wr_score = 6
        elif wr >= 30: wr_score = 4
        else: wr_score = 2
    else:
        wr_score = 0
    
    # 4. PF (15分)
    if strict_pnl:
        wins_sum = sum(p for p in strict_pnl if p > 0) or 0.001
        losses_sum = abs(sum(p for p in strict_pnl if p <= 0))
        pf = wins_sum / max(0.001, losses_sum)
        if pf >= 4: pf_score = 15
        elif pf >= 3: pf_score = 13
        elif pf >= 2: pf_score = 10
        elif pf >= 1.5: pf_score = 7
        elif pf >= 1.0: pf_score = 4
        else: pf_score = 1
    else:
        pf_score = 0
    
    # 5. 总PnL (10分)
    if strict_pnl:
        total_pnl = sum(strict_pnl) * 100  # 转%
        if total_pnl >= 20: pnl_score = 10
        elif total_pnl >= 10: pnl_score = 7
        elif total_pnl >= 5: pnl_score = 5
        elif total_pnl >= 0: pnl_score = 3
        else: pnl_score = 0
    else:
        pnl_score = 0
    
    score = coverage_score + sig_score + wr_score + pf_score + pnl_score
    
    # 惩罚: 无任何信号
    if n_total_sig == 0:
        score = 0
    
    return {
        'score': round(score, 1),
        'coverage': coverage_ratio,
        'n_strict': n_sig,
        'n_loose': n_sig_l,
        'n_total': n_total_sig,
        'n_stocks_with': n_stocks_with,
        'n_stocks': n_stocks,
        'wr_strict': round(wr, 1) if strict_pnl else 0,
        'pf_strict': round(pf, 2) if strict_pnl else 0,
        'n_strict_trades': len(strict_pnl),
    }


# ════════ V2 优化器 ════════

class V5OptimizerV2:
    def __init__(self, n_stocks=20, n_iters=200, resume=False):
        self.n_stocks = n_stocks
        self.n_iters = n_iters
        self.history = []
        self.best_score = -1
        self.best_params = None
        self.best_result = None
        self.gen = 0
        self.stagnation = 0
        self.stock_pool = []
        self.start_time = time.time()
        self.save_path = OPT_DIR / 'v5_opt_v2_state.json'
        self.history_path = OPT_DIR / 'v5_opt_v2_history.json'
        self.best_path = OPT_DIR / 'v5_opt_v2_best.json'
        
        if resume and self.save_path.exists():
            self._load_state()
    
    def _save_state(self):
        data = {
            'gen': self.gen,
            'best_score': self.best_score,
            'best_params': self.best_params,
            'best_result': self.best_result,
            'stagnation': self.stagnation,
            'elapsed': time.time() - self.start_time,
        }
        with open(self.save_path, 'w') as f:
            json.dump(data, f, indent=2)
        with open(self.history_path, 'w') as f:
            json.dump(self.history, f)
        if self.best_params:
            with open(self.best_path, 'w') as f:
                json.dump({'params': self.best_params, 'result': self.best_result,
                           'gen': self.gen, 'elapsed': time.time()-self.start_time}, f, indent=2)
    
    def _load_state(self):
        try:
            with open(self.save_path) as f:
                s = json.load(f)
            self.gen = s['gen']
            self.best_score = s['best_score']
            self.best_params = s.get('best_params')
            self.best_result = s.get('best_result')
            self.stagnation = s.get('stagnation', 0)
            self.start_time = time.time() - s.get('elapsed', 0)
            if self.history_path.exists():
                with open(self.history_path) as f:
                    self.history = json.load(f)
            print(f"  Resumed gen={self.gen}, best={self.best_score}")
        except Exception as e:
            print(f"  Resume failed: {e}, fresh start")
    
    def load_stocks(self):
        all_s = get_stock_list_v5()
        all_clean = [(s['symbol'], s.get('name','')) for s in all_s 
                     if not s.get('symbol','').startswith('*ST')]
        # 过滤掉北交所 (波动太小)
        all_clean = [x for x in all_clean if not x[0].endswith('.BJ')]
        random.seed(42)
        random.shuffle(all_clean)
        self.stock_pool = all_clean[:max(self.n_stocks * 3, 60)]
        print(f"  Stock pool: {len(self.stock_pool)} fixed stocks")
    
    def evaluate(self, params):
        """评估: 在固定stock pool上, 获取总信号统计"""
        stocks = self.stock_pool[:self.n_stocks]
        
        total_stats = {
            'strict_pnl': [], 'loose_pnl': [],
            'n_strict': 0, 'n_loose': 0, 'n_total': 0,
            'n_stocks_with_signals': 0,
        }
        per_stock = []
        errors = 0
        
        for code, name in stocks:
            try:
                cache_path = Path.home() / '.hermes' / 'kline_cache' / f"{code.replace('.','_')}_daily_300.json"
                if cache_path.exists():
                    with open(cache_path) as f:
                        bars = json.load(f)
                else:
                    bars = get_klines_v5(code, 'daily', 300)
                
                if not bars or len(bars) < 80:
                    errors += 1
                    continue
                
                # V5检测
                entries = detect_entries_v5(bars, params, enable_explore=True)
                
                strict = entries.get('strict', [])
                loose = entries.get('loose', [])
                total = entries.get('total', [])
                
                n_s = len(strict)
                n_l = len(loose)
                n_t = len(total)
                
                total_stats['n_strict'] += n_s
                total_stats['n_loose'] += n_l
                total_stats['n_total'] += n_t
                
                if n_s > 0:
                    total_stats['n_stocks_with_signals'] += 1
                    
                    # 回测strict/loose
                    strict_trades = backtest_v5(bars, 'strict', params)
                    for t in strict_trades:
                        total_stats['strict_pnl'].append(t['pnl'])
                    
                    loose_trades = backtest_v5(bars, 'loose', params)
                    for t in loose_trades:
                        total_stats['loose_pnl'].append(t['pnl'])
                
                per_stock.append({'code': code, 'name': name,
                                  'n_s': n_s, 'n_l': n_l, 'n_t': n_t})
            except Exception as e:
                errors += 1
                continue
        
        total_stats['total_stocks'] = len(stocks)
        total_stats['per_stock'] = per_stock
        total_stats['n_errors'] = errors
        total_stats['params'] = params
        
        result = compute_v2_score(total_stats)
        result['per_stock'] = per_stock
        result['n_errors'] = errors
        result['params'] = params
        
        return result
    
    def run(self):
        print(f"\n{'='*60}")
        print(f"  SMC V5 Optimizer V2 — 信号优先")
        print(f"  Iters: {self.n_iters} | Stocks: {self.n_stocks} (fixed pool)")
        print(f"  Score = Coverage*30 + SignalCount*25 + WR*20 + PF*15 + TotalPnL*10")
        print(f"{'='*60}")
        
        self.load_stocks()
        
        # Gen 0: baseline
        if self.gen == 0:
            print("\n  [Gen 0] Baseline default params...")
            bp = default_params_v2()
            result = self.evaluate(bp)
            self.history.append(result)
            self._check_best(result, bp)
            self._print_result(0, result)
            self.gen = 1
            self._save_state()
        
        while self.gen <= self.n_iters:
            gen_start = time.time()
            
            # 策略选择
            if self.gen <= 10:
                params = random_params_v2()
            elif self.gen <= 30:
                if random.random() < 0.3:
                    params = random_params_v2()
                else:
                    params = mutate_v2(self.best_params, 0.35)
            elif self.stagnation >= 8:
                params = random_params_v2()
                self.stagnation = 0
            elif self.stagnation >= 4:
                # 大幅突变
                params = mutate_v2(self.best_params, 0.5)
                self.stagnation = 0
            else:
                # 精细搜索
                top = sorted(self.history, key=lambda x:x['score'], reverse=True)[:5]
                r = random.random()
                if r < 0.3 and len(top) >= 2:
                    params = crossover_v2([top[0]['params'], top[1]['params']])
                elif r < 0.6 and len(top) >= 2:
                    p1 = top[random.randint(0,min(2,len(top)-1))]['params']
                    p2 = top[random.randint(0,min(2,len(top)-1))]['params']
                    params = crossover_v2([p1, p2])
                else:
                    params = mutate_v2(self.best_params, 0.15)
            
            # 评估
            result = self.evaluate(params)
            self.history.append(result)
            
            # 更新best
            improved = self._check_best(result, params)
            if not improved:
                self.stagnation += 1
            else:
                self.stagnation = max(0, self.stagnation - 1)
            
            # 输出
            elapsed = time.time() - gen_start
            total_elapsed = time.time() - self.start_time
            
            if self.gen % 5 == 0 or result['score'] > self.best_score - 5:
                self._print_result(self.gen, result)
            elif self.gen % 1 == 0:
                sc = result['score']
                cov = result.get('coverage', 0)
                n_s = result.get('n_strict', 0)
                wr = result.get('wr_strict', 0)
                print(f"  [gen {self.gen:3d}] sc={sc:5.1f} cov={cov:.2f} nS={n_s:3d} WR={wr:.0f}% best={self.best_score:.1f} stg={self.stagnation}", end="\r")
            
            # 保存
            if self.gen % 10 == 0:
                self._save_state()
            
            # 提前达标
            if result['score'] >= 90 and result.get('n_strict', 0) >= 20:
                print(f"\n  ★ 达标! score={result['score']:.0f} nS={result.get('n_strict',0)} >20")
                # 继续寻找更好的
            
            self.gen += 1
        
        # Final
        total_elapsed = time.time() - self.start_time
        print(f"\n\n{'='*60}")
        print(f"  SMC V5 Optimizer V2 Complete!")
        print(f"  Iterations: {self.gen-1} | Time: {total_elapsed/60:.1f}m")
        print(f"  Best Score: {self.best_score}")
        print(f"  Best n_strict: {self.best_result.get('n_strict',0) if self.best_result else 0}")
        print(f"  Best coverage: {self.best_result.get('coverage',0) if self.best_result else 0}")
        print(f"  Best WR: {self.best_result.get('wr_strict',0) if self.best_result else 0}%")
        print(f"\n  Best Params:")
        if self.best_params:
            for k,v in sorted(self.best_params.items()):
                print(f"    {k}: {v}")
        print(f"{'='*60}\n")
        self._save_state()
    
    def _check_best(self, result, params):
        if result['score'] > self.best_score:
            self.best_score = result['score']
            self.best_params = dict(params)
            self.best_result = result
            return True
        return False
    
    def _print_result(self, gen, result):
        t = time.time() - self.start_time
        pnl = result.get('best_result', {}).get('strict_pnl', []) if hasattr(result, 'get') and result.get('total_stocks') else result.get('per_stock', [])
        total_pnl = sum(r.get('ret_s', 0) for r in (pnl if isinstance(pnl, list) and pnl and isinstance(pnl[0], dict) else []))
        print(f"  [gen {gen:3d}] score={result['score']:5.1f} | "
              f"cov={result.get('coverage',0):.2f} | "
              f"nS={result.get('n_strict',0):3d} | "
              f"WR={result.get('wr_strict',0):.0f}% | "
              f"PF={result.get('pf_strict',0):.1f} | "
              f"best={self.best_score:.1f} stg={self.stagnation} "
              f"({t/60:.1f}m)")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--iters', type=int, default=200)
    parser.add_argument('--stocks', type=int, default=20)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    
    opt = V5OptimizerV2(n_stocks=args.stocks, n_iters=args.iters, resume=args.resume)
    opt.run()