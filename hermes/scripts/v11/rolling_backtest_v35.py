#!/usr/bin/env python3
"""
V35 信号时序+价格行为+趋势延续+反转系统
============================================
全面升级:  4层信号时序 + 多周期共振 + 摆动点自适应 + 固定SL/TP

核心改进:
  1. 固定SL/TP代替复杂trailing — 消除99%1-bar退出问题
     SL=0.5%, TP=2.0%/3.0%, 不trail到breakeven
  2. 多周期共振: 周线趋势过滤 + 日线信号时序
  3. 4层信号评分: POI+价格上下文+链模式+多周期共振
  4. 周期性参数自适应: 阶段+周期
  5. 每种股票独立参数优化
"""
import json, sys, time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v35')
OUTPUT_DIR.mkdir(exist_ok=True)

# === V35 NEW PARAMS (wider, no trailing to breakeven) ===
SL_FIXED = 0.5        # was 0.3 — wider to allow multi-bar holds
TP_PROFIT = 2.0       # fixed take-profit at +2.0%
TP_MAX = 3.0          # max profit target (extended trend)

SWING_SL_CAP = 0.8    # was 0.5 — allow wider swing SL
SWING_MAX_DIST = 25   # was 20

MIN_VOL_RATIO = 0.7
MIN_FVG_GAP = 0.2
MIN_TRADES = 2
MIN_BARS = 120
ROLL_START = 60
ROLL_END_OFFSET = 10
MAX_HOLD = 120        # was 60 — allow longer holds
COOLDOWN = 3          # was 8 — shorter cooldown to catch more trades

# No trailing to breakeven — use fixed SL/TP
# SL is hit when price goes below SL price (any time during bar)
# TP is hit when price goes above TP price (any time during bar)
# If neither is hit within MAX_HOLD, exit at close

def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data

def synthesize_weekly(ohlcv):
    """合成周线数据"""
    weekly = []
    for i in range(0, len(ohlcv), 5):
        chunk = ohlcv[i:i+5]
        if not chunk: continue
        weekly.append({
            'o': chunk[0]['o'], 'h': max(b['h'] for b in chunk),
            'l': min(b['l'] for b in chunk), 'c': chunk[-1]['c'],
            'v': sum(b.get('v', b.get('vol', 0)) for b in chunk)
        })
    return weekly

def weekly_trend(weekly, lookback=8):
    """判断周线趋势 (多周期共振)"""
    if len(weekly) < lookback: return 'neutral'
    seg = weekly[-lookback:]
    start, end = seg[0]['c'], seg[-1]['c']
    pct = (end - start) / start * 100
    green = sum(1 for b in seg if b['c'] > b['o'])
    red = sum(1 for b in seg if b['c'] < b['o'])
    if pct > 3 and green >= lookback * 0.6: return 'bull'
    if pct < -3 and red >= lookback * 0.6: return 'bear'
    return 'neutral'

def short_trend(ohlcv, idx, lookback=10):
    """短期趋势判断"""
    if idx < lookback: return 'neutral', 0.0, 0.0
    seg = ohlcv[idx-lookback:idx+1]
    start, end = seg[0]['c'], seg[-1]['c']
    pct = (end - start) / start * 100
    ema = sum(ohlcv[i]['c'] for i in range(max(0, idx-8), idx+1)) / min(9, idx+1)
    ed = (ohlcv[idx]['c'] - ema) / ema * 100
    return pct, ed

def find_all_swing_lows(ohlcv, end_idx, lookback=60):
    """找摆动低点 (支撑位)"""
    if end_idx < 3: return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx - 1, start, -1):
        left = ohlcv[i-1] if i > start else None
        right = ohlcv[i+1] if i < end_idx-1 else None
        lv = left['l'] if left else 9999
        rv = right['l'] if right else 9999
        if ohlcv[i]['l'] < lv and ohlcv[i]['l'] < rv:
            swings.append((i, ohlcv[i]['l'], end_idx - i))
    return swings

def find_all_swing_highs(ohlcv, end_idx, lookback=60):
    """找摆动高点 (阻力位)"""
    if end_idx < 3: return []
    start = max(0, end_idx - lookback)
    swings = []
    for i in range(end_idx - 1, start, -1):
        left = ohlcv[i-1] if i > start else None
        right = ohlcv[i+1] if i < end_idx-1 else None
        hv = left['h'] if left else 0
        rv = right['h'] if right else 0
        if ohlcv[i]['h'] > hv and ohlcv[i]['h'] > rv:
            swings.append((i, ohlcv[i]['h'], end_idx - i))
    return swings

def find_best_swing_sl(ohlcv, end_idx, entry_price, sl_candidates=None):
    """摆动点SL — 找最近的摆动低点作为SL"""
    swings = find_all_swing_lows(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= SWING_MAX_DIST]
    if not swings: return None
    best, bs = None, 999
    for idx, price, dist in swings:
        capped = min(price, entry_price * (1 - SWING_SL_CAP / 100))
        sl_pct = (entry_price - capped) / entry_price * 100
        if 0.2 <= sl_pct <= 1.5:
            score = abs(sl_pct - 0.6) * 0.5 + (dist / SWING_MAX_DIST) * 0.5
            if score < bs: bs = score; best = {'sl_price': capped, 'sl_pct': round(sl_pct, 2), 'swing_idx': idx}
    return best

def find_swing_tp(ohlcv, end_idx, entry_price, lookback=60):
    """摆动点TP — 找最近的摆动高点作为初步TP"""
    swings = find_all_swing_highs(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= 30]
    if not swings: return None
    # 找最近的阻力位
    for idx, price, dist in swings:
        tp_pct = (price - entry_price) / entry_price * 100
        if 1.0 <= tp_pct <= 8.0:
            return {'tp_price': price, 'tp_pct': round(tp_pct, 2), 'swing_idx': idx}
    return None

# ============================================================
# V35信号时序评分系统 (4层)
# ============================================================

# 核心信号类型
CORE_SIGNAL_TYPES = {'FVG', 'OB', 'Sweep', 'CHOCH'}
SIGNAL_CODES = {
    'FVG_Bull': 'F', 'FVG_Bear': 'f',
    'OB_Bull': 'O', 'OB_Bear': 'o',
    'SweepDown': 'S', 'SweepUp': 's',
    'CHOCH_Bull': 'C', 'CHOCH_Bear': 'c',
}

PATTERN_DB = {
    # GOLD
    'CF': {'desc': 'CHOCH→FVG', 'bonus': 0.35, 'min': 2, 'wr': 0.85},
    'FO': {'desc': 'FVG→OB', 'bonus': 0.30, 'min': 2, 'wr': 0.82},
    'SF': {'desc': 'Sweep→FVG', 'bonus': 0.30, 'min': 2, 'wr': 0.80},
    # SILVER
    'FF': {'desc': 'FVG→FVG', 'bonus': 0.20, 'min': 2, 'wr': 0.72},
    'SO': {'desc': 'Sweep→OB', 'bonus': 0.18, 'min': 2, 'wr': 0.68},
    'OF': {'desc': 'OB→FVG', 'bonus': 0.18, 'min': 2, 'wr': 0.65},
    'OFC': {'desc': 'OB→FVG→CHOCH', 'bonus': 0.45, 'min': 3, 'wr': 0.88},
    'COF': {'desc': 'CHOCH→OB→FVG', 'bonus': 0.40, 'min': 3, 'wr': 0.83},
    'SFF': {'desc': 'Sweep→FVG→FVG', 'bonus': 0.40, 'min': 3, 'wr': 0.85},
    'OFF': {'desc': 'OB→FVG→FVG', 'bonus': 0.35, 'min': 3, 'wr': 0.82},
    'CSF': {'desc': 'CHOCH→Sweep→FVG', 'bonus': 0.50, 'min': 3, 'wr': 0.90},
    'SCF': {'desc': 'Sweep→CHOCH→FVG', 'bonus': 0.45, 'min': 3, 'wr': 0.88},
    # BRONZE
    'CO': {'desc': 'CHOCH→OB', 'bonus': 0.15, 'min': 2, 'wr': 0.60},
    'OO': {'desc': 'OB→OB', 'bonus': 0.05, 'min': 2, 'wr': 0.45},
    'SS': {'desc': 'Sweep→Sweep', 'bonus': -0.10, 'min': 2, 'wr': 0.35},
    'FCF': {'desc': 'FVG→CHOCH→FVG', 'bonus': 0.35, 'min': 3, 'wr': 0.80},
}

def classify_signal_code(signal):
    stype = signal.get('type', '')
    for pattern, code in SIGNAL_CODES.items():
        if pattern in stype: return code
    if stype: return stype[0].upper()
    return '?'

def _is_core_signal(signal):
    stype = signal.get('type', '')
    return any(core in stype for core in CORE_SIGNAL_TYPES)

def score_signal_v35(all_signals: List[Dict], target_signal: Dict,
                     ohlcv: List[Dict], weekly_trend_val: str,
                     phase: str, params: Dict = None) -> Dict:
    """
    V35 4层信号评分:
    Layer 1: POI分析 — FVG lower是否被测试/反弹
    Layer 2: 价格行为上下文 — 趋势延续/反转/回调/新鲜
    Layer 3: 信号链模式匹配 (V33)
    Layer 4: 多周期共振 (周线+日线趋势对齐)
    """
    target_idx = target_signal.get('idx', 0)
    direction = target_signal.get('direction', 'bull')
    target_type = target_signal.get('type', '')
    
    if 'FVG' not in target_type:
        return {'score': 0.50, 'grade': 'C', 'action': 'enter', 
                'entry_mult': 0.6, 'desc': '非FVG信号', 'context': 'unknown'}
    
    # === Layer 1: POI分析 ===
    fvg_lower = target_signal.get('lower', 0)
    fvg_upper = target_signal.get('upper', 0)
    
    # 检查FVG lower是否被后续K线测试过
    poi_tested = False
    poi_bounce = False
    test_bars = 0
    min_distance = 999
    
    for i in range(target_idx + 1, min(target_idx + 60, len(ohlcv))):
        bar = ohlcv[i]
        bar_low, bar_close = bar['l'], bar['c']
        
        # 价格进入FVG区域
        if fvg_lower > 0 and fvg_upper > 0:
            if bar_low <= fvg_upper and bar_low >= fvg_lower * 0.999:
                poi_tested = True
                test_bars = i - target_idx
                distance = abs(bar_low - fvg_lower) / fvg_lower * 100
                min_distance = min(min_distance, distance)
                # 有反弹迹象: close > low (价格在POI处获得支撑)
                if bar_close > bar_low and bar_close > fvg_lower:
                    poi_bounce = True
    
    # === Layer 2: 价格行为上下文 ===
    # 短期趋势
    trend_pct, ema_dist = short_trend(ohlcv, target_idx, 5)
    trend_10, _ = short_trend(ohlcv, target_idx, 10)
    
    if poi_tested and poi_bounce:
        context = 'poi_pullback'
        base_score = 0.70  # POI回调+反弹 = 高置信度
        context_desc = 'POI回调确认'
    elif poi_tested:
        context = 'poi_tested'
        base_score = 0.60
        context_desc = 'POI已测试'
    elif trend_10 > 0.5 and ema_dist > 0:
        context = 'trend_continuation'
        base_score = 0.55  # 趋势延续中
        context_desc = '趋势延续向上'
    elif trend_10 < -0.5 and ema_dist < 0:
        context = 'reversal'
        base_score = 0.50  # 趋势反转尝试
        context_desc = '逆势信号(反转尝试)'
    else:
        context = 'fresh'
        base_score = 0.50
        context_desc = '新鲜信号(无前序价格行为)'
    
    # === Layer 3: 信号链模式匹配 (V33延续) ===
    # 提取前序信号链
    preceding = [s for s in all_signals 
                 if s.get('idx', 0) < target_idx
                 and s.get('idx', 0) >= target_idx - 30
                 and s.get('direction') == direction
                 and _is_core_signal(s)]
    
    preceding.sort(key=lambda s: s.get('idx', 0))
    recent = preceding[-5:] if len(preceding) >= 5 else preceding
    
    chain_code = ''.join(classify_signal_code(s) for s in recent)
    
    # Pattern matching
    pattern_bonus = 0.0
    matched_desc = ''
    for length in range(min(5, len(chain_code)), 1, -1):
        for start in range(len(chain_code) - length + 1):
            sub = chain_code[start:start+length]
            if sub in PATTERN_DB:
                p = PATTERN_DB[sub]
                pattern_bonus = p['bonus']
                matched_desc = p['desc']
                break
        if pattern_bonus != 0:
            break
    
    if not matched_desc:
        matched_desc = '孤立' if len(preceding) == 0 else f'未识别({chain_code[-3:]})'
    
    # === Layer 4: 多周期共振 ===
    resonance_bonus = 0.0
    if weekly_trend_val == 'bull' and context in ('trend_continuation', 'poi_pullback'):
        resonance_bonus = 0.15  # 周线牛+日线趋势/回调 = 强共振
    elif weekly_trend_val == 'bull':
        resonance_bonus = 0.05  # 周线牛
    elif weekly_trend_val == 'bear':
        resonance_bonus = -0.10  # 周线熊 - 逆势交易降级
    
    # 阶段加成
    phase_bonus = 0.0
    if phase == 'breakout':
        phase_bonus = 0.10  # 突破阶段信号更可靠
    elif phase == 'volatile':
        phase_bonus = 0.05
    elif phase == 'consolidation':
        phase_bonus = 0.0
    elif phase == 'ranging':
        phase_bonus = -0.05
    
    # === 合成评分 ===
    score = base_score + pattern_bonus + resonance_bonus + phase_bonus
    
    # 时间衰减: 信号太旧降分
    if test_bars > 0 and test_bars > 20:
        score -= 0.10
    
    score = max(0.0, min(1.0, score))
    
    # === 分级 ===
    if score >= 0.75:
        grade = 'A'
        action = 'enter'
        entry_mult = 1.2
    elif score >= 0.60:
        grade = 'B'
        action = 'enter'
        entry_mult = 1.0
    elif score >= 0.50:
        grade = 'C'
        action = 'enter'
        entry_mult = 0.7
    elif score >= 0.35:
        grade = 'D'
        action = 'wait'
        entry_mult = 0.0
    else:
        grade = 'F'
        action = 'skip'
        entry_mult = 0.0
    
    return {
        'score': round(score, 3),
        'grade': grade,
        'action': action,
        'entry_mult': entry_mult,
        'chain': chain_code[-6:],
        'desc': context_desc,
        'pattern': matched_desc,
        'context': context,
        'poi_tested': poi_tested,
        'poi_bounce': poi_bounce,
        'test_bars': test_bars,
        'resonance': weekly_trend_val,
        'pattern_bonus': pattern_bonus,
        'resonance_bonus': resonance_bonus,
        'phase_bonus': phase_bonus,
    }


def calc_exit_v35(ohlcv, entry_idx, entry_price, sl_price, tp_price, max_hold=120):
    """
    V35固定SL/TP退出:
    - 价格≤SL时止损退出
    - 价格≥TP时止盈退出
    - 否则max_hold后收盘退出
    """
    exit_idx, exit_price, won = -1, None, False
    
    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(ohlcv))):
        bar = ohlcv[j]
        bar_low, bar_high, bar_close = bar['l'], bar['h'], bar['c']
        
        # 先检查TP (同一根K线优先止盈)
        if tp_price and bar_high >= tp_price:
            exit_idx = j
            exit_price = tp_price
            won = True
            break
        
        # 检查SL
        if sl_price and bar_low <= sl_price:
            exit_idx = j
            exit_price = sl_price
            won = False
            break
        
        # 收盘检查
        if bar_close <= sl_price:
            exit_idx = j
            exit_price = bar_close
            won = False
            break
        if tp_price and bar_close >= tp_price:
            exit_idx = j
            exit_price = bar_close
            won = True
            break
    
    if exit_idx == -1:
        exit_idx = min(entry_idx + max_hold, len(ohlcv) - 1)
        exit_price = ohlcv[exit_idx]['c']
        won = exit_price > entry_price
    
    return exit_idx, exit_price, won


def run_stock_v35(symbol: str, sl_values: List[float] = None, 
                  tp_values: List[float] = None) -> Optional[Dict]:
    """
    V35单股票回测 — 支持多种SL/TP组合参数优化
    """
    if sl_values is None:
        sl_values = [0.5, 0.8, 1.0]
    if tp_values is None:
        tp_values = [2.0, 3.0]
    
    ohlcv = load_ohlcv(symbol)
    if not ohlcv: return None
    
    try:
        n = len(ohlcv)
        roll_end = n - ROLL_END_OFFSET
        phase = detect_market_phase(ohlcv)
        base = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
        all_signals = detect_all_signals_v11(ohlcv, params=base, tf='daily')['all']
        if not all_signals or len(all_signals) < 3: return None
        
        # Weekly trend (multi-timeframe)
        weekly = synthesize_weekly(ohlcv)
        wt = weekly_trend(weekly)
        
        # === 每股参数优化: 测试不同SL/TP组合，选最优 ===
        best_perf = None
        best_params = None
        best_trades = None
        
        for sl_pct in sl_values:
            for tp_pct in tp_values:
                trades = []
                entered_bar = -999
                swing_count = 0
                fixed_count = 0
                
                for i in range(ROLL_START, roll_end):
                    if i - entered_bar < COOLDOWN: continue
                    
                    # 找已确认的FVG Bull信号
                    sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
                    fvg_bull = [s for s in sigs_before if 'FVG_Bull' in s.get('type', '')]
                    if not fvg_bull: continue
                    
                    sig = None
                    for s in reversed(fvg_bull):
                        s_conf = s.get('confirmed_at', s.get('idx', 0) + 1)
                        if i >= s_conf:
                            sig = s
                            break
                    if sig is None: continue
                    
                    # V35信号评分
                    timing = score_signal_v35(all_signals, sig, ohlcv, wt, phase)
                    if timing['grade'] in ('D', 'F'): continue
                    if timing['grade'] == 'C' and timing['entry_mult'] < 0.5: continue
                    
                    # 成交量过滤
                    bar_vol = ohlcv[i].get('v', ohlcv[i].get('vol', 0))
                    avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0)) 
                                  for j in range(max(0,i-30),i)) / 30
                    if avg_vol > 0 and bar_vol < avg_vol * MIN_VOL_RATIO: continue
                    
                    # 阳线
                    if ohlcv[i]['c'] <= ohlcv[i]['o']: continue
                    
                    # FVG gap
                    upper = sig.get('upper', 0); lower = sig.get('lower', 0)
                    if upper > 0 and lower > 0:
                        if (upper - lower) / lower * 100 < MIN_FVG_GAP: continue
                    
                    # Entry价格
                    entry_price = ohlcv[i]['c']
                    
                    # SL: 摆动点优先
                    sl_info = find_best_swing_sl(ohlcv, i, entry_price)
                    if sl_info is not None:
                        sl_price = sl_info['sl_price']
                        sl_type = 'swing'
                    else:
                        sl_price = entry_price * (1 - sl_pct / 100)
                        sl_type = 'fixed'
                    
                    # TP: 摆动点优先, 否则固定
                    tp_info = find_swing_tp(ohlcv, i, entry_price)
                    if tp_info is not None:
                        tp_price = tp_info['tp_price']
                        tp_type = 'swing'
                    else:
                        tp_price = entry_price * (1 + tp_pct / 100)
                        tp_type = 'fixed'
                    
                    # 退出
                    exit_idx, exit_price, won = calc_exit_v35(
                        ohlcv, i, entry_price, sl_price, tp_price, MAX_HOLD)
                    
                    pnl = (exit_price - entry_price) / entry_price * 100
                    risk = abs(entry_price - sl_price)
                    actual_rr = abs(exit_price - entry_price) / risk if risk > 0 else 10
                    
                    trade = {
                        'entry_idx': i, 'exit_idx': exit_idx,
                        'entry_price': round(entry_price, 2),
                        'exit_price': round(exit_price, 2),
                        'sl': round(sl_price, 2),
                        'tp': round(tp_price, 2),
                        'pnl_pct': round(pnl, 2),
                        'won': won, 'rr': round(actual_rr, 2),
                        'hold_bars': exit_idx - i,
                        'sl_type': sl_type, 'tp_type': tp_type,
                        'sl_pct': sl_pct, 'tp_pct': tp_pct,
                        'signal_type': 'FVG',
                        'v35_score': timing['score'],
                        'v35_grade': timing['grade'],
                        'v35_chain': timing['chain'],
                        'v35_desc': timing['desc'],
                        'v35_context': timing['context'],
                        'pattern': timing['pattern'],
                        'poi_tested': timing['poi_tested'],
                        'poi_bounce': timing['poi_bounce'],
                        'test_bars': timing['test_bars'],
                        'resonance': timing['resonance'],
                        'phase': phase,
                    }
                    trades.append(trade)
                    entered_bar = i
                
                if len(trades) < MIN_TRADES: continue
                
                wins = sum(1 for t in trades if t['won'])
                wr = wins / len(trades) * 100
                win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
                loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
                pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
                avg_rr = sum(t['rr'] for t in trades) / len(trades)
                avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
                avg_hold = sum(t['hold_bars'] for t in trades) / len(trades)
                
                # 评分: WR * RR * (1 + avg_hold/max_hold)
                perf_score = (wr / 100) * avg_rr * (1 + avg_hold / 30)
                
                if best_perf is None or perf_score > best_perf:
                    best_perf = perf_score
                    best_params = {'sl': sl_pct, 'tp': tp_pct}
                    best_trades = trades
        
        if best_trades is None or len(best_trades) < MIN_TRADES:
            return None
        
        wins = sum(1 for t in best_trades if t['won'])
        wr = wins / len(best_trades) * 100
        win_pnl = sum(t['pnl_pct'] for t in best_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in best_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in best_trades) / len(best_trades)
        avg_pnl = sum(t['pnl_pct'] for t in best_trades) / len(best_trades)
        swing_count = sum(1 for t in best_trades if t['sl_type'] == 'swing')
        
        return {
            'trades': best_trades,
            'perf': {
                'symbol': symbol,
                'n_trades': len(best_trades), 'wins': wins, 'losses': len(best_trades)-wins,
                'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
                'profit_factor': round(pf, 1) if pf < 999 else 999,
                'avg_pnl': round(avg_pnl, 2),
                'avg_hold': round(sum(t['hold_bars'] for t in best_trades)/len(best_trades), 1),
                'swing_sl_pct': round(swing_count/len(best_trades)*100, 1) if best_trades else 0,
                'opt_sl': best_params['sl'],
                'opt_tp': best_params['tp'],
                'phase': phase,
                'avg_v35_score': round(sum(t['v35_score'] for t in best_trades)/len(best_trades), 2),
            },
        }
    except Exception as e:
        return None


def main():
    symbols = sorted([f.stem.replace('_daily_300','').replace('_','.') 
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V35 — 4层信号时序 + 多周期共振 + 固定SL/TP + 每股参数优化")
    print(f"  Layer 1: POI分析 | Layer 2: 价格上下文 | Layer 3: 链模式 | Layer 4: 多周期共振")
    print(f"  SL: 0.5/0.8/1.0% | TP: 2.0/3.0% | 无breakeven trailing")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:200]):
        result = run_stock_v35(sym)
        if result:
            p = result['perf']
            all_trades.extend(result['trades'])
            stock_results.append(p)
            print(f"  [{idx+1:3d}/200] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% hold={p['avg_hold']:.1f} "
                  f"SL={p['opt_sl']}/TP={p['opt_tp']} PF={p['profit_factor']:.0f}", flush=True)
        else:
            print(f"  [{idx+1:3d}/200] {sym:12s} SKIP", flush=True)
    
    total_time = time.time() - t_start
    
    if not all_trades:
        print("No trades!")
        return
    
    n = len(all_trades)
    wins = sum(1 for t in all_trades if t['won'])
    wr = wins / n * 100
    win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
    loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
    avg_rr = sum(t['rr'] for t in all_trades) / n
    avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
    avg_hold = sum(t['hold_bars'] for t in all_trades) / n
    swing_trades = [t for t in all_trades if t.get('sl_type') == 'swing']
    sw_wr = sum(1 for t in swing_trades if t['won']) / len(swing_trades) * 100 if swing_trades else 0
    
    print(f"\n{'='*80}")
    print(f"V35 — {len(stock_results)}/{200} tradable | {total_time:.0f}s")
    print(f"{'='*80}")
    print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.0f}")
    print(f"  P&L: {avg_pnl:+.2f}% | Avg hold: {avg_hold:.1f} bars")
    print(f"  Swing SL: {len(swing_trades)}/{n} ({len(swing_trades)/n*100:.0f}%) | WR={sw_wr:.1f}%")
    print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}/{len(stock_results)}")
    
    # Hold bars distribution
    hold_dist = {}
    for t in all_trades:
        h = t['hold_bars']
        hold_dist[h] = hold_dist.get(h, 0) + 1
    print(f"\n  Hold bars distribution:")
    for h in sorted(hold_dist.keys()):
        print(f"    {h:3d} bars: {hold_dist[h]:4d} trades ({hold_dist[h]/n*100:.1f}%)")
    
    # Context breakdown
    contexts = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0.0, 'hold': 0})
    for t in all_trades:
        ctx = t.get('v35_context', 'unknown')
        contexts[ctx]['n'] += 1
        contexts[ctx]['wins'] += 1 if t['won'] else 0
        contexts[ctx]['pnl'] += t['pnl_pct']
        contexts[ctx]['hold'] += t['hold_bars']
    
    print(f"\n  Context breakdown:")
    for ctx, data in sorted(contexts.items(), key=lambda x: x[1]['n'], reverse=True):
        cwr = data['wins'] / data['n'] * 100
        apnl = data['pnl'] / data['n']
        ahold = data['hold'] / data['n']
        print(f"    {ctx:25s}: {data['n']:4d} trades | WR={cwr:.1f}% | P&L={apnl:+.2f}% | hold={ahold:.1f}")
    
    # P&L distribution
    print(f"\n  P&L Distribution:")
    buckets = [(-5,0),(0,0.5),(0.5,1),(1,2),(2,5),(5,10),(10,50)]
    for b in buckets:
        subset = [t for t in all_trades if b[0] <= t['pnl_pct'] < b[1]]
        if subset:
            print(f"    {b[0]:+}% to {b[1]:+}%: {len(subset):3d} trades | "
                  f"RR>=2: {sum(1 for t in subset if t['rr']>=2):3d}")
    
    # RR>=2.0
    good = [t for t in all_trades if t['rr'] >= 2.0]
    gw = sum(1 for t in good if t['won'])/len(good)*100 if good else 0
    print(f"\n  RR>=2.0 subset: {len(good)}/{n} trades | WR={gw:.1f}% | "
          f"P&L={sum(t['pnl_pct'] for t in good)/len(good):+.2f}%")
    
    print(f"\n{'='*80}")
    print(f"                    VERSION COMPARISON")
    print(f"{'='*80}")
    print(f"  V28: WR=76.6% RR=5.94x PF=27 P&L=+1.59% (SL=0.3%, trailing)")
    print(f"  V33: WR=71.3% RR=4.85x PF=24 P&L=+1.47% (SL=0.3%, chain scoring)")
    print(f"  V34: WR=71.9% RR=5.10x PF=26 P&L=+1.54% (SL=0.3%, POI+context)")
    print(f"  V35: WR={wr:.1f}% RR={avg_rr:.2f}x PF={pf:.0f} P&L={avg_pnl:+.2f}% "
          f"(SL=0.5-1.0%, TP=2-3%, 4-layer timing)")
    
    # Save
    outpath = OUTPUT_DIR / 'backtest_v35.json'
    json.dump({
        'timestamp': datetime.now().isoformat(),
        'config': {'version': 'V35', 'sl_range': '0.5-1.0', 'tp_range': '2.0-3.0'},
        'summary': {
            'total_trades': n, 'tradable': len(stock_results),
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2), 'avg_pnl': round(avg_pnl, 2),
            'avg_hold': round(avg_hold, 1),
        },
        'stocks': stock_results, 'all_trades': all_trades,
    }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
