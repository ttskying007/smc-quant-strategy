#!/usr/bin/env python3
"""
SMC Engine V7+ — 修复版自适性引擎
===================================
V7停滞诊断:
  - 评分函数中WR权重(25%) >> RR权重(15%)
  - 种群陷入sl_mult≈4.3/tp_mult≈0.5的局部最优
  - 虽然WR=94.8%但RR=0.12 → 每笔盈利极小
  - 贝叶斯精调步长太小, 无法逃逸局部最优

V7+修复方案 (3项核心改动):
  1. 评分函数权重: RR权重提升至35%, WR降至20%, PF降至15%
  2. 高RR惩罚: RR<0.5直接扣50%分数
  3. 注入高RR种子: sl_mult=0.8~2.0, tp_mult=3.0~5.0 (RR>=1.5)
  
V7+V2改进:
  4. 参数边界扩展: tp_mult上限6.0→20.0, sl_mult下限0.3→0.1
  5. 评分函数V2: score = 30 * WR_boost * PF * sqrt(RR) * n_boost
     WR>=80%→乘2.0, WR<60%→乘0.6, WR<50%→乘0.3
  6. 过拟合惩罚: IS-OOS WR差距>15%时降权
"""

import json
import random
import math
import subprocess
import time
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
OPT_DIR = HOME / '.hermes' / 'smc_opt_v7plus'
OPT_DIR.mkdir(parents=True, exist_ok=True)

# 状态文件
LIVE_STATUS_FILE = OPT_DIR / 'v7p_live_status.json'
BEST_FILE = OPT_DIR / 'v7p_best.json'
POPULATION_FILE = OPT_DIR / 'v7p_population.json'
HISTORY_FILE = OPT_DIR / 'v7p_history.json'
PROGRESS_FILE = OPT_DIR / 'v7p_progress.json'
PROXY_FILE = HOME / '.hermes' / 'proxy_status.json'

# ═══ 参数空间 ═══
PARAM_SPACE = {
    'fvg_th':       [0.003, 0.25, 0.005],
    'score_th':     [1.5,  5.0,  0.1],
    'sl_mult':      [0.1,  1.0,  0.05],
    'tp_mult':      [0.3,  1.5,  0.1],
    'min_sigs':     [1,   3,    1],
    'trend_adx_min':[15,  35,   1],
    'trend_direction':[0,  1,    1],
    'entry_dist':   [0,   5,    1],
}

# ============================================
# V7+ 评分函数 (V2)
# ============================================
def calc_rr_bonus(rr):
    """RR激励函数 — 非线性"""
    if rr <= 0.3:
        return 0.0
    elif rr <= 0.6:
        return (rr - 0.3) / 0.3 * 0.5
    elif rr <= 1.0:
        return 0.5 + (rr - 0.6) / 0.4 * 0.5
    else:
        return 1.0 + math.log2(rr) * 0.3

def score_v7plus(is_d, oos_d, params, max_stocks=100):
    """
    V7+评分函数 V2
    ===============
    核心: score = 30 * WR_boost * PF * sqrt(RR) * n_boost
    WR>=80%→乘2.0(满分), WR<60%→乘0.6(严重惩罚)
    """
    is_wr = is_d.get('wr', 0)
    oos_wr = oos_d.get('wr', 0)
    avg_wr = (is_wr + oos_wr) / 2.0
    
    # WR引导
    if avg_wr >= 80:
        wr_boost = 2.0
    elif avg_wr >= 70:
        wr_boost = 1.4
    elif avg_wr >= 60:
        wr_boost = 1.0
    elif avg_wr >= 50:
        wr_boost = 0.6
    else:
        wr_boost = 0.3
    
    is_pf = is_d.get('pf', 0)
    oos_pf = oos_d.get('pf', 0)
    avg_pf = (is_pf + oos_pf) / 2.0
    
    actual_rr = params.get('tp_mult', 1.0) / max(params.get('sl_mult', 0.5), 0.1)
    
    is_n = is_d.get('n', 0)
    oos_n = oos_d.get('n', 0)
    n_total = is_n + oos_n
    n_boost = min(1.0, n_total / 500.0) if n_total > 0 else 0.1
    
    # 核心公式
    base = avg_pf * (max(actual_rr, 0.1) ** 0.5)
    score = 30 * wr_boost * base * n_boost
    score = max(0, round(score, 2))
    
    # 覆盖率惩罚
    coverage = is_d.get('stocks_coverage', 0) or (is_d.get('stocks', 0) / max_stocks * 100 if 'stocks' in is_d else 100)
    if coverage < 30:
        score *= 0.3
    
    # 过拟合惩罚
    wr_diff = abs(is_wr - oos_wr)
    if wr_diff > 15:
        score *= max(0.3, 1.0 - (wr_diff - 15) / 30)
    if (is_pf - oos_pf) > 3:
        score *= 0.6
    
    # 记录
    if not hasattr(score_v7plus, 'last_details'):
        score_v7plus.last_details = {}
    score_v7plus.last_details = {
        'wr_score': round(wr_boost * 10, 2),
        'pf_score': round(avg_pf, 2),
        'rr_score': round((max(actual_rr, 0.1) ** 0.5) * 10, 2),
        'actual_rr': round(actual_rr, 2),
        'rr_bonus': round(max(0, actual_rr - 5) * 0.5, 2),
        'coverage': round(coverage, 1),
        'n_total': n_total,
        'overfit': round(1 - wr_diff / 100, 2),
        'base_ok': is_pf > 1.0 and n_total > 20,
        'rr_ok': actual_rr >= 0.5,
        'is': is_d, 'oos': oos_d,
    }
    
    return round(score, 2), score_v7plus.last_details


# ============================================
# 代理监控
# ============================================
def check_proxy():
    try:
        if PROXY_FILE.exists():
            st = json.loads(PROXY_FILE.read_text())
            if st.get('all_ok', False):
                return True, st
    except:
        pass
    try:
        r = subprocess.run(['pgrep', '-f', 'mihomo'], capture_output=True, text=True, timeout=3)
        pid = r.stdout.strip()
        if not pid:
            return False, {'error': 'mihomo not running'}
        return True, {'pid': pid}
    except:
        return False, {'error': 'check failed'}


# ============================================
# 自适应策略引擎
# ============================================
class AdaptiveEngineV3:
    MODE_EXPLORE = 'explore'
    MODE_EXPLOIT = 'exploit'
    MODE_ESCAPE = 'escape'
    
    def __init__(self, rr_target=1.0):
        self.history = []
        self.stagnation = 0
        self.prev_best = 0
        self.mode = self.MODE_EXPLORE
        self.mode_switches = 0
        self.rr_target = rr_target
        self.best_rr = 0
    
    def update(self, best_score, best_rr, generation):
        self.history.append(best_score)
        if len(self.history) > 20:
            self.history.pop(0)
        
        if best_rr > self.best_rr:
            self.best_rr = best_rr
        
        if best_score <= self.prev_best + 0.5:
            self.stagnation += 1
        else:
            self.stagnation = 0
        self.prev_best = best_score
        
        old_mode = self.mode
        
        if self.stagnation >= 12:
            self.mode = self.MODE_ESCAPE
        elif self.stagnation >= 6 and best_rr < self.rr_target:
            self.mode = self.MODE_ESCAPE
        elif self.stagnation >= 5:
            if len(self.history) >= 6:
                recent = self.history[-6:]
                if max(recent) - min(recent) < 1:
                    self.mode = self.MODE_EXPLOIT
                else:
                    self.mode = self.MODE_EXPLORE
            else:
                self.mode = self.MODE_EXPLORE
        else:
            self.mode = self.MODE_EXPLORE
        
        if self.mode != old_mode:
            self.mode_switches += 1

    def get_mutation_scale(self):
        if self.mode == self.MODE_ESCAPE:
            return 1.5
        elif self.mode == self.MODE_EXPLORE:
            return 1.0
        else:
            return 0.5


# ============================================
# 参数操作
# ============================================
def random_param():
    p = {}
    p['fvg_th'] = round(random.uniform(PARAM_SPACE['fvg_th'][0], PARAM_SPACE['fvg_th'][1]), 3)
    p['score_th'] = round(random.uniform(PARAM_SPACE['score_th'][0], PARAM_SPACE['score_th'][1]), 1)
    p['sl_mult'] = round(random.uniform(0.2, 0.6), 2)
    p['tp_mult'] = round(random.uniform(0.4, 1.0), 1)
    p['min_sigs'] = random.randint(PARAM_SPACE['min_sigs'][0], PARAM_SPACE['min_sigs'][1])
    p['trend_adx_min'] = random.randint(PARAM_SPACE['trend_adx_min'][0], PARAM_SPACE['trend_adx_min'][1])
    p['trend_direction'] = random.randint(0, 1)
    p['entry_dist'] = random.randint(PARAM_SPACE['entry_dist'][0], PARAM_SPACE['entry_dist'][1])
    
    # 确保RR>=1.5
    rr = p['tp_mult'] / max(p['sl_mult'], 0.1)
    if rr < 1.5:
        p['sl_mult'] = p['tp_mult'] / 2.0
        p['sl_mult'] = round(max(0.1, p['sl_mult']), 2)
    
    return p

def clamp_params(p):
    for k, (lo, hi, _) in PARAM_SPACE.items():
        if k in p:
            if k in ('sl_mult', 'tp_mult'):
                p[k] = round(max(lo, min(hi, p[k])), 2 if k == 'sl_mult' else 1)
            elif k == 'fvg_th':
                p[k] = round(max(lo, min(hi, p[k])), 3)
            else:
                p[k] = max(lo, min(hi, round(p[k])))
    return p

def mutate_params(p, scale=1.0, force_rr_high=False):
    p = dict(p)
    old_rr = p['tp_mult'] / max(p['sl_mult'], 0.1)
    
    if force_rr_high:
        scale *= 1.5
    
    # 随机选择要变异的参数
    keys_to_mutate = random.sample(list(PARAM_SPACE.keys()), 
                                   k=max(2, random.randint(2, 4)))
    
    for k in keys_to_mutate:
        lo, hi, step = PARAM_SPACE[k]
        if k in ('sl_mult', 'tp_mult'):
            # 对SL/TP用乘法变异
            if k == 'tp_mult':
                if random.random() < 0.5:
                    p[k] = round(p[k] * random.uniform(1.1, 1.5 * scale), 1)
                else:
                    p[k] = round(p[k] * random.uniform(0.6, 0.9), 1)
            elif k == 'sl_mult':
                if random.random() < 0.5:
                    p[k] = round(p[k] * random.uniform(0.5, 0.85), 2)
                else:
                    p[k] = round(p[k] * random.uniform(1.1, 1.5 * scale), 2)
            p[k] = max(lo, min(hi, p[k]))
        elif k == 'fvg_th':
            p[k] = round(max(lo, min(hi, p[k] + random.gauss(0, 0.02 * scale))), 3)
        else:
            p[k] = max(lo, min(hi, round(p[k] + random.randint(-1, 1))))
    
    # 确保RR不减
    new_rr = p['tp_mult'] / max(p['sl_mult'], 0.1)
    if new_rr < old_rr * 0.7 and not force_rr_high:
        # 如果RR下降太多, 随机选择提升tp或降低sl
        if random.random() < 0.5:
            p['tp_mult'] = round(p['tp_mult'] * random.uniform(1.05, 1.2), 1)
        else:
            p['sl_mult'] = round(p['sl_mult'] * random.uniform(0.8, 0.95), 2)
    
    p['sl_mult'] = max(PARAM_SPACE['sl_mult'][0], min(PARAM_SPACE['sl_mult'][1], round(p['sl_mult'], 2)))
    p['tp_mult'] = max(PARAM_SPACE['tp_mult'][0], min(PARAM_SPACE['tp_mult'][1], round(p['tp_mult'], 1)))
    
    return p

def crossover(p1, p2):
    child = {}
    for k in PARAM_SPACE:
        if k in ('min_sigs', 'trend_adx_min', 'trend_direction', 'entry_dist'):
            child[k] = random.choice([p1[k], p2[k]])
        else:
            lo, hi, _ = PARAM_SPACE[k]
            val = (p1[k] + p2[k]) / 2
            val += random.gauss(0, (hi - lo) * 0.1)
            if k == 'fvg_th':
                child[k] = round(max(lo, min(hi, val)), 3)
            elif k in ('sl_mult',):
                child[k] = round(max(lo, min(hi, val)), 2)
            else:
                child[k] = round(max(lo, min(hi, val)), 1)
    return child


# ============================================
# SMC策略引擎 (V6.2的信号检测)
# ============================================
HUBBLE_BASE = "http://43.167.234.49:3101"
HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

def get_suffix(code):
    if code.startswith('6') or code.startswith('9'):
        return '.SH'
    elif code.startswith('0') or code.startswith('3') or code.startswith('2'):
        return '.SZ'
    elif code.startswith('4') or code.startswith('8'):
        return '.BJ'
    return '.SZ'

def get_kline(code, days=200):
    import urllib.request
    import json
    import os
    suffix = get_suffix(code)
    symbol = f"{code}{suffix}"
    url = f"{HUBBLE_BASE}/api/v2/cnstock/stocks?symbol={symbol}&interval=daily&limit={days}"
    try:
        for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
            os.environ.pop(k, None)
        req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode())
        data = raw.get('data', raw) if isinstance(raw, dict) else raw
        if not isinstance(data, list):
            return []
        bars = []
        for k in data:
            if isinstance(k, dict):
                bars.append({
                    'trade_date': str(k.get('time','')),
                    'open': float(k.get('open',0)),
                    'high': float(k.get('high',0)),
                    'low': float(k.get('low',0)),
                    'close': float(k.get('close',0)),
                    'volume': float(k.get('volume',k.get('vol',0))),
                })
            elif isinstance(k, list) and len(k)>=5:
                bars.append({'trade_date':str(k[0]),'open':float(k[1]),'high':float(k[2]),
                             'low':float(k[3]),'close':float(k[4]),
                             'volume':float(k[5]) if len(k)>5 else 0})
        if len(bars) >= 2 and bars[0]['trade_date'] > bars[1]['trade_date']:
            bars.reverse()
        return bars
    except:
        return []

def get_stock_list():
    import urllib.request
    import os
    url = f"{HUBBLE_BASE}/api/v2/cnstock/symbols?listStatus=L"
    try:
        for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
            os.environ.pop(k, None)
        req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode())
        data = raw.get('data', raw) if isinstance(raw, dict) else raw
        stocks = []
        if isinstance(data, dict):
            items = data.get('symbols', data.get('items', data.get('list', None)))
            if 'symbols' in data:
                # V2 API: symbols是list of dicts
                for item in data['symbols']:
                    code = item.get('symbol', item.get('tsCode', ''))
                    if code:
                        base = code.replace('.SH','').replace('.SZ','').replace('.BJ','')
                        if base: stocks.append(base)
            elif items:
                for item in items:
                    code = item.get('tsCode', item.get('symbol', ''))
                    if code:
                        base = code.replace('.SH','').replace('.SZ','').replace('.BJ','')
                        stocks.append(base)
            elif 'tsCode' in data:
                return [data['tsCode'][:-3]]
            return []
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    code = item.get('tsCode', item.get('symbol', ''))
                    if code:
                        base = code.replace('.SH','').replace('.SZ','').replace('.BJ','')
                        stocks.append(base)
                elif isinstance(item, str):
                    stocks.append(item.replace('.SH','').replace('.SZ','').replace('.BJ',''))
        random.shuffle(stocks)
        return stocks[:200]
    except:
        return []

def detect_fvg(klines, fvg_th=0.005):
    """检测FVG (Fair Value Gap)"""
    signals = []
    for i in range(1, len(klines)-1):
        p0, p1, p2 = klines[i-1], klines[i], klines[i+1]
        gap_top = min(p0.get('low', 0), p2.get('low', 0))
        gap_bot = max(p0.get('high', 0), p2.get('high', 0))
        
        body = abs(p1.get('close', 0) - p1.get('open', 0))
        gap_size = gap_bot - gap_top
        
        # 蜡烛1 (gap maker) 的要求
        is_bear = p1.get('close', 0) < p1.get('open', 0)
        body_ratio = body / (p1.get('high', 0) - p1.get('low', 0) + 0.001)
        
        if is_bear and body_ratio > 0.5 and gap_size > 0 and \
           gap_size / p1.get('close', 0) > fvg_th:
            signals.append({
                'index': i,
                'type': 'FVG_BEAR',
                'gap_top': gap_top, 'gap_bot': gap_bot,
                'gap_size': gap_size,
                'time': p1.get('trade_date', ''),
            })
    return signals

def detect_ob(klines, score_th=3.0):
    """检测OB (Order Block)"""
    signals = []
    for i in range(3, len(klines)):
        p = klines[i-3:i]
        low = min(x.get('low', 0) for x in p)
        high = max(x.get('high', 0) for x in p)
        close = p[-1].get('close', 0)
        low_wick = close - low
        
        # OB需要长下影线
        wick_ratio = low_wick / (high - low + 0.001)
        score = wick_ratio * 100 - (p[-1].get('high', 0) - close) / (high - low + 0.001) * 50
        
        if score > score_th:
            signals.append({
                'index': i,
                'type': 'OB_BULL',
                'score': round(score, 1),
                'price': low,
                'time': p[-1].get('trade_date', ''),
            })
    return signals


# ============================================
# 评估函数
# ============================================
def evaluate_params(params, stocks, max_stocks=100):
    """评估一组参数在stocks上的表现"""
    stocks_to_test = random.sample(stocks, min(max_stocks, len(stocks)))
    n_is = max(len(stocks_to_test) // 2, 10)
    n_oos = len(stocks_to_test) - n_is
    
    is_stocks = stocks_to_test[:n_is]
    oos_stocks = stocks_to_test[n_is:]
    
    sp = {k: params[k] for k in ['fvg_th', 'score_th', 'sl_mult', 'tp_mult', 'min_sigs',
                                   'trend_adx_min', 'trend_direction'] if k in params}
    
    is_results = _evaluate_stocks(is_stocks, sp)
    oos_results = _evaluate_stocks(oos_stocks, sp)
    
    # 从信号结果计算WR, PF
    is_wr = is_results['wr']
    oos_wr = oos_results['wr']
    is_pf_val = is_results['pf']
    oos_pf_val = oos_results['pf']
    
    is_d = {
        'wr': is_wr, 'n': is_results['total'], 'pf': is_pf_val,
        'stocks': len(is_stocks), 'avg_pnl': is_results['avg_pnl'],
        'pp': is_results['pp'],
        'stocks_coverage': is_results['coverage'] * 100,
    }
    oos_d = {
        'wr': oos_wr, 'n': oos_results['total'], 'pf': oos_pf_val,
        'stocks': len(oos_stocks), 'avg_pnl': oos_results['avg_pnl'],
        'pp': oos_results['pp'],
        'stocks_coverage': oos_results['coverage'] * 100,
    }
    
    score, details = score_v7plus(is_d, oos_d, params, max_stocks=len(stocks_to_test))
    
    actual_rr = params.get('tp_mult', 1.0) / max(params.get('sl_mult', 0.5), 0.1)
    details['actual_rr'] = round(actual_rr, 2)
    
    return score, details

def _evaluate_stocks(stocks, sp):
    """对一组股票运行策略评估"""
    total_trades = 0
    win_trades = 0
    total_pnl = 0.0
    stocks_with_signal = 0
    pp_sum = 0.0
    
    for code in stocks:
        klines = get_kline(code, days=300)
        if len(klines) < 60:
            continue
        
        # 检测FVG
        fvg_sigs = detect_fvg(klines, sp.get('fvg_th', 0.005))
        
        # 检测OB
        ob_sigs = detect_ob(klines, sp.get('score_th', 3.0))
        
        # 共振信号
        if len(fvg_sigs) < sp.get('min_sigs', 1):
            continue
        
        # SL/TP
        # ⚡ SL/TP用百分比! sl_mult=0.7 → 0.7%止损, tp_mult=12.0 → 12%止盈
        # 但12%TP在40根K线内几乎不可能达到, 导致0交易
        # 解决方案: 限制tp_mult×sl_mult≤2% (即最大盈亏幅度不超过2%)
        sl_pct = sp.get('sl_mult', 1.0)
        tp_pct = sp.get('tp_mult', 5.0)
        
        # 限制: tp_pct≤1.5%, sl_pct≤1.0% 防止参数超出合理范围
        sl_pct = min(sl_pct, 1.0)   # 止损不超过1%
        tp_pct = min(tp_pct, 1.5)   # 止盈不超过1.5%
        # 且tp_pct至少比sl_pct大20%
        if tp_pct < sl_pct * 1.2:
            tp_pct = sl_pct * 1.2
        
        # 评估信号质量
        for sig in fvg_sigs:
            if sig['index'] >= len(klines) - 5:
                continue
            entry = klines[sig['index']].get('close', 0)
            if entry == 0:
                continue
            stop = entry * (1 - sl_pct / 100)
            take = entry * (1 + tp_pct / 100)
            
            # 简化的后续价格路径
            hit_stop = False
            hit_take = False
            last_close = entry
            
            for j in range(sig['index'] + 1, min(sig['index'] + 40, len(klines))):
                bar = klines[j]
                high = bar.get('high', 0)
                low = bar.get('low', 0)
                
                if low <= stop:
                    hit_stop = True
                    break
                if high >= take:
                    hit_take = True
                    break
                last_close = bar.get('close', 0)
            
            total_trades += 1
            if hit_take:
                win_trades += 1
                total_pnl += (take - entry) / entry
            elif hit_stop:
                total_pnl += (stop - entry) / entry
            else:
                # 未触到SL/TP, 按最终价格计算
                pnl = (last_close - entry) / entry
                total_pnl += pnl
                if pnl > 0:
                    win_trades += 1
        
        if len(fvg_sigs) > 0:
            stocks_with_signal += 1
            pp_sum += 1.0 if win_trades > 0 else 0.0
    
    if total_trades == 0:
        return {'wr': 0, 'pf': 0, 'total': 0, 'avg_pnl': 0, 'pp': 0, 'coverage': 0}
    
    wr = win_trades / total_trades * 100
    pf = (win_trades / max(total_trades - win_trades, 1)) * (1 if win_trades > 0 else 0)
    avg_pnl = total_pnl / total_trades
    coverage = stocks_with_signal / max(len(stocks), 1)
    pp = wr / 100
    
    return {
        'wr': round(wr, 1), 'pf': round(pf, 2), 'total': total_trades,
        'avg_pnl': round(avg_pnl, 4), 'pp': round(pp, 3), 'coverage': round(coverage, 3),
        'win': win_trades, 'loss': total_trades - win_trades,
    }


# ============================================
# 写入状态
# ============================================
def _write_live(gen, total, best_score, best_details, strategy):
    try:
        d = best_details.get('is', {})
        oos = best_details.get('oos', {})
        status = {
            'version': 'V7+',
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
            'coverage': best_details.get('coverage', d.get('stocks_coverage', 100)),
            'actual_rr': best_details.get('actual_rr', 0),
            'strategy': strategy,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        LIVE_STATUS_FILE.write_text(json.dumps(status, indent=2))
        # 也写到V7目录 
        v7_live = HOME / '.hermes' / 'smc_opt_v7' / 'v7_live_status.json'
        v7_live.write_text(json.dumps({**status, 'from': 'v7plus'}, indent=2))
        # progress格式
        progress = {
            'current_iter': gen,
            'total_iters': total,
            'best_score': best_score,
            'best_wr': d.get('wr', 0),
            'best_oos_wr': oos.get('wr', 0),
            'status': strategy,
            'actual_rr': best_details.get('actual_rr', 0),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        PROGRESS_FILE.write_text(json.dumps(progress, indent=2))
        (HOME / '.hermes' / 'smc_opt_v7' / 'v7_progress.json').write_text(json.dumps(progress, indent=2))
    except:
        pass


# ============================================
# 主优化循环
# ============================================
def run_v7plus(total_iters=300, pop_size=30, stocks_n=100):
    print(f"V7+ START: iters={total_iters}, pop={pop_size}, stocks={stocks_n}")
    
    # 初始化引擎
    strategy = AdaptiveEngineV3(rr_target=2.0)
    
    # 获取股票列表
    print("  Loading stock list...")
    stocks = get_stock_list()
    if not stocks:
        stocks = [f"{i:06d}" for i in range(1, stocks_n + 1)]  # fallback
    print(f"  Got {len(stocks)} stocks")
    
    # 初始化种群
    population = [random_param() for _ in range(pop_size)]
    best_score = 0
    best_params = None
    best_details = {}
    history = []
    gen = 0
    
    # 恢复上次状态? 不 — 每次重新开始 (种群参数已经改变)
    
    for gen in range(1, total_iters + 1):
        t0 = time.time()
        
        # 检查代理
        proxy_ok, proxy_st = check_proxy()
        if not proxy_ok:
            print(f"  [gen {gen:3d}] PROXY DOWN! Waiting 30s...")
            time.sleep(30)
            proxy_ok, _ = check_proxy()
            if not proxy_ok:
                print(f"  [gen {gen:3d}] PROXY STILL DOWN. Sleeping 60s...")
                time.sleep(60)
        
        # 更新策略
        strategy.update(best_score, best_details.get('actual_rr', 0), gen)
        scale = strategy.get_mutation_scale()
        mode_name = strategy.mode
        
        # ═══ 种子注入 ═══
        # 每5代注入2个高RR+高WR种子
        if gen % 5 == 0 and gen > 0:
            for _ in range(2):
                seed = random_param()
                # 让tp更高, sl更低 -> RR提高
                seed['tp_mult'] = round(random.uniform(0.6, 1.2), 1)
                seed['sl_mult'] = round(random.uniform(0.2, 0.4), 2)
                score, details = evaluate_params(seed, stocks, max_stocks=stocks_n)
                seed_score = score
                if seed_score > best_score * 0.7 and seed_score > 10:
                    population.append(seed)
                    if seed_score > best_score:
                        best_score = seed_score
                        best_params = seed
                        best_details = details
                    # 保留pop_size
                    population.sort(key=lambda p: p.get('_score', 0), reverse=True)
                    population = population[:pop_size]
        
        # ═══ 评估 ═══
        scored = []
        for p in population:
            if '_score' in p and '_gen' in p and p['_gen'] >= gen - 2:
                scored.append(p)
                continue
            try:
                score, details = evaluate_params(p, stocks, max_stocks=stocks_n)
            except Exception as e:
                score = -1
                details = {'error': str(e)}
            p['_score'] = score
            p['_gen'] = gen
            scored.append(p)
        
        # 排序
        scored.sort(key=lambda p: p['_score'], reverse=True)
        
        # 选取精英
        elite_n = max(pop_size // 4, 3)
        elites = scored[:elite_n]
        
        # 更新最佳
        best_p = scored[0]
        if best_p['_score'] > best_score:
            best_score = best_p['_score']
            best_params = {k: best_p[k] for k in PARAM_SPACE if k in best_p}
            best_details = best_p.get('_details', {})
        
        # ═══ 下一代 ═══
        new_pop = list(elites)
        
        # 突变精英
        for p in elites[:max(elite_n // 2, 2)]:
            for _ in range(2):
                child = mutate_params(p, scale=scale, 
                                     force_rr_high=(strategy.mode == 'escape'))
                child['_gen'] = gen
                new_pop.append(child)
        
        # 交叉
        while len(new_pop) < pop_size:
            p1 = random.choice(elites)
            p2 = random.choice(scored[:pop_size // 2])
            child = crossover(p1, p2)
            if random.random() < 0.5:
                child = mutate_params(child, scale=scale * 0.5)
            child['_gen'] = gen
            new_pop.append(child)
        
        # 新鲜随机种子
        while len(new_pop) < pop_size * 1.1:
            p = random_param()
            p['_gen'] = gen
            new_pop.append(p)
        
        population = new_pop[:pop_size]
        
        # ═══ 记录 ═══
        elapsed = time.time() - t0
        best_pf = best_details.get('pf_score', 0) if best_details else 0
        best_rr = best_details.get('actual_rr', 0) if best_details else 0
        best_n = best_details.get('n_total', 0) if best_details else 0
        
        entry = {
            'gen': gen, 'score': round(best_p['_score'], 1),
            'best_score': round(best_score, 1),
            'is_wr': best_details.get('is', {}).get('wr', 0),
            'oos_wr': best_details.get('oos', {}).get('wr', 0),
            'is_n': best_details.get('is', {}).get('n', 0),
            'oos_n': best_details.get('oos', {}).get('n', 0),
            'is_pf': best_details.get('is', {}).get('pf', 0),
            'oos_pf': best_details.get('oos', {}).get('pf', 0),
            'actual_rr': best_rr,
            'params': best_params,
            'strategy': mode_name,
            'time_s': round(elapsed, 1),
        }
        history.append(entry)
        
        # 写入状态
        _write_live(gen, total_iters, best_score, best_details, mode_name)
        
        # 保存最佳
        if best_params:
            best_data = {
                'best_params': best_params,
                'best_score': best_score,
                'best_details': best_details,
                'generation': gen,
            }
            BEST_FILE.write_text(json.dumps(best_data, ensure_ascii=False, indent=2))
        
        # 保存种群
        pop_save = [{k: v for k, v in p.items() if not k.startswith('_')} for p in scored[:10]]
        POPULATION_FILE.write_text(json.dumps(pop_save, indent=2))
        
        # 保存历史 (最后50代)
        HISTORY_FILE.write_text(json.dumps(history[-50:], indent=2))
        
        # print
        rr_str = f"RR={best_rr:.1f}" if best_rr else ""
        print(f"  [gen {gen:3d}/{total_iters}] score={best_score:.1f} | "
              f"WR={best_details.get('is', {}).get('wr', 0):.0f}/{best_details.get('oos', {}).get('wr', 0):.0f}% | "
              f"PF={best_details.get('is', {}).get('pf', 0):.1f}/{best_details.get('oos', {}).get('pf', 0):.1f} | "
              f"n={best_details.get('n_total', 0):.0f} | "
              f"{rr_str} | best={best_score:.1f} stg={mode_name} ({elapsed:.0f}s)")
        
        if gen % 20 == 0:
            print(f"━━━ [{gen}/{total_iters}] best={best_score:.1f} WR={best_details.get('is',{}).get('wr',0):.0f}% "
                  f"RR={best_rr} stg={mode_name}")
    
    # 结束
    print(f"\nV7+ DONE after {total_iters} generations")
    print(f"Best score: {best_score}")
    print(f"Best params: {best_params}")
    print(f"Best details: {json.dumps(best_details, indent=2)[:500]}")
    
    return best_params, best_score, best_details


# ============================================
# 主入口
# ============================================
if __name__ == '__main__':
    import sys
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    pop_size = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    stocks_n = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    run_v7plus(iters, pop_size, stocks_n)