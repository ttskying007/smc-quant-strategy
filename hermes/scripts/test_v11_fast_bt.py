#!/usr/bin/env python3
"""
V11 快速回测引擎 — 单次信号检测 + 序列匹配 + 交易模拟

加速关键: 不逐bar滚动, 一次检测全量数据上的所有信号,
然后按序列匹配结果模拟交易。
"""
import json, math, logging, sys, time
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import dataclass, field

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/root/.hermes/scripts')

from v11.data_loader import load_cached_ohlcv
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v11')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fast_backtest(ohlcv, symbol, params, tf='daily', min_rr=1.5):
    """
    快速回测: 一次信号检测 → 序列匹配 → 按信号位置入场
    
    主要局限: 没有模拟持仓重叠, 每个信号独立看待。
    但优势: 极快, 适合快速迭代参数。
    """
    n = len(ohlcv)
    if n < 100:
        return {'trades': [], 'stats': {'error': 'insufficient data'}}
    
    train_bars = 100  # 前100根用于预热
    
    # 全量信号检测 (只做一次)
    sig_result = detect_all_signals_v11(ohlcv, params=params, tf=tf)
    all_signals = sig_result['all']
    
    trades = []
    used_indices = set()  # 同一个K线索引不会重复入场
    
    # 在每个信号进入点, 检查序列 + 共振
    for i, sig in enumerate(all_signals):
        entry_idx = sig.get('idx', 0)
        
        # 跳过训练期的信号
        if entry_idx < train_bars or entry_idx >= n - 3:
            continue
        
        # 跳过已经用过的索引
        if entry_idx in used_indices:
            continue
        
        # 以当前信号为"最新"信号, 做局部序列分析
        # 取到当前信号为止的所有信号
        relevant_sigs = all_signals[:i+1]
        if len(relevant_sigs) < 3:
            continue
        
        # 序列分析
        seq_result = analyze_sequence_v11(relevant_sigs, params=params)
        best = seq_result.get('best_sequence')
        if not best:
            continue
        
        # 共振评估 (用全部数据)
        resonance = evaluate_full_resonance_v11(
            all_signals=relevant_sigs,
            ohlcv=ohlcv[:entry_idx+1],
        )
        
        # 入场决策
        decision = make_entry_decision_v11(resonance, seq_result, params)
        
        if decision['action'] != 'enter':
            continue
        if not decision.get('entry_price'):
            continue
        if decision.get('rr', 0) < min_rr:
            continue
        if decision.get('confidence', 0) < 0.60:
            continue
        
        direction = decision['direction']
        entry_price = decision['entry_price']
        sl = decision['sl']
        tp = decision['tp']
        
        # 模拟交易: 从entry_idx开始扫描SL/TP触发
        exit_idx = -1
        exit_price = 0
        won = False
        
        for k in range(entry_idx + 1, min(entry_idx + 60, n)):
            bar = ohlcv[k]
            if direction == 'bull':
                if bar['l'] <= sl:
                    exit_idx = k
                    exit_price = sl
                    won = False
                    break
                elif bar['h'] >= tp:
                    exit_idx = k
                    exit_price = tp
                    won = True
                    break
            else:  # bear
                if bar['h'] >= sl:
                    exit_idx = k
                    exit_price = sl
                    won = False
                    break
                elif bar['l'] <= tp:
                    exit_idx = k
                    exit_price = tp
                    won = True
                    break
        
        # 未触发则market close
        if exit_idx < 0:
            exit_idx = n - 1
            exit_price = ohlcv[-1]['c']
            if direction == 'bull':
                won = exit_price > entry_price
            else:
                won = exit_price < entry_price
        
        # 计算盈亏
        if direction == 'bull':
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100
        
        actual_rr = abs(exit_price - entry_price) / max(abs(entry_price - sl), 0.01) if sl else 0
        
        trades.append({
            'symbol': symbol,
            'direction': direction,
            'entry_idx': entry_idx,
            'entry_price': round(entry_price, 2),
            'sl': round(sl, 2),
            'tp': round(tp, 2),
            'rr_planned': round(decision.get('rr', 0), 2),
            'rr_actual': round(actual_rr, 2),
            'exit_idx': exit_idx,
            'exit_price': round(exit_price, 2),
            'pnl_pct': round(pnl_pct, 2),
            'won': won,
            'sequence': best.get('name', ''),
            'grade': decision.get('grade', ''),
            'confidence': round(decision.get('confidence', 0), 3),
        })
        used_indices.add(entry_idx)
    
    # 统计
    stats = compute_stats(trades)
    return {'trades': trades, 'stats': stats, 'params': params}


def compute_stats(trades):
    if not trades:
        return {'n_trades': 0}
    
    n = len(trades)
    wins = [t for t in trades if t['won']]
    losses = [t for t in trades if not t['won']]
    n_wins = len(wins)
    
    wr = n_wins / n * 100 if n > 0 else 0
    avg_rr = sum(t['rr_actual'] for t in trades) / n if n > 0 else 0
    avg_planned_rr = sum(t['rr_planned'] for t in trades) / n if n > 0 else 0
    
    total_profit = sum(t['pnl_pct'] for t in trades if t['won'])
    total_loss = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = total_profit / total_loss if total_loss > 0 else (999 if total_profit > 0 else 0)
    
    # 权益曲线和最回撤
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t['pnl_pct']
        if equity > peak:
            peak = equity
        dd = (peak - equity) / max(peak, 1)
        if dd > max_dd:
            max_dd = dd
    
    return {
        'n_trades': n,
        'n_wins': n_wins,
        'n_losses': n - n_wins,
        'win_rate': round(wr, 1),
        'avg_rr': round(avg_rr, 2),
        'avg_planned_rr': round(avg_planned_rr, 2),
        'profit_factor': round(pf, 2),
        'total_return_pct': round(equity, 1),
        'max_drawdown_pct': round(max_dd * 100, 1),
        'avg_pnl_per_trade': round(sum(t['pnl_pct'] for t in trades) / n, 2),
    }


def main():
    # 获取缓存股票
    symbols = sorted([
        f.stem.replace('_daily_300', '').replace('_', '.')
        for f in CACHE_DIR.glob('*_daily_300.json')
    ])
    
    limit = min(200, len(symbols))
    print(f"V11.1 快速回测 — 首批 {limit} 只股票 (日线, 缓存数据)")
    print(f"{'='*70}")
    
    all_trades = []
    all_stats = []
    results = {}
    start_time = time.time()
    
    for idx, sym in enumerate(symbols[:limit]):
        t0 = time.time()
        ohlcv = load_cached_ohlcv(sym, 'daily', 300)
        if not ohlcv or len(ohlcv) < 100:
            continue
        
        phase = detect_market_phase(ohlcv)
        params = calc_stock_params(ohlcv, sym, phase=phase, tf="daily")
        
        bt = fast_backtest(ohlcv, sym, params)
        stats = bt['stats']
        trades = bt['trades']
        
        elapsed = time.time() - t0
        results[sym] = stats
        
        if stats.get('n_trades', 0) >= 3:
            all_stats.append(stats)
            all_trades.extend(trades)
            print(f"  [{idx+1:3d}/{limit}] {sym:12s} | "
                  f"N={stats['n_trades']:2d} WR={stats['win_rate']:5.1f}% "
                  f"RR={stats['avg_rr']:.2f}x PF={stats['profit_factor']:.2f} "
                  f"Ret={stats['total_return_pct']:+.0f}% DD={stats['max_drawdown_pct']:.1f}% | "
                  f"{elapsed:.1f}s")
        elif trades:
            print(f"  [{idx+1:3d}/{limit}] {sym:12s} | N={len(trades):2d} (too few) | {elapsed:.1f}s")
        
        # 每50只保存一次
        if (idx + 1) % 50 == 0:
            print(f"\n  --- 进度: {idx+1}/{limit}, 已用时 {time.time()-start_time:.0f}s ---\n")
    
    total_time = time.time() - start_time
    
    # 总统计
    print(f"\n{'='*70}")
    print(f"总体汇总 — {len(results)} 只股票 | 共 {len(all_trades)} 笔交易 | 耗时 {total_time:.0f}s")
    print(f"{'='*70}")
    
    if all_stats:
        # 加权平均
        total_n = sum(s['n_trades'] for s in all_stats)
        avg_wr = sum(s['win_rate'] * s['n_trades'] for s in all_stats) / total_n if total_n else 0
        avg_rr = sum(s['avg_rr'] * s['n_trades'] for s in all_stats) / total_n if total_n else 0
        avg_pf = sum(s['profit_factor'] for s in all_stats) / len(all_stats)
        total_ret = sum(s['total_return_pct'] for s in all_stats)
        
        print(f"  总交易:    {total_n}")
        print(f"  加权WR:    {avg_wr:.1f}%")
        print(f"  加权RR:    {avg_rr:.2f}x")
        print(f"  平均PF:    {avg_pf:.2f}")
        print(f"  累计收益:  {total_ret:+.0f}%")
        print(f"  有交易的股票: {len(all_stats)}/{len(results)}")
    
        # 序列分布
        seq_counts = Counter(t['sequence'] for t in all_trades)
        print(f"\n  序列分布:")
        for seq_name, cnt in seq_counts.most_common(10):
            wins = sum(1 for t in all_trades if t['sequence'] == seq_name and t['won'])
            wr = wins / cnt * 100
            print(f"    {seq_name:20s}: {cnt:3d}笔 (WR={wr:.0f}%)")
    
    # 保存结果
    output = {
        'version': '11.1.0',
        'n_symbols': len(results),
        'n_trades': len(all_trades),
        'n_stocks_with_trades': len(all_stats),
        'overall': {
            'total_trades': total_n if all_stats else 0,
            'weighted_wr': round(avg_wr, 1) if all_stats else 0,
            'weighted_rr': round(avg_rr, 2) if all_stats else 0,
            'avg_pf': round(avg_pf, 2) if all_stats else 0,
            'total_return': round(total_ret, 1) if all_stats else 0,
        },
        'per_stock': results,
        'sequences': dict(seq_counts.most_common(20)) if all_trades else {},
        'time_seconds': round(total_time, 1),
    }
    
    out_path = OUTPUT_DIR / 'v11_1_baseline.json'
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    print(f"\n结果已保存: {out_path}")


if __name__ == '__main__':
    main()
