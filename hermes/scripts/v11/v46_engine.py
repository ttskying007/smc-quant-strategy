#!/usr/bin/env python3
"""
SMC V46 — 信号反转检测 + 价格回踩入场 + 自适应止盈止损引擎
================================================================
核心改进 (对V45的3项根本性修复):

1. OB检测: 仅反转结构处, 趋势延续不误报
2. 入场: 价格回踩信号区间后入场 (POI激活 = 入场门限)
3. 止盈止损: 自适应moving SL/TP + 跳空保护

V46架构:
  signals_v11 (14种全检测) → OB反转过滤 → POI回踩等待 → 区间入场
  → 自适应trailing(ATR动态阶) → 方向感知TP
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v46')
OUTPUT_DIR.mkdir(exist_ok=True)

MIN_BARS = 120
MAX_HOLD = 60

# ── 交易信号类型 ──
TRADE_SIGNAL_TYPES = {'FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear',
                      'SweepUp', 'SweepDown', 'CHOCH_Bull', 'CHOCH_Bear'}

# ── 入口信号类型 (入场必须回踩) ──
ENTRY_SIGNAL_TYPES = {'FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear'}

# ── 质量门限 ──
QUALITY_THRESHOLDS = {
    'FVG_Bull': 0.65,   # 提高FVG门槛减少低质量
    'FVG_Bear': 0.70,
    'OB_Bull': 0.50,
    'OB_Bear': 0.55,
}

# ── 共振门限 ──
RESONANCE_THRESHOLDS = {'bull': 0.50, 'bear': 0.60}

# ── 做空开关 ──
ENABLE_BEAR = False

# ── 回踩入场最大等待时间 ──
MAX_RETEST_BARS = 30  # 信号后最多等30根K线回踩

# ============================================================
# 核心函数1: 反转OB检测 (替换signals_v11中的OB过滤)
# ============================================================
def is_reversal_ob(ohlcv, sig, all_signals):
    """判断OB是否在结构反转处 (延续上升中的pullback不算)
    
    反转OB判定规则 (Bull OB):
    1. 20-bar趋势必须为下行 (trend20 < -1%) 或 neutral
    2. 有近期的SweepDown (流动性猎杀)在10bar内
    3. 或者OB附近有摆动低点结构
    
    返回: (is_reversal: bool, reason: str)
    """
    idx = sig.get('idx', 0)
    sig_dir = sig.get('direction', '')
    sig_type = sig.get('type', '')
    
    # 只处理OB
    if 'OB' not in sig_type:
        return True, 'not_ob'
    
    if sig_dir == 'bull':
        # 1. 检查20-bar趋势
        if idx >= 20:
            trend20 = (ohlcv[idx]['c'] - ohlcv[idx-20]['c']) / ohlcv[idx-20]['c'] * 100
        else:
            trend20 = 0
        
        # 2. 检查10-bar内是否有SweepDown
        has_sweep = any(
            'SweepDown' in s.get('type', '')
            and abs(s.get('idx', 0) - idx) <= 10
            for s in all_signals
        )
        
        # 3. 检查附近CHOCH_Bull (结构转换)
        has_reversal_choch = any(
            'CHOCH_Bull' in s.get('type', '')
            and s.get('idx', 0) <= idx
            and idx - s.get('idx', 0) <= 15
            for s in all_signals
        )
        
        # 4. 检查摆动点附近
        at_swing = sig.get('metadata', {}).get('at_structure', False)
        
        # 判定逻辑:
        # 如果trend20 > +1%, 是上升趋势中的回调 → 非反转OB
        if trend20 > 1.0:
            # 但有sweep+choch可豁免
            if has_sweep and has_reversal_choch:
                return True, f'reversal_with_sweep_choch_trend{trend20:+.1f}%'
            return False, f'uptrend_pullback_{trend20:+.1f}%'
        
        # 趋势下跌或中性 → 反转OB (加分项)
        score = 0
        if has_sweep:
            score += 1
        if has_reversal_choch:
            score += 1
        if at_swing:
            score += 1
        if trend20 < -1.0:
            score += 1  # 明显下降趋势
        
        if score >= 1:
            return True, f'reversal_score{score}'
        else:
            return True, f'weak_reversal_trend{trend20:+.1f}%'
    
    elif sig_dir == 'bear':
        if idx >= 20:
            trend20 = (ohlcv[idx]['c'] - ohlcv[idx-20]['c']) / ohlcv[idx-20]['c'] * 100
        else:
            trend20 = 0
        
        has_sweep = any(
            'SweepUp' in s.get('type', '')
            and abs(s.get('idx', 0) - idx) <= 10
            for s in all_signals
        )
        has_reversal_choch = any(
            'CHOCH_Bear' in s.get('type', '')
            and s.get('idx', 0) <= idx
            and idx - s.get('idx', 0) <= 15
            for s in all_signals
        )
        at_swing = sig.get('metadata', {}).get('at_structure', False)
        
        if trend20 < -1.0:
            if has_sweep and has_reversal_choch:
                return True, f'reversal_with_sweep_choch'
            return False, f'downtrend_pullback'
        
        return True, 'bear_reversal'
    
    return True, 'default'


# ============================================================
# 核心函数2: 价格回踩POI检测
# ============================================================
def find_retest_entry(ohlcv, sig, sig_idx, all_signals, direction):
    """价格回踩信号区域后入场
    
    核心逻辑:
    - 信号(FVG/OB)定义了一个价格区间(lower~upper)
    - 等待价格回到这个区间
    - 回踩后, 以区间边界入场 (Bull:下沿, Bear:上沿)
    
    返回: (entry_bar, entry_price, sl_price, sl_type) or None
    """
    n = len(ohlcv)
    lower = sig.get('lower', 0)
    upper = sig.get('upper', 0)
    
    if lower <= 0 or upper <= 0 or upper <= lower:
        return None
    
    # 遍历信号后所有K线找回踩
    for j in range(sig_idx + 1, min(sig_idx + MAX_RETEST_BARS + 1, n - 2)):
        bar = ohlcv[j]
        
        if direction == 'bull':
            # Bull: 价格回到信号区域内 (low <= upper, high >= lower)
            # = 价格从上方回落到支撑区
            if bar['l'] <= upper and bar['h'] >= lower:
                # 回踩确认: 以bar收盘价入场
                entry_price = round(bar['c'], 2)
                # SL: 先用信号边界, 太远则用ATR自适应紧SL
                raw_sl = round(max(lower * 0.995, entry_price * 0.985), 2)
                raw_pct = (entry_price - raw_sl) / entry_price * 100 if entry_price > 0 else 0
                # 限制SL在0.15%-1.0%之间
                sl_pct = max(0.15, min(raw_pct, 1.0))
                sl_price = round(entry_price * (1 - sl_pct/100), 2)
                return {
                    'entry_bar': j,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'sl_type': 'retest_' + ('fvg_lower' if 'FVG' in sig.get('type','') else 'ob_lower'),
                    'sl_pct': sl_pct,
                    'retest_bars': j - sig_idx,
                }
        
        else:  # bear
            if bar['h'] >= lower and bar['l'] <= upper:
                entry_price = round(min(upper, bar['c']), 2)
                raw_sl = round(upper * 1.005, 2)
                raw_pct = (raw_sl - entry_price) / entry_price * 100 if entry_price > 0 else 0
                if raw_pct > 1.5:
                    sl_price = round(entry_price * 1.012, 2)
                    sl_pct = 1.2
                elif raw_pct < 0.15:
                    sl_price = round(entry_price * 1.002, 2)
                    sl_pct = 0.2
                else:
                    sl_price = raw_sl
                    sl_pct = round(raw_pct, 2)
                return {
                    'entry_bar': j,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'sl_type': 'retest_' + ('fvg_upper' if 'FVG' in sig.get('type','') else 'ob_upper'),
                    'sl_pct': sl_pct,
                    'retest_bars': j - sig_idx,
                }
    
    return None  # 没有回踩, 放弃


# ============================================================
# ============================================================
# 核心函数3: V46自适应trailing — 专门优化回踩入场
# ============================================================
def calc_v46_trailing(ohlcv, entry_idx, entry_price, initial_sl,
                       structural_tp, n, max_hold, direction,
                       atr_pct, be_lock=0.20, look_lock=0.50):
    """V46 自适应trailing — 专为回踩入场优化
    
    回踩入场的特性: 
    - 价格刚回踩到支撑区, 不是刚突破
    - 需要给价格"喘息"空间 (跳空低开直接打SL的情况少)
    - SL应该反应支撑区下方的结构距离
    
    策略: 
    - 0.15%获利即锁保本 (比V38.4更早)
    - ATR自适应阈值
    """
    sl = initial_sl
    extreme = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None

    is_bear = (direction == 'bear')
    has_tp = tp_price is not None

    # ATR自适应阈值 (V46.0 proven)
    if atr_pct < 1.5:
        be_th = 0.15     # 保本
        lk1_th = 0.30    # 微利锁1
        lk2_th = 0.50    # 微利锁2
        pr1_th = 1.0     # 小赢锁
        pr2_th = 2.0     # 中赢锁
        pr3_th = 4.0     # 大赢锁
    elif atr_pct < 3.0:
        be_th = 0.20
        lk1_th = 0.40
        lk2_th = 0.70
        pr1_th = 1.5
        pr2_th = 3.0
        pr3_th = 6.0
    else:
        be_th = 0.30
        lk1_th = 0.60
        lk2_th = 1.0
        pr1_th = 2.0
        pr2_th = 4.0
        pr3_th = 8.0
    
    # 无TP更宽松
    if not has_tp:
        be_th *= 1.5
        lk1_th *= 1.5
        lk2_th *= 1.5
        pr1_th *= 1.5

    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]

        if is_bear:
            if bar['l'] < extreme:
                extreme = bar['l']
            gain_pct = (entry_price - extreme) / entry_price * 100
            
            if tp_price and extreme <= tp_price * 1.05:
                sl = min(sl, extreme * (1 + max(0.3, tp_pct * 0.2) / 100))
                if extreme <= tp_price * 1.02:
                    return j, tp_price, True
                if bar['h'] >= sl:
                    return j, min(sl, bar['h']), extreme < entry_price
            else:
                if gain_pct >= pr3_th:
                    sl = min(sl, extreme * (1 + pr3_th/2/100))
                elif gain_pct >= pr2_th:
                    sl = min(sl, extreme * (1 + pr2_th/3/100))
                elif gain_pct >= pr1_th:
                    sl = min(sl, extreme * (1 + 0.3/100))
                elif gain_pct >= lk2_th:
                    sl = min(sl, entry_price * (1 + 0.1/100))
                elif gain_pct >= lk1_th:
                    sl = min(sl, entry_price * 1.0)
                elif gain_pct >= be_th:
                    sl = min(sl, entry_price * 1.0)

            if bar['h'] >= sl:
                exit_price = min(sl, bar['h'])
                return j, round(exit_price, 2), exit_price < entry_price

        else:  # bull
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100
            
            if tp_price and extreme >= tp_price * 0.92:
                sl = max(sl, extreme * (1 - max(0.3, tp_pct * 0.2) / 100))
                if extreme >= tp_price * 0.98:
                    return j, tp_price, True
                if bar['l'] <= sl:
                    return j, max(sl, bar['l']), True
            else:
                if gain_pct >= pr3_th:
                    sl = max(sl, extreme * (1 - pr3_th/2/100))
                elif gain_pct >= pr2_th:
                    sl = max(sl, extreme * (1 - pr2_th/3/100))
                elif gain_pct >= pr1_th:
                    sl = max(sl, extreme * (1 - 0.3/100))
                elif gain_pct >= lk2_th:
                    sl = max(sl, entry_price * (1 - 0.1/100))
                elif gain_pct >= lk1_th:
                    sl = max(sl, entry_price * 1.0)
                elif gain_pct >= be_th:
                    sl = max(sl, entry_price * 1.0)

            if bar['l'] <= sl:
                exit_price = max(sl, bar['l'])
                return j, round(exit_price, 2), exit_price > entry_price

    # Max hold
    exit_idx = min(entry_idx + max_hold, n - 1)
    exit_price = ohlcv[exit_idx]['c']
    won = exit_price > entry_price if not is_bear else exit_price < entry_price
    return exit_idx, round(exit_price, 2), won


# ============================================================
# 辅助函数
# ============================================================
def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS:
        return None
    for bar in data:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    return data


def calc_atr_v46(ohlcv, idx, period=14):
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100 if ohlcv[idx]['l'] > 0 else 0.5
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100 if ohlcv[idx]['l'] > 0 else 0.5


def calc_stock_atr(ohlcv):
    """计算股票平均ATR%"""
    n = len(ohlcv)
    atr_list = [calc_atr_v46(ohlcv, i) for i in range(14, min(50, n))]
    return sum(atr_list) / len(atr_list) if atr_list else 1.0


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback:
        return 'neutral', 0
    seg = ohlcv[idx-lookback:idx+1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e - s) / s * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5, idx), idx+1)) / min(6, idx+1)
    ema_d = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_d > 0:
        return 'up', change
    if change < -0.6 and ema_d < 0:
        return 'down', abs(change)
    return 'neutral', 0


def find_swing_high_forward(ohlcv, entry_idx, lookahead=60):
    n = len(ohlcv)
    best = None
    for i in range(entry_idx + 2, min(entry_idx + lookahead, n - 2)):
        is_high = all(ohlcv[i]['h'] >= ohlcv[j]['h']
                      for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_high and ohlcv[i]['h'] > ohlcv[entry_idx]['c']:
            if best is None or ohlcv[i]['h'] < ohlcv[best['idx']]['h']:
                best = {'idx': i, 'price': ohlcv[i]['h']}
    return best


def find_swing_low_forward(ohlcv, entry_idx, lookahead=60):
    n = len(ohlcv)
    best = None
    for i in range(entry_idx + 2, min(entry_idx + lookahead, n - 2)):
        is_low = all(ohlcv[i]['l'] <= ohlcv[j]['l']
                     for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_low and ohlcv[i]['l'] < ohlcv[entry_idx]['c']:
            if best is None or ohlcv[i]['l'] > ohlcv[best['idx']]['l']:
                best = {'idx': i, 'price': ohlcv[i]['l']}
    return best


# ============================================================
# TP计算
# ============================================================
def calc_v46_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals):
    """TP: 前方CHOCH > 前方摆动 > 无TP"""
    # 1. 前方CHOCH
    if direction == 'bull':
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bull' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 60]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('upper', 0))
            if tp_price > entry_price:
                tp_pct = (tp_price - entry_price) / entry_price * 100
                if tp_pct >= 0.3:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']
    else:
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bear' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 60]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('lower', 0))
            if tp_price > 0 and tp_price < entry_price:
                tp_pct = (entry_price - tp_price) / entry_price * 100
                if tp_pct >= 0.3:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']
    
    # 2. 前方摆动
    if direction == 'bull':
        swing = find_swing_high_forward(ohlcv, entry_idx, 60)
        if swing and swing['price'] > entry_price:
            tp_pct = (swing['price'] - entry_price) / entry_price * 100
            if tp_pct >= 0.5:
                return round(swing['price'], 4), 'swing_high', round(tp_pct, 2), swing['idx']
    else:
        swing = find_swing_low_forward(ohlcv, entry_idx, 60)
        if swing and swing['price'] < entry_price:
            tp_pct = (entry_price - swing['price']) / entry_price * 100
            if tp_pct >= 0.5:
                return round(swing['price'], 4), 'swing_low', round(tp_pct, 2), swing['idx']
    
    return None, None, None, None


# ============================================================
# V46 入场评估
# ============================================================
def evaluate_v46_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n,
                        direction, params, stock_params):
    """V46统一入场评估 — 反转OB + 价格回踩 + 自适应trailing"""
    sig_type = sig.get('type', '')
    sig_idx = sig.get('idx', 0)
    
    if sig_idx < 40 or sig_idx >= n - 15:
        return None
    
    # ── 入口类型判定 ──
    is_fvg = 'FVG' in sig_type and 'Mitigated' not in sig_type and 'IFVG' not in sig_type
    is_ob = 'OB' in sig_type and 'BreakerBlock' not in sig_type
    
    if not (is_fvg or is_ob):
        return None
    
    quality = sig.get('confidence', sig.get('quality', 0.5))
    sig_dir = sig.get('direction', '')
    
    # ── 做空开关 ──
    if sig_dir == 'bear' and not ENABLE_BEAR:
        return None
    if sig_dir == 'bear' and not is_ob:
        return None
    
    # ── 质量门限 ──
    q_threshold = QUALITY_THRESHOLDS.get(sig_type, 0.50)
    if quality < q_threshold:
        return None
    
    # ── 核心改进1: 反转OB过滤 — OB必须反转处
    if is_ob:
        is_rev, rev_reason = is_reversal_ob(ohlcv, sig, all_signals)
        if not is_rev:
            return None  # 趋势延续的OB不交易
    
    # OB-only模式: 保留OB但FVG也不排除(用户要求用FVG)
    # 但FVG质量门限提高到0.65
    
    # ── 成交量过滤 ──
    if sig_idx > 30 and sig_idx < n:
        bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                     for j in range(max(0, sig_idx-30), sig_idx)) / 30
        if bv < avg_vol * 0.6:
            return None
    
    # ── 序列+共振过滤 ──
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None
    
    window = ohlcv[:sig_idx+1]
    tf_seq = {'daily': seq_r}
    res = evaluate_full_resonance_v11(
        all_signals=all_sigs_up_to_idx,
        tf_sequences=tf_seq,
        ohlcv=window)
    
    mr = RESONANCE_THRESHOLDS.get(sig_dir, 0.50)
    if res.total < mr:
        return None
    
    dec = make_entry_decision_v11(res, seq_r, params, tf_sequences=tf_seq)
    if dec['action'] != 'enter':
        return None
    
    # ── 核心改进2: 价格回踩入场 ──
    retest = find_retest_entry(ohlcv, sig, sig_idx, all_signals, sig_dir)
    if not retest:
        return None  # 价格未回踩, 放弃交易
    
    entry_bar = retest['entry_bar']
    entry_price = retest['entry_price']
    init_sl = retest['sl_price']
    sl_type_name = retest['sl_type']
    sl_pct_val = retest['sl_pct']
    retest_bars = retest['retest_bars']
    
    # ── 趋势过滤 ──
    td, _ = short_trend(ohlcv, entry_bar)
    if sig_dir == 'bull' and td == 'down':
        return None
    if sig_dir == 'bear' and td == 'up':
        return None
    
    micro = short_trend(ohlcv, entry_bar, 8)
    meso = short_trend(ohlcv, entry_bar, 20)
    macro = short_trend(ohlcv, entry_bar, 40)
    uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
    if sig_dir == 'bull' and dc >= 2:
        return None
    if sig_dir == 'bear' and uc >= 2:
        return None
    
    # ── TP ──
    tp_price, tp_type, tp_pct, tp_idx = calc_v46_tp(
        ohlcv, entry_bar, entry_price, sig, sig_dir, all_signals)
    
    # ── ATR ──
    atr_pct = stock_params.get('atr_pct', 2.0)
    max_hold = stock_params.get('max_hold', 30)
    
    # ── 核心改进3: 自适应trailing ──
    exit_idx, exit_price, won = calc_v46_trailing(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, max_hold, sig_dir,
        atr_pct=atr_pct, be_lock=0.20, look_lock=0.50)
    
    pnl = (exit_price - entry_price) / entry_price * 100
    actual_rr = abs(exit_price - entry_price) / abs(entry_price - init_sl) if entry_price != init_sl else 10
    
    is_bear = sig_dir == 'bear'
    
    return {
        'entry_idx': entry_bar,
        'sig_idx': sig_idx,
        'exit_idx': exit_idx,
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'sl': round(init_sl, 2),
        'pnl_pct': round(pnl, 2),
        'won': won,
        'rr': round(actual_rr, 2),
        'hold_bars': exit_idx - entry_bar,
        'sl_type': sl_type_name,
        'sl_pct': round(sl_pct_val, 2),
        'tp_type': tp_type,
        'tp_pct': round(tp_pct, 2) if tp_pct else None,
        'signal_type': sig_type,
        'direction': sig_dir,
        'entry_type': 'FVG' if 'FVG' in sig_type else 'OB',
        'exit_method': 'tp_hit' if tp_type and tp_price and (
            (not is_bear and exit_price >= tp_price) or
            (is_bear and exit_price <= tp_price)
        ) else 'trailing',
        'resonance_total': round(res.total, 3),
        'retest_bars': retest_bars,
    }


# ============================================================
# 回测
# ============================================================
def calc_stock_params_v46(ohlcv, symbol):
    n = len(ohlcv)
    if n < 30:
        return {'atr_pct': 2.0, 'max_hold': 30, 'vol_class': 'medium'}
    
    atr_list = [calc_atr_v46(ohlcv, i) for i in range(14, min(50, n))]
    avg_atr = sum(atr_list) / len(atr_list) if atr_list else 1.0
    
    if avg_atr < 1.0:
        vol_class = 'low'
        max_hold = 30
    elif avg_atr < 3.0:
        vol_class = 'medium'
        max_hold = 30
    else:
        vol_class = 'high'
        max_hold = 25
    
    return {
        'atr_pct': round(avg_atr, 3),
        'max_hold': max_hold,
        'vol_class': vol_class,
    }


def backtest_stock_v46(ohlcv, symbol):
    """V46单股票回测"""
    n = len(ohlcv)
    stock_params = calc_stock_params_v46(ohlcv, symbol)
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
    
    signals_result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_signals = signals_result.get('all', [])
    
    if not all_signals or len(all_signals) < 3:
        return None
    
    trades = []
    used_bars = set()
    
    for sig in all_signals:
        sig_idx = sig.get('idx', 0)
        sig_type = sig.get('type', '')
        direction = sig.get('direction', '')
        
        if sig_type not in TRADE_SIGNAL_TYPES:
            continue
        if 'FVG' not in sig_type and 'OB' not in sig_type:
            continue
        if sig_idx < 40 or sig_idx >= n - 10:
            continue
        
        sigs_up_to = [s for s in all_signals if s.get('idx', 0) <= sig_idx]
        
        result = evaluate_v46_entry(
            all_signals, sigs_up_to, sig, ohlcv, n, direction,
            base_params, stock_params)
        
        if result:
            if result['entry_idx'] in used_bars:
                continue
            used_bars.add(result['entry_idx'])
            trades.append(result)
    
    if len(trades) < 2:
        return None
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    
    sl_types = Counter(t.get('sl_type', 'unknown') for t in trades)
    tp_types = Counter(t.get('tp_type', 'none') for t in trades)
    exit_methods = Counter(t.get('exit_method', 'unknown') for t in trades)
    directions = Counter(t.get('direction', 'unknown') for t in trades)
    entry_types = Counter(t.get('entry_type', 'unknown') for t in trades)
    retest_count = sum(1 for t in trades if t.get('retest_bars', 0) > 0)
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades),
            'wins': wins,
            'losses': len(trades) - wins,
            'win_rate': round(wr, 1),
            'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2),
            'sl_types': dict(sl_types),
            'tp_types': dict(tp_types),
            'exit_methods': dict(exit_methods),
            'directions': dict(directions),
            'entry_types': dict(entry_types),
            'retest_count': retest_count,
            'vol_class': stock_params.get('vol_class', 'medium'),
            'stock_params': {k: v for k, v in stock_params.items()},
        }
    }


# ============================================================
# 批量回测
# ============================================================
def run_backtest(symbols, label="V46"):
    all_trades, stock_results = [], []
    t_start = time.time()
    sl_type_stats = Counter()
    tp_type_stats = Counter()
    direction_stats = Counter()
    entry_type_stats = Counter()
    retest_total = 0
    
    print(f"{'='*80}")
    print(f"V46 — 反转OB+回踩入场+自适应trailing")
    print(f"  {len(symbols)} 只股票 | 核心: 反转过滤/回踩门限/ATR自适应")
    print(f"{'='*80}")
    
    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} NO-DATA")
            continue
        
        result = backtest_stock_v46(ohlcv, sym)
        if result:
            p = result['perf']
            for st, cnt in p['sl_types'].items():
                sl_type_stats[st] += cnt
            for tt, cnt in p['tp_types'].items():
                tp_type_stats[tt] += cnt
            for d, cnt in p['directions'].items():
                direction_stats[d] += cnt
            for et, cnt in p['entry_types'].items():
                entry_type_stats[et] += cnt
            retest_total += p.get('retest_count', 0)
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x "
                  f"retest={p.get('retest_count',0)}")
        else:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} SKIP")
        
        if (idx + 1) % 50 == 0:
            time.sleep(0.1)
    
    total_time = time.time() - t_start
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = wp / lp if lp > 0 else 999
        rr = sum(t['rr'] for t in all_trades) / n
        pnl = sum(t['pnl_pct'] for t in all_trades) / n
        holds = [t['hold_bars'] for t in all_trades]
        
        tp_hits = [t for t in all_trades if t.get('exit_method') == 'tp_hit']
        trailing_trades = [t for t in all_trades if t.get('exit_method') == 'trailing']
        n_tp = len(tp_hits)
        n_trail = len(trailing_trades)
        bull_trades = [t for t in all_trades if t.get('direction') == 'bull']
        bear_trades = [t for t in all_trades if t.get('direction') == 'bear']
        n_bull = len(bull_trades)
        n_bear = len(bear_trades)
        
        print(f"\n  === {label} RESULTS ===")
        print(f"  Time: {total_time:.0f}s | Stocks: {len(stock_results)}/{len(symbols)}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars | Max: {max(holds)}")
        print(f"  Retest entry: {retest_total}/{n} ({retest_total/n*100:.1f}%)")
        print(f"  Avg retest bars: {sum(t.get('retest_bars',0) for t in all_trades)/max(1,retest_total):.1f}")
        
        print(f"\n  TP vs Trailing:")
        if n_tp > 0:
            print(f"    TP hit:  n={n_tp:5d} WR={sum(1 for t in tp_hits if t['won'])/n_tp*100:.1f}% RR={sum(t['rr'] for t in tp_hits)/n_tp:.2f}x")
        if n_trail > 0:
            print(f"    Trailing: n={n_trail:5d} WR={sum(1 for t in trailing_trades if t['won'])/n_trail*100:.1f}% RR={sum(t['rr'] for t in trailing_trades)/n_trail:.2f}x")
        
        print(f"\n  Direction:")
        if n_bull > 0:
            wr_b = sum(1 for t in bull_trades if t['won'])/n_bull*100
            rr_b = sum(t['rr'] for t in bull_trades)/n_bull
            pnl_b = sum(t['pnl_pct'] for t in bull_trades)/n_bull
            print(f"    Bull: n={n_bull:5d} WR={wr_b:.1f}% RR={rr_b:.2f}x P&L={pnl_b:+.2f}%")
        if n_bear > 0:
            wr_b = sum(1 for t in bear_trades if t['won'])/n_bear*100
            rr_b = sum(t['rr'] for t in bear_trades)/n_bear
            pnl_b = sum(t['pnl_pct'] for t in bear_trades)/n_bear
            print(f"    Bear: n={n_bear:5d} WR={wr_b:.1f}% RR={rr_b:.2f}x P&L={pnl_b:+.2f}%")
        
        avg_win = sum(t['pnl_pct'] for t in all_trades if t['won']) / wins if wins > 0 else 0
        avg_loss = abs(sum(t['pnl_pct'] for t in all_trades if not t['won'])) / (n - wins) if n > wins else 0
        wl_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        print(f"    W/L ratio: avgWin={avg_win:.3f}% avgLoss={avg_loss:.3f}% ratio={wl_ratio:.1f}x")
        
        print(f"\n  SL Type breakdown:")
        for st, cnt in sl_type_stats.most_common():
            s_trades = [t for t in all_trades if t['sl_type'] == st]
            s_wr = sum(1 for t in s_trades if t['won'])/len(s_trades)*100
            s_pnl = sum(t['pnl_pct'] for t in s_trades)/len(s_trades)
            print(f"    {st:25s}: {cnt:5d} ({cnt/n*100:.1f}%) | WR={s_wr:.1f}% | avgP&L={s_pnl:+.2f}%")
        
        print(f"\n  TP Type breakdown:")
        for tt, cnt in tp_type_stats.most_common():
            t_trades = [t for t in all_trades if t['tp_type'] == tt]
            t_rr = sum(t['rr'] for t in t_trades)/len(t_trades)
            t_wr = sum(1 for t in t_trades if t['won'])/len(t_trades)*100
            tt_key = tt if tt else 'none'
            print(f"    {tt_key:15s}: {cnt:5d} | WR={t_wr:.1f}% | avgRR={t_rr:.2f}x")
        
        print(f"\n  Entry Type breakdown:")
        for et, cnt in entry_type_stats.most_common():
            e_trades = [t for t in all_trades if t['entry_type'] == et]
            e_wr = sum(1 for t in e_trades if t['won'])/len(e_trades)*100
            e_rr = sum(t['rr'] for t in e_trades)/len(e_trades)
            print(f"    {et:15s}: {cnt:5d} | WR={e_wr:.1f}% | avgRR={e_rr:.2f}x")
        
        print(f"\n  Direction distribution:")
        for d, cnt in direction_stats.most_common():
            print(f"    {d:10s}: {cnt:5d} ({cnt/n*100:.1f}%)")
    
    return stock_results, all_trades, total_time


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    # 测试000001.SZ
    ohlcv = load_ohlcv('000001.SZ')
    if ohlcv:
        result = backtest_stock_v46(ohlcv, '000001.SZ')
        if result:
            p = result['perf']
            print(f"\n000001.SZ: n={p['n_trades']} WR={p['win_rate']}% RR={p['avg_rr']}x PF={p['profit_factor']} P&L={p['avg_pnl']}%")
            print(f"  SL: {p['sl_types']}")
            print(f"  TP: {p['tp_types']}")
            print(f"  Entry: {p['entry_types']}")
            print(f"  Retest: {p['retest_count']}")
            
            # 打印每笔交易详情
            for i, t in enumerate(result['trades'][:10]):
                print(f"  Trade {i+1}: signal={t['signal_type']} "
                      f"enter_bar={t['entry_idx']} price={t['entry_price']} "
                      f"exit={t['exit_price']} sl={t['sl']} "
                      f"pnl={t['pnl_pct']:+.2f}% "
                      f"retest_bars={t.get('retest_bars',0)} "
                      f"hold={t['hold_bars']} exit={t['exit_method']}")
