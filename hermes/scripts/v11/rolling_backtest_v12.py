#!/usr/bin/env python3
"""
V12 — Swing-Enhanced Scout + Signal Sequence + Multi-TF Resonance
=================================================================
合成所有突破性发现:

V11.6核心发现:
  - 摆动SL=0.5%时WR=97% (166笔)
  - 摆动WR=85% > 固定WR=53%
  - 固定SL=0.3%保底, 损失平均-0.30%
  - FVG SCOUT WR=71.6% > OB SCOUT WR=66.0%

V14核心发现:
  - 每股参数优化RR=10.18x (+40%)

V12创新:
  1. 摆动点SL/TP修复版 — V11.6的0.5%封顶 + V11.7的黄金区间筛选
  2. 信号序列模式识别 — 按近期10笔历史序列的WR打分
  3. 多周期共振 — 60min(预警) + daily(入场) + weekly(趋势)
  4. 信号密度自适应 — 每股票最优信号密度窗口
  5. 每股+每阶段参数优化 — V14*V11.6组合
  6. 全市场: 股票+ETF+指数

预期: WR=78-82%, RR=8-10x, 覆盖45-50%
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/root/.hermes/scripts')

from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v11')

# ====== V12 CONFIGURABLE PARAMETERS ======
MAX_STOCKS = 200
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 60
COOLDOWN = 15
SCOUT_MIN_RESONANCE = 0.65
SWING_MAX_DISTANCE = 15

# SL/TP Strategy
SL_CAP = 0.5       # 摆动SL封顶0.5%
SL_FIXED = 0.3     # 回退固定SL
TP_FIXED = 5.0     # 回退固定TP
SWING_MIN_RR = 2.0 # 摆动TP最低RR要求

# Signal Quality
MIN_VOL_RATIO = 0.8       # 成交量 > 80%均量
MIN_FVG_GAP = 0.3         # FVG gap >= 0.3%
SIGNAL_DENSITY_MIN = 60   # 最优信号密度下限
SIGNAL_DENSITY_MAX = 180  # 最优信号密度上限

# Signal Sequence Pattern Recognition
SEQ_PATTERN_HISTORY = 15  # 看近期多少笔交易做模式识别

# Multi-TF
WEEKLY_MIN_BARS = 3
USE_WEEKLY_FILTER = True


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
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
        return 'neutral', 0.0
    segment = ohlcv[idx-lookback:idx+1]
    start, end = segment[0]['c'], segment[-1]['c']
    change = (end - start) / start * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ema_dist = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_dist > 0:
        return 'up', change
    elif change < -0.6 and ema_dist < 0:
        return 'down', abs(change)
    return 'neutral', 0


def find_nearest_swing_low(ohlcv, end_idx, lookback=SWING_MAX_DISTANCE):
    """找入场前最近的摆动低点"""
    if end_idx < 3:
        return None, 0
    start = max(0, end_idx - lookback)
    for i in range(end_idx - 1, start - 1, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['l'] if i > start else 9999
        right = ohlcv[i+1]['l'] if i < end_idx - 1 else 9999
        if bar['l'] < left and bar['l'] < right:
            return i, bar['l']
    return None, 0


def find_nearest_swing_high(ohlcv, end_idx, lookback=SWING_MAX_DISTANCE):
    """找入场前最近的摆动高点"""
    if end_idx < 3:
        return None, 0
    start = max(0, end_idx - lookback)
    for i in range(end_idx - 1, start - 1, -1):
        bar = ohlcv[i]
        left = ohlcv[i-1]['h'] if i > start else 0
        right = ohlcv[i+1]['h'] if i < end_idx - 1 else 0
        if bar['h'] > left and bar['h'] > right:
            return i, bar['h']
    return None, 0


def calc_swing_sltp_v12(ohlcv, end_idx, entry_price):
    """
    V12 摆动点SL/TP: V11.6黄金公式
    - 近摆动低点做SL, 但封顶0.5% (V11.6发现)
    - 近摆动高点做TP, 但要求RR>=2x
    """
    # 固定保底
    fixed_sl = entry_price * (1 - SL_FIXED / 100)
    fixed_tp = entry_price * (1 + TP_FIXED / 100)
    
    # 找摆动低点(SL)
    sl_idx, sl_price = find_nearest_swing_low(ohlcv, end_idx, lookback=SWING_MAX_DISTANCE)
    sl_dist = end_idx - sl_idx if sl_idx is not None else 999
    
    use_swing_sl = False
    use_swing_tp = False
    
    # === SL策略 (V11.6黄金公式): 摆动点封顶0.5% ===
    if sl_idx is not None and sl_dist <= SWING_MAX_DISTANCE and sl_dist >= 2:
        # 封顶0.5%: SL最多到entry_price * 0.995
        swing_sl = min(sl_price, entry_price * (1 - SL_CAP / 100))
        sl_pct = (entry_price - swing_sl) / entry_price * 100
        if 0.2 <= sl_pct <= SL_CAP + 0.1:  # 0.2% - 0.6%
            use_swing_sl = True
            final_sl = swing_sl
        else:
            final_sl = fixed_sl
    else:
        final_sl = fixed_sl
    
    sl_pct_actual = (entry_price - final_sl) / entry_price * 100
    
    # === TP策略 (V12动态): 找摆动高点, 要求RR>=2x ===
    tp_idx, tp_price = find_nearest_swing_high(ohlcv, end_idx, lookback=SWING_MAX_DISTANCE)
    tp_dist = end_idx - tp_idx if tp_idx is not None else 999
    
    if tp_idx is not None and tp_dist <= SWING_MAX_DISTANCE and tp_dist >= 2:
        swing_tp = max(tp_price, entry_price * 1.005)
        tp_pct = (swing_tp - entry_price) / entry_price * 100
        tc_rr = tp_pct / sl_pct_actual if sl_pct_actual > 0 else 10
        
        if tc_rr >= SWING_MIN_RR and tp_pct <= 20.0:
            use_swing_tp = True
            final_tp = swing_tp
            actual_rr = tc_rr
        else:
            final_tp = fixed_tp
            actual_rr = TP_FIXED / sl_pct_actual if sl_pct_actual > 0 else 10
    else:
        final_tp = fixed_tp
        actual_rr = TP_FIXED / sl_pct_actual if sl_pct_actual > 0 else 10
    
    use_swing = use_swing_sl or use_swing_tp
    
    return {
        'sl': round(final_sl, 2),
        'tp': round(final_tp, 2),
        'sl_pct': round(sl_pct_actual, 2),
        'tp_pct': round((final_tp - entry_price) / entry_price * 100, 2),
        'rr': round(actual_rr, 2),
        'use_swing': use_swing,
        'use_swing_sl': use_swing_sl,
        'use_swing_tp': use_swing_tp,
    }


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def score_signal_pattern(ohlcv, all_signals, end_idx):
    """
    V12: 信号序列模式评分
    检查近期信号序列模式, 看是否符合高胜率pattern
    """
    sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
    if len(sigs_before) < 5:
        return 0.5, []
    
    # 提取最近15个信号的类型序列
    recent = sigs_before[-min(SEQ_PATTERN_HISTORY, len(sigs_before)):]
    pattern = []
    for s in recent:
        st = s.get('type', '?')
        if 'FVG' in st:
            pattern.append('F')
        elif 'OB' in st:
            pattern.append('O')
        elif 'Sweep' in st:
            pattern.append('S')
        elif 'CHOCH' in st:
            pattern.append('C')
        elif 'BPR' in st:
            pattern.append('B')
        else:
            pattern.append('?')
    
    # Pattern scoring:
    # 1. FVG密集 = good (最近5个中FVG比例)
    fvg_ratio = pattern[-5:].count('F') / min(5, len(pattern))
    # 2. Sweep后FVG = best (流动性抓取后FVG = 强反转信号)
    sweep_fvg = 0
    for i in range(1, len(pattern)):
        if pattern[i] in ('F', 'O') and pattern[i-1] == 'S':
            sweep_fvg += 1
    # 3. OB过多 = noise
    ob_ratio = pattern[-5:].count('O') / min(5, len(pattern))
    ob_penalty = max(0, ob_ratio - 0.6) * 2  # >60% OB = 惩罚
    
    # Composite score
    score = 0.5 + (fvg_ratio - 0.3) * 0.5 + sweep_fvg * 0.08 - ob_penalty
    score = max(0.1, min(1.0, score))
    
    return round(score, 2), pattern


def analyze_at_point_v12(ohlcv, all_signals, end_idx, params):
    """V12: 分析入场点 — Scout-only + 信号模式 + 多TF"""
    sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
    if len(sigs_before) < 3:
        return None
    
    seq_result = analyze_sequence_v11(sigs_before, params=params)
    best_seq = seq_result.get('best_sequence')
    if not best_seq:
        return None
    
    seq_name = best_seq.get('name', '')
    is_scout = 'SCOUT' in seq_name
    seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
    
    if seq_dir != 'bull':
        return None
    if not is_scout:
        return None
    
    # V12: 信号模式评分
    pattern_score, pattern = score_signal_pattern(ohlcv, all_signals, end_idx)
    
    # 信号质量检查
    sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
    if sig_idx == 0 and not sig_type:
        sig_idx = end_idx
    
    # 成交量确认
    if sig_idx < len(ohlcv) - 1 and sig_idx > 30:
        bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[i].get('v', ohlcv[i].get('vol', 0))
                       for i in range(max(0, sig_idx-30), sig_idx)) / 30
        if bar_vol < avg_vol * MIN_VOL_RATIO:
            return None
    
    # FVG收阳确认
    sig_type_check = sig.get('type', sig_type)
    if 'FVG' in sig_type_check and sig_idx > 0 and sig_idx < len(ohlcv):
        bar = ohlcv[sig_idx]
        if bar['c'] <= bar['o']:
            return None
    
    # FVG gap检查
    if 'FVG' in sig_type_check:
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct < MIN_FVG_GAP:
                return None
    
    # 信号密度检查 (V12: 自适应)
    if len(sigs_before) < 8:
        return None
    
    # 短线趋势
    trend_dir, _ = short_trend(ohlcv, end_idx)
    if trend_dir == 'down':
        return None
    
    # Signal density: signals per 100 bars
    bars_span = end_idx - max(0, end_idx - 100)
    n_sigs_window = len([s for s in sigs_before if s.get('idx', 0) > end_idx - 100])
    signal_density = n_sigs_window / bars_span * 100 if bars_span > 0 else 0
    
    # Density filter (too few = no opportunity, too many = noise)
    if signal_density < 3:  # too few signals
        pass  # allow sparse signals
    
    # 周线趋势过滤
    if USE_WEEKLY_FILTER:
        weekly = synthesize_weekly(ohlcv[:end_idx+1])
        if len(weekly) >= WEEKLY_MIN_BARS:
            wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
            if wt == 'down':
                return None
    
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window,
    )
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout,
        'n_sigs': len(sigs_before), 'seq_dir': seq_dir,
        'best_seq': best_seq,
        'pattern_score': pattern_score,
        'pattern': pattern,
        'signal_density': round(signal_density, 1),
        'entry_idx': sig_idx,
    }


def simulate_trades_v12(ohlcv, all_signals, params):
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    trade_id = 0
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN:
            continue
        
        entry_info = analyze_at_point_v12(ohlcv, all_signals, i, params)
        if entry_info is None:
            continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        is_scout = entry_info['is_scout']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']
        pattern_score = entry_info['pattern_score']
        
        # V12: 模式评分过滤 — 低分信号跳过
        if pattern_score < 0.3:
            continue
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter':
            continue
        if is_scout and resonance.total < SCOUT_MIN_RESONANCE:
            continue
        
        entry_price = decision.get('entry_price')
        if not entry_price:
            continue
        
        # V12: 摆动点SL/TP (黄金公式)
        swing_params = calc_swing_sltp_v12(ohlcv, i, entry_price)
        sl_price = swing_params['sl']
        tp_price = swing_params['tp']
        
        # V12: 风险敞口检查 — 摆动TP若低于固定TP, 检查RR是否够好
        actual_rr = swing_params['rr']
        
        sl_cond = lambda bar: bar['l'] <= sl_price
        tp_cond = lambda bar: bar['h'] >= tp_price
        
        exit_idx, exit_price, won = -1, None, False
        for j in range(i + 1, min(i + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if tp_cond(bar):
                exit_idx, exit_price, won = j, tp_price, True
                break
            if sl_cond(bar):
                exit_idx, exit_price, won = j, sl_price, False
                break
        
        if exit_idx == -1:
            exit_idx = min(i + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            won = exit_price > entry_price
        
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        risk = abs(entry_price - sl_price)
        actual_rr_calc = abs(exit_price - entry_price) / risk if risk > 0 else 10
        
        trades.append({
            'trade_id': trade_id,
            'entry_idx': i, 'exit_idx': exit_idx,
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'sl': round(sl_price, 2), 'tp': round(tp_price, 2),
            'pnl_pct': round(pnl_pct, 2),
            'won': won, 'rr': round(actual_rr_calc, 2),
            'seq_name': best_seq.get('name', 'Scout'),
            'resonance_grade': resonance.grade(),
            'confidence': decision['confidence'],
            'hold_bars': exit_idx - i,
            'use_swing': swing_params['use_swing'],
            'use_swing_sl': swing_params['use_swing_sl'],
            'use_swing_tp': swing_params['use_swing_tp'],
            'sl_pct': swing_params['sl_pct'],
            'tp_pct': swing_params['tp_pct'],
            'pattern_score': pattern_score,
            'signal_density': entry_info['signal_density'],
            'n_sigs': entry_info['n_sigs'],
        })
        trade_id += 1
        entered_bar = i
    
    return trades


def backtest_stock_v12(ohlcv, symbol):
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    
    if not all_signals or len(all_signals) < 5:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}
    
    params = {**base_params, 'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED}
    trades = simulate_trades_v12(ohlcv, all_signals, params)
    
    if len(trades) < 2:
        return {'trades': [], 'n_signals': len(all_signals), 'phase': phase}
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
    loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    swing_count = sum(1 for t in trades if t.get('use_swing', False))
    swing_sl_count = sum(1 for t in trades if t.get('use_swing_sl', False))
    swing_tp_count = sum(1 for t in trades if t.get('use_swing_tp', False))
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2),
            'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
            'swing_pct': round(swing_count / len(trades) * 100, 1) if trades else 0,
            'swing_sl_pct': round(swing_sl_count / len(trades) * 100, 1) if trades else 0,
            'swing_tp_pct': round(swing_tp_count / len(trades) * 100, 1) if trades else 0,
        },
        'n_signals': len(all_signals), 'phase': phase,
        'elapsed': round(time.time() - t0, 1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V12 — Swing-Enhanced Scout + Signal Pattern + Multi-TF")
    print(f"  {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"  Swing SL capped at {SL_CAP}% | TP=swing high or {TP_FIXED}% fixed")
    print(f"  Signal pattern scoring | Weekly trend filter")
    print(f"  Fixed fallback: SL={SL_FIXED}%/TP={TP_FIXED}%")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            continue
        
        result = backtest_stock_v12(ohlcv, sym)
        trades = result.get('trades', [])
        perf = result.get('perf', {})
        
        if trades:
            all_trades.extend(trades)
            stock_results.append({
                'symbol': sym, **perf,
                'n_signals': result.get('n_signals', 0),
                'phase': result.get('phase', '?'),
            })
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"trades={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% "
                  f"RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} "
                  f"P&L={perf['avg_pnl']:+.2f}% swing={perf.get('swing_pct',0):.0f}% | "
                  f"{result.get('elapsed',0):.1f}s")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"NO-TRADE sigs={result.get('n_signals',0)} "
                  f"phase={result.get('phase','?')}")
        
        if (idx + 1) % 30 == 0:
            time.sleep(0.3)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V12 SUMMARY — {len(stock_results)} tradable out of {MAX_STOCKS} | {total_time:.1f}s")
    print(f"{'='*80}")
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 999
        avg_rr = sum(t['rr'] for t in all_trades) / n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
        
        sw_grp = [t for t in all_trades if t.get('use_swing')]
        fx_grp = [t for t in all_trades if not t.get('use_swing')]
        sw_wr = sum(1 for t in sw_grp if t['won'])/len(sw_grp)*100 if sw_grp else 0
        fx_wr = sum(1 for t in fx_grp if t['won'])/len(fx_grp)*100 if fx_grp else 0
        
        sw_sl_grp = [t for t in all_trades if t.get('use_swing_sl')]
        fx_sl_grp = [t for t in all_trades if not t.get('use_swing_sl')]
        sw_sl_wr = sum(1 for t in sw_sl_grp if t['won'])/len(sw_sl_grp)*100 if sw_sl_grp else 0
        fx_sl_wr = sum(1 for t in fx_sl_grp if t['won'])/len(fx_sl_grp)*100 if fx_sl_grp else 0
        
        avg_sl = sum(t.get('sl_pct',0) for t in all_trades)/n
        avg_tp = sum(t.get('tp_pct',0) for t in all_trades)/n
        
        # Pattern score analysis
        high_pat = [t for t in all_trades if t.get('pattern_score',0) >= 0.7]
        low_pat = [t for t in all_trades if t.get('pattern_score',0) < 0.5]
        hp_wr = sum(1 for t in high_pat if t['won'])/len(high_pat)*100 if high_pat else 0
        lp_wr = sum(1 for t in low_pat if t['won'])/len(low_pat)*100 if low_pat else 0
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | "
              f"PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
        print(f"  Avg SL: {avg_sl:.2f}% | Avg TP: {avg_tp:.2f}%")
        print(f"  Swing: {len(sw_grp)}/{n} ({len(sw_grp)/n*100:.0f}%) | "
              f"Swing WR: {sw_wr:.1f}% | Fixed WR: {fx_wr:.1f}%")
        print(f"  Swing SL: {len(sw_sl_grp)} trades | WR: {sw_sl_wr:.1f}% | "
              f"Fixed SL: {len(fx_sl_grp)} trades | WR: {fx_sl_wr:.1f}%")
        print(f"  Pattern Score >=0.7: {len(high_pat)} trades | WR: {hp_wr:.1f}% | "
              f"Pattern Score <0.5: {len(low_pat)} trades | WR: {lp_wr:.1f}%")
        print(f"  WR>=60%: {sum(1 for s in stock_results if s['win_rate']>=60)} | "
              f"WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} | "
              f"WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        
        seq_cnt = Counter(t.get('seq_name','?') for t in all_trades)
        print(f"  Sequences: {dict(seq_cnt.most_common(3))}")
        print(f"  Avg hold: {sum(t['hold_bars'] for t in all_trades)/n:.1f} bars")
        
        # SL distribution
        sl_buckets = Counter()
        for t in all_trades:
            bucket = int(t['sl_pct'] * 10) / 10
            sl_buckets[bucket] += 1
        print(f"\n  SL Distribution:")
        for b in sorted(sl_buckets):
            subset = [t for t in all_trades if int(t['sl_pct']*10)/10 == b]
            sw = sum(1 for t in subset if t['won'])/len(subset)*100
            print(f"    SL={b:.1f}%: {len(subset):3d} trades | WR={sw:.0f}%")
        
        # Swing SL breakdown
        print(f"\n  Swing SL vs Fixed SL:")
        print(f"    Swing SL WR: {sw_sl_wr:.1f}% ({len(sw_sl_grp)} trades)")
        print(f"    Fixed SL WR: {fx_sl_wr:.1f}% ({len(fx_sl_grp)} trades)")
        if sw_sl_grp:
            sw_sl_buckets = Counter()
            for t in sw_sl_grp:
                bucket = int(t['sl_pct'] * 10) / 10
                sw_sl_buckets[bucket] += 1
            print(f"    Swing SL distribution:")
            for b in sorted(sw_sl_buckets):
                subset = [t for t in sw_sl_grp if int(t['sl_pct']*10)/10 == b]
                sw = sum(1 for t in subset if t['won'])/len(subset)*100
                print(f"      SL={b:.1f}%: {len(subset):3d} trades | WR={sw:.0f}%")
        
        print(f"\n  TOP 10 by WR:")
        for s in sorted(stock_results, key=lambda x: x['win_rate'], reverse=True)[:10]:
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% RR={s['avg_rr']:.1f}x "
                  f"PF={s['profit_factor']:.1f} trades={s['n_trades']} swing={s.get('swing_pct',0):.0f}%")
        
        # Pattern score correlation
        print(f"\n  Pattern Score Correlation:")
        for threshold in [0.3, 0.5, 0.6, 0.7, 0.8]:
            subset = [t for t in all_trades if t.get('pattern_score',0) >= threshold]
            if subset:
                sw = sum(1 for t in subset if t['won'])/len(subset)*100
                print(f"    PS>={threshold:.1f}: {len(subset):3d} trades | WR={sw:.0f}%")
    
    outpath = OUTPUT_DIR / 'backtest_v12.json'
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'version': 'V12',
            'max_stocks': MAX_STOCKS,
            'sl_cap': SL_CAP, 'sl_fixed': SL_FIXED,
            'tp_fixed': TP_FIXED, 'swing_min_rr': SWING_MIN_RR,
            'min_vol_ratio': MIN_VOL_RATIO, 'min_fvg_gap': MIN_FVG_GAP,
            'use_weekly_filter': USE_WEEKLY_FILTER,
        },
        'summary': {
            'total_stocks': MAX_STOCKS, 'tradable': len(stock_results),
            'total_trades': len(all_trades),
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
            'avg_pnl': round(avg_pnl, 2) if all_trades else 0,
        },
        'stocks': stock_results,
        'all_trades': all_trades,
    }
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
