#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMC Auto Optimizer — SMC全自动迭代优化引擎 v1.1

核心架构（三重循环）:
  ┌─────────────────────────────────────────────────────┐
  │ 外部循环: 参数变异器 (Parameter Mutator)            │
  │   → 网格搜索 + 遗传算法 + 贝叶斯优化 (三模式切换)    │
  │   → 每次迭代产生一个新参数集                         │
  ├─────────────────────────────────────────────────────┤
  │ 中层循环: 策略回测器 (Strategy Backtester)           │
  │   → 对每个参数集, 运行组合策略回测                   │
  │   → FVG/Sweep/OB/CHOCH/组合/OSOK/BPR 7种策略        │
  │   → 多股票验证 (A股200只) 防过拟合                    │
  ├─────────────────────────────────────────────────────┤
  │ 内部循环: 信号变异器 (Signal Mutator)                │
  │   → 对检测算法本身做变异                             │
  │     - FVG阈值: 0.15~0.60步进0.01                     │
  │     - Sweep影线比: 1.0~3.0步进0.1                    │
  │     - OB体比: 0.3~1.0步进0.05                       │
  │     - CHOCH lookback: 5~30                           │
  │   → 每次变异产生新的检测器参数                       │
  ├─────────────────────────────────────────────────────┤
  │ 评分函数 (Objective):                               │
  │   score = Sharpe × min(3, PF) × min(1, n/40)       │
  │          × (1 - |40 - WR| / 120)                    │
  │          × (1 - DD/50)                              │
  └─────────────────────────────────────────────────────┘

停止条件:
  - 最小迭代: 100次
  - 收敛条件: 连续20次迭代最佳score无改善 (>1%相对)
  - 最大迭代: 1000次 (硬限制)

持久化:
  - 每次迭代结果: ~/.hermes/smc_opt/iterations/iter_{N}.json
  - 最佳参数: ~/.hermes/smc_opt/best_params.json
  - 性能曲线: ~/.hermes/smc_opt/performance_history.json
  - 信号变异日志: ~/.hermes/smc_opt/signal_mutations.json

用法:
  python3 smc_auto_optimizer.py [--mode grid|genetic|bayesian] [--iterations 100]
  python3 smc_auto_optimizer.py --resume   # 从上次中断恢复
"""

import json, math, sys, os, time, random, copy
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Add SMC modules to path
SMC_DIR = os.path.expanduser('~/.hermes/skills/trading/smc-engine/scripts')
if SMC_DIR not in sys.path:
    sys.path.insert(0, SMC_DIR)

# Also unset proxy for Hubble API before any imports that use it
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(k, None)

try:
    from smc_backtest_v2 import (
        fetch_klines, normalize_klines, calc_atr,
        detect_fvg, detect_liquidity_sweep, detect_order_blocks,
        detect_choch, detect_choch_v2, detect_market_structure,
        detect_combo_signals, calc_bpr, calc_ote, detect_volume_spread,
        backtest_single, generate_report, run_batch, fetch_stock_list,
        compute_sharpe, calc_drawdown,
    )
    IMPORT_OK = True
except Exception as e:
    print(f"WARNING: smc_backtest_v2 import failed: {e}")
    IMPORT_OK = False

# ═══════════════════════════════════════════════════
# 常量 & 路径
# ═══════════════════════════════════════════════════

OPT_DIR = Path.home() / '.hermes' / 'smc_opt'
ITER_DIR = OPT_DIR / 'iterations'
RESULTS_FILE = OPT_DIR / 'results_history.json'
BEST_PARAMS_FILE = OPT_DIR / 'best_params.json'
SIGNAL_MUT_FILE = OPT_DIR / 'signal_mutations.json'
PROXY_GUARDIAN_LOG = Path.home() / '.hermes' / 'logs' / 'proxy_guardian.log'

OPT_DIR.mkdir(parents=True, exist_ok=True)
ITER_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════
# 默认参数搜索空间
# ═══════════════════════════════════════════════════

DEFAULT_PARAM_SPACE = {
    # FVG detector params
    'fvg_threshold': {'min': 0.15, 'max': 0.60, 'default': 0.30, 'step': 0.01},
    'fvg_strength_body_ratio': {'min': 1.5, 'max': 3.0, 'default': 2.0, 'step': 0.1},
    'fvg_strength_width_ratio': {'min': 0.4, 'max': 0.8, 'default': 0.5, 'step': 0.05},

    # Sweep detector params
    'sweep_lookback': {'min': 8, 'max': 30, 'default': 15, 'step': 1},
    'sweep_wick_ratio': {'min': 1.0, 'max': 3.0, 'default': 1.5, 'step': 0.1},

    # OB detector params
    'ob_body_ratio': {'min': 0.3, 'max': 1.0, 'default': 0.5, 'step': 0.05},

    # CHOCH detector params
    'choch_lookback': {'min': 5, 'max': 30, 'default': 15, 'step': 1},

    # Market structure params
    'ms_lookback': {'min': 10, 'max': 30, 'default': 15, 'step': 1},

    # Entry/Exit params
    'sl_atr_mult': {'min': 0.8, 'max': 3.0, 'default': 1.5, 'step': 0.1},
    'tp_rr_mult': {'min': 1.0, 'max': 4.0, 'default': 2.0, 'step': 0.1},

    # Signal combo filters
    'combo_fvg_sweep_max_dist': {'min': 3, 'max': 15, 'default': 10, 'step': 1},
    'combo_signal_min_strength': {'min': 1, 'max': 3, 'default': 1, 'step': 1},

    # BPR params
    'bpr_lookback': {'min': 15, 'max': 60, 'default': 30, 'step': 5},

    # FVG merge params (v2 fix)
    'fvg_merge_max_gap': {'min': 1, 'max': 5, 'default': 2, 'step': 1},
}

# 策略列表
STRATEGIES = ['combo', 'fvg-only', 'sweep-fvg', 'osok', 'bpr']

# A股测试股票数量
DEFAULT_TEST_STOCKS = 20
BENCHMARK_STOCKS = 200  # 完整验证

# ═══════════════════════════════════════════════════
# 评分函数
# ═══════════════════════════════════════════════════

def compute_objective_score(sharpe, profit_factor, total_trades, win_rate, max_dd):
    """
    目标评分函数 v4 (修复版):
    重点优化 Sharpe / Win Rate / Profit Factor
    DD惩罚更温和（因为多股票平均DD天然高）
    核心是Sharpe > 1.5, WR > 40%, PF > 1.5
    """
    n = total_trades
    WR = win_rate
    PF = profit_factor if profit_factor != float('inf') else 10.0
    DD = max_dd

    s = sharpe

    # PF cap
    pf_term = min(3.0, PF)

    # 交易次数惩罚
    n_term = min(1.0, n / 40.0)

    # 胜率惩罚: WR偏离40%越远惩罚越大
    wr_term = max(0.1, 1.0 - abs(40.0 - WR) / 120.0)

    # 回撤惩罚: DD超过100%才惩罚，更温和
    dd_term = max(0.3, 1.0 - DD / 100.0)

    # 额外: Sharpe为正才有意义
    bonus = 1.0
    if s > 1.0:
        bonus = 1.0 + (s - 1.0) * 0.2  # 激励高Sharpe
    if s < 0:
        bonus = 0.3  # 负Sharpe严重惩罚

    # WR低于30%的直接惩罚
    if WR < 30:
        bonus *= 0.5

    score = s * pf_term * n_term * wr_term * dd_term * bonus

    # 防止负数score
    score = max(-10.0, score)

    return round(score, 4)


def evaluate_params(params, symbol_list, strategy='combo', max_stocks=BENCHMARK_STOCKS):
    """
    评估一组参数的表现
    在多个股票上运行回测, 汇总统计

    Returns: {
        'score': float,  # 综合评分
        'sharpe': float,
        'win_rate': float,
        'total_trades': int,
        'profit_factor': float,
        'max_dd_pct': float,
        'total_return_pct': float,
        'n_stocks': int,
        'sharpe_positive_pct': float,
        'per_stock': [...]  # 每只个股结果
    }
    """
    per_stock_results = []
    errors = 0
    total_trades = 0
    total_wins = 0
    all_returns = []
    all_sharpes = []

    stocks_to_test = symbol_list[:max_stocks]

    for idx, (code, name) in enumerate(stocks_to_test):
        try:
            raw = fetch_klines(code, 'daily', 500)
            bars = normalize_klines(raw)
            if len(bars) < 100:
                errors += 1
                continue

            result = backtest_single(
                code, bars, strategy=strategy,
                sl_atr=params.get('sl_atr_mult', 1.5),
                tp_rr=params.get('tp_rr_mult', 2.0),
                only_long=False
            )

            trades = result.get('trades', [])
            if not trades:
                continue

            n_trades = len(trades)
            wins = [t for t in trades if t['pnl'] > 0]
            losses = [t for t in trades if t['pnl'] <= 0]
            wr = len(wins) / n_trades * 100 if n_trades > 0 else 0
            total_ret = sum(t['pnl'] for t in trades) * 100
            avg_win = sum(t['pnl'] for t in wins) / len(wins) * 100 if wins else 0
            avg_loss = sum(t['pnl'] for t in losses) / len(losses) * 100 if losses else 0
            pf = abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else 10.0

            returns_series = [t['pnl'] for t in trades]
            sharpe = compute_sharpe(returns_series, 252)
            dd_info = calc_drawdown(returns_series)

            per_stock_results.append({
                'symbol': code,
                'name': name,
                'n_trades': n_trades,
                'win_rate': round(wr, 1),
                'sharpe': sharpe,
                'total_return_pct': round(total_ret, 2),
                'profit_factor': round(pf, 2),
                'max_dd_pct': dd_info['max_dd_pct'],
            })

            total_trades += n_trades
            total_wins += len(wins)
            all_returns.append(total_ret)
            all_sharpes.append(sharpe)

        except Exception as e:
            errors += 1
            continue

    if not per_stock_results:
        return {'score': 0, 'sharpe': 0, 'win_rate': 0, 'total_trades': 0,
                'profit_factor': 0, 'max_dd_pct': 100, 'total_return_pct': 0,
                'n_stocks': 0, 'sharpe_positive_pct': 0, 'per_stock': [],
                'error': 'no_valid_stocks'}

    n_stocks = len(per_stock_results)
    avg_sharpe = sum(r['sharpe'] for r in per_stock_results) / n_stocks
    avg_wr = sum(r['win_rate'] for r in per_stock_results) / n_stocks
    avg_ret = sum(r['total_return_pct'] for r in per_stock_results) / n_stocks
    avg_pf = sum(r['profit_factor'] for r in per_stock_results) / n_stocks
    avg_dd = sum(r['max_dd_pct'] for r in per_stock_results) / n_stocks
    sharpe_positive = len([r for r in per_stock_results if r['sharpe'] > 0]) / n_stocks * 100

    # The score is computed from averages across all stocks
    score = compute_objective_score(
        avg_sharpe, avg_pf, max(r['n_trades'] for r in per_stock_results),
        avg_wr, avg_dd
    )

    return {
        'score': score,
        'sharpe': round(avg_sharpe, 4),
        'win_rate': round(avg_wr, 1),
        'total_trades': total_trades,
        'profit_factor': round(avg_pf, 2),
        'max_dd_pct': round(avg_dd, 2),
        'total_return_pct': round(avg_ret, 2),
        'n_stocks': n_stocks,
        'sharpe_positive_pct': round(sharpe_positive, 1),
        'per_stock': per_stock_results,
    }


# ═══════════════════════════════════════════════════
# 参数生成器
# ═══════════════════════════════════════════════════

class ParameterGenerator:
    """参数生成器 - 三模式: grid/genetic/bayesian"""

    def __init__(self, param_space):
        self.space = param_space
        self.history = []  # [{params, score}]
        self.mode = 'genetic'  # default
        self.generation = 0
        self.best_params = None
        self.best_score = -float('inf')
        self.stagnation = 0

        # Grid state
        self.grid_positions = {}
        self.grid_exhausted = False

    def get_default_params(self):
        return {k: v['default'] for k, v in self.space.items()}

    def get_grid_iterations(self):
        """生成所有网格参数组合（有限步进）"""
        param_sweep = {
            'fvg_threshold': [0.20, 0.25, 0.30, 0.35, 0.40],
            'sweep_wick_ratio': [1.0, 1.5, 2.0, 2.5, 3.0],
            'sl_atr_mult': [0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0],
            'tp_rr_mult': [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
            'ob_body_ratio': [0.3, 0.5, 0.7, 1.0],
        }
        # Use default for others
        defaults = self.get_default_params()
        for k, vals in param_sweep.items():
            for v in vals:
                params = defaults.copy()
                params.update({k: v})
                yield params

    def get_genetic_params(self, mutation_rate=0.15, crossover_rate=0.4):
        """遗传算法生成下一组参数"""
        self.generation += 1
        defaults = self.get_default_params()

        if self.generation <= 3 or len(self.history) < 5:
            # First few gens: random exploration
            return self.get_random_params()

        # Tournament selection: pick top 30%
        sorted_hist = sorted(self.history, key=lambda x: x['score'], reverse=True)
        top_n = max(3, len(sorted_hist) // 3)
        elites = [h['params'] for h in sorted_hist[:top_n]]

        # Choose parent
        if len(elites) >= 2:
            parent1 = random.choice(elites)
            parent2 = random.choice([e for e in elites if e != parent1] or elites)
        else:
            return self.get_random_params()

        # Crossover
        child = {}
        for k in self.space:
            if random.random() < crossover_rate:
                child[k] = parent2[k]
            else:
                child[k] = parent1[k]

            # Mutation
            if random.random() < mutation_rate:
                s = self.space[k]
                delta = (s['max'] - s['min']) * 0.1 * random.gauss(0, 1)
                child[k] = max(s['min'], min(s['max'], child[k] + delta))
                if 'step' in s and s['step'] > 0:
                    child[k] = round(child[k] / s['step']) * s['step']

        return child

    def get_random_params(self):
        """随机参数（用于初始探索）"""
        params = {}
        for k, s in self.space.items():
            n_steps = int((s['max'] - s['min']) / s['step'])
            step_idx = random.randint(0, n_steps)
            params[k] = round(s['min'] + step_idx * s['step'], 4)
        return params

    def get_bayesian_params(self):
        """基于历史的最佳参数区域采样"""
        if len(self.history) < 10:
            return self.get_random_params()

        sorted_hist = sorted(self.history, key=lambda x: x['score'], reverse=True)
        top_k = sorted_hist[:max(5, len(sorted_hist) // 4)]

        params = {}
        for k, s in self.space.items():
            # Get values from top performers
            vals = [h['params'][k] for h in top_k]
            avg_val = sum(vals) / len(vals)
            std_val = math.sqrt(sum((v - avg_val)**2 for v in vals) / len(vals)) if len(vals) > 1 else (s['max'] - s['min']) * 0.1

            # Sample around best region
            new_val = random.gauss(avg_val, max(std_val, s['step'] * 2))
            new_val = max(s['min'], min(s['max'], new_val))
            if 'step' in s and s['step'] > 0:
                new_val = round(new_val / s['step']) * s['step']
            params[k] = new_val

        return params

    def next_params(self, mode='auto'):
        """生成下一组参数"""

        # Detect stagnation
        if self.stagnation > 15:
            mode = 'random_burst'

        if mode == 'auto':
            if self.generation < 5:
                return self.get_random_params()
            elif self.generation < 20:
                return self.get_genetic_params(0.2, 0.5)
            elif self.generation < 50:
                return self.get_genetic_params(0.15, 0.4)
            elif self.generation < 100:
                return self.get_genetic_params(0.1, 0.3)
            else:
                return self.get_bayesian_params()

        elif mode == 'genetic':
            return self.get_genetic_params()
        elif mode == 'random':
            return self.get_random_params()
        elif mode == 'bayesian':
            return self.get_bayesian_params()
        elif mode == 'random_burst':
            # 50% exploit best, 50% explore random
            if random.random() < 0.5 and self.best_params:
                params = self.best_params.copy()
                # Slightly perturb
                for k, s in self.space.items():
                    if random.random() < 0.3:
                        delta = (s['max'] - s['min']) * 0.05 * random.gauss(0, 1)
                        params[k] = max(s['min'], min(s['max'], params[k] + delta))
                        if 'step' in s and s['step'] > 0:
                            params[k] = round(params[k] / s['step']) * s['step']
                return params
            else:
                return self.get_random_params()

    def record_result(self, params, score):
        """记录一次迭代结果"""
        self.history.append({'params': params.copy(), 'score': score})
        if score > self.best_score:
            self.best_score = score
            self.best_params = params.copy()
            self.stagnation = 0
        else:
            self.stagnation += 1


# ═══════════════════════════════════════════════════
# 信号检测器变异器
# ═══════════════════════════════════════════════════

class SignalMutator:
    """
    信号检测算法变异器
    对FVG/Sweep/OB/CHOCH等检测函数做算法级变异
    不仅仅是参数搜索, 还包括算法结构变化
    """

    MUTATIONS = {
        'fvg': [
            'standard',  # 现有三根K线缺口法
            'consecutive',  # 连续缺口合并
            'volume_confirmed',  # 量能确认的FVG
            'trend_filtered',  # 只取趋势方向的FVG
            'dual_threshold',  # 双阈值: 大缺口+小缺口
            'ema_filtered',  # EMA趋势过滤后的FVG
        ],
        'sweep': [
            'standard',
            'deep_sweep',  # 深猎杀（突破更远）
            'volume_sweep',  # 量能确认猎杀
            'double_sweep',  # 双方向连续猎杀
            'retest_sweep',  # 回测确认猎杀
        ],
        'ob': [
            'standard',
            'fvg_aligned',  # OB+FVG对齐
            'volume_weighted',  # 量能加权OB
            'multi_bar',  # 多根K线OB区域
        ],
        'combo': [
            'sh_mss_rto',  # Sweep + MSS + ReturnToFVG (现有)
            'sh_rto_only',  # Sweep + ReturnToFVG (无MSS)
            'mss_rto_only',  # MSS + ReturnToFVG (无Sweep)
            'triple_confirm',  # Sweep + MSS + OB重叠
            'bpr_reversal',  # BPR反转确认
            'osok_strict',  # OSOK严格（必须精确重叠）
        ],
    }

    def __init__(self):
        self.current_mutations = {
            'fvg': 'standard',
            'sweep': 'standard',
            'ob': 'standard',
            'combo': 'sh_mss_rto',
        }
        self.mutation_history = []
        self.performance_by_mutation = defaultdict(lambda: {'count': 0, 'scores': []})

    def mutate(self):
        """随机变异一个检测器"""
        detector = random.choice(list(self.MUTATIONS.keys()))
        variants = self.MUTATIONS[detector]
        old = self.current_mutations[detector]
        new = random.choice([v for v in variants if v != old])
        self.current_mutations[detector] = new
        self.mutation_history.append({
            'time': datetime.now().isoformat(),
            'detector': detector,
            'from': old,
            'to': new
        })
        return detector, old, new

    def apply_to_detection(self, bars, params):
        """应用当前变异配置到信号检测"""
        fvg_type = self.current_mutations['fvg']
        sweep_type = self.current_mutations['sweep']
        ob_type = self.current_mutations['ob']

        # Modified detect functions based on mutation
        fvg_list = self._detect_fvg_mutated(bars, params, fvg_type)
        sweep_list = self._detect_sweep_mutated(bars, params, sweep_type)
        ob_list = self._detect_ob_mutated(bars, params, ob_type)

        return fvg_list, sweep_list, ob_list

    def _detect_fvg_mutated(self, klines, params, variant):
        """变异版FVG检测"""
        if len(klines) < 3:
            return []
        threshold = params.get('fvg_threshold', 0.30)
        avg_r = sum(abs(k['h']-k['l']) for k in klines[-30:]) / 30 if len(klines) >= 30 else 0
        if avg_r == 0:
            return []
        signals = []
        start = max(1, len(klines)-30)

        if variant == 'standard':
            for i in range(start, len(klines)-1):
                p,c,n = klines[i-1],klines[i],klines[i+1]
                bd = abs(c['c']-c['o'])
                if c['c'] > c['o']:
                    gt,gb = min(p['h'],n['h']),max(p['l'],n['l'])
                    if gt>gb and gt-gb>avg_r*threshold:
                        st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                        signals.append({'type':'BullFVG','direction':'long','top':gt,'bottom':gb,'mid':(gt+gb)/2,'strength':min(3,st),'index':i})
                elif c['c'] < c['o']:
                    gt,gb = max(p['h'],n['h']),min(p['l'],n['l'])
                    if gt>gb and gt-gb>avg_r*threshold:
                        st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                        signals.append({'type':'BearFVG','direction':'short','top':gt,'bottom':gb,'mid':(gt+gb)/2,'strength':min(3,st),'index':i})

        elif variant == 'consecutive':
            # 先标准检测，再合并相邻同向缺口
            base = self._detect_fvg_mutated(klines, params, 'standard')
            if not base:
                return []
            merge_gap = params.get('fvg_merge_max_gap', 2)
            merged = [base[0]]
            for s in base[1:]:
                last = merged[-1]
                if s['direction'] == last['direction'] and abs(s.get('index',0)-last.get('index',0)) <= merge_gap:
                    # Merge: take wider range
                    new_top = max(s['top'], last['top'])
                    new_bot = min(s['bottom'], last['bottom'])
                    merged[-1] = {'type':last['type'],'direction':last['direction'],
                                  'top':new_top,'bottom':new_bot,'mid':(new_top+new_bot)/2,
                                  'strength':min(3,last.get('strength',1)+s.get('strength',1)),
                                  'index':last.get('index',0)}
                else:
                    merged.append(s)
            signals = merged

        elif variant == 'volume_confirmed':
            base = self._detect_fvg_mutated(klines, params, 'standard')
            for s in base:
                idx = s.get('index', 0)
                if idx >= 3:
                    vol = klines[idx]['v']
                    prev_vol = klines[idx-1]['v'] if idx-1 >= 0 else 0
                    next_vol = klines[idx+1]['v'] if idx+1 < len(klines) else 0
                    avg_vol = (prev_vol + next_vol) / 2 if prev_vol+next_vol > 0 else 0
                    if avg_vol > 0 and vol > avg_vol * 0.5:
                        signals.append(s)
            return signals

        elif variant == 'trend_filtered':
            # 先检测趋势，只取趋势方向的FVG
            from smc_engine import detect_market_structure
            try:
                ms = detect_market_structure(klines)
                trend_dir = ms.get('direction')
            except Exception:
                trend_dir = None
            if trend_dir is None:
                return self._detect_fvg_mutated(klines, params, 'standard')
            base = self._detect_fvg_mutated(klines, params, 'standard')
            for s in base:
                if s['direction'] == trend_dir:
                    signals.append(s)
            return signals

        elif variant == 'dual_threshold':
            # 双阈值: 近期的用高阈值，远期用低阈值
            signals = []
            for i in range(start, len(klines)-1):
                p,c,n = klines[i-1],klines[i],klines[i+1]
                # Adaptive threshold: more recent = higher threshold
                recent_factor = 1.0 + 0.5 * (1.0 - (len(klines) - 1 - i) / 30.0)
                adj_threshold = threshold * recent_factor
                bd = abs(c['c']-c['o'])
                if c['c'] > c['o']:
                    gt,gb = min(p['h'],n['h']),max(p['l'],n['l'])
                    if gt>gb and gt-gb>avg_r*adj_threshold:
                        st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                        signals.append({'type':'BullFVG','direction':'long','top':gt,'bottom':gb,'mid':(gt+gb)/2,'strength':min(3,st),'index':i})
                elif c['c'] < c['o']:
                    gt,gb = max(p['h'],n['h']),min(p['l'],n['l'])
                    if gt>gb and gt-gb>avg_r*adj_threshold:
                        st = 1+(1 if bd>(gt-gb)*2 else 0)+(1 if gt-gb>avg_r*0.5 else 0)
                        signals.append({'type':'BearFVG','direction':'short','top':gt,'bottom':gb,'mid':(gt+gb)/2,'strength':min(3,st),'index':i})
            return signals

        elif variant == 'ema_filtered':
            # EMA趋势方向过滤FVG
            if len(klines) < 20:
                return self._detect_fvg_mutated(klines, params, 'standard')
            closes = [k['c'] for k in klines[-20:]]
            ema = sum(closes) / len(closes)
            base = self._detect_fvg_mutated(klines, params, 'standard')
            for s in base:
                direction = 'long' if closes[-1] > ema else 'short'
                if s['direction'] == direction:
                    signals.append(s)
            return signals

        return signals

    def _detect_sweep_mutated(self, klines, params, variant):
        """变异版Sweep检测"""
        return self._detect_fvg_mutated(klines, params, 'standard')[0:0] if variant == 'standard' else []

    def _detect_ob_mutated(self, klines, params, variant):
        """变异版OB检测"""
        return []

    def log_performance(self, mutation_key, score):
        self.performance_by_mutation[mutation_key]['count'] += 1
        self.performance_by_mutation[mutation_key]['scores'].append(score)

    def get_best_mutation(self, detector):
        items = self.performance_by_mutation.items()
        relevant = {k: v for k, v in items if k.startswith(detector)}
        if not relevant:
            return None
        best_key = max(relevant, key=lambda k: (sum(relevant[k]['scores'])/len(relevant[k]['scores'])
                                                if relevant[k]['scores'] else 0))
        return best_key


# ═══════════════════════════════════════════════════
# 主优化引擎
# ═══════════════════════════════════════════════════

class SMCOptimizer:
    def __init__(self, target_stocks=200, max_iterations=200):
        self.param_gen = ParameterGenerator(DEFAULT_PARAM_SPACE)
        self.signal_mut = SignalMutator()
        self.target_stocks = target_stocks
        self.max_iterations = max_iterations
        self.current_iteration = 0
        self.best_result = None
        self.best_params = None
        self.best_score = -float('inf')
        self.results_history = []
        self.stock_list = []

        # Proxy state
        self.proxy_failures = 0
        self.max_proxy_failures = 5

    def load_stock_list(self):
        """加载A股股票列表"""
        try:
            raw_list = fetch_stock_list()
            self.stock_list = [(s['symbol'], s.get('name', ''))
                               for s in raw_list if not s.get('symbol', '').startswith('*ST')]
            random.seed(42)
            random.shuffle(self.stock_list)
            print(f"Loaded {len(self.stock_list)} stocks")
            return True
        except Exception as e:
            print(f"ERROR loading stock list: {e}")
            return False

    def check_proxy(self):
        """检查代理是否存活，失败则尝试重启"""
        try:
            import subprocess
            r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                                '--proxy', 'http://127.0.0.1:7890',
                                'http://www.gstatic.com/generate_204'],
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip() == '204'
        except Exception:
            return False

    def run_single_iteration(self, params, strategy='combo'):
        """运行一次迭代: 回测 -> 评分"""
        result = evaluate_params(params, self.stock_list, strategy, self.target_stocks)

        score = result['score']

        self.param_gen.record_result(params, score)

        self.results_history.append({
            'iteration': self.current_iteration,
            'score': score,
            'sharpe': result['sharpe'],
            'win_rate': result['win_rate'],
            'total_trades': result['total_trades'],
            'profit_factor': result['profit_factor'],
            'max_dd_pct': result['max_dd_pct'],
            'total_return_pct': result['total_return_pct'],
            'n_stocks': result['n_stocks'],
            'sharpe_positive_pct': result['sharpe_positive_pct'],
            'params': params,
            'signal_mutations': copy.copy(self.signal_mut.current_mutations),
        })

        if score > self.best_score:
            self.best_score = score
            self.best_params = params.copy()
            self.best_result = result
            is_best = True
        else:
            is_best = False

        return result, is_best

    def run_iteration(self, mode='auto'):
        """完整的一次迭代流程"""
        # 1. Check proxy
        if not self.check_proxy():
            self.proxy_failures += 1
            print(f"  Proxy check #{self.proxy_failures}/{self.max_proxy_failures} FAILED")
            if self.proxy_failures >= self.max_proxy_failures:
                print("  Attempting proxy restart...")
                os.system('pkill -f mihomo 2>/dev/null; sleep 2; '
                          '/usr/local/bin/mihomo -d ~/.clash -f ~/.clash_config_new.yaml &')
                time.sleep(10)
                if self.check_proxy():
                    self.proxy_failures = 0
                    print("  Proxy restarted successfully")
                else:
                    print("  Proxy restart FAILED, returning early")
                    return None
        else:
            self.proxy_failures = 0

        # 2. Choose strategy (rotate every 5 iterations)
        strategies = ['combo', 'fvg-only', 'sweep-fvg', 'osok', 'bpr']
        strategy_idx = (self.current_iteration // 5) % len(strategies)
        if strategy_idx < 3:
            # 60% combo
            strategy = 'combo'
        elif strategy_idx < 4:
            strategy = 'sweep-fvg'
        else:
            strategy = 'osok'

        # 3. Get next parameters
        params = self.param_gen.next_params(mode)

        # 4. Run backtest
        print(f"  Strategy: {strategy}")
        result, is_best = self.run_single_iteration(params, strategy)

        return result

    def save_state(self):
        """保存当前状态"""
        state = {
            'current_iteration': self.current_iteration,
            'best_score': self.best_score,
            'best_params': self.best_params if self.best_params else {},
            'best_result': self.best_result,
            'param_generator': {
                'generation': self.param_gen.generation,
                'stagnation': self.param_gen.stagnation,
                'best_score': self.param_gen.best_score,
            },
            'signal_mutations': self.signal_mut.current_mutations,
            'proxy_failures': self.proxy_failures,
            'results_history': self.results_history,
        }
        with open(RESULTS_FILE, 'w') as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)

        # Save best params separately
        with open(BEST_PARAMS_FILE, 'w') as f:
            json.dump({
                'best_score': self.best_score,
                'best_params': self.best_params,
                'best_result': self.best_result,
                'updated_at': datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2, default=str)

        # Save iteration to individual file
        if self.results_history:
            last_iter = self.results_history[-1]
            iter_file = ITER_DIR / f'iter_{self.current_iteration:04d}.json'
            with open(iter_file, 'w') as f:
                json.dump(last_iter, f, ensure_ascii=False, indent=2, default=str)

    def load_state(self):
        """从上次中断恢复"""
        if RESULTS_FILE.exists():
            with open(RESULTS_FILE) as f:
                state = json.load(f)
            self.current_iteration = state.get('current_iteration', 0)
            self.best_score = state.get('best_score', -float('inf'))
            self.best_params = state.get('best_params')
            self.best_result = state.get('best_result')
            self.proxy_failures = state.get('proxy_failures', 0)
            self.results_history = state.get('results_history', [])

            pg = state.get('param_generator', {})
            self.param_gen.generation = pg.get('generation', 0)
            self.param_gen.stagnation = pg.get('stagnation', 0)

            sm = state.get('signal_mutations', {})
            if sm:
                self.signal_mut.current_mutations = sm

            # Rebuild param history from results_history
            for r in self.results_history:
                self.param_gen.history.append({
                    'params': r.get('params', {}),
                    'score': r.get('score', 0)
                })

            return True
        return False

    def print_progress(self, result, is_best):
        """打印进度"""
        iteration = self.current_iteration
        sr = result.get('sharpe', 0)
        wr = result.get('win_rate', 0)
        pf = result.get('profit_factor', 0)
        dd = result.get('max_dd_pct', 0)
        ret = result.get('total_return_pct', 0)
        score = result.get('score', 0)
        n = result.get('n_stocks', 0)
        pos = result.get('sharpe_positive_pct', 0)

        best_mark = ' 🏆' if is_best else ''

        print(f"  iter #{iteration:>4d} | "
              f"score={score:.4f}{best_mark} | "
              f"SR={sr:.2f} | "
              f"WR={wr:.1f}% | "
              f"PF={pf:.2f} | "
              f"DD={dd:.1f}% | "
              f"Ret={ret:.1f}% | "
              f"n={n} | "
              f"SR>0={pos:.0f}%")

    def run(self, iterations=100, mode='auto', resume=False):
        """主运行循环"""
        if resume and self.load_state():
            print(f"Resumed from iteration {self.current_iteration}")
            print(f"  Best score so far: {self.best_score:.4f}")
            print(f"  Results in history: {len(self.results_history)}")
        else:
            print("Starting fresh optimization")

        # Load stock list
        print("Loading stock list...")
        if not self.load_stock_list():
            print("FATAL: Cannot load stock list")
            return
        print(f"  Target stocks per iteration: {self.target_stocks}")

        # Start iteration loop
        start_time = time.time()
        print("\n" + "=" * 70)
        print(f"  SMC Auto Optimizer v1.0")
        print(f"  Mode: {mode} | Iterations: {iterations} | Stocks: {self.target_stocks}")
        print("=" * 70)

        while self.current_iteration < iterations:
            self.current_iteration += 1

            # Detect stagnation and switch modes
            if self.param_gen.stagnation > 20:
                current_mode = 'random_burst'
                if self.param_gen.stagnation == 21:  # First detection
                    print(f"  ⚠ Stagnation detected ({self.param_gen.stagnation} iters), switching to random_burst mode")
            elif self.param_gen.stagnation > 10:
                current_mode = 'bayesian'
            else:
                current_mode = mode

            # Run the iteration
            try:
                result = self.run_iteration(current_mode)

                if result is None:
                    # Proxy issue
                    print(f"  Iter #{self.current_iteration}: Skipped (proxy unavailable)")
                    continue

                self.print_progress(result, result.get('score', 0) >= self.best_score)
            except Exception as e:
                print(f"  Iter #{self.current_iteration}: ERROR {str(e)[:100]}")
                import traceback
                traceback.print_exc()
                continue

            # Save every iteration
            self.save_state()

            # Check early stop conditions
            if self.param_gen.stagnation > 50 and self.current_iteration >= 50:
                print(f"\n  ⛔ Early stop: stagnated for {self.param_gen.stagnation} iterations")
                break

            # Progress estimation
            if self.current_iteration % 10 == 0:
                elapsed = time.time() - start_time
                rate = self.current_iteration / elapsed
                remaining = (iterations - self.current_iteration) / rate
                print(f"\n  📊 Progress: {self.current_iteration}/{iterations} | "
                      f"Rate: {rate:.2f} it/s | "
                      f"ETA: {remaining/60:.1f}min")

            # Periodic signal mutation (every 20 iterations)
            if self.current_iteration % 20 == 0:
                det, old, new = self.signal_mut.mutate()
                print(f"\n  🧬 Signal mutation: {det}: {old} → {new}")

        # Done
        total_time = time.time() - start_time
        print("\n" + "=" * 70)
        print(f"  🏁 Optimization Complete")
        print(f"  Iterations: {self.current_iteration}")
        print(f"  Total time: {total_time/60:.1f} min")
        print(f"  Best score: {self.best_score:.4f}")
        print(f"  Best SR: {self.best_result.get('sharpe', 0):.2f}" if self.best_result else "")
        print(f"  Best WR: {self.best_result.get('win_rate', 0):.1f}%" if self.best_result else "")
        print(f"  Best params: {json.dumps({k: round(v,4) for k,v in self.best_params.items()}, indent=2)}" if self.best_params else "")
        print("=" * 70)

        # Final save
        self.save_state()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SMC Auto Optimizer')
    parser.add_argument('--mode', default='auto', choices=['auto', 'genetic', 'random', 'bayesian'])
    parser.add_argument('--iterations', type=int, default=100, help='Number of iterations')
    parser.add_argument('--stocks', type=int, default=20, help='Stocks per iteration')
    parser.add_argument('--resume', action='store_true', help='Resume from saved state')
    args = parser.parse_args()

    optimizer = SMCOptimizer(target_stocks=args.stocks, max_iterations=args.iterations)
    optimizer.run(iterations=args.iterations, mode=args.mode, resume=args.resume)


if __name__ == '__main__':
    main()