#!/usr/bin/env python3
"""
SMC V14 — 每股参数优化扫描引擎
====================================================
关键改进:
1. 先检测入场点, 再快速模拟SL/TP组合(比V12快5-10x)
2. 每股独立最优SL/TP参数
3. 每阶段默认参数(breakout=0.5/5.0, volatile=0.7/4.0)
4. 摆动点入场确认
5. 信号质量增强过滤(FVG gap%/成交量/K线/趋势)
====================================================
"""
import json, sys, time, math
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
from multiprocessing import Pool

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v14')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# === 配置 ===
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 40
COOLDOWN = 15
SCOUT_MIN_RESONANCE = 0.65
TREND_THRESHOLD = 0.8

# 每阶段默认参数
PHASE_PARAMS = {
    'breakout': [{'sl': 0.5, 'tp': 5.0}],
    'volatile': [{'sl': 0.7, 'tp': 4.0}],
    'ranging': [{'sl': 0.5, 'tp': 3.0}],
    'trending_down': [{'sl': 0.5, 'tp': 3.0}],
}

# 参数扫描空间 (optimal search)
OPTIMIZE_PARAMS = [
    {'sl': 0.3, 'tp': 5.0}, {'sl': 0.5, 'tp': 5.0}, {'sl': 0.7, 'tp': 5.0},
    {'sl': 0.5, 'tp': 3.0}, {'sl': 0.5, 'tp': 4.0}, {'sl': 0.7, 'tp': 4.0},
    {'sl': 1.0, 'tp': 5.0}, {'sl': 0.3, 'tp': 3.0}, {'sl': 0.5, 'tp': 6.0},
    {'sl': 0.7, 'tp': 6.0},
]

# ============================================================
# 核心逻辑
# ============================================================
def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data


def find_swing_points(ohlcv, lookback=5):
    highs, lows = [], []
    n = len(ohlcv)
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['h'] >= ohlcv[j]['h'] for j in range(i-lookback, i+lookback+1) if j != i):
            highs.append({'idx': i, 'price': ohlcv[i]['h']})
        if all(ohlcv[i]['l'] <= ohlcv[j]['l'] for j in range(i-lookback, i+lookback+1) if j != i):
            lows.append({'idx': i, 'price': ohlcv[i]['l']})
    return highs, lows


def score_signal_quality(first_sig, ohlcv, swing_highs, swing_lows):
    """信号质量评分 (0-100), 宽松版"""
    if not first_sig or not isinstance(first_sig, dict):
        return 30
    
    sig_idx = first_sig.get('idx', 0)
    sig_type = first_sig.get('type', '')
    direction = first_sig.get('direction', '')
    
    if sig_idx <= 0 or sig_idx >= len(ohlcv):
        return 30
    
    bar = ohlcv[sig_idx]
    score = 50
    
    # 1. Volume
    vol = bar.get('v', bar.get('vol', 0))
    avg_vol = 0
    for i in range(max(0, sig_idx-30), sig_idx):
        avg_vol += ohlcv[i].get('v', ohlcv[i].get('vol', 0))
    avg_vol = avg_vol / max(1, min(30, sig_idx))
    if avg_vol > 0:
        if vol > avg_vol * 1.5: score += 15
        elif vol > avg_vol * 1.0: score += 8
        elif vol > avg_vol * 0.7: score += 3
        else: score -= 5
    
    # 2. K-line body
    body = abs(bar['c'] - bar['o'])
    rng = bar['h'] - bar['l']
    if rng > 0 and body/rng > 0.6 and (
        (direction == 'bull' and bar['c'] > bar['o']) or
        (direction == 'bear' and bar['c'] < bar['o'])
    ):
        score += 10
    
    # 3. FVG gap
    if 'FVG' in sig_type:
        upper = first_sig.get('upper', 0) or first_sig.get('price', 0)*1.01
        lower = first_sig.get('lower', 0) or first_sig.get('price', 0)*0.99
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct >= 1.0: score += 15
            elif gap_pct >= 0.5: score += 10
            elif gap_pct >= 0.3: score += 5
            else: score -= 5
    
    # 4. Swing point proximity
    near_low = sum(1 for s in swing_lows if abs(s['idx'] - sig_idx) <= 3)
    near_high = sum(1 for s in swing_highs if abs(s['idx'] - sig_idx) <= 3)
    if direction == 'bull' and near_low: score += 10
    elif direction == 'bear' and near_high: score += 10
    elif near_low or near_high: score += 3
    
    # 5. Trend alignment
    if sig_idx >= 20:
        ma10 = sum(ohlcv[i]['c'] for i in range(sig_idx-10, sig_idx)) / 10
        ma20 = sum(ohlcv[i]['c'] for i in range(sig_idx-20, sig_idx)) / 20
        if direction == 'bull' and ma10 > ma20: score += 10
        elif direction == 'bear' and ma10 < ma20: score += 10
        elif direction == 'bull' and bar['c'] > ma20: score += 5
        elif direction == 'bear' and bar['c'] < ma20: score += 5
    
    return min(100, max(10, score))


def find_entry_points(ohlcv, all_signals, swing_highs, swing_lows, base_params):
    """一次检测所有入场点, 返回entry列表供后续参数模拟"""
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    entries = []
    entered_bar = -999
    
    for end_idx in range(ROLL_START, roll_end):
        if end_idx - entered_bar < COOLDOWN: continue
        
        sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
        if len(sigs_before) < 3: continue
        
        seq_result = analyze_sequence_v11(sigs_before, params=base_params)
        best_seq = seq_result.get('best_sequence')
        if not best_seq: continue
        
        seq_name = best_seq.get('name', '')
        is_scout = 'SCOUT' in seq_name
        seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
        
        # Bull-only
        if seq_dir != 'bull': continue
        if not is_scout: continue  # Scout-only
        
        # Signal quality - use seq_result's entry_signal
        entry_signal = seq_result.get('entry_signal', {})
        sig_idx = entry_signal.get('idx', end_idx) if isinstance(entry_signal, dict) else end_idx
        
        quality = score_signal_quality(entry_signal, ohlcv, swing_highs, swing_lows)
        if quality < 35: continue
        
        # Trend check
        if sig_idx >= 10:
            trend = (ohlcv[sig_idx]['c'] - ohlcv[sig_idx-10]['c']) / ohlcv[sig_idx-10]['c'] * 100
            if trend < -1.0: continue
        if len(sigs_before) < 8: continue
        
        # Resonance + decision
        window = ohlcv[:end_idx + 1]
        tf_sequences = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
        
        if resonance.total < SCOUT_MIN_RESONANCE: continue
        
        decision = make_entry_decision_v11(resonance, seq_result, base_params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter': continue
        
        entry_price = decision.get('entry_price')
        if not entry_price: continue
        
        entries.append({
            'entry_idx': end_idx,
            'direction': 'bull',
            'entry_price': entry_price,
            'seq_name': best_seq.get('name', 'Scout'),
            'quality': quality,
            'confidence': decision['confidence'],
            'resonance_grade': resonance.grade(),
        })
        entered_bar = end_idx
    
    return entries


def simulate_exits(ohlcv, entries, sl_pct, tp_pct):
    """对给定的SL/TP, 模拟所有entry的退出结果"""
    trades = []
    n = len(ohlcv)
    
    for e in entries:
        idx = e['entry_idx']
        entry_price = e['entry_price']
        
        sl_price = entry_price * (1 - sl_pct / 100)
        tp_price = entry_price * (1 + tp_pct / 100)
        
        exit_idx, exit_price, won = -1, None, False
        for j in range(idx + 1, min(idx + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if bar['h'] >= tp_price:
                exit_idx, exit_price, won = j, tp_price, True
                break
            if bar['l'] <= sl_price:
                exit_idx, exit_price, won = j, sl_price, False
                break
        
        if exit_idx == -1:
            exit_idx = min(idx + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            won = exit_price > entry_price
        
        pnl = ((exit_price - entry_price) / entry_price * 100)
        rr = abs(exit_price - entry_price) / abs(entry_price - sl_price + 0.001)
        
        trades.append({
            'entry_idx': idx, 'exit_idx': exit_idx,
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'sl': round(sl_price, 2), 'tp': round(tp_price, 2),
            'pnl_pct': round(pnl, 2), 'won': won, 'rr': round(rr, 2),
            'seq_name': e['seq_name'],
            'quality_score': e['quality'],
            'confidence': e['confidence'],
            'resonance_grade': e['resonance_grade'],
            'hold_bars': exit_idx - idx,
        })
    
    return trades


def backtest_stock(args):
    """单股票 — 入场检测1次 + 参数扫描10次模拟"""
    symbol, optimize = args
    try:
        t0 = time.time()
        ohlcv = load_ohlcv(symbol)
        if not ohlcv: return None
        
        phase = detect_market_phase(ohlcv)
        base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
        
        all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
        if not all_signals or len(all_signals) < 5: return None
        
        swing_highs, swing_lows = find_swing_points(ohlcv)
        
        # 一次性检测所有入场点
        entries = find_entry_points(ohlcv, all_signals, swing_highs, swing_lows, base_params)
        if not entries: return None
        
        # 选择参数方案
        if optimize:
            param_list = OPTIMIZE_PARAMS
        else:
            param_list = PHASE_PARAMS.get(phase, [{'sl': 0.5, 'tp': 5.0}])
        
        # 模拟所有参数
        best = None
        best_score = -1
        
        for p in param_list:
            trades = simulate_exits(ohlcv, entries, p['sl'], p['tp'])
            if len(trades) < 2: continue
            
            wins = sum(1 for t in trades if t['won'])
            n = len(trades)
            wr = wins / n * 100
            win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
            loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
            pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
            avg_rr = sum(t['rr'] for t in trades) / n
            avg_pnl = sum(t['pnl_pct'] for t in trades) / n
            
            score = (wr/100)**2 * min(3, avg_rr) * min(3, pf) * min(2, n/5)
            
            if score > best_score:
                best_score = score
                best = {
                    'sl_pct': p['sl'], 'tp_pct': p['tp'],
                    'n_trades': n, 'wins': wins, 'losses': n-wins,
                    'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
                    'profit_factor': round(pf, 2) if pf != float('inf') else 99.9,
                    'avg_pnl': round(avg_pnl, 2),
                    'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
                    'trades': trades, 'score': round(best_score, 1),
                }
        
        if best is None: return None
        
        elapsed = time.time() - t0
        return {
            'symbol': symbol, 'phase': phase,
            'n_signals': len(all_signals),
            'n_swing_highs': len(swing_highs),
            'n_swing_lows': len(swing_lows),
            'perf': {k: best[k] for k in ['sl_pct','tp_pct','n_trades','wins','losses',
                                           'win_rate','avg_rr','profit_factor','avg_pnl','total_pnl','score']},
            'n_trades': best['n_trades'],
            'elapsed': round(elapsed, 1),
        }
    except Exception as e:
        return {'symbol': symbol, 'error': str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--limit', type=int, default=4800)
    parser.add_argument('--batch', type=int, default=500)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--optimize', action='store_true', help='Per-stock param optimization')
    parser.add_argument('--output', type=str, default=None)
    args = parser.parse_args()
    
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    total = min(args.limit, len(symbols) - args.start)
    batch_end = min(args.start + args.batch, args.start + total)
    batch = symbols[args.start:batch_end]
    
    mode = "每股参数优化" if args.optimize else "阶段默认参数"
    print(f"SMC V14 扫描 — {mode}")
    print(f"  批次: {args.start}-{batch_end}/{len(symbols)} ({len(batch)}股票)")
    print(f"  并行: {args.workers} workers")
    if args.optimize:
        print(f"  参数空间: {len(OPTIMIZE_PARAMS)}组合")
    print()
    
    t_start = time.time()
    pool_args = [(s, args.optimize) for s in batch]
    
    t0 = time.time()
    with Pool(processes=args.workers) as pool:
        results = pool.map(backtest_stock, pool_args)
    scan_time = time.time() - t0
    
    stock_results = []
    for r in results:
        if r is None: continue
        if 'error' in r:
            print(f"  ERROR {r['symbol']}: {r['error']}")
            continue
        if 'perf' in r:
            p = r['perf']
            print(f"  {r['symbol']:12s} SL={p['sl_pct']:.1f}% TP={p['tp_pct']:.1f}% "
                  f"n={p['n_trades']:3d} WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x "
                  f"PF={p['profit_factor']:.1f} P&L={p['avg_pnl']:+.2f}% {r['phase'][:8]:8s} "
                  f"score={p.get('score',0):.0f} {r['elapsed']:.1f}s")
            stock_results.append(r)
    
    elapsed = time.time() - t_start
    
    # === 汇总 ===
    print(f"\n{'='*70}")
    print(f"V14 汇总 — {len(stock_results)} 可交易 / {len(batch)} 扫描, {elapsed:.1f}s")
    print(f"{'='*70}")
    
    if stock_results:
        total_t = sum(s['perf']['n_trades'] for s in stock_results)
        avg_wr = sum(s['perf']['win_rate'] for s in stock_results) / len(stock_results)
        avg_rr = sum(s['perf']['avg_rr'] for s in stock_results) / len(stock_results)
        
        wr80 = sum(1 for s in stock_results if s['perf']['win_rate'] >= 80)
        wr70 = sum(1 for s in stock_results if s['perf']['win_rate'] >= 70)
        
        print(f"\n  总交易: {total_t} | 平均WR: {avg_wr:.1f}% | 平均RR: {avg_rr:.2f}x")
        print(f"  WR>=80%: {wr80} | WR>=70%: {wr70}")
        
        sl_dist = Counter(s['perf']['sl_pct'] for s in stock_results)
        tp_dist = Counter(s['perf']['tp_pct'] for s in stock_results)
        print(f"  SL分布: {dict(sl_dist.most_common())}")
        print(f"  TP分布: {dict(tp_dist.most_common())}")
        
        phase_dist = Counter(s['phase'] for s in stock_results)
        print(f"  阶段分布: {dict(phase_dist.most_common())}")
        
        sorted_s = sorted(stock_results, key=lambda s: -s['perf']['score'])
        print(f"\n  TOP 10 (by score):")
        for s in sorted_s[:10]:
            p = s['perf']
            print(f"    {s['symbol']:12s} WR={p['win_rate']:.0f}% n={p['n_trades']:3d} "
                  f"RR={p['avg_rr']:.2f}x SL={p['sl_pct']:.1f}% TP={p['tp_pct']:.1f}% score={p['score']:.0f}")
    
    # 保存
    output_name = args.output or f'v14_{args.start}_{batch_end}.json'
    outpath = OUTPUT_DIR / output_name
    
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {'mode': mode, 'optimize': args.optimize,
                   'batch_start': args.start, 'batch_end': batch_end,
                   'workers': args.workers},
        'summary': {
            'scanned': len(batch), 'tradable': len(stock_results),
            'avg_win_rate': round(avg_wr, 1) if stock_results else 0,
            'avg_rr': round(avg_rr, 2) if stock_results else 0,
        },
        'stocks': stock_results,
    }
    outpath.write_text(json.dumps(out, ensure_ascii=False, default=str))
    print(f"\n  保存: {outpath}")


if __name__ == '__main__':
    main()
