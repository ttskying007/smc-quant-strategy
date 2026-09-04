#!/usr/bin/env python3
"""
SMC V8.4 Optimizer — 全自动六阶段+精英+爬山寻优
===============================================
V8.4 优化升级:
  1. 6阶段搜索 (随机→模拟退火→局部→精英→爬山→收敛)
  2. 精英保留 — 保留Top 10参数
  3. 岛屿模型 — 3个独立搜索岛，定期交换精英
  4. 动态自适应收紧参数空间
  5. 种子加载 — 从上一轮best_params.json继续
  6. 实时状态输出到live_status.json
  7. 300次迭代 (V8.4增加)
  
用法:
  python3 smc_optimizer_v84.py [iterations] [stocks] [--seed best_params.json] [--tighten 0.3]
"""

import sys, os, json, math, time, random, traceback, copy
from pathlib import Path

HOME = Path.home()
LOG_DIR = HOME / '.hermes' / 'smc_opt_v83'
LOG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = HOME / '.hermes' / 'kline_cache'

# 动态导入V8.4引擎
sys.path.insert(0, str(HOME / '.hermes' / 'scripts'))
from smc_engine_v84 import *

# ════════════════════════════════════════════
# 配置
# ════════════════════════════════════════════

N_ITERATIONS = 300  # 缺省300次
N_STOCKS = 30       # 缺省30只
N_ISLANDS = 3       # 3个并行岛
ELITE_SIZE = 10     # 精英池
SEED_FILE = None
TIGHTEN_PCT = 0.0   # 空间收紧比例

def parse_args():
    global N_ITERATIONS, N_STOCKS, SEED_FILE, TIGHTEN_PCT
    args = sys.argv[1:]
    nums = []
    for a in args:
        if a.startswith('--'):
            continue
        try:
            nums.append(int(a))
        except:
            pass
    if len(nums) >= 1:
        N_ITERATIONS = nums[0]
    if len(nums) >= 2:
        N_STOCKS = nums[1]
    for i, a in enumerate(args):
        if a == '--seed' and i + 1 < len(args):
            SEED_FILE = args[i+1]
        elif a == '--tighten' and i + 1 < len(args):
            TIGHTEN_PCT = float(args[i+1])

parse_args()
stocks = TEST_STOCKS[:N_STOCKS]
print(f"V8.4 Optimizer: {N_ITERATIONS} iters x {len(stocks)} stocks x {N_ISLANDS} islands")
print(f"Seed: {SEED_FILE}  Tighten: {TIGHTEN_PCT}")

# ════════════════════════════════════════════
# 参数工具
# ════════════════════════════════════════════

def random_params(space, seed_params=None, tighten_pct=0):
    """生成随机参数"""
    params = {}
    for name, pdef in space.items():
        if seed_params and name in seed_params and tighten_pct > 0:
            # 围绕种子值缩小范围
            center = seed_params[name]
            half_range = (pdef['max'] - pdef['min']) * (1 - tighten_pct) / 2
            lo = max(pdef['min'], center - half_range)
            hi = min(pdef['max'], center + half_range)
            if pdef['step'] >= 1:
                params[name] = random.randint(int(lo), int(hi))
            else:
                params[name] = round(random.uniform(lo, hi), 2)
                params[name] = round(params[name] / pdef['step']) * pdef['step'] if pdef['step'] > 0 else params[name]
        else:
            if pdef['step'] >= 1:
                params[name] = random.randint(int(pdef['min']), int(pdef['max']))
            elif pdef['step'] > 0:
                steps = int((pdef['max'] - pdef['min']) / pdef['step'])
                params[name] = round(pdef['min'] + random.randint(0, steps) * pdef['step'], 2)
            else:
                params[name] = round(random.uniform(pdef['min'], pdef['max']), 2)
    # 强制tp/sl >= 1.5
    if params.get('tp_pct', 0) / max(params.get('sl_pct', 1), 0.1) < 1.5:
        params['tp_pct'] = params['sl_pct'] * 1.5 + 0.5
    # 强制atr_max > atr_min
    if params.get('atr_min_pct', 0) >= params.get('atr_max_pct', 10):
        params['atr_max_pct'] = params['atr_min_pct'] + 2.0
    return params

def mutate_params(params, space, mutation_rate=0.3):
    """突变"""
    newp = dict(params)
    for name, pdef in space.items():
        if random.random() < mutation_rate:
            r = (pdef['max'] - pdef['min']) * random.random() * 0.4 - (pdef['max'] - pdef['min']) * 0.2
            val = params[name] + r
            val = max(pdef['min'], min(pdef['max'], val))
            if pdef['step'] >= 1:
                val = round(val)
            newp[name] = round(val, 2) if pdef['step'] < 1 else int(val)
    # 强制约束
    if newp.get('tp_pct', 0) / max(newp.get('sl_pct', 1), 0.1) < 1.5:
        newp['tp_pct'] = newp['sl_pct'] * 1.5 + 0.5
    if newp.get('atr_min_pct', 0) >= newp.get('atr_max_pct', 10):
        newp['atr_max_pct'] = newp['atr_min_pct'] + 2.0
    return newp

def crossover_params(p1, p2, space):
    """交叉"""
    child = {}
    for name in space:
        if random.random() < 0.5:
            child[name] = p1.get(name, space[name]['default'])
        else:
            child[name] = p2.get(name, space[name]['default'])
    # 强制约束
    if child.get('tp_pct', 0) / max(child.get('sl_pct', 1), 0.1) < 1.5:
        child['tp_pct'] = child['sl_pct'] * 1.5 + 0.5
    return child

# ════════════════════════════════════════════
# 缓存加速 — 对每个股票缓存K线数据
# ════════════════════════════════════════════

def warmup_cache():
    """预热所有股票K线缓存"""
    print("🔥 预热K线缓存...")
    loaded = 0
    for s in stocks:
        try:
            k = fetch_kline_cached(s, 'daily', 300)
            if k and len(k) > 30:
                loaded += 1
        except:
            pass
    print(f"  ✓ {loaded}/{len(stocks)} stocks cached")

# ════════════════════════════════════════════
# V8.4 优化主循环
# ════════════════════════════════════════════

class V84Optimizer:
    def __init__(self):
        self.best_score = 0
        self.best_params = None
        self.best_result = None
        self.elite = []  # 精英池 [(score, params, result), ...]
        self.history = []  # 迭代历史
        self.start_time = time.time()
        self.phase = 0
        self.temp = 1.0  # SA温度
        self.islands = [[] for _ in range(N_ISLANDS)]  # 每个岛当前参数

    def save_state(self):
        """保存状态"""
        state = {
            'round': len(self.history),
            'total_rounds': N_ITERATIONS,
            'best_score': round(self.best_score, 2),
            'best_wr': round(self.best_result.get('wr', 0), 1) if self.best_result else 0,
            'best_n': self.best_result.get('n', 0) if self.best_result else 0,
            'best_pf': round(self.best_result.get('pf', 0), 2) if self.best_result else 0,
            'best_rr': round(self.best_result.get('rr_avg', 0), 2) if self.best_result else 0,
            'best_ret': round(self.best_result.get('ret', 0), 2) if self.best_result else 0,
            'best_coverage': round(self.best_result.get('coverage', 0), 1) if self.best_result else 0,
            'status': 'running',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'engine': 'V8.4',
            'details': {
                'phase': self.phase,
                'temp': round(self.temp, 2),
                'elite_size': len(self.elite),
                'elapsed': round(time.time() - self.start_time)
            }
        }
        (LOG_DIR / 'live_status.json').write_text(json.dumps(state, ensure_ascii=False))

    def save_best(self):
        """保存最佳参数"""
        if self.best_params and self.best_result:
            data = {
                'score': round(self.best_score, 2),
                'params': self.best_params,
                'full_eval': self.best_result,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'engine': 'V8.4'
            }
            (LOG_DIR / 'best_params.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def save_history(self):
        """保存历史"""
        (LOG_DIR / 'history.json').write_text(json.dumps(self.history, ensure_ascii=False))

    def save_elite(self):
        """保存精英池"""
        elite_data = []
        for score, params, result in self.elite:
            elite_data.append({
                'score': round(score, 2),
                'wr': round(result.get('wr', 0), 1),
                'n': result.get('n', 0),
                'params': params
            })
        (LOG_DIR / 'elite_pool.json').write_text(json.dumps(elite_data, ensure_ascii=False, indent=2))

    def evaluate(self, params):
        """评估一组参数"""
        result = evaluate_params(params, stocks)
        score = result.get('score', 0)
        return score, result

    def update_best(self, score, params, result):
        """更新最佳"""
        if score > self.best_score:
            self.best_score = score
            self.best_params = dict(params)
            self.best_result = result
            return True
        return False

    def add_to_elite(self, score, params, result):
        """加入精英池"""
        self.elite.append((score, dict(params), result))
        self.elite.sort(key=lambda x: -x[0])
        if len(self.elite) > ELITE_SIZE:
            self.elite = self.elite[:ELITE_SIZE]

    def run(self):
        """主优化循环"""
        print("\n╔═══════════════════════════════════════════════════╗")
        print("║  SMC V8.4 六阶段搜索                            ║")
        print("║  RR优先 | 精英保留 | 岛屿模型 | 局部爬山        ║")
        print("╚═══════════════════════════════════════════════════╝\n")

        warmup_cache()
        self.save_state()

        # 加载种子
        seed_params = None
        if SEED_FILE:
            try:
                sd = json.loads(Path(SEED_FILE).read_text())
                if 'params' in sd:
                    seed_params = sd['params']
                print(f"📥 加载种子参数: Score={sd.get('score', '?')}")
            except Exception as e:
                print(f"  ⚠ 种子加载失败: {e}")

        # 初始化各岛
        for i in range(N_ISLANDS):
            self.islands[i] = random_params(V84_PARAM_SPACE, seed_params,
                                            TIGHTEN_PCT if seed_params else 0)

        # ═══ 阶段0: 全随机探索（前50次） ═══
        self.phase = 0
        print(f"\n{'─'*50}")
        print(f"阶段0: 全随机探索 (1-50)")
        print(f"{'─'*50}")

        for it in range(1, N_ITERATIONS + 1):
            # 阶段切换
            if it == 51:
                self.phase = 1
                self.temp = 0.8
                print(f"\n{'─'*50}")
                print(f"阶段1: 模拟退火搜索 (51-100), 初始温度={self.temp}")
                print(f"{'─'*50}")
            elif it == 101:
                self.phase = 2
                print(f"\n{'─'*50}")
                print(f"阶段2: 精英引导搜索 (101-150)")
                print(f"{'─'*50}")
            elif it == 151:
                self.phase = 3
                print(f"\n{'─'*50}")
                print(f"阶段3: 岛屿进化 (151-200)")
                print(f"{'─'*50}")
            elif it == 201:
                self.phase = 4
                print(f"\n{'─'*50}")
                print(f"阶段4: 局部爬山 (201-260)")
                print(f"{'─'*50}")
            elif it == 261:
                self.phase = 5
                print(f"\n{'─'*50}")
                print(f"阶段5: 收敛精调 (261-300)")
                print(f"{'─'*50}")

            # 生成参数
            if self.phase == 0:
                # 全随机
                island_idx = random.randint(0, N_ISLANDS - 1)
                if it % 10 == 0:
                    params = random_params(V84_PARAM_SPACE, seed_params,
                                           min(TIGHTEN_PCT, 0.1))
                else:
                    params = random_params(V84_PARAM_SPACE)
                source = 'random'

            elif self.phase == 1:
                # 模拟退火: 在当前最佳附近扰动
                if self.best_params and random.random() < 0.7:
                    params = mutate_params(self.best_params, V84_PARAM_SPACE, self.temp)
                    source = 'sa_mutate'
                else:
                    params = random_params(V84_PARAM_SPACE)
                    source = 'sa_random'

            elif self.phase == 2:
                # 精英引导
                if self.elite and random.random() < 0.6:
                    p1 = random.choice(self.elite)[1]
                    p2 = random.choice(self.elite)[1] if len(self.elite) > 1 else p1
                    if random.random() < 0.5:
                        params = crossover_params(p1, p2, V84_PARAM_SPACE)
                        source = 'elite_xover'
                    else:
                        params = mutate_params(p1, V84_PARAM_SPACE, 0.2)
                        source = 'elite_mutate'
                else:
                    params = random_params(V84_PARAM_SPACE)
                    source = 'elite_random'

            elif self.phase == 3:
                # 岛屿进化
                island_idx = (it - 151) % N_ISLANDS
                if self.islands[island_idx] and random.random() < 0.7:
                    if random.random() < 0.3 and len(self.elite) > 1:
                        # 跨岛交换
                        other = (island_idx + 1) % N_ISLANDS
                        # 从精英取一个好的
                        best_elite = self.elite[0][1]
                        params = crossover_params(self.islands[island_idx], best_elite, V84_PARAM_SPACE)
                        source = f'island{island_idx}_exchange'
                    else:
                        params = mutate_params(self.islands[island_idx], V84_PARAM_SPACE, 0.2)
                        source = f'island{island_idx}_mutate'
                else:
                    params = random_params(V84_PARAM_SPACE)
                    source = f'island{island_idx}_random'
                    self.islands[island_idx] = params

            elif self.phase == 4:
                # 局部爬山 + WR冲刺
                mutation = 0.08 if random.random() < 0.6 else 0.20
                if self.best_params and random.random() < 0.8:
                    # 40%概率做WR定向突变: 调高score_min降低max_trades提高胜率
                    if random.random() < 0.4:
                        params = dict(self.best_params)
                        params['score_min'] = min(V84_PARAM_SPACE['score_min']['max'], params['score_min'] + random.uniform(0.2, 1.0))
                        params['max_trades'] = max(V84_PARAM_SPACE['max_trades']['min'], int(params['max_trades'] - random.randint(0, 2)))
                        source = 'wr_directed'
                    else:
                        params = mutate_params(self.best_params, V84_PARAM_SPACE, mutation)
                        source = 'hillclimb'
                elif self.elite and random.random() < 0.5:
                    params = mutate_params(random.choice(self.elite)[1], V84_PARAM_SPACE, 0.15)
                    source = 'hill_elite'
                else:
                    params = random_params(V84_PARAM_SPACE, self.best_params, 0.3)
                    source = 'hill_random'

            elif self.phase == 5:
                # 收敛精调 + WR最后冲刺
                if self.best_params:
                    if random.random() < 0.3:
                        # WR冲刺: 从当前最佳做小突变 + 覆盖更多股票
                        params = mutate_params(self.best_params, V84_PARAM_SPACE, 0.03)
                        # 调低atr_min_pct和调高atr_max_pct来覆盖更多股票
                        if random.random() < 0.5:
                            params['atr_min_pct'] = max(V84_PARAM_SPACE['atr_min_pct']['min'], params['atr_min_pct'] - 0.2)
                            params['atr_max_pct'] = min(V84_PARAM_SPACE['atr_max_pct']['max'], params['atr_max_pct'] + 0.5)
                        source = 'wr_sprint'
                    else:
                        params = mutate_params(self.best_params, V84_PARAM_SPACE, 0.05)
                        source = 'converge'
                else:
                    params = random_params(V84_PARAM_SPACE, self.best_params, 0.2)
                    source = 'converge_random'

            # 评估
            score, result = self.evaluate(params)
            is_better = self.update_best(score, params, result)
            if is_better:
                self.add_to_elite(score, params, result)

            # 模拟退火接受
            if self.phase == 1 and not is_better and self.elite:
                last_elite_score = self.elite[0][0]
                if score > 0:
                    delta = score - last_elite_score
                    if delta < 0 and self.temp > 0.01:
                        accept_prob = math.exp(delta / self.temp)
                        if random.random() < accept_prob:
                            self.add_to_elite(score, params, result)

            # 更新岛屿
            if self.phase == 3:
                self.islands[island_idx] = params
                # 定期精英注入
                if it % 10 == 0 and self.elite:
                    self.islands[island_idx] = self.elite[0][1]

            # 阶段1降温
            if self.phase == 1:
                self.temp = max(0.01, self.temp * 0.97)

            # 记录历史
            self.history.append({
                'it': it, 'score': round(score, 2),
                'wr': round(result.get('wr', 0), 1),
                'n': result.get('n', 0),
                'pf': round(result.get('pf', 0), 2),
                'rr': round(result.get('rr_avg', 0), 2),
                'best': round(self.best_score, 2),
                'source': source,
                'phase': self.phase
            })

            # 每5次迭代输出
            if it == 1 or it % 5 == 0:
                self.save_state()
                self.save_best()
                self.save_history()
                self.save_elite()

                best_wr = self.best_result.get('wr', 0) if self.best_result else 0
                best_n = self.best_result.get('n', 0) if self.best_result else 0
                best_rr = self.best_result.get('rr_avg', 0) if self.best_result else 0
                best_pf = self.best_result.get('pf', 0) if self.best_result else 0

                elapsed = time.time() - self.start_time
                it_sec = f"{it/elapsed:.1f}/s" if elapsed > 0 else "?"

                print(f"  [{it:3d}/{N_ITERATIONS}] "
                      f"score={score:7.1f} WR={result['wr']:4.1f}% "
                      f"N={result['n']:2d} PF={result['pf']:.1f} "
                      f"RR={result['rr_avg']:.2f} "
                      f"| best={self.best_score:8.1f} WR={best_wr}% N={best_n} RR={best_rr} PF={best_pf} "
                      f"| src={source[:10]:10s} | {it_sec}")

        # ═══ 完成 ═══
        print(f"\n{'='*50}")
        print(f"✅ V8.4 优化完成!")
        print(f"   Best Score: {self.best_score:.2f}")
        print(f"   Best WR:    {self.best_result.get('wr',0):.1f}%")
        print(f"   Best N:     {self.best_result.get('n',0)}")
        print(f"   Best PF:    {self.best_result.get('pf',0):.2f}")
        print(f"   Best RR:    {self.best_result.get('rr_avg',0):.2f}")
        print(f"   Best Ret:   {self.best_result.get('ret',0):.2f}%")
        print(f"   Coverage:   {self.best_result.get('coverage',0):.1f}%")
        print(f"   Elite Pool: {len(self.elite)}")
        print(f"   Time:       {time.time() - self.start_time:.0f}s")
        print(f"{'='*50}")

        # 最终保存
        state = json.loads((LOG_DIR / 'live_status.json').read_text())
        state['status'] = 'complete'
        state['details']['phase'] = self.phase
        state['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        (LOG_DIR / 'live_status.json').write_text(json.dumps(state, ensure_ascii=False))
        self.save_best()
        self.save_history()
        self.save_elite()

        # 同步到V7/V82目录
        try:
            for d in [LOG_DIR / '..' / 'smc_opt_v7',
                      LOG_DIR / '..' / 'smc_opt_v82']:
                td = d.resolve()
                if td.exists():
                    (td / 'v7_live_status.json').write_text(json.dumps(state))
                    (td / 'live_status.json').write_text(json.dumps(state))
        except:
            pass

        return self.best_score, self.best_params


if __name__ == '__main__':
    opt = V84Optimizer()
    score, params = opt.run()
    print(f"\nBest params: {json.dumps(params, indent=2)}")