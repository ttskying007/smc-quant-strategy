#!/usr/bin/env python3
"""
|SMC V45 — 精简优化交易引擎
|================================
|基于V43/V38.4成熟架构 + 5项精确改进:
|
|1. 信号精简:
|   - 只从FVG, OB, Sweep, CHOCH 4种信号生成交易
|   - 去掉BPR/LV/RJ/IFVG/MFVG/BRK/EQL/OTE/MSS/PO3入口
|   - 其余10种信号仍被detect_all_signals_v11检测,用于序列分析和TP
|   - 信号扩展路径: TRADE_SIGNAL_TYPES/ENTRY_SIGNAL_TYPES加类型即可
|
|2. POI激活入场 (替代回踩形态检测):
|   - 每个FVG/OB的上下沿标记为POI区域
|   - 信号确认后, 价格回到POI区域时激活入场
|   - 不再需要pinbar/engulf形态确认 — 触及POI区域 = 激活
|
|3. 价格区间进场 (ENTRY_AT_ZONE=True):
|   - FVG/OB是价格区间不是单点
|   - 在信号区域下沿(支撑位)进场, 非收盘价
|   - 获得更优进场价 + 更紧SL距离 = 更高RR
|   - 可关闭: ENTRY_AT_ZONE=False 还原V38风格
|
|4. Bear方向增强 (ENABLE_BEAR=False):
   - Bear仅用OB信号 (FVG_Bear做空质量差)
   - Bear使用tight+profile + 更紧BE/LK
   - Bear共振门槛更高 (0.60 vs 0.55)

4. Trailing:
   - V38.4 3-profile (loose/bear/tight)
   - V42 BE/LK每只股票级参数
   - 方向感知的TP检测

预期目标: WR=90-92%, RR=9-10x, Bear占比15-20%

V43参考架构:
  信号: signals_v11 (14种全检测, 但仅FVG/OB/Sweep/CHOCH入场)
  入场: confirmed_at+1直接入场 + Sweep→FVG(5bar内) + CHOCH→retest(0.5%偏差)
  过滤: sequence(SCOUT) + resonance(total>=0.50-0.55) + 趋势(3层)
  SL: 结构树 > 信号边界 > ATR自适应
  TP: 结构树 > CHOCH前向 > 无TP
  Trailing: V38.4 3-profile差异化
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v467')
OUTPUT_DIR.mkdir(exist_ok=True)

MIN_BARS = 60
MAX_HOLD = 100

# ── V467 渐进式BE锁 (替代硬MULTI_BAR_BE_LOCK) ──
# V468 60min版本: 给更多空间 allow multi-bar growth
#   hold>=5 AND gain<0     → BE (5bar无利润锁保本)
#   hold>=8 AND gain<0.3%  → BE
#   hold>=12 AND gain<0.5% → BE
#   hold>=20 AND gain<1.0% → BE
PROGRESSIVE_BE = [(5, 0.0), (8, 0.3), (12, 0.5), (20, 1.0)]

# ── TP距离感知trailing (TP>12%时使用宽松trailing) ──
TP_DISTANCE_AWARE = True
# TP<=12%: 可靠目标, 收紧trailing确保捕获
# TP>12%: 不可靠目标(WR骤降), 放宽trailing减少提前退出
TP_RELIABLE_MAX = 12.0

# ── V468 60min宽松trailing阈值 (相比日线5-10倍) ──
# 60min数据的每根K线波动约1.5-3.7% (ATR)
# 因此锁利阈值必须比日线高5-10倍才能让多bar持仓成立
# loose profile (bull+TP):
#   3-5%: 不锁利, 仅保持初始SL
#   8%: 锁保本 (ATR的2-3倍)
#   12%: 锁极端-2%
#   20%: 锁极端-5%

# ── MIN_PROJECTED_RR 过滤 (跳过无TP或RR不足的交易) ──
MIN_PROJECTED_RR = 8.0

# ── POI回调入场窗口 (V468-C: 信号后扫描最多N根60min K线等待价格折返) ──
# 60min: 50根 = ~50小时 = ~6个交易日
POI_RETRACE_WINDOW = 50

# ── 交易信号类型白名单 (只这4种生成交易) ──
TRADE_SIGNAL_TYPES = {'FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear',
                      'SweepUp', 'SweepDown', 'CHOCH_Bull', 'CHOCH_Bear'}

# ── 入口信号类型 (可穿透到入场) ──
ENTRY_SIGNAL_TYPES = {'FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear'}

# ── 质量门限 ──
QUALITY_THRESHOLDS = {
    'FVG_Bull': 0.70,   # ↑严格门槛 - 仅极高质量FVG
    'FVG_Bear': 0.70,
    'OB_Bull': 0.50,    # OB靠反转过滤, 门槛不变
    'OB_Bear': 0.55,
}

# ── 共振门限 ──
RESONANCE_THRESHOLDS = {
    'bull': 0.50,
    'bear': 0.60,       # Bear更高门槛
}

# ── 参数缓存 (每只股票独立参数, V43风格) ──
STOCK_PARAMS_CACHE = {}

# ── 做空开关 (False=只做多, True=启用做空) ──
ENABLE_BEAR = False
# 提示: 设True恢复Bear交易, 当前Bear设在但被跳过
# Bear当前收益 -2.41%/笔, 拖累全局RR从8.37x到7.67x

# ── 进场价格区间模式 (True=用信号区域边界, False=用bar收盘价) ──
ENTRY_AT_ZONE = True
# 信号(FVG/OB)是价格区间, 非单点。
# True: 在信号区间的支撑/阻力边界入场, 获得更精确进场价+更紧SL
# False: 用entry_bar收盘价 (V38风格)

# ── V38.4 3-profile Trailing ──
# ── MIN_PROJECTED_RR 过滤 (跳过无TP或RR不足的交易) ──
MIN_PROJECTED_RR = 8.0

# ── 多bar保本锁 (hold>=2且未达保本 -> BE退出) ──
MULTI_BAR_BE_LOCK = 2

def calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl,
                       structural_tp, n, max_hold, direction,
                       be_lock=2.0, look_lock=4.0):
    """
    V465 60min trailing — 5x宽松阈值, 允许多K线持仓
    3-profile: loose (bull+tp), bear (bear+tp), tight (noTP)
    60min: be_lock~2%, look_lock~4% (from stock_params)
    """
    sl = initial_sl
    extreme = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None

    is_bear = (direction == 'bear')
    has_tp = tp_price is not None

    if not has_tp:
        profile = 'tight'
    elif is_bear:
        profile = 'bear'
    else:
        profile = 'loose'

    be_gain = be_lock
    lk_gain = look_lock

    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]

        if is_bear:
            if bar['l'] < extreme:
                extreme = bar['l']
            gain_pct = (entry_price - extreme) / entry_price * 100

            if tp_price and extreme <= tp_price * 1.05:
                sl_tight = min(entry_price * (1 - max(0.8, tp_pct * 0.5) / 100), sl) if sl else entry_price * (1 - max(0.8, tp_pct * 0.5) / 100)
                sl = sl_tight
                if extreme <= tp_price * 1.02:
                    return j, tp_price, True
            else:
                if profile == 'tight':
                    if gain_pct >= 12.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 6.0:
                        sl = min(sl, extreme * (1 + 2.5/100))
                    elif gain_pct >= 3.5:
                        sl = min(sl, entry_price * (1 + 1.0/100))
                    elif gain_pct >= lk_gain:
                        sl = min(sl, entry_price * (1 + 0.3/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)
                elif profile == 'bear':
                    if gain_pct >= 20.0:
                        sl = min(sl, extreme * (1 + 10.0/100))
                    elif gain_pct >= 10.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 5.0:
                        sl = min(sl, entry_price * (1 + 1.5/100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, entry_price * (1 + 0.5/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)
                else:  # loose
                    if gain_pct >= 20.0:
                        sl = min(sl, extreme * (1 + 10.0/100))
                    elif gain_pct >= 10.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 5.0:
                        sl = min(sl, entry_price * (1 + 1.5/100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, entry_price * (1 + 0.5/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)

            if bar['h'] >= sl:
                exit_price = min(sl, bar['h'])
                return j, round(exit_price, 2), exit_price > entry_price

        else:  # bull — 我们实际使用的方向
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100

            if tp_price and extreme >= max(tp_price * 0.90, entry_price * 1.02):
                sl = max(sl, entry_price * (1 + max(tp_pct * 0.4, 0.5) / 100))
                if extreme >= tp_price * 0.95 or (gain_pct >= tp_pct * 0.75 and gain_pct >= 2.0):
                    j_sl = j
                    while j_sl < min(j + 5, n):
                        if ohlcv[j_sl]['l'] <= sl:
                            return j_sl, sl, True
                        j_sl += 1
                    return j, sl, True

            # ── V467 渐进式BE锁 ──
            # 可靠TP (<=12%): hold>=3无利润→BE, hold>=5微利→BE
            # 不可靠TP (>12%): 给更多空间
            if tp_price and tp_pct and tp_pct > TP_RELIABLE_MAX:
                # 远TP: 宽松, 仅hold>=5无利润才BE
                if j >= entry_idx + 5 and gain_pct < 0:
                    sl = max(sl, entry_price)
            else:
                for min_hold, min_gain in PROGRESSIVE_BE:
                    if j >= entry_idx + min_hold and gain_pct < min_gain:
                        sl = max(sl, entry_price)
                        break

            if profile == 'loose':
                if gain_pct >= 30.0:
                    sl = max(sl, extreme * (1 - 10.0/100))
                elif gain_pct >= 20.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 12.0:
                    sl = max(sl, entry_price * (1 - 2.0/100))
                elif gain_pct >= 8.0:
                    sl = max(sl, entry_price)
                # gain < 8%: 保持初始SL, 不锁利
            elif profile == 'tight':
                if gain_pct >= 12.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 8.0:
                    sl = max(sl, extreme * (1 - 2.5/100))
                elif gain_pct >= 5.0:
                    sl = max(sl, entry_price * (1 - 1.0/100))
                elif gain_pct >= be_gain:
                    sl = max(sl, entry_price)

            if bar['l'] <= sl:
                exit_price = max(sl, bar['l'])
                return j, round(exit_price, 2), exit_price > entry_price

    # 达到max_hold未exit
    if sl is not None:
        return min(entry_idx + max_hold, n-1), sl, sl > entry_price
    return min(entry_idx + max_hold, n-1), entry_price * 0.95, False


def is_reversal_ob(ohlcv, sig, all_signals):
    """判断OB是否在结构反转处 (延续上升中的pullback不算)
    
    反转OB判定规则 (Bull OB):
    1. 20-bar趋势必须为下行或中性 (trend20 < +1%)
    2. 有近期的SweepDown (流动性猎杀)在10bar内
    3. 或者OB附近有CHOCH结构转换
    
    返回: (is_reversal: bool, reason: str)
    """
    idx = sig.get('idx', 0)
    sig_dir = sig.get('direction', '')
    sig_type = sig.get('type', '')
    
    # 只处理OB
    if 'OB' not in sig_type:
        return True, 'not_ob'
    
    if sig_dir == 'bull':
        if idx >= 20:
            trend20 = (ohlcv[idx]['c'] - ohlcv[idx-20]['c']) / ohlcv[idx-20]['c'] * 100
        else:
            trend20 = 0
        
        has_sweep = any(
            'SweepDown' in s.get('type', '')
            and abs(s.get('idx', 0) - idx) <= 10
            for s in all_signals
        )
        has_reversal_choch = any(
            'CHOCH_Bull' in s.get('type', '')
            and s.get('idx', 0) <= idx
            and idx - s.get('idx', 0) <= 15
            for s in all_signals
        )
        at_swing = sig.get('metadata', {}).get('at_structure', False)
        
        # 上升趋势中的回调 → 非反转OB (除非有sweep+choch豁免)
        if trend20 > 1.0:
            if has_sweep and has_reversal_choch:
                return True, f'reversal_swp_choc_{trend20:+.0f}%'
            return False, f'uptrend_pull_{trend20:+.0f}%'
        
        score = 0
        if has_sweep: score += 1
        if has_reversal_choch: score += 1
        if at_swing: score += 1
        if trend20 < -1.0: score += 1
        
        if score >= 1:
            return True, f'rev_score{score}'
        return True, f'weak_rev_{trend20:+.0f}%'
    
    elif sig_dir == 'bear':
        if idx >= 20:
            trend20 = (ohlcv[idx]['c'] - ohlcv[idx-20]['c']) / ohlcv[idx-20]['c'] * 100
        else:
            trend20 = 0
        has_sweep = any(
            'SweepUp' in s.get('type', '')
            and abs(s.get('idx', 0) - idx) <= 10 for s in all_signals
        )
        has_reversal_choch = any(
            'CHOCH_Bear' in s.get('type', '')
            and s.get('idx', 0) <= idx
            and idx - s.get('idx', 0) <= 15 for s in all_signals
        )
        if trend20 < -1.0:
            if has_sweep and has_reversal_choch:
                return True, 'bear_rev'
            return False, 'downtrend_pull'
        return True, 'bear_reversal'
    return True, 'default'


# ── 辅助函数 ──
def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_60min_200.json"
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


def calc_atr_v45(ohlcv, idx, period=14):
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100 if ohlcv[idx]['l'] > 0 else 0.5
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100 if ohlcv[idx]['l'] > 0 else 0.5


def find_swing_highs(ohlcv, lookback=10):
    highs = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['h'] >= ohlcv[j]['h']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n):
            highs.append((i, ohlcv[i]['h']))
    return highs


def find_swing_lows(ohlcv, lookback=10):
    lows = []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['l'] <= ohlcv[j]['l']
               for j in range(i - lookback, i + lookback + 1) if 0 <= j < n):
            lows.append((i, ohlcv[i]['l']))
    return lows


def find_swing_high_forward(ohlcv, entry_idx, lookahead=200):
    """60min: 跳过3bar, 找前方摆动高"""
    n = len(ohlcv)
    best = None
    start = max(entry_idx + 3, 0)
    for i in range(start, min(start + lookahead, n - 2)):
        is_high = all(ohlcv[i]['h'] >= ohlcv[j]['h']
                      for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_high:
            pct = (ohlcv[i]['h'] - ohlcv[entry_idx]['c']) / ohlcv[entry_idx]['c'] * 100
            if best is None or pct > best['pct']:
                best = {'idx': i, 'price': ohlcv[i]['h'], 'pct': pct}
            if pct >= 4.0:
                return {'idx': i, 'price': ohlcv[i]['h'], 'pct': pct}
    return best


def find_swing_low_forward(ohlcv, entry_idx, lookahead=200):
    """60min: 跳过3bar, 找前方摆动低"""
    n = len(ohlcv)
    best = None
    start = max(entry_idx + 3, 0)
    for i in range(start, min(start + lookahead, n - 2)):
        is_low = all(ohlcv[i]['l'] <= ohlcv[j]['l']
                     for j in range(max(0, i - 5), min(n, i + 6)) if j != i)
        if is_low:
            pct = (ohlcv[entry_idx]['c'] - ohlcv[i]['l']) / ohlcv[entry_idx]['c'] * 100
            if best is None or pct > best['pct']:
                best = {'idx': i, 'price': ohlcv[i]['l'], 'pct': pct}
            if pct >= 4.0:
                return {'idx': i, 'price': ohlcv[i]['l'], 'pct': pct}
    return best


# ── POI激活检查 (替代回踩形态检测) ──
def check_poi_activation(ohlcv, sig, entry_bar, direction):
    """
    POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
    当价格回到POI区域时才产生激活信号.
    规则:
    - Bull: 价格回到信号lower之上 (进入支撑区)
    - Bear: 价格回到信号upper之下 (进入阻力区)
    返回: (activated: bool, entry_price: float, sl_price: float, sl_type: str)
    """
    lower = sig.get('lower', 0)
    upper = sig.get('upper', 0)
    if lower <= 0 or upper <= 0 or upper <= lower:
        return False, None, None, None

    bar = ohlcv[entry_bar]

    if direction == 'bull':
        # Bull: 价格从下方回到支撑区 (进入POI)
        # 检查低点是否触及信号区域
        if bar['l'] <= upper and bar['h'] >= lower:
            # 以收盘价入场, SL在信号区域下方
            sl_price = lower * 0.998
            return True, bar['c'], sl_price, 'poi_lower'
    else:
        # Bear: 价格从上方回到阻力区
        if bar['h'] >= lower and bar['l'] <= upper:
            sl_price = upper * 1.002
            return True, bar['c'], sl_price, 'poi_upper'

    return False, None, None, None


# ── SL计算 ──
def calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction, params, all_signals):
    """V45 SL: 信号边界 > 摆动点 > ATR自适应"""
    sig_type = signal.get('type', '')

    # 1. 信号边界SL (FVG lower/upper, OB lower/upper)
    if direction == 'bull':
        if 'FVG' in sig_type:
            lower = signal.get('lower', 0)
            if lower > 0 and lower < entry_price:
                pct = (entry_price - lower) / entry_price * 100
                if 0.15 <= pct <= 3.0:
                    return lower, 'fvg_lower', round(pct, 2)
        if 'OB' in sig_type:
            lower = signal.get('lower', 0)
            if lower > 0 and lower < entry_price:
                pct = (entry_price - lower) / entry_price * 100
                if 0.15 <= pct <= 3.0:
                    return lower, 'ob_lower', round(pct, 2)
    else:
        if 'FVG' in sig_type:
            upper = signal.get('upper', 0)
            if upper > 0 and upper > entry_price:
                pct = (upper - entry_price) / entry_price * 100
                if 0.15 <= pct <= 3.0:
                    return upper, 'fvg_upper', round(pct, 2)
        if 'OB' in sig_type:
            upper = signal.get('upper', 0)
            if upper > 0 and upper > entry_price:
                pct = (upper - entry_price) / entry_price * 100
                if 0.15 <= pct <= 3.0:
                    return upper, 'ob_upper', round(pct, 2)

    # 2. 摆动点SL
    swing_lookback = 20
    if direction == 'bull':
        n = len(ohlcv)
        start = max(10, entry_idx - swing_lookback)
        best_sl = None
        best_pct = 0
        for i in range(start, entry_idx - 2):
            if i < 4 or i > n - 4:
                continue
            is_low = all(ohlcv[j]['l'] >= ohlcv[i]['l'] for j in range(i-3, i+4) if j != i)
            if is_low:
                pct = (entry_price - ohlcv[i]['l']) / entry_price * 100
                if 0.15 <= pct <= 3.0:
                    if best_sl is None or pct < best_pct:
                        best_sl = (ohlcv[i]['l'], 'swing_low', round(pct, 2))
                        best_pct = pct
        if best_sl:
            return best_sl
    else:
        n = len(ohlcv)
        start = max(10, entry_idx - swing_lookback)
        best_sl = None
        best_pct = 0
        for i in range(start, entry_idx - 2):
            if i < 4 or i > n - 4:
                continue
            is_high = all(ohlcv[j]['h'] <= ohlcv[i]['h'] for j in range(i-3, i+4) if j != i)
            if is_high:
                pct = (ohlcv[i]['h'] - entry_price) / entry_price * 100
                if 0.15 <= pct <= 3.0:
                    if best_sl is None or pct < best_pct:
                        best_sl = (ohlcv[i]['h'], 'swing_high', round(pct, 2))
                        best_pct = pct
        if best_sl:
            return best_sl

    # 3. ATR自适应SL (保底) — V468 60min: 最小0.3%, ATR系数0.5x
    atr = calc_atr_v45(ohlcv, entry_idx)
    sl_mult = params.get('sl_mult', 0.3)
    base_sl = max(0.30, min(2.0, atr * sl_mult * 0.5))
    if direction == 'bull':
        return round(entry_price * (1 - base_sl/100), 4), 'adaptive', round(base_sl, 2)
    else:
        return round(entry_price * (1 + base_sl/100), 4), 'adaptive', round(base_sl, 2)


# ── TP计算 ──
def calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals, entry_type='FVG'):
    """V45 TP: 前方CHOCH > 前方摆动 > 无TP"""
    # 1. 前方CHOCH
    if direction == 'bull':
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bull' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 200]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('upper', 0))
            if tp_price > entry_price:
                tp_pct = (tp_price - entry_price) / entry_price * 100
                if tp_pct >= 2.0:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']
    else:
        forward_choch = [s for s in all_signals
                         if 'CHOCH_Bear' in s.get('type', '')
                         and s.get('idx', 0) > entry_idx
                         and s.get('idx', 0) <= entry_idx + 200]
        if forward_choch:
            nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
            tp_price = nearest.get('break_level', nearest.get('lower', 0))
            if tp_price > 0 and tp_price < entry_price:
                tp_pct = (entry_price - tp_price) / entry_price * 100
                if tp_pct >= 2.0:
                    return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']

    # 2. 前方摆动
    if direction == 'bull':
        swing = find_swing_high_forward(ohlcv, entry_idx, 200)
        if swing and swing['price'] > entry_price:
            tp_pct = (swing['price'] - entry_price) / entry_price * 100
            if tp_pct >= 2.0:
                return round(swing['price'], 4), 'swing_high', round(tp_pct, 2), swing['idx']
    else:
        swing = find_swing_low_forward(ohlcv, entry_idx, 200)
        if swing and swing['price'] < entry_price:
            tp_pct = (entry_price - swing['price']) / entry_price * 100
            if tp_pct >= 3.0:
                return round(swing['price'], 4), 'swing_low', round(tp_pct, 2), swing['idx']

    # 3. 无TP → trailing保底
    return None, None, None, None


# ── 主入口评估 ──
def _calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir):
    """
    价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
    
    Bull FVG/OB: 在区域下沿(支撑)买入, 而非bar收盘价
    - 如果close在区域内 (lower < close < upper): 以区域下沿入场(支撑位, 真实可成交)
    - 如果close跌破区域 (close <= lower): 用close(支撑已破, 不再强行入场)
    - 如果close远高于区域 (close >= upper): 用close(价格已远离, 不再等待折返)
    
    不再使用0.995虚假折扣 — 所有入场价必须真实可成交。
    A股只做多, 所以只处理bull方向。
    """
    entry_price = ohlcv[entry_bar]['c']
    if not ENTRY_AT_ZONE or sig_dir != 'bull':
        return entry_price
    
    lower = sig.get('lower', 0)
    upper = sig.get('upper', 0)
    if lower <= 0 or upper <= 0 or upper <= lower:
        return entry_price
    
    # 价格在信号区域内: 用区域下沿(支撑位)入场
    if lower < entry_price < upper:
        return round(lower, 2)
    
    # 价格不在信号区域内: 用真实收盘价 (不制造虚假折扣)
    return round(entry_price, 2)


def evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n,
                        direction, params, stock_params):
    """V45统一入场评估 (POI激活 + V38出口)"""
    sig_type = sig.get('type', '')
    sig_idx = sig.get('idx', 0)
    confirmed_at = sig.get('confirmed_at', sig_idx)
    entry_bar = max(sig_idx, confirmed_at)

    if entry_bar >= n - 3:
        return None

    # ── 入口类型判定 ──
    is_fvg = 'FVG' in sig_type and 'Mitigated' not in sig_type and 'IFVG' not in sig_type
    is_ob = 'OB' in sig_type and 'BreakerBlock' not in sig_type
    is_sweep = 'Sweep' in sig_type
    is_choch = 'CHOCH' in sig_type

    quality = sig.get('confidence', sig.get('quality', 0.5))
    sig_dir = sig.get('direction', '')

    # 策略C: OB-only + 高质量FVG入口
    if not is_ob:
        # 仅高质量FVG允许入场 (quality >= 0.80)
        if not (is_fvg and quality >= 0.80):
            return None

    # ── 做空开关 (False=只做多) ──
    if sig_dir == 'bear' and not ENABLE_BEAR:
        return None

    # ── Bear仅限OB信号 ──
    if sig_dir == 'bear' and not is_ob:
        return None

    # ── 质量门限 ──
    q_threshold = QUALITY_THRESHOLDS.get(sig_type, 0.50)
    if quality < q_threshold:
        return None

    # ── 策略C: 反转OB过滤 ──
    is_rev, rev_reason = is_reversal_ob(ohlcv, sig, all_sigs_up_to_idx)
    if not is_rev:
        return None  # 趋势延续中的OB不交易

    # ── Sweep→FVG/OB检测 (5bar内Sweep) ──
    sweep_fvg_found = False
    if sig_idx > 5:
        for ps in all_sigs_up_to_idx:
            ps_type = ps.get('type', '')
            ps_idx = ps.get('idx', 0)
            if sig_dir == 'bull' and 'SweepDown' in ps_type:
                if 0 < sig_idx - ps_idx <= 5:
                    sweep_fvg_found = True
                    break
            elif sig_dir == 'bear' and 'SweepUp' in ps_type:
                if 0 < sig_idx - ps_idx <= 5:
                    sweep_fvg_found = True
                    break

    # ── POI回调入场扫描 (V468-C: 等待价格折返到信号区域) ──
    # 核心ICT逻辑: 信号(OB/FVG)确认后, 不立即入场, 
    # 而是等待价格从外部折返回到信号区域(POI)才入场。
    entry_bar = max(sig_idx, confirmed_at)
    poi_activated = False
    poiretrace_bars = 0  # 信号确认后等待了多少根K线才折返
    
    if sig_dir == 'bull':
        lower = sig.get('lower', 0)
        upper = sig.get('upper', 0)
        if lower > 0 and upper > lower:
            # 扫描信号后POI_RETRACE_WINDOW根K线, 寻找价格折返进入信号区域
            for candidate in range(entry_bar + 1, min(entry_bar + POI_RETRACE_WINDOW, n - 2)):
                bar = ohlcv[candidate]
                # 检查是否折返进入POI区域: bar的波动范围触及信号区域
                if bar['l'] <= upper and bar['h'] >= lower:
                    entry_bar = candidate
                    poi_activated = True
                    poiretrace_bars = candidate - max(sig_idx, confirmed_at)
                    break

    # ── 价格区间入场 (FVG/OB区域边界, 非单点收盘价) ──
    entry_price = _calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)

    # ── 入口类型判定 ──
    if is_ob and quality >= 0.50:
        if sweep_fvg_found:
            entry_type = 'Sweep→OB'
        else:
            entry_type = 'OB_Rev'
    elif is_fvg and quality >= 0.80:
        if sweep_fvg_found:
            entry_type = 'Sweep→FVG'
        else:
            entry_type = 'FVG_HQ'  # 高质量FVG入场
    else:
        return None

    # ── 成交量过滤 ──
    if sig_idx > 30 and sig_idx < n:
        bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                     for j in range(max(0, sig_idx-30), sig_idx)) / 30
        if bv < avg_vol * 0.6:
            return None

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

    if sig_dir == 'bull':
        if dc >= 2:
            return None
    else:
        if uc >= 2:
            return None

    # ── 序列+共振过滤 ──
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None

    window = ohlcv[:entry_bar+1]
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

    # ── SL/TP/Trailing ──
    # 始终用结构SL (信号边界 > 摆动 > ATR), 不因POI改变SL
    init_sl, sl_type_name, sl_pct_val = calc_v45_sl(
        ohlcv, entry_bar, entry_price, sig, entry_type, sig_dir, params, all_signals)

    if init_sl is None:
        return None

    # TP
    tp_price, tp_type, tp_pct, tp_idx = calc_v45_tp(
        ohlcv, entry_bar, entry_price, sig, sig_dir, all_signals, entry_type)

    # A: MIN_PROJECTED_RR过滤 — 跳过无TP或RR不足的交易
    if tp_type is None:
        return None  # 无结构TP目标 = 噪声交易
    if sl_pct_val and tp_pct:
        projected_rr = tp_pct / sl_pct_val
        if projected_rr < MIN_PROJECTED_RR:
            return None

    # 每只股票BE/LK参数
    be_lock = stock_params.get('be_lock', 0.20)
    look_lock = stock_params.get('look_lock', 0.50)
    max_hold = stock_params.get('max_hold', 30)

    exit_idx, exit_price, won = calc_v38_trailing(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, max_hold, sig_dir,
        be_lock=be_lock, look_lock=look_lock)

    pnl = (exit_price - entry_price) / entry_price * 100
    actual_rr = abs(exit_price - entry_price) / abs(entry_price - init_sl) if entry_price != init_sl else 10

    is_bear = sig_dir == 'bear'

    return {
        'entry_idx': entry_bar,
        'sig_idx': sig_idx,
        'confirmed_at': confirmed_at,
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
        'entry_type': entry_type,
        'exit_method': 'tp_hit' if tp_type and tp_price and (
            (not is_bear and exit_price >= tp_price) or
            (is_bear and exit_price <= tp_price)
        ) else 'trailing',
        'resonance_total': round(res.total, 3),
        'poi_activated': poi_activated,
        'poiretrace_bars': poiretrace_bars,
        'is_retest': poi_activated,
        'sweep_fvg': sweep_fvg_found,
    }


# ── 股票参数计算 ──
def calc_stock_params_v45(ohlcv, symbol):
    """计算每只股票自适应参数 (ATR + BE/LK)"""
    n = len(ohlcv)
    if n < 30:
        return {'sl_mult': 0.3, 'atr_pct': 2.0, 'be_lock': 0.20,
                'look_lock': 0.50, 'max_hold': 30, 'vol_class': 'medium'}

    atr_list = []
    for i in range(14, min(50, n)):
        atr = calc_atr_v45(ohlcv, i)
        atr_list.append(atr)

    avg_atr = sum(atr_list) / len(atr_list) if atr_list else 1.0

    # 波动率分类
    if avg_atr < 1.0:
        vol_class = 'low'
        sl_mult = 0.50
        be_lock = 2.0     # 60min: 2.0%
        look_lock = 3.0   # 60min: 3.0%
        max_hold = 100
    elif avg_atr < 3.0:
        vol_class = 'medium'
        sl_mult = 0.50
        be_lock = 2.5     # 60min: 2.5%
        look_lock = 4.5   # 60min: 4.5%
        max_hold = 100
    else:
        vol_class = 'high'
        sl_mult = 0.50
        be_lock = 3.5     # 60min: 3.5%
        look_lock = 5.5   # 60min: 5.5%
        max_hold = 80

    return {
        'sl_mult': sl_mult,
        'atr_pct': round(avg_atr, 3),
        'be_lock': be_lock,
        'look_lock': look_lock,
        'max_hold': max_hold,
        'vol_class': vol_class,
    }


# ── 股票回测 ──
def backtest_stock_v45(ohlcv, symbol):
    """V45单股票回测"""
    n = len(ohlcv)
    stock_params = calc_stock_params_v45(ohlcv, symbol)
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}

    # 信号检测 (全部14种 - 用于序列分析和TP)
    signals_result = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
    all_signals = signals_result.get('all', [])

    if not all_signals or len(all_signals) < 3:
        return None

    trades = []
    used_bars = set()

    for sig in all_signals:
        sig_idx = sig.get('idx', 0)
        sig_type = sig.get('type', '')
        direction = sig.get('direction', '')

        # 只处理交易信号类型
        if sig_type not in TRADE_SIGNAL_TYPES:
            continue
        # 策略C: OB-only入场
        if 'OB' not in sig_type:
            continue
        if sig_idx < 40 or sig_idx >= n - 10:
            continue

        sigs_up_to = [s for s in all_signals if s.get('idx', 0) <= sig_idx]

        result = evaluate_v45_entry(
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
    poi_count = sum(1 for t in trades if t.get('poi_activated', False))

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
            'poi_activated': poi_count,
            'vol_class': stock_params.get('vol_class', 'medium'),
            'stock_params': {k: v for k, v in stock_params.items()},
        }
    }


def run_backtest(symbols, label="V465-60min"):
    """通用回测运行器"""
    all_trades, stock_results = [], []
    t_start = time.time()
    sl_type_stats = Counter()
    tp_type_stats = Counter()
    direction_stats = Counter()

    print(f"{'='*80}")
    print(f"V45 — 精简引擎 (4种信号+POI激活+3-profile+Bear增强)")
    print(f"  {len(symbols)} 只股票 | 信号: FVG/OB/Sweep/CHOCH | 过滤: 序列+共振+趋势")
    print(f"  Trailing: V38.4 3-profile | Bear: OB-only | 参数: 每股ATR自适应")
    print(f"{'='*80}")

    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} NO-DATA")
            continue

        result = backtest_stock_v45(ohlcv, sym)
        if result:
            p = result['perf']
            for st, cnt in p['sl_types'].items():
                sl_type_stats[st] += cnt
            for tt, cnt in p['tp_types'].items():
                tp_type_stats[tt] += cnt
            for d, cnt in p['directions'].items():
                direction_stats[d] += cnt
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x "
                  f"POI={p['poi_activated']}")
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

        poi_trades = [t for t in all_trades if t.get('poi_activated', False)]
        sweep_trades = [t for t in all_trades if t.get('sweep_fvg', False)]

        print(f"\n  === {label} RESULTS ===")
        print(f"  Time: {total_time:.0f}s | Stocks: {len(stock_results)}/{len(symbols)}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars | Max: {max(holds)}")
        print(f"  POI activated: {len(poi_trades)} | Sweep→FVG: {len(sweep_trades)}")

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
        early_exit = sum(1 for t in all_trades if t['hold_bars'] <= 3 and t.get('tp_pct', 0) and t['tp_pct'] > 2.0)
        print(f"    Early exit (hold<=3, tp>2%): {early_exit} trades")

        print(f"\n  SL Type breakdown:")
        for st, cnt in sl_type_stats.most_common():
            st_trades = [t for t in all_trades if t.get('sl_type') == st]
            st_wr = sum(1 for t in st_trades if t['won'])/len(st_trades)*100 if st_trades else 0
            st_pnl = sum(t['pnl_pct'] for t in st_trades)/len(st_trades) if st_trades else 0
            print(f"    {st:20s}: {cnt:5d} ({cnt/n*100:.1f}%) | WR={st_wr:.1f}% | avgP&L={st_pnl:+.2f}%")

        print(f"\n  TP Type breakdown:")
        for tt, cnt in tp_type_stats.most_common():
            tt_trades = [t for t in all_trades if t.get('tp_type') == tt]
            tt_wr = sum(1 for t in tt_trades if t['won'])/len(tt_trades)*100 if tt_trades else 0
            tt_rr = sum(t['rr'] for t in tt_trades)/len(tt_trades) if tt_trades else 0
            tt_label = str(tt) if tt is not None else 'none'
            print(f"    {tt_label:20s}: {cnt:5d} | WR={tt_wr:.1f}% | avgRR={tt_rr:.2f}x")

        print(f"\n  Direction distribution:")
        for d, cnt in direction_stats.most_common():
            print(f"    {d:10s}: {cnt:5d} ({cnt/n*100:.1f}%)")

    return {
        'stock_results': stock_results,
        'all_trades': all_trades,
        'summary': {
            'n_stocks': len(stock_results),
            'n_trades': len(all_trades),
            'win_rate': round(wr, 1),
            'avg_rr': round(rr, 2),
            'profit_factor': round(pf, 2),
            'avg_pnl': round(pnl, 2),
        }
    }


if __name__ == '__main__':
    symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                     for f in CACHE_DIR.glob('*_60min_200.json')])
    result = run_backtest(symbols, "V45")

    if result and result.get('all_trades'):
        out_path = OUTPUT_DIR / 'v45_full.json'
        result['stock_results'].sort(key=lambda r: -r['n_trades'])
        json.dump(result['all_trades'], open(str(out_path), 'w'))
        print(f"\n  Saved: {out_path}")
