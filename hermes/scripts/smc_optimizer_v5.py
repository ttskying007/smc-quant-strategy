#!/usr/bin/env python3
"""
SMC V5 Optimizer — 全自动迭代优化引擎
========================================
目标: WR>80%, PF>5.0
迭代: >=100轮 (默认200)
股票: 每轮15只 (更多样本)
策略: 随机探索→遗传→局部搜索→自适应

V5创新:
  1. 24维参数空间 (vs V4的18维)
  2. 多策略变异 (3种模式自动切换)
  3. 自适应学习率 (stagnation时放大搜索)
  4. 精英保留 (Top3始终保留)
  5. 实时保存结果 (每轮写入)
  6. 自动重启恢复 (掉电不断)
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

# ════════ 参数工具 ════════

def random_params():
    p = {}
    for k, s in V5_PARAM_SPACE.items():
        if 'step' in s:
            v = s['min'] + random.random() * (s['max'] - s['min'])
            p[k] = round(v / s['step']) * s['step']
            p[k] = max(s['min'], min(s['max'], p[k]))
    return p

def default_params():
    return {k: s['default'] for k, s in V5_PARAM_SPACE.items()}

def mutate(params, rate=0.25, spread=0.15):
    p = dict(params)
    for k, s in V5_PARAM_SPACE.items():
        if random.random() < rate:
            if 'step' in s:
                delta = (s['max'] - s['min']) * spread * random.gauss(0, 1)
                p[k] = max(s['min'], min(s['max'], p[k] + delta))
                p[k] = round(p[k] / s['step']) * s['step']
    return p

def crossover(parents):
    p1, p2 = parents[0], parents[1]
    child = {}
    for k in V5_PARAM_SPACE:
        child[k] = p1[k] if random.random() < 0.5 else p2[k]
        if random.random() < 0.2:
            s = V5_PARAM_SPACE[k]
            if 'step' in s:
                delta = (s['max'] - s['min']) * 0.05 * random.gauss(0, 1)
                child[k] = max(s['min'], min(s['max'], child[k] + delta))
                child[k] = round(child[k] / s['step']) * s['step']
    return child

def big_mutate(params):
    """大幅变异 — 跳出局部最优"""
    p = dict(params)
    for k, s in V5_PARAM_SPACE.items():
        if random.random() < 0.5:
            v = s['min'] + random.random() * (s['max'] - s['min'])
            p[k] = round(v / s['step']) * s['step']
    return p

# ════════ V5 优化器 ════════

class V5Optimizer:
    def __init__(self, n_stocks=15, n_iters=200, resume=False):
        self.n_stocks = n_stocks
        self.n_iters = n_iters
        self.history = []
        self.best_score = -1
        self.best_params = None
        self.best_result = None
        self.gen = 0
        self.stagnation = 0
        self.stock_list = []
        self.start_time = time.time()
        self.mode = 'random'
        self.save_path = OPT_DIR / 'v5_optimizer_state.json'
        self.history_path = OPT_DIR / 'v5_results_history.json'
        self.best_path = OPT_DIR / 'v5_best_params.json'
        
        if resume and self.save_path.exists():
            self._load_state()
            
    def _save_state(self):
        state = {
            'gen': self.gen,
            'best_score': self.best_score,
            'best_params': self.best_params,
            'best_result': self.best_result,
            'stagnation': self.stagnation,
            'mode': self.mode,
            'elapsed': time.time() - self.start_time,
            'history_len': len(self.history),
        }
        with open(self.save_path, 'w') as f:
            json.dump(state, f, indent=2)
        with open(self.history_path, 'w') as f:
            json.dump(self.history, f)
        if self.best_params:
            with open(self.best_path, 'w') as f:
                json.dump({
                    'params': self.best_params,
                    'result': self.best_result,
                    'gen': self.gen,
                    'elapsed': time.time() - self.start_time,
                }, f, indent=2)
    
    def _load_state(self):
        try:
            with open(self.save_path) as f:
                state = json.load(f)
            self.gen = state['gen']
            self.best_score = state['best_score']
            self.best_params = state['best_params']
            self.best_result = state['best_result']
            self.stagnation = state['stagnation']
            self.mode = state['mode']
            self.start_time = time.time() - state.get('elapsed', 0)
            if self.history_path.exists():
                with open(self.history_path) as f:
                    self.history = json.load(f)
            print(f"  Resumed from gen {self.gen}, best_score={self.best_score}")
        except:
            print("  Failed to resume, starting fresh")
    
    def load_stocks(self):
        all_s = get_stock_list_v5()
        self.stock_list = [(s['symbol'], s.get('name','')) for s in all_s 
                          if not s.get('symbol','').startswith('*ST')]
        random.seed(int(time.time()))
        random.shuffle(self.stock_list)
        print(f"  Loaded {len(self.stock_list)} stocks")
    
    def evaluate(self, params):
        """评估一组参数 — 在N只股票上回测"""
        n = min(self.n_stocks * 2, len(self.stock_list))
        stocks = self.stock_list[:n]
        random.shuffle(stocks)
        stocks = stocks[:self.n_stocks]
        
        per_stock = []
        errors = 0
        
        for idx, (code, name) in enumerate(stocks):
            try:
                # 缓存检查
                cache_path = Path.home() / '.hermes' / 'kline_cache' / f"{code.replace('.','_')}_daily_300.json"
                if cache_path.exists():
                    with open(cache_path) as f:
                        bars = json.load(f)
                else:
                    bars = get_klines_v5(code, 'daily', 300)
                
                if not bars or len(bars) < 100:
                    errors += 1
                    continue
                
                # V5回测
                strict_trades = backtest_v5(bars, 'strict', params)
                total_trades = backtest_v5(bars, 'total', params)
                
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
                    'code': code, 'name': name,
                    'n_s': n_s, 'wr_s': round(wr_s,1), 'pf_s': round(pf_s,2), 'sr_s': round(sr_s,2), 'ret_s': round(ret_s,2),
                    'n_t': n_t, 'wr_t': round(wr_t,1), 'pf_t': round(pf_t,2),
                })
            except Exception as e:
                errors += 1
                continue
        
        # 评分
        result = compute_v5_score(per_stock)
        result['n_errors'] = errors
        result['n_stocks'] = len(per_stock)
        result['per_stock'] = per_stock
        result['params'] = params
        
        return result
    
    def run(self):
        print(f"\n{'='*60}")
        print(f"  SMC V5 Optimizer — 全自动迭代优化")
        print(f"  Iterations: {self.n_iters}  |  Stocks/round: {self.n_stocks}")
        print(f"  Params: {len(V5_PARAM_SPACE)} dimensions")
        print(f"  Max per-stock entries: unlimited")
        print(f"{'='*60}")
        
        self.load_stocks()
        
        # 验证基线
        if self.gen == 0:
            print("\n  [Gen 0] 评估默认参数...")
            def_params = default_params()
            result = self.evaluate(def_params)
            self.history.append(result)
            self.best_score = result['score']
            self.best_params = dict(def_params)
            self.best_result = result
            self._save_state()
            self._print_result(0, result)
            self.gen = 1
        
        # 使用固定stock pool保证可比性
        pool_size = min(self.n_stocks * 3, len(self.stock_list))
        pool = self.stock_list[:pool_size]
        
        while self.gen <= self.n_iters:
            gen_start = time.time()
            
            # ═══ 参数生成策略 ═══
            if self.gen <= 10:
                # 纯随机探索
                params = random_params()
                self.mode = 'explore'
            elif self.stagnation >= 8:
                # 深度停滞: 全面随机
                self.mode = 'burst'
                params = random_params()
                self.stagnation = 0
            elif self.stagnation >= 4:
                # 轻度停滞: 大幅变异
                self.mode = 'big_mutate'
                params = big_mutate(self.best_params)
                self.stagnation = 0
            elif self.gen <= 50:
                # 遗传阶段 (Top10)
                self.mode = 'genetic'
                top = sorted(self.history, key=lambda x:x['score'], reverse=True)[:10]
                if random.random() < 0.6 and len(top) >= 4:
                    p1 = top[random.randint(0,3)]['params']
                    p2 = top[random.randint(0,3)]['params']
                    params = crossover([p1, p2])
                else:
                    params = mutate(top[0]['params'], rate=0.3, spread=0.2)
            else:
                # 局部精细搜索
                self.mode = 'fine_tune'
                r = random.random()
                if r < 0.4 and self.best_params:
                    params = mutate(self.best_params, rate=0.15, spread=0.05)
                elif r < 0.7 and len(self.history) >= 10:
                    top = sorted(self.history, key=lambda x:x['score'], reverse=True)[:10]
                    p1 = top[random.randint(0,4)]['params']
                    p2 = top[random.randint(0,4)]['params']
                    params = crossover([p1, p2])
                else:
                    params = mutate(self.best_params, rate=0.3, spread=0.1)
            
            # ═══ 评估 ═══
            result = self.evaluate(params)
            self.history.append(result)
            
            # ═══ 更新最佳 ═══
            if result['score'] > self.best_score:
                improvement = result['score'] - self.best_score
                self.best_score = result['score']
                self.best_params = dict(params)
                self.best_result = result
                self.stagnation = 0
                
                if self.gen % 10 == 0 or improvement >= 5:
                    print(f"\n  ★★★ NEW BEST! gen={self.gen} score={result['score']:.1f} (+{improvement:.1f})")
            else:
                self.stagnation += 1
            
            # ═══ 进度输出 ═══
            elapsed = time.time() - gen_start
            total_elapsed = time.time() - self.start_time
            
            if self.gen % 5 == 0 or result['score'] > self.best_score - 0.5:
                self._print_result(self.gen, result)
            elif self.gen % 1 == 0:
                print(f"  [gen {self.gen}] sc={result['score']:.1f} wr={result.get('median_wr',0):.1f}% "
                      f"pf={result.get('median_pf',0):.1f} "
                      f"n={result.get('n_valid',0)} err={result.get('n_errors',0)} "
                      f"best={self.best_score:.1f} stg={self.stagnation} "
                      f"({elapsed:.1f}s)", end="\r")
            
            # ═══ 保存 ═══
            if self.gen % 10 == 0:
                self._save_state()
            
            self.gen += 1
        
        # 最终结果
        total_elapsed = time.time() - self.start_time
        print(f"\n\n{'='*60}")
        print(f"  SMC V5 Optimization Complete!")
        print(f"  Iterations: {self.gen-1} | Time: {total_elapsed/60:.1f}m")
        print(f"  Best Score: {self.best_score}")
        print(f"\n  Best Params:")
        for k, v in sorted(self.best_params.items()):
            print(f"    {k}: {v}")
        print(f"\n  Best Result:")
        for k in ['median_wr','median_pf','median_sr','high_wr_ratio',
                  'coverage','total_strict','n_valid']:
            if self.best_result and k in self.best_result:
                print(f"    {k}: {self.best_result[k]}")
        print(f"{'='*60}\n")
        
        self._save_state()
        
        # 写入报告
        report = [f"V5 Optimizer Report"]
        report.append(f"Iterations: {self.gen-1} | Time: {total_elapsed/60:.1f}m")
        report.append(f"Best Score: {self.best_score}")
        report.append(f"\nBest Params:")
        for k, v in sorted(self.best_params.items()):
            report.append(f"  {k}: {v}")
        report.append(f"\nBest Result:")
        for k in ['median_wr','median_pf','median_sr','high_wr_ratio',
                  'coverage','total_strict','n_valid']:
            if self.best_result and k in self.best_result:
                report.append(f"  {k}: {self.best_result[k]}")
        with open(OPT_DIR / 'v5_optimizer_report.txt', 'w') as f:
            f.write('\n'.join(report))
    
    def _print_result(self, gen, result):
        total_elapsed = time.time() - self.start_time
        print(f"  [gen {gen:3d}] score={result['score']:.1f} | "
              f"WR={result.get('median_wr',0):.1f}% | "
              f"PF={result.get('median_pf',0):.1f} | "
              f"SR={result.get('median_sr',0):.2f} | "
              f"HS={result.get('high_wr_ratio',0):.2f} | "
              f"N={result.get('n_valid',0)} | "
              f"best={self.best_score:.1f} stg={self.stagnation} "
              f"({total_elapsed/60:.1f}m)")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='V5 Optimizer')
    parser.add_argument('--iters', type=int, default=200)
    parser.add_argument('--stocks', type=int, default=15)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    
    opt = V5Optimizer(n_stocks=args.stocks, n_iters=args.iters, resume=args.resume)
    opt.run()