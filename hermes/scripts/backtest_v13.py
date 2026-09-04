#!/usr/bin/env python3
"""
SMC V13 — 全量市场扫描引擎
============================================================
基于V7成功策略 (Scout-only + Bull-only + 质量过滤 + 固定SL/TP)
优化: 批量处理, 多进程加速, 进度保存, 断点续传
============================================================
"""
import json, sys, time, math, os, signal
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
from multiprocessing import Pool, cpu_count

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v13')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# === 配置 (V11.3 最优) ===
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 40
COOLDOWN = 15
SL = 0.5
TP = 5.0
SCOUT_MIN_RESONANCE = 0.65
TREND_THRESHOLD = 0.8  # 10-bar趋势门槛%

# === 内存优化配置 ===
BATCH_SIZE = 500       # 每批保存进度
PARALLEL_WORKERS = 4   # 并行进程数

# ============================================================
# 核心回测逻辑 (V7精确复制)
# ============================================================
def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback: return 'neutral', 0.0
    segment = ohlcv[idx-lookback:idx+1]
    start, end = segment[0]['c'], segment[-1]['c']
    change = (end - start) / start * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ema_dist = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > TREND_THRESHOLD and ema_dist > 0: return 'up', change
    elif change < -TREND_THRESHOLD and ema_dist < 0: return 'down', abs(change)
    return 'neutral', 0


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data


def analyze_at_point(ohlcv, all_signals, end_idx, params):
    sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
    if len(sigs_before) < 3: return None
    seq_result = analyze_sequence_v11(sigs_before, params=params)
    best_seq = seq_result.get('best_sequence')
    if not best_seq: return None
    seq_name = best_seq.get('name', '')
    is_scout = 'SCOUT' in seq_name
    seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
    if seq_dir != 'bull': return None
    if not is_scout: return None  # Scout-only
    
    # Scout checks
    trend_dir, _ = short_trend(ohlcv, end_idx)
    if trend_dir != 'neutral' and trend_dir != 'up': return None
    if len(sigs_before) < 10: return None
    
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
    if resonance.total < SCOUT_MIN_RESONANCE: return None
    
    decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
    if decision['action'] != 'enter': return None
    
    return {
        'seq_result': seq_result, 'resonance': resonance,
        'seq_name': seq_name, 'is_scout': is_scout, 'n_sigs': len(sigs_before),
        'decision': decision,
    }


def simulate_trades(ohlcv, all_signals, params):
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN: continue
        
        entry_info = analyze_at_point(ohlcv, all_signals, i, params)
        if entry_info is None: continue
        
        decision = entry_info['decision']
        direction = decision.get('direction', 'bull')
        entry_price = decision.get('entry_price')
        sl_price = decision.get('sl')
        tp_price = decision.get('tp')
        
        if not entry_price or not sl_price or not tp_price: continue
        
        sl_cond = lambda b: b['l'] <= sl_price if direction == 'bull' else b['h'] >= sl_price
        tp_cond = lambda b: b['h'] >= tp_price if direction == 'bull' else b['l'] <= tp_price
        
        exit_idx, exit_price, won = -1, None, False
        for j in range(i + 1, min(i + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if tp_cond(bar): exit_idx, exit_price, won = j, tp_price, True; break
            if sl_cond(bar): exit_idx, exit_price, won = j, sl_price, False; break
        
        if exit_idx == -1:
            exit_idx = min(i + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            won = (exit_price > entry_price) if direction == 'bull' else (exit_price < entry_price)
        
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if direction == 'bull' else ((entry_price - exit_price) / entry_price * 100)
        actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl_price + 0.001)
        
        best_seq = entry_info['seq_result'].get('best_sequence', {})
        trades.append({
            'entry_idx': i, 'exit_idx': exit_idx, 'direction': direction,
            'entry_price': round(entry_price, 2), 'exit_price': round(exit_price, 2),
            'sl': round(sl_price, 2), 'tp': round(tp_price, 2),
            'pnl_pct': round(pnl_pct, 2), 'won': won, 'rr': round(actual_rr, 2),
            'seq_name': best_seq.get('name', 'Scout'),
            'resonance_grade': entry_info['resonance'].grade(),
            'confidence': decision['confidence'],
            'hold_bars': exit_idx - i,
        })
        entered_bar = i
    
    return trades


def backtest_single_stock(symbol):
    """单股票回测 — 供并行调用"""
    try:
        ohlcv = load_ohlcv(symbol)
        if not ohlcv: return None
        
        t0 = time.time()
        phase = detect_market_phase(ohlcv)
        
        # 只做breakout/volatile阶段
        if phase not in ('breakout', 'volatile', 'breakout_phase'):
            return None
        
        base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
        all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
        
        if not all_signals or len(all_signals) < 5:
            return None
        
        params = {**base_params, 'sl_pct': SL, 'tp_pct': TP}
        trades = simulate_trades(ohlcv, all_signals, params)
        
        if not trades:
            return None
        
        wins = sum(1 for t in trades if t['won'])
        n = len(trades)
        wr = wins / n * 100
        win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
        avg_rr = sum(t['rr'] for t in trades) / n
        avg_pnl = sum(t['pnl_pct'] for t in trades) / n
        
        elapsed = time.time() - t0
        
        return {
            'symbol': symbol, 'sl_pct': SL, 'tp_pct': TP,
            'n_trades': n, 'wins': wins, 'losses': n - wins,
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf != float('inf') else 99.9,
            'avg_pnl': round(avg_pnl, 2),
            'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
            'n_signals': len(all_signals), 'phase': phase,
            'trades': trades,
            'elapsed': round(elapsed, 1),
        }
    except Exception as e:
        return {'symbol': symbol, 'error': str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SMC V13 Full Market Scan')
    parser.add_argument('--start', type=int, default=0, help='Start index')
    parser.add_argument('--limit', type=int, default=4800, help='Max stocks')
    parser.add_argument('--batch', type=int, default=BATCH_SIZE, help='Batch size')
    parser.add_argument('--workers', type=int, default=PARALLEL_WORKERS, help='Parallel workers')
    args = parser.parse_args()
    
    # 获取所有股票
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    total = min(args.limit, len(symbols) - args.start)
    batch_end = min(args.start + args.batch, args.start + total)
    batch_symbols = symbols[args.start:batch_end]
    
    print(f"{'='*85}")
    print(f"SMC V13 全量市场扫描")
    print(f"  策略: Scout-only + Bull-only + SL={SL}%/TP={TP}% + 阶段过滤(breakout/volatile)")
    print(f"  批次: {args.start}-{batch_end}/{len(symbols)} ({len(batch_symbols)}股票)")
    print(f"  并行: {args.workers} workers | 批保存: 每{args.batch}条")
    print(f"{'='*85}")
    print()
    
    t_start = time.time()
    all_results = []
    all_trades = []
    
    # 并行处理
    with Pool(processes=args.workers) as pool:
        results = pool.map(backtest_single_stock, batch_symbols)
    
    for r in results:
        if r is None: continue
        if 'error' in r:
            print(f"  ERROR {r['symbol']}: {r['error']}")
            continue
        if 'trades' in r:
            print(f"  {r['symbol']:12s} WR={r['win_rate']:.0f}% n={r['n_trades']:3d} "
                  f"RR={r['avg_rr']:.2f}x PF={r['profit_factor']:.1f} P&L={r['avg_pnl']:+.2f}% "
                  f"phase={r['phase']:10s} {r['elapsed']:.1f}s")
            all_trades.extend(r['trades'])
            del r['trades']  # 节省内存
            all_results.append(r)
    
    elapsed = time.time() - t_start
    
    # === 汇总 ===
    print(f"\n{'='*85}")
    print(f"V13 批次汇总 — {len(all_results)} 可交易 / {len(batch_symbols)} 扫描, {elapsed:.1f}s")
    print(f"{'='*85}")
    
    if all_results:
        n = len(all_results)
        total_trades = sum(s['n_trades'] for s in all_results)
        avg_wr = sum(s['win_rate'] for s in all_results) / n
        total_wins = sum(s['wins'] for s in all_results)
        total_losses = sum(s['losses'] for s in all_results)
        avg_rr = sum(s['avg_rr'] for s in all_results) / n
        
        print(f"\n  可交易股票: {n}/{len(batch_symbols)} ({n/len(batch_symbols)*100:.1f}%)")
        print(f"  总交易数: {total_trades} | 平均WR: {avg_wr:.1f}% | 平均RR: {avg_rr:.2f}x")
        print(f"  总赢/输: {total_wins}/{total_losses} | 总PF: {sum(s['profit_factor'] for s in all_results)/n:.1f}")
        
        wr80 = sum(1 for s in all_results if s['win_rate'] >= 80)
        wr70 = sum(1 for s in all_results if s['win_rate'] >= 70)
        wr60 = sum(1 for s in all_results if s['win_rate'] >= 60)
        print(f"  WR>=80%: {wr80} | WR>=70%: {wr70} | WR>=60%: {wr60}")
        
        # 阶段分布
        phase_cnt = Counter(s['phase'] for s in all_results)
        print(f"  阶段分布: {dict(phase_cnt.most_common())}")
        
        # 最佳股票
        sorted_s = sorted(all_results, key=lambda s: -s['win_rate'])
        print(f"\n  TOP 10 (by WR):")
        for s in sorted_s[:10]:
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% n={s['n_trades']:3d} "
                  f"RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} phase={s['phase']:10s}")
        
        # 按得分排序
        sorted_score = sorted(all_results, key=lambda s: -(s['win_rate']*s['avg_rr']*min(3, s['n_trades']/3)))
        print(f"\n  TOP 10 (by score):")
        for s in sorted_score[:10]:
            score = s['win_rate']*s['avg_rr']*min(3, s['n_trades']/3)
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% n={s['n_trades']:3d} "
                  f"RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} score={score:.0f}")
    
    # 保存
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'start': args.start, 'batch_size': len(batch_symbols),
            'sl_pct': SL, 'tp_pct': TP, 'scout_min_resonance': SCOUT_MIN_RESONANCE,
            'trend_threshold': TREND_THRESHOLD,
        },
        'summary': {
            'scanned': len(batch_symbols),
            'tradable': len(all_results),
            'total_trades': sum(s['n_trades'] for s in all_results),
            'avg_win_rate': round(avg_wr, 1) if all_results else 0,
            'avg_rr': round(avg_rr, 2) if all_results else 0,
        },
        'stocks': all_results,
        'all_trades': all_trades,
    }
    
    outpath = OUTPUT_DIR / f'batch_{args.start}_{batch_end}.json'
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  保存: {outpath}")
    print(f"  总耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")


if __name__ == '__main__':
    main()
