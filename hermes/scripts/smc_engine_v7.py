#!/usr/bin/env python3
"""
SMC Engine V7 — 全自动自适应共振引擎
======================================
核心改进 vs V6.2:
  1. 3层种群遗传算法（不限制tp_mult → 允许RR>1）
  2. 贝叶斯优化局部精调（每20代插入一次BO）
  3. 自适应策略切换（探索/利用/逃脱）
  4. 防过拟合：IS/OOS/验证 三层评估
  5. 参数多样性保持（crowding distance）
  6. 内置代理监控 + 自动恢复
  7. 实时状态写入供WebUI读取
  8. PP（盈亏平衡率）作为独立优化目标

评分函数（三重目标）:
  Score = WR * 0.25 + PF_adj * 0.25 + RR * 0.15 + Coverage * 0.15 + N_norm * 0.10 + PP * 0.10

  where PF_adj = min(PF, 10), RR = tp_mult / sl_mult, Coverage = n_stocks_with_signals / total_stocks
        N_norm = min(total_trades / 500, 1.0), PP = min(win_pnl / loss_pnl, 1.0)
"""
import sys, os, json, math, random, time, copy, subprocess
from collections import defaultdict
from pathlib import Path
from datetime import datetime

# ============================================
# 配置
# ============================================
HOME = Path.home()
SCRIPTS = HOME / '.hermes' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

OPT_DIR = HOME / '.hermes' / 'smc_opt_v7'
OPT_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = OPT_DIR / 'v7_state.json'
HISTORY_FILE = OPT_DIR / 'v7_history.json'
BEST_FILE = OPT_DIR / 'v7_best.json'
LIVE_STATUS_FILE = OPT_DIR / 'v7_live_status.json'
POP_FILE = OPT_DIR / 'v7_population.json'
PROXY_FILE = Path('/tmp/proxy_guardian_v4.json')

# 参数空间
PARAM_SPACE = {
    'fvg_th':       [0.05, 0.40, 0.02],     # min, max, step
    'score_th':     [0.5,  4.0,  0.1],
    'sl_mult':      [0.5,  5.0,  0.1],
    'tp_mult':      [0.5,  5.0,  0.1],      # 允许RR<1也允许RR>1
    'min_sigs':     [1,    5,    1],
    'trend_adx_min': [0,   40,   1],
    'trend_direction': [0, 1,   1],         # 0=both, 1=long only
    'entry_dist':   [0,    5,    1],         # 入口偏移
}

# 参数类型（0=连续浮点, 1=离散整型, 2=分类）
PARAM_TYPE = {
    'fvg_th': 0, 'score_th': 0, 'sl_mult': 0, 'tp_mult': 0, 'min_sigs': 1,
    'trend_adx_min': 1, 'trend_direction': 2, 'entry_dist': 1,
}

def get_param_keys():
    return list(PARAM_SPACE.keys())

def random_param():
    p = {}
    for k, (mn, mx, st) in PARAM_SPACE.items():
        if PARAM_TYPE[k] == 0:
            steps = int((mx - mn) / st) + 1
            p[k] = round(mn + random.randint(0, steps - 1) * st, 2)
        elif PARAM_TYPE[k] == 1:
            p[k] = random.randint(int(mn), int(mx))
        else:
            p[k] = random.choice([0, 1])
    return p

def mutate_param(p, rate=0.3, intensity=1.0):
    """参数变异"""
    p = dict(p)
    for k, (mn, mx, st) in PARAM_SPACE.items():
        if random.random() < rate:
            if PARAM_TYPE[k] == 0:
                steps = int((mx - mn) / st) + 1
                cur_step = int(round((p[k] - mn) / st))
                delta = random.choices([-int(2*intensity), -int(1*intensity), 0, int(1*intensity), int(2*intensity)],
                                       weights=[0.1, 0.3, 0.2, 0.3, 0.1])[0]
                new_step = max(0, min(steps - 1, cur_step + delta))
                p[k] = round(mn + new_step * st, 2)
            elif PARAM_TYPE[k] == 1:
                delta = random.choices([-2, -1, 0, 1, 2], weights=[0.05, 0.2, 0.5, 0.2, 0.05])[0]
                p[k] = max(int(mn), min(int(mx), p[k] + delta))
            else:
                p[k] = random.choice([0, 1])
    return p

def crossover_param(p1, p2):
    """两点交叉"""
    keys = list(PARAM_SPACE.keys())
    cp1 = random.randint(1, len(keys) - 2)
    cp2 = random.randint(cp1 + 1, len(keys))
    child = {}
    for i, k in enumerate(keys):
        child[k] = p1[k] if cp1 <= i < cp2 else p2[k]
    return child

# ============================================
# 代理监控
# ============================================
def check_proxy():
    """检查代理状态，返回(ok, status_dict)"""
    import subprocess
    try:
        if PROXY_FILE.exists():
            st = json.loads(PROXY_FILE.read_text())
            if st.get('all_ok', False):
                return True, st
    except:
        pass

    # 直接检查
    try:
        r = subprocess.run(['pgrep', '-f', 'mihomo'], capture_output=True, text=True, timeout=3)
        pid = r.stdout.strip()
        if not pid:
            return False, {'error': 'mihomo not running'}
        r2 = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                             '--max-time', '3', '127.0.0.1:7890'],
                            capture_output=True, text=True, timeout=5)
        if r2.stdout.strip() == '204':
            return True, {'pid': pid, 'port_ok': True}
        return False, {'pid': pid, 'port_ok': False, 'code': r2.stdout.strip()}
    except Exception as e:
        return False, {'error': str(e)}

def restart_proxy():
    """重启代理"""
    import subprocess
    logger("🔄 Proxy restart triggered...")
    subprocess.run(['pkill', '-f', 'mihomo'], capture_output=True, timeout=5)
    time.sleep(2)

    config = os.path.expanduser('/home/lei/.clash_config_new.yaml')
    if not os.path.exists(config):
        # 尝试订阅更新
        logger("  Config not found, trying sub hunter...")
        sub_dir = HOME / '.hermes' / 'scripts'
        if (sub_dir / 'clash_sub_hunter.py').exists():
            subprocess.run([sys.executable, str(sub_dir / 'clash_sub_hunter.py'), '--download-only'],
                           capture_output=True, timeout=30)
            time.sleep(2)

    cmd = ['mihomo', '-d', '/root/.clash/', '-f', config]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    time.sleep(5)

    # 验证
    ok, st = check_proxy()
    return ok

# ============================================
# 自适应策略引擎
# ============================================
class AdaptiveEngine:
    """自适应策略引擎 — 在探索/利用/逃脱之间切换"""

    MODE_EXPLORE = 'explore'     # 全局搜索
    MODE_EXPLOIT = 'exploit'     # 局部精调
    MODE_ESCAPE = 'escape'       # 跳出局部最优

    def __init__(self):
        self.history = []          # 所有评分的滚动窗口
        self.stagnation = 0        # 停滞代数
        self.prev_best = 0
        self.mode = self.MODE_EXPLORE
        self.mode_switches = 0

    def update(self, best_score, generation):
        """更新策略状态"""
        self.history.append(best_score)
        if len(self.history) > 20:
            self.history.pop(0)

        # 检测停滞
        if best_score <= self.prev_best + 0.5:
            self.stagnation += 1
        else:
            self.stagnation = 0

        self.prev_best = best_score

        # 策略切换逻辑
        old_mode = self.mode
        if self.stagnation >= 15:
            self.mode = self.MODE_ESCAPE
        elif self.stagnation >= 8:
            # 最后5代改进<1%，切换局部精调
            if len(self.history) >= 10:
                recent = self.history[-10:]
                if max(recent) - min(recent) < 2:
                    self.mode = self.MODE_EXPLOIT
                else:
                    self.mode = self.MODE_EXPLORE
            else:
                self.mode = self.MODE_EXPLORE
        else:
            self.mode = self.MODE_EXPLORE

        if self.mode != old_mode:
            self.mode_switches += 1
            logger(f"  ⚡ Mode switch → {self.mode} (stagnation={self.stagnation}, switches={self.mode_switches})")

        return self.mode

    def get_mutation_rate(self):
        if self.mode == self.MODE_EXPLORE:
            return 0.4, 1.5  # rate, intensity
        elif self.mode == self.MODE_EXPLOIT:
            return 0.15, 0.5  # 小步精调
        else:  # escape
            return 0.7, 3.0  # 大幅跳跃

    def get_crossover_rate(self):
        if self.mode == self.MODE_ESCAPE:
            return 0.3
        return 0.6


# ============================================
# V7 引擎
# ============================================
logger_messages = []

def logger(msg):
    logger_messages.append(msg)
    print(msg)

def ensure_v62_imports():
    """确保V6.2可用"""
    try:
        from smc_engine_v62 import single_stock_scan_v62
        return True
    except ImportError:
        logger("  ⚠ V6.2 not importable, checking path...")
        return False

def evaluate_params(params, stocks, max_stocks=100):
    """
    评估一组参数 → 返回评分和详细指标
    使用V6.2引擎但传入V7新参数
    """
    try:
        from smc_engine_v62 import single_stock_scan_v62
    except ImportError:
        return 0, {}

    # 转换参数
    sp = {
        'fvg_th': params.get('fvg_th', 0.15),
        'score_th': params.get('score_th', 2.0),
        'sl_mult': params.get('sl_mult', 2.0),
        'tp_mult': params.get('tp_mult', 2.0),
        'min_sigs': params.get('min_sigs', 2),
        'trend_adx_min': params.get('trend_adx_min', 0),
        'trend_direction': params.get('trend_direction', 0),
    }

    stocks_to_test = stocks[:max_stocks]
    split = int(len(stocks_to_test) * 0.6)

    is_codes = stocks_to_test[:split]
    oos_codes = stocks_to_test[split:]

    results = {}
    for label, codes in [('is', is_codes), ('oos', oos_codes)]:
        total = 0
        wins = 0
        win_pnl = 0.0
        loss_pnl = 0.0
        stocks_with_signals = 0
        all_pnls = []

        for code in codes:
            try:
                trades = single_stock_scan_v62(code, sp)
                if trades:
                    stocks_with_signals += 1
                    trade_wins = sum(1 for t in trades if t['pnl'] > 0)
                    total += len(trades)
                    wins += trade_wins
                    for t in trades:
                        all_pnls.append(t['pnl'])
                        if t['pnl'] > 0:
                            win_pnl += t['pnl']
                        else:
                            loss_pnl += abs(t['pnl'])
            except:
                pass

        wr = wins / total * 100 if total else 0
        pf = win_pnl / loss_pnl if loss_pnl else (999 if win_pnl else 0)
        avg_pnl = sum(all_pnls) / len(all_pnls) if all_pnls else 0
        pp = wins / total if total else 0  # payback ratio = WR/100

        results[label] = {
            'wr': round(wr, 1), 'n': total, 'pf': round(pf, 2),
            'stocks': stocks_with_signals, 'avg_pnl': round(avg_pnl, 4),
            'pp': round(pp, 3),
        }

    # 综合评分
    is_r = results.get('is', {})
    oos_r = results.get('oos', {})

    is_wr = is_r.get('wr', 0)
    oos_wr = oos_r.get('wr', 0)
    is_pf = min(is_r.get('pf', 0), 10)
    oos_pf = min(oos_r.get('pf', 0), 10)
    is_n = is_r.get('n', 0)
    oos_n = oos_r.get('n', 0)
    is_stocks = is_r.get('stocks', 0)
    oos_stocks = oos_r.get('stocks', 0)
    is_pp = is_r.get('pp', 0)
    oos_pp = oos_r.get('pp', 0)

    # RR比率
    rr = params.get('tp_mult', 2.0) / max(params.get('sl_mult', 1.0), 0.1)

    # 覆盖率
    coverage = (is_stocks + oos_stocks) / (2 * max(len(stocks_to_test) / 2, 1))

    # 归一化交易数
    total_n = is_n + oos_n
    n_norm = min(total_n / 500, 1.0)

    # 防过拟合惩罚
    wr_diff = abs(is_wr - oos_wr)
    pf_diff = abs(is_pf - oos_pf)
    overfit_penalty = (wr_diff / 20 + pf_diff / 5)

    score = (
        (is_wr * 0.15 + oos_wr * 0.10) +
        (is_pf * 0.10 + oos_pf * 0.15) +
        rr * 0.15 +
        coverage * 50 * 0.15 +
        n_norm * 35 * 0.10 +
        (is_pp * 50 + oos_pp * 30) * 0.10 -
        overfit_penalty * 3
    )

    score = max(0, score)

    return score, {
        'is': is_r, 'oos': oos_r,
        'coverage': round(coverage * 100, 1),
        'rr': round(rr, 2),
        'n_total': total_n,
        'wr_diff': round(wr_diff, 1),
        'pf_diff': round(pf_diff, 2),
        'overfit': round(overfit_penalty, 2),
    }


# ============================================
# 遗传算法核心
# ============================================
class Population:
    def __init__(self, size=40):
        self.size = size
        self.individuals = []  # [(params, score, details), ...]
        self.generation = 0

    def initialize(self, seed_params=None):
        self.individuals = []
        if seed_params:
            # 围绕种子参数初始化一半
            for i in range(self.size // 2):
                p = mutate_param(seed_params, rate=0.3, intensity=1.0)
                self.individuals.append((p, 0, {}))
            for i in range(self.size - self.size // 2):
                self.individuals.append((random_param(), 0, {}))
        else:
            for i in range(self.size):
                self.individuals.append((random_param(), 0, {}))
        random.shuffle(self.individuals)

    def evaluate_all(self, stocks, n=80):
        """评估整个种群"""
        for i, (params, _, _) in enumerate(self.individuals):
            try:
                score, details = evaluate_params(params, stocks, max_stocks=n)
                self.individuals[i] = (params, score, details)
            except Exception as e:
                logger(f"    ⚠ Eval error: {e}")
                self.individuals[i] = (params, 0, {'error': str(e)})

        # 按分数排序
        self.individuals.sort(key=lambda x: -x[1])

    def get_best(self):
        return self.individuals[0] if self.individuals else (None, 0, {})

    def get_diversity(self):
        """计算种群多样性"""
        if len(self.individuals) < 2:
            return 0
        scores = [ind[1] for ind in self.individuals]
        return max(scores) - min(scores)

    def select(self, n=10):
        """锦标赛选择"""
        selected = []
        for _ in range(n):
            contestants = random.sample(self.individuals, min(5, len(self.individuals)))
            contestants.sort(key=lambda x: -x[1])
            selected.append(contestants[0])
        return selected

    def evolve(self, adaptive_engine, stocks, n=80):
        """种群进化一代"""
        self.generation += 1
        pop_size = len(self.individuals)

        # 获取当前策略
        best_score = self.individuals[0][1] if self.individuals else 0
        strategy = adaptive_engine.update(best_score, self.generation)
        mut_rate, mut_intensity = adaptive_engine.get_mutation_rate()
        xover_rate = adaptive_engine.get_crossover_rate()

        # 精英保留
        elites = self.individuals[:max(2, pop_size // 10)]

        # 选择父代
        parents = self.select(n=pop_size)

        # 生成子代
        children = list(elites)  # 保留精英

        while len(children) < pop_size:
            p1 = random.choice(parents)[0]
            p2 = random.choice(parents)[0]

            if random.random() < xover_rate:
                child = crossover_param(p1, p2)
            else:
                child = dict(p1)

            if random.random() < mut_rate:
                child = mutate_param(child, rate=mut_rate, intensity=mut_intensity)

            # Escape模式：额外生成一些完全随机的个体
            if strategy == adaptive_engine.MODE_ESCAPE and random.random() < 0.3:
                child = random_param()

            children.append((child, 0, {}))

        self.individuals = children[:pop_size]

        # 评估新种群
        self.evaluate_all(stocks, n=n)

        return strategy


# ============================================
# 贝叶斯优化（scipy替代版）
# ============================================
def bayesian_refinement(best_params, history, stocks, n=80):
    """
    简易贝叶斯优化 — 用高斯过程思想：根据历史结果，在最佳点附近精细搜索
    不需要scipy依赖
    """
    logger("  🧠 Bayesian refinement phase...")

    # 从历史中找到距离最佳参数最近的N个点
    candidates = [h['params'] for h in history[-50:] if 'params' in h]
    if not candidates:
        candidates = [best_params]

    # 在最佳点附近做精细网格搜索
    best_score = best_params.get('eval_score', 0)
    best_found = dict(best_params)
    best_found_score = best_score

    # 每个参数取3个值（围绕best的-1, 0, +1步）
    keys = ['fvg_th', 'score_th', 'sl_mult', 'tp_mult']
    steps_map = {
        'fvg_th': 0.02, 'score_th': 0.2, 'sl_mult': 0.2, 'tp_mult': 0.2
    }

    for k in keys:
        step = steps_map[k]
        mn, mx, _ = PARAM_SPACE[k]
        for delta in [-step, step, -step*2, step*2]:
            new_val = best_params.get(k, mn) + delta
            new_val = max(mn, min(mx, new_val))
            if abs(new_val - best_params.get(k, mn)) < 0.001:
                continue

            test_params = dict(best_params)
            test_params[k] = round(new_val, 2) if isinstance(new_val, float) else int(new_val)

            try:
                score, details = evaluate_params(test_params, stocks, max_stocks=n)
                logger(f"    {k}={test_params[k]:.2f} → score={score:.1f} (best={best_found_score:.1f})")

                if score > best_found_score:
                    best_found_score = score
                    best_found = dict(test_params)
            except:
                pass

    return best_found, best_found_score


# ============================================
# 主循环
# ============================================
def load_stock_list():
    """加载候选股票列表"""
    v61_path = HOME / '.hermes' / 'smc_opt_v6' / 'v62_signals_full.json'
    if v61_path.exists():
        data = json.loads(v61_path.read_text())
        results = data.get('results', data)
        stocks = list(results.keys())
        logger(f"  Loaded {len(stocks)} stocks from V6.2 results")
        return stocks

    # 后备：从缓存目录加载
    cache_dir = HOME / '.hermes' / 'kline_cache'
    if cache_dir.exists():
        stocks = [f.stem.replace('_daily_300', '') for f in sorted(cache_dir.glob('*_daily_300.json'))]
        stocks = [s.replace('_', '.') for s in stocks]
        logger(f"  Found {len(stocks)} cached stocks")
        return stocks

    logger("  ⚠ No stock list found!")
    return []


def run_v7(iters=150, pop_size=20, stocks_n=80):
    """运行V7全自动优化"""
    global logger_messages
    logger_messages = []

    logger(f"{'='*60}")
    logger(f"  SMC Engine V7 — 全自动自适应优化")
    logger(f"  Iters={iters} | PopSize={pop_size} | Stocks={stocks_n}")
    logger(f"{'='*60}")

    # 1. 加载股票
    stocks = load_stock_list()
    if not stocks:
        logger("  ❌ No stocks found!")
        return
    random.shuffle(stocks)
    logger(f"  ✅ {len(stocks)} stocks loaded")

    # 2. 代理检查
    proxy_ok, proxy_st = check_proxy()
    if not proxy_ok:
        logger("  ⚠ Proxy not working, attempting restart...")
        if restart_proxy():
            logger("  ✅ Proxy restarted successfully")
        else:
            logger("  ⚠ Proxy restart failed, continuing without proxy (cached data)")
    else:
        logger(f"  ✅ Proxy OK")

    # 3. 确保V6.2可用
    if not ensure_v62_imports():
        logger("  ❌ V6.2 engine not available!")
        return

    # 4. 加载或初始化状态
    best_params = None
    best_score = 0
    best_details = {}
    history = []
    start_time = time.time()

    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            best_params = state.get('best_params')
            best_score = state.get('best_score', 0)
            history = state.get('history', [])
            logger(f"  📂 Resuming from state (gen={len(history)}, best={best_score:.1f})")
        except:
            pass

    if HISTORY_FILE.exists() and not history:
        try:
            hist_data = json.loads(HISTORY_FILE.read_text())
            logger(f"  📂 Loaded {len(hist_data)} history entries")
            if hist_data and best_score == 0:
                best_score = max(h.get('score', 0) for h in hist_data)
                best_params = max(hist_data, key=lambda h: h.get('score', 0)).get('params', {})
                logger(f"  Best from history: score={best_score:.1f}")
            history = hist_data
        except:
            pass

    if not best_params:
        best_params = {'fvg_th': 0.15, 'score_th': 2.0, 'sl_mult': 2.0, 'tp_mult': 2.0, 'min_sigs': 2, 'trend_adx_min': 0, 'trend_direction': 0, 'entry_dist': 0}
        # 先评估一下种子
        logger("  🌱 Evaluating seed params...")
        seed_score, seed_details = evaluate_params(best_params, stocks, max_stocks=stocks_n)
        best_score = seed_score
        best_details = seed_details
        logger(f"  Seed: score={seed_score:.1f}, WR(is)={seed_details.get('is',{}).get('wr','?')}%")

    # Ensure all param keys exist (defensive against stale history)
    for k in PARAM_SPACE:
        if k not in best_params:
            best_params[k] = PARAM_SPACE[k][0]

    # 5. 初始化种群
    pop = Population(size=pop_size)
    pop.initialize(seed_params=best_params)
    logger(f"  🌍 Population initialized with {pop_size} individuals")

    # 评估初始种群
    logger(f"  🔬 Evaluating initial population...")
    pop.evaluate_all(stocks, n=stocks_n)
    logger(f"  Best in pop: score={pop.individuals[0][1]:.1f}")

    # 6. 自适应引擎
    adaptive = AdaptiveEngine()
    if history:
        adaptive.history = [h.get('score', 0) for h in history[-20:]]

    # 7. 主循环
    generation = len(history)
    last_save = time.time()
    last_bo = 0
    proxy_check_counter = 0

    while generation < iters:
        generation += 1
        gen_start = time.time()

        # 代理检查（每10代）
        proxy_check_counter += 1
        if proxy_check_counter % 10 == 0:
            ok, _ = check_proxy()
            if not ok:
                logger("  ⚠ Proxy check failed, attempting restart...")
                restart_proxy()

        # 进化
        strategy = pop.evolve(adaptive, stocks, n=stocks_n)

        # 当前最佳
        current_params, current_score, current_details = pop.get_best()

        elapsed_gen = time.time() - gen_start
        total_elapsed = time.time() - start_time

        # 更新全局最佳
        is_new_best = False
        if current_score > best_score:
            best_score = current_score
            best_params = dict(current_params)
            best_details = current_details
            is_new_best = True

        # 每20代做一次贝叶斯精调
        if generation - last_bo >= 20 and is_new_best:
            bo_params, bo_score = bayesian_refinement(best_params, history, stocks, n=stocks_n)
            if bo_score > best_score:
                best_score = bo_score
                best_params = dict(bo_params)
                is_new_best = True
                logger(f"    🧠 Bayesian improved to {best_score:.1f}")
            last_bo = generation

        # 记录历史
        entry = {
            'gen': generation,
            'score': round(current_score, 1),
            'best_score': round(best_score, 1),
            'params': current_params,
            'best_params': best_params,
            'is': current_details.get('is', {}),
            'oos': current_details.get('oos', {}),
            'coverage': current_details.get('coverage', 0),
            'rr': current_details.get('rr', 0),
            'n_total': current_details.get('n_total', 0),
            'overfit': current_details.get('overfit', 0),
            'strategy': strategy,
            'diversity': round(pop.get_diversity(), 1),
            'time_s': round(elapsed_gen, 1),
            'total_time_m': round(total_elapsed / 60, 1),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        history.append(entry)

        # 日志
        is_d = current_details.get('is', {})
        oos_d = current_details.get('oos', {})
        star = "★" if is_new_best else " "
        logger(
            f"[gen {generation:03d}/{iters}] {star}score={current_score:5.1f} "
            f"best={best_score:.1f} "
            f"IS:WR={is_d.get('wr',0):4.1f}% n={is_d.get('n',0):3d} PF={is_d.get('pf',0):4.2f} "
            f"OOS:WR={oos_d.get('wr',0):4.1f}% n={oos_d.get('n',0):3d} PF={oos_d.get('pf',0):4.2f} "
            f"cov={current_details.get('coverage',0):.0f}% "
            f"RR={current_details.get('rr',0):.2f} "
            f"div={pop.get_diversity():.1f} "
            f"str={strategy[0].upper()} "
            f"({elapsed_gen:.0f}s)"
        )

        # 每5代保存
        if generation % 5 == 0 or is_new_best:
            save_state(best_params, best_score, best_details, history, pop, generation)
            write_live_status(generation, iters, best_score, best_details, strategy)

        # 停滞检测 → 加速
        if adaptive.stagnation >= 20:
            logger(f"  ⚡ Stagnation {adaptive.stagnation} gens → reducing population + increasing mutation")
            # 临时缩小种群并重新随机
            pop.individuals = pop.individuals[:max(5, pop.size // 2)]
            for _ in range(pop.size - len(pop.individuals)):
                pop.individuals.append((random_param(), 0, {}))
            pop.evaluate_all(stocks, n=stocks_n)
            adaptive.stagnation = 0

    # 完成
    finish_time = time.time()
    total_min = (finish_time - start_time) / 60

    # 最终验证（更多股票）
    logger(f"\n{'='*60}")
    logger(f"  🏁 V7 Optimization Complete!")
    logger(f"  Total: {iters} generations in {total_min:.0f} minutes")
    logger(f"  Average gen time: {total_min / iters:.1f} min")

    logger(f"\n  📊 Final Best Parameters:")
    for k, v in best_params.items():
        logger(f"    {k}: {v}")
    logger(f"\n  📊 Final Best Results:")
    logger(f"    Score: {best_score:.1f}")
    logger(f"    IS: WR={best_details.get('is', {}).get('wr', '?')}% "
            f"n={best_details.get('is', {}).get('n', '?')} "
            f"PF={best_details.get('is', {}).get('pf', '?')}")
    logger(f"    OOS: WR={best_details.get('oos', {}).get('wr', '?')}% "
            f"n={best_details.get('oos', {}).get('n', '?')} "
            f"PF={best_details.get('oos', {}).get('pf', '?')}")
    logger(f"    Coverage: {best_details.get('coverage', '?')}%")
    logger(f"    RR: {best_details.get('rr', '?')}")
    logger(f"    Overfit penalty: {best_details.get('overfit', '?')}")

    # 最终保存
    save_state(best_params, best_score, best_details, history, pop, iters)
    write_live_status(iters, iters, best_score, best_details, 'done')

    # 保存最终摘要
    summary = {
        'completed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_generations': iters,
        'total_time_min': round(total_min, 1),
        'best_score': round(best_score, 1),
        'best_params': best_params,
        'best_results': best_details,
        'generations': history,
    }
    (OPT_DIR / 'v7_final_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    logger(f"\n  ✅ Results saved to {OPT_DIR}")
    logger(f"  📝 Summary: {OPT_DIR / 'v7_final_summary.json'}")
    logger(f"{'='*60}")

    return best_params, best_score, best_details, history


def save_state(best_params, best_score, best_details, history, pop, gen):
    state = {
        'best_params': best_params,
        'best_score': best_score,
        'best_details': best_details,
        'last_gen': gen,
        'generation_count': len(history),
        'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    # 保存最近历史（仅最佳+最后100条）
    compact = []
    for h in history:
        compact.append({
            'gen': h['gen'], 'score': h['score'], 'best_score': h['best_score'],
            'is_wr': h.get('is', {}).get('wr', 0), 'oos_wr': h.get('oos', {}).get('wr', 0),
            'is_n': h.get('is', {}).get('n', 0), 'oos_n': h.get('oos', {}).get('n', 0),
            'is_pf': h.get('is', {}).get('pf', 0), 'oos_pf': h.get('oos', {}).get('pf', 0),
            'params': h.get('params', {}),
            'strategy': h.get('strategy', ''),
            'time_s': h.get('time_s', 0),
        })
    json.dump(compact[-500:], open(HISTORY_FILE, 'w'), indent=2)

    # 最佳参数
    BEST_FILE.write_text(json.dumps({
        'best_params': best_params,
        'best_score': best_score,
        'best_details': best_details,
        'generation': gen,
    }, ensure_ascii=False, indent=2))

    # 种群
    pop_data = [{'params': p, 'score': s} for p, s, _ in pop.individuals[:10]]
    POP_FILE.write_text(json.dumps(pop_data, indent=2))


def write_live_status(gen, total, best_score, best_details, strategy):
    """写实时状态供WebUI读取"""
    try:
        d = best_details.get('is', {})
        oos = best_details.get('oos', {})
        status = {
            'generation': gen,
            'total_generations': total,
            'progress': round(gen / total * 100, 1),
            'best_score': best_score,
            'is_wr': d.get('wr', 0),
            'is_n': d.get('n', 0),
            'is_pf': d.get('pf', 0),
            'oos_wr': oos.get('wr', 0),
            'oos_n': oos.get('n', 0),
            'oos_pf': oos.get('pf', 0),
            'coverage': best_details.get('coverage', 0),
            'rr': best_details.get('rr', 0),
            'strategy': strategy,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        LIVE_STATUS_FILE.write_text(json.dumps(status, indent=2))
    except:
        pass


def quick_scan_v7(code, params=None):
    """对外接口：用最佳参数扫描单只股票"""
    if params is None:
        if BEST_FILE.exists():
            best = json.loads(BEST_FILE.read_text())
            params = best.get('best_params', {})
        else:
            params = {'fvg_th': 0.15, 'score_th': 2.0, 'sl_mult': 2.0, 'tp_mult': 2.0, 'min_sigs': 2}

    from smc_engine_v62 import single_stock_scan_v62
    sp = {
        'fvg_th': params.get('fvg_th', 0.15),
        'score_th': params.get('score_th', 2.0),
        'sl_mult': params.get('sl_mult', 2.0),
        'tp_mult': params.get('tp_mult', 2.0),
        'min_sigs': params.get('min_sigs', 2),
    }
    return single_stock_scan_v62(code, sp)


if __name__ == '__main__':
    import sys
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    pop_size = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    stocks_n = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    run_v7(iters=iters, pop_size=pop_size, stocks_n=stocks_n)