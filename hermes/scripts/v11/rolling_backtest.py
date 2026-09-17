#!/usr/bin/env python3
"""V11 高效滚动回测 — 基于预检测信号的滑动窗口模拟

策略:
1. 一次性全量信号检测 (不用逐bar重检)
2. 从bar 80到bar 280滑动: 每个点只用该点之前的信号
3. 若信号序列+共振满足入场条件 → 模拟持仓跟踪P&L
4. 统计胜率/盈亏比/利润因子
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/root/.hermes/scripts')

from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11, ResonanceResult
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v11')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_STOCKS = 100   # 第一批100只
MIN_BARS = 120     # 最少需要120根K线才有足够滚动窗口
ROLL_START = 80    # 从bar 80开始检查入场
ROLL_END_OFFSET = 10  # 留10根K线作为退出空间
MAX_HOLD = 40      # 最多持40根K线
FEE_PCT = 0.20     # 审计修复(§3.5): 往返成本 0.20%(与 V699 标准一致)

# 参数扫描范围
SL_RANGE = [0.5, 0.7, 1.0, 1.3, 1.5, 2.0]
TP_RANGE = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]


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


def analyze_at_point(ohlcv, all_signals, end_idx, params, tf='daily'):
    """Analyze signals up to end_idx and make entry decision"""
    # Filter signals up to end_idx
    sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
    
    if len(sigs_before) < 3:
        return None
    
    # Sequence analysis
    seq_result = analyze_sequence_v11(sigs_before, params=params)
    best_seq = seq_result.get('best_sequence')
    
    if not best_seq:
        # No sequence at all — skip (needs at least Bronze or Scout)
        return None
    
    # Check if sequence is tradable (Gold/Silver/Bronze enter, Scout needs higher bar)
    seq_name = best_seq.get('name', '')
    is_scout = 'SCOUT' in seq_name
    
    if is_scout and len(sigs_before) < 8:
        # Scout with very few signals = too risky
        return None
    
    # Resonance
    window = ohlcv[:end_idx + 1]
    tf_sequences = {tf: seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=sigs_before,
        tf_sequences=tf_sequences,
        ohlcv=window,
    )
    
    # Decision
    decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
    
    if decision['action'] != 'enter':
        return None
    
    entry_price = decision.get('entry_price')
    direction = decision.get('direction')
    sl_price = decision.get('sl')
    tp_price = decision.get('tp')
    
    if not entry_price or not direction or not sl_price or not tp_price:
        return None
    
    return {
        'entry_idx': end_idx,
        'entry_price': entry_price,
        'direction': direction,
        'sl': sl_price,
        'tp': tp_price,
        'seq_name': best_seq.get('name', 'Scout'),
        'seq_confidence': best_seq.get('confidence', 0),
        'resonance_grade': resonance.grade(),
        'resonance_total': resonance.total,
        'confidence': decision['confidence'],
        'expected_wr': resonance.expected_wr(),
    }


def simulate_exit(ohlcv, entry_idx, direction, sl, tp, max_hold=MAX_HOLD,
                  fee_pct=FEE_PCT):
    """Simulate trade exit —— 审计修复(2026-09, §3.5 P1).

    继承 V699 的最低标准:
      - **T+1**: 从 entry_idx+1 起评估(禁止同日退出)
      - **SL 优先**: 同 bar 同时触发 TP/SL 时按 SL 处理(保守顺序)
      - **跳空穿越止损**: bar 开盘价已低于 SL -> 按开盘价成交(GAP_SL),
        而非用 SL 价(实盘跳空时止损单以开盘价成交)
      - **成本**: 返回的 exit_price 扣除 fee_pct 往返成本(用于净收益)
      - **超时**: 第 max_hold 根 bar 收盘平仓
    返回: (exit_idx, exit_price_gross, won, reason)
      reason: 'TP' / 'SL' / 'GAP_SL' / 'TIME'
    """
    n = len(ohlcv)
    entry_o = ohlcv[entry_idx]['o']
    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]
        if direction == 'bull':
            # 跳空穿越止损: 开盘价已 <= SL
            if bar['o'] <= sl:
                return j, bar['o'], False, 'GAP_SL'
            # 同 bar 先 SL 后 TP(保守)
            if bar['l'] <= sl:
                return j, sl, False, 'SL'
            if bar['h'] >= tp:
                return j, tp, True, 'TP'
        else:
            if bar['o'] >= sl:
                return j, bar['o'], False, 'GAP_SL'
            if bar['h'] >= sl:
                return j, sl, False, 'SL'
            if bar['l'] <= tp:
                return j, tp, True, 'TP'
    # Time out: close at close price (扣除成本)
    exit_idx = min(entry_idx + max_hold, n - 1)
    exit_price = ohlcv[exit_idx]['c']
    won = (exit_price > entry_o if direction == 'bull'
           else exit_price < entry_o)
    return exit_idx, exit_price, won, 'TIME'


def run_backtest(ohlcv, symbol, sl_pct, tp_pct, verbose=False):
    """Run rolling backtest with given SL/TP params"""
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET

    # 审计修复(2026-09, 审计§3.4 P1): 消除参数层 look-ahead.
    # 原实现用完整 ohlcv 一次性计算 detect_market_phase/calc_stock_params,
    # 使后期波动/成交量进入早期决策. 现改为**滚动前缀参数**:
    #   - 按 PARAM_REFRESH_BARS 分块, 每块边界处仅用 ohlcv[:i](过去前缀)重算参数
    #   - 信号检测仍一次性(审计 P0 的事件流改造记为 Iteration 0-1 后续),
    #     但参数不再读未来; 信号层的 confirmed_at 语义由 analyze_at_point 的
    #     idx 过滤承担(已知限制, 见审计 §3.2).
    PARAM_REFRESH_BARS = 20

    # 1. 初始参数: 用滚动起点之前的**过去前缀**(而非全样本)
    init_end = max(ROLL_START, PARAM_REFRESH_BARS)
    prefix = ohlcv[:init_end]
    phase = detect_market_phase(prefix)
    base_params = calc_stock_params(prefix, symbol, phase=phase, tf='daily')
    params = {**base_params, 'sl_pct': sl_pct, 'tp_pct': tp_pct}

    # 2. One-shot signal detection
    sig_result = detect_all_signals_v11(ohlcv, params=params, tf='daily')
    all_signals = sig_result['all']

    if not all_signals or len(all_signals) < 5:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}

    # 3. Rolling: check entry at each bar in range
    trades = []
    entered_bar = -999  # cooldown: don't re-enter within 20 bars of last entry
    cooldown = 20

    for i in range(ROLL_START, roll_end):
        if i - entered_bar < cooldown:
            continue

        # 分块刷新参数: 每 PARAM_REFRESH_BARS 根 bar 用**过去前缀**重算一次
        if i % PARAM_REFRESH_BARS == 0 and i >= PARAM_REFRESH_BARS:
            prefix = ohlcv[:i]
            phase = detect_market_phase(prefix)
            base_params = calc_stock_params(prefix, symbol, phase=phase, tf='daily')
            params = {**base_params, 'sl_pct': sl_pct, 'tp_pct': tp_pct}

        entry_info = analyze_at_point(ohlcv, all_signals, i, params)
        if not entry_info:
            continue
        
        # Enter trade
        exit_idx, exit_price, won, exit_reason = simulate_exit(
            ohlcv, i, entry_info['direction'],
            entry_info['sl'], entry_info['tp']
        )

        # P&L —— 审计修复(§3.5): 扣除 0.20% 往返成本(FEE_PCT)
        fee = entry_info['entry_price'] * FEE_PCT / 100.0
        if entry_info['direction'] == 'bull':
            gross_pnl = (exit_price - entry_info['entry_price']) * 100.0 / entry_info['entry_price']
            pnl_pct = (exit_price - fee - entry_info['entry_price']) / entry_info['entry_price'] * 100
            actual_rr = abs(exit_price - entry_info['entry_price']) / abs(entry_info['entry_price'] - entry_info['sl'] + 0.001)
        else:
            gross_pnl = (entry_info['entry_price'] - exit_price) * 100.0 / entry_info['entry_price']
            pnl_pct = (entry_info['entry_price'] - exit_price - fee) / entry_info['entry_price'] * 100
            actual_rr = abs(entry_info['entry_price'] - exit_price) / abs(entry_info['sl'] - entry_info['entry_price'] + 0.001)
        
        trades.append({
            'symbol': symbol,
            'entry_idx': i,
            'exit_idx': exit_idx,
            'direction': entry_info['direction'],
            'entry_price': round(entry_info['entry_price'], 2),
            'exit_price': round(exit_price, 2),
            'sl': round(entry_info['sl'], 2),
            'tp': round(entry_info['tp'], 2),
            'pnl_pct': round(pnl_pct, 2),
            'won': won,
            'exit_reason': exit_reason,
            'rr': round(actual_rr, 2),
            'seq_name': entry_info['seq_name'],
            'resonance_grade': entry_info['resonance_grade'],
            'confidence': entry_info['confidence'],
            'phase': phase,
            'hold_bars': exit_idx - i,
        })
        
        entered_bar = i
        if verbose:
            print(f"    TRADE: {symbol} {entry_info['direction']} @{entry_info['entry_price']:.2f} "
                  f"→ {exit_price:.2f} {'W' if won else 'L'} pnl={pnl_pct:+.2f}%")
    
    return {'trades': trades, 'n_signals': len(all_signals), 'phase': phase}


def scan_params(ohlcv, symbol, verbose=False):
    """Find optimal SL/TP for this stock"""
    best = {'sl_pct': 1.0, 'tp_pct': 3.0, 'win_rate': 0, 'profit_factor': 0, 'n_trades': 0}
    
    for sl_pct in SL_RANGE:
        for tp_pct in TP_RANGE:
            result = run_backtest(ohlcv, symbol, sl_pct, tp_pct, verbose=False)
            trades = result['trades']
            if len(trades) < 3:
                continue
            
            wins = sum(1 for t in trades if t['won'])
            losses = len(trades) - wins
            wr = wins / len(trades) * 100
            
            win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
            loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
            pf = win_pnl / loss_pnl if loss_pnl > 0 else 0
            
            # Objective: WR * RR * PF
            avg_rr = sum(t['rr'] for t in trades) / len(trades)
            score = (wr / 100) ** 2 * avg_rr * min(2, pf) * min(1.5, len(trades) / 10)
            
            if score > best.get('score', 0):
                best = {
                    'sl_pct': sl_pct, 'tp_pct': tp_pct,
                    'n_trades': len(trades), 'wins': wins, 'losses': losses,
                    'win_rate': round(wr, 1),
                    'avg_rr': round(avg_rr, 2),
                    'profit_factor': round(pf, 2) if pf != float('inf') else 99.9,
                    'avg_pnl': round(sum(t['pnl_pct'] for t in trades) / len(trades), 2),
                    'score': round(score, 2),
                }
    
    return best


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V11 滚动回测 — {min(MAX_STOCKS, len(symbols))}/{len(symbols)} 股票 (SL/TP参数扫描)")
    print(f"{'='*80}")
    
    all_trades = []
    stock_opt = []
    
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        t0 = time.time()
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SKIP (no data)")
            continue
        
        # Find optimal params
        best = scan_params(ohlcv, sym)
        
        if best['n_trades'] > 0:
            # Re-run with optimal params
            opt_result = run_backtest(ohlcv, sym, best['sl_pct'], best['tp_pct'], verbose=False)
            all_trades.extend(opt_result['trades'])
            
            stock_opt.append({
                'symbol': sym,
                'best_params': {'sl_pct': best['sl_pct'], 'tp_pct': best['tp_pct']},
                'performance': {k: best[k] for k in ['n_trades','wins','losses','win_rate','avg_rr','profit_factor','avg_pnl','score']},
                'phase': opt_result['phase'],
                'n_signals': opt_result['n_signals'],
            })
            
            elapsed = time.time() - t0
            perf = best
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SL={perf['sl_pct']:.1f}% TP={perf['tp_pct']:.1f}% "
                  f"trades={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% RR={perf['avg_rr']:.2f}x "
                  f"PF={perf['profit_factor']:.1f} avgP&L={perf['avg_pnl']:+.2f}% {elapsed:.1f}s")
        else:
            elapsed = time.time() - t0
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} no trades (no valid sequence) {elapsed:.1f}s")
        
        # Rate limit
        if (idx + 1) % 10 == 0:
            time.sleep(0.3)
    
    total_time = time.time() - t_start
    
    # === COMPREHENSIVE SUMMARY ===
    print(f"\n{'='*80}")
    print(f"RETURN SUMMARY — {len(stock_opt)} tradable out of {MAX_STOCKS}, {total_time:.1f}s")
    print(f"{'='*80}")
    
    n_traded = len(stock_opt)
    n_with_trades = sum(1 for s in stock_opt if s['performance']['n_trades'] > 0)
    print(f"\n  Tradable stocks: {n_with_trades}/{n_traded} ({n_with_trades/n_traded*100:.0f}%)")
    
    if all_trades:
        total = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        losses = total - wins
        wr = wins / total * 100
        
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
        avg_rr = sum(t['rr'] for t in all_trades) / total
        avg_pnl = sum(t['pnl_pct'] for t in all_trades) / total
        total_pnl = sum(t['pnl_pct'] for t in all_trades)
        
        print(f"\n  === AGGREGATE STATS ({total} trades) ===")
        print(f"    Win Rate:     {wr:.1f}%")
        print(f"    Wins/Losses:  {wins}/{losses}")
        print(f"    Avg RR:       {avg_rr:.2f}x")
        print(f"    Avg P&L:      {avg_pnl:+.2f}%")
        print(f"    Total P&L:    {total_pnl:+.2f}%")
        print(f"    Profit Factor:{pf:.2f}")
        
        # Per-stock analysis
        wr_above_60 = sum(1 for s in stock_opt if s['performance']['win_rate'] >= 60)
        wr_above_70 = sum(1 for s in stock_opt if s['performance']['win_rate'] >= 70)
        pf_above_2 = sum(1 for s in stock_opt if s['performance']['profit_factor'] >= 2.0)
        
        print(f"\n  === STOCK QUALITY ===")
        print(f"    Stocks WR>=60%: {wr_above_60}/{n_with_trades}")
        print(f"    Stocks WR>=70%: {wr_above_70}/{n_with_trades}")
        print(f"    Stocks PF>=2:   {pf_above_2}/{n_with_trades}")
        
        # Best/worst
        sorted_stocks = sorted(stock_opt, key=lambda s: s['performance']['score'], reverse=True)
        print(f"\n  === TOP 5 STOCKS ===")
        for s in sorted_stocks[:5]:
            p = s['performance']
            print(f"    {s['symbol']:12s} SL={s['best_params']['sl_pct']:.1f}% TP={s['best_params']['tp_pct']:.1f}% "
                  f"WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x PF={p['profit_factor']:.1f} "
                  f"trades={p['n_trades']} score={p.get('score',0):.1f}")
        
        print(f"\n  === WORST 5 STOCKS ===")
        for s in sorted_stocks[-5:]:
            p = s['performance']
            print(f"    {s['symbol']:12s} SL={s['best_params']['sl_pct']:.1f}% TP={s['best_params']['tp_pct']:.1f}% "
                  f"WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x PF={p['profit_factor']:.1f} "
                  f"trades={p['n_trades']} score={p.get('score',0):.1f}")
        
        # Params distribution
        sl_counter = Counter()
        tp_counter = Counter()
        for s in stock_opt:
            sl_counter[s['best_params']['sl_pct']] += 1
            tp_counter[s['best_params']['tp_pct']] += 1
        print(f"\n  === OPTIMAL SL DISTRIBUTION ===")
        for sl, cnt in sl_counter.most_common():
            print(f"    SL={sl}%: {cnt} stocks")
        print(f"\n  === OPTIMAL TP DISTRIBUTION ===")
        for tp, cnt in tp_counter.most_common():
            print(f"    TP={tp}%: {cnt} stocks")
    else:
        print("  No trades generated for any stock!")
    
    # Save
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'max_stocks': MAX_STOCKS,
            'sl_range': SL_RANGE,
            'tp_range': TP_RANGE,
            'roll_start': ROLL_START,
            'max_hold': MAX_HOLD,
        },
        'stock_optimizations': stock_opt,
        'all_trades': all_trades,
        'summary': {
            'total_stocks': n_traded,
            'tradable_stocks': n_with_trades,
            'total_trades': len(all_trades),
            'wins': sum(1 for t in all_trades if t['won']) if all_trades else 0,
            'losses': sum(1 for t in all_trades if not t['won']) if all_trades else 0,
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'avg_pnl': round(avg_pnl, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
            'total_pnl': round(total_pnl, 2) if all_trades else 0,
        }
    }
    outpath = OUTPUT_DIR / 'backtest_v11_rolling.json'
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
