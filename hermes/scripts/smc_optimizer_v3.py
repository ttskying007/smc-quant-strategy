#!/usr/bin/env python3
"""
SMC Optimizer v3 — 基于V3.1共振引擎的200轮迭代优化
"""
import sys, os, json, random, math, time
from pathlib import Path
from collections import Counter

SMC_DIR = os.path.expanduser('~/.hermes/skills/trading/smc-engine/scripts')
sys.path.insert(0, SMC_DIR)
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))

for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_backtest_v2 import fetch_stock_list, fetch_klines, normalize_klines, compute_sharpe
from smc_engine_v3_1 import backtest_v3_1, detect_high_winrate_entries_v3_1

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v3'
OPT_DIR.mkdir(parents=True, exist_ok=True)

PARAM_SPACE = {
    'sl_atr_sl': {'min': 1.0, 'max': 3.5, 'default': 2.0, 'step': 0.1},
    'tp_atr_tp': {'min': 1.5, 'max': 4.0, 'default': 3.0, 'step': 0.1},
    'fvg_loose_threshold': {'min': 0.12, 'max': 0.20, 'default': 0.15, 'step': 0.01},
    'fvg_standard_threshold': {'min': 0.20, 'max': 0.35, 'default': 0.25, 'step': 0.01},
    'fvg_strict_threshold': {'min': 0.30, 'max': 0.50, 'default': 0.40, 'step': 0.01},
    'sweep_lookbacks': {'choices': ['8,12,15', '8,12,15,20', '10,15,20', '5,10,15,20,25']},
    'sweep_wick_min': {'min': 1.0, 'max': 2.5, 'default': 1.2, 'step': 0.1},
    'ob_proximity': {'min': 3, 'max': 15, 'default': 8, 'step': 1},
    'score_threshold': {'min': 3, 'max': 6, 'default': 4, 'step': 1},
    'choch_lookback': {'min': 8, 'max': 20, 'default': 12, 'step': 1},
}

TEST_STOCKS = 6  # 快速测试用
BENCHMARK_STOCKS = 30

class V3Optimizer:
    def __init__(self):
        self.history = []
        self.best_score = -1
        self.best_params = None
        self.best_result = None
        self.gen = 0
        self.stagnation = 0
        self.stock_list = []
    
    def load_stocks(self):
        all_s = fetch_stock_list()
        self.stock_list = [(s['symbol'], s.get('name','')) for s in all_s 
                          if not s.get('symbol','').startswith('*ST')]
        random.seed(42)
        random.shuffle(self.stock_list)
        print(f"  Loaded {len(self.stock_list)} stocks")
    
    def random_params(self):
        p = {}
        for k, s in PARAM_SPACE.items():
            if 'choices' in s:
                p[k] = random.choice(s['choices'])
            elif 'step' in s:
                v = s['min'] + random.random() * (s['max'] - s['min'])
                p[k] = round(v / s['step']) * s['step']
        return p
    
    def default_params(self):
        return {k: s['default'] for k, s in PARAM_SPACE.items()}
    
    def mutate(self, base=None, rate=0.3):
        p = dict(base or self.best_params or self.default_params())
        for k, s in PARAM_SPACE.items():
            if random.random() < rate:
                if 'choices' in s:
                    p[k] = random.choice(s['choices'])
                elif 'step' in s:
                    delta = (s['max'] - s['min']) * 0.1 * random.gauss(0, 1)
                    p[k] = max(s['min'], min(s['max'], p[k] + delta))
                    p[k] = round(p[k] / s['step']) * s['step']
        return p
    
    def crossover(self):
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
    
    def score_params(self, params, n_stocks=TEST_STOCKS):
        """评估一组参数"""
        total_trades = []
        errors = 0
        
        stocks = self.stock_list[:n_stocks]
        for idx, (code, name) in enumerate(stocks):
            try:
                bars = normalize_klines(fetch_klines(code, 'daily', 500))
                if len(bars) < 100:
                    errors += 1
                    continue
                
                # 使用V3.1引擎但用自定义参数会影响函数内部
                # 这里我们先回测标准V3.1，后面再细化
                trades = backtest_v3_1(bars)
                total_trades.extend(trades)
                
            except Exception as e:
                errors += 1
                continue
        
        n = len(total_trades)
        if n < 3:
            return {'score': 0, 'trades': 0, 'wr': 0, 'sharpe': 0}
        
        wins = [t for t in total_trades if t['pnl'] > 0]
        losses = [t for t in total_trades if t['pnl'] <= 0]
        wr = len(wins)/n*100
        ret = sum(t['pnl'] for t in total_trades)*100
        pf = abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 10.0
        
        returns = [t['pnl'] for t in total_trades]
        sharpe = compute_sharpe(returns, 252)
        
        # 评分: 核心奖励WR和Sharpe
        wr_score = min(50, wr * 0.6)  # WR 50% = 30, WR 80% = 48
        sharpe_score = min(40, sharpe * 20)  # Sharpe 1.0 = 20, Sharpe 2.0 = 40
        n_score = min(10, n * 0.2)  # 50笔 = 10分
        
        score = wr_score + sharpe_score + n_score
        
        if pf < 1.0:
            score *= 0.3
        
        return {
            'score': round(score, 1),
            'trades': n, 'wr': round(wr, 1),
            'sharpe': round(sharpe, 2),
            'pf': round(pf, 2),
            'ret': round(ret, 2),
            'n_stocks': n_stocks - errors,
        }
    
    def run(self, iterations=200, n_stocks=TEST_STOCKS):
        self.load_stocks()
        
        print(f"\n{'='*70}")
        print(f"  SMC V3.1 Optimizer")
        print(f"  Iterations: {iterations} | Stocks/iter: {n_stocks}")
        print(f"{'='*70}")
        
        start = time.time()
        
        for i in range(1, iterations + 1):
            self.gen = i
            
            # 参数生成
            if i <= 3:
                params = self.random_params()
            elif self.stagnation > 10:
                params = self.mutate(rate=0.5)
            elif random.random() < 0.3:
                params = self.random_params()
            elif random.random() < 0.5:
                params = self.crossover()
            else:
                params = self.mutate(rate=0.2)
            
            # 评估
            try:
                t0 = time.time()
                result = self.score_params(params, n_stocks)
                elapsed = time.time() - t0
                
                result['params'] = params
                result['iteration'] = i
                self.history.append(result)
                
                is_best = result['score'] > self.best_score
                if is_best:
                    self.best_score = result['score']
                    self.best_params = dict(params)
                    self.best_result = result
                    self.stagnation = 0
                else:
                    self.stagnation += 1
                
                marker = ' 🏆' if is_best else ''
                
                print(f"  iter {i:>4d}/{iterations} | "
                      f"score={result['score']:>5.1f}{marker} | "
                      f"WR={result['wr']:>4.1f}% | "
                      f"SR={result['sharpe']:>4.2f} | "
                      f"n={result['trades']:>3} | "
                      f"PF={result['pf']:>3.1f} | "
                      f"{elapsed:.1f}s")
                
                # Save every iteration
                entry = {
                    'iteration': i, 'score': result['score'],
                    'wr': result['wr'], 'sharpe': result['sharpe'],
                    'trades': result['trades'], 'params': params,
                    'best_score': self.best_score,
                    'best_params': self.best_params,
                }
                with open(OPT_DIR / f'iter_{i:04d}.json', 'w') as f:
                    json.dump(entry, f, ensure_ascii=False, indent=2)
            
            except Exception as e:
                print(f"  iter {i:>4d}: ERROR {str(e)[:60]}")
                import traceback; traceback.print_exc()
                continue
            
            # Progress
            if i % 20 == 0:
                elapsed = time.time() - start
                rate = i / elapsed
                remaining = (iterations - i) / rate
                print(f"\n  📊 [{i}/{iterations}] Rate: {rate:.2f}it/s | "
                      f"ETA: {remaining/60:.1f}min | Best: {self.best_score} | "
                      f"Stag: {self.stagnation}")
            
            # Early stop
            if self.stagnation > 30 and i > 50:
                print(f"\n  ⚡ Early stop at iter {i}")
                break
        
        # Final
        total = time.time() - start
        print(f"\n{'='*70}")
        print(f"  🏁 Done! {i} iters in {total/60:.1f}min")
        print(f"  Best score: {self.best_score}")
        if self.best_params:
            print(f"  Best WR: {self.best_result['wr']}%")
            print(f"  Best Sharpe: {self.best_result['sharpe']}")
            print(f"  Best params: {json.dumps(self.best_params, indent=2)}")
        print(f"{'='*70}")
        
        # Save final best
        with open(OPT_DIR / 'best_params.json', 'w') as f:
            json.dump({
                'best_score': self.best_score,
                'best_wr': self.best_result['wr'] if self.best_result else 0,
                'best_sharpe': self.best_result['sharpe'] if self.best_result else 0,
                'best_params': self.best_params,
                'total_iters': i,
            }, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    opt = V3Optimizer()
    opt.run(iterations=200, n_stocks=TEST_STOCKS)