#!/usr/bin/env python3
"""
V11 Real Rolling Backtest — simulates actual trades with SL/TP

Key differences from full-window analysis:
- Walks forward bar by bar
- Tracks open positions (no pyramiding by default)
- Realistic win/loss accounting
"""
import json, math, logging, sys, time
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, field

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/root/.hermes/scripts')

from v11.data_loader import load_cached_ohlcv
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11, quick_analyze_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase, calc_sl_price, calc_tp_price

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v11')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Trade:
    symbol: str
    direction: str
    entry_idx: int
    entry_price: float
    sl: float
    tp: float
    rr_planned: float
    sequence_name: str = ''
    resonance_grade: str = 'D'
    confidence: float = 0.0
    exit_idx: int = -1
    exit_price: float = 0.0
    won: bool = False
    pnl_pct: float = 0.0


def rolling_backtest_one_stock(ohlcv, symbol, params, min_confidence=0.60):
    """Walk forward bar-by-bar, enter on resonance signal, exit on SL/TP hit"""
    n = len(ohlcv)
    if n < 100:
        return []
    
    train_bars = 100  # warmup
    trades = []
    open_positions = {}  # direction -> Trade
    
    for i in range(train_bars, n - 1):
        window = ohlcv[max(0, i - 200):i + 1]
        cur_idx = i
        cur_bar = ohlcv[i]
        
        # === EXIT: Check open positions ===
        for direction, trade in list(open_positions.items()):
            if direction == 'bull':
                if cur_bar['l'] <= trade.sl:
                    # STOP LOSS hit
                    trade.exit_idx = cur_idx
                    trade.exit_price = trade.sl
                    trade.pnl_pct = (trade.sl - trade.entry_price) / trade.entry_price * -100  # always negative
                    trade.won = False
                    del open_positions[direction]
                elif cur_bar['h'] >= trade.tp:
                    # TAKE PROFIT hit
                    trade.exit_idx = cur_idx
                    trade.exit_price = trade.tp
                    trade.pnl_pct = (trade.tp - trade.entry_price) / trade.entry_price * 100
                    trade.won = True
                    del open_positions[direction]
            else:  # bear
                if cur_bar['h'] >= trade.sl:
                    trade.exit_idx = cur_idx
                    trade.exit_price = trade.sl
                    trade.pnl_pct = (trade.entry_price - trade.sl) / trade.entry_price * -100
                    trade.won = False
                    del open_positions[direction]
                elif cur_bar['l'] <= trade.tp:
                    trade.exit_idx = cur_idx
                    trade.exit_price = trade.tp
                    trade.pnl_pct = (trade.entry_price - trade.tp) / trade.entry_price * 100
                    trade.won = True
                    del open_positions[direction]
        
        # === ENTRY: Only if no open position ===
        if len(open_positions) > 0:
            continue
        
        # Analyze window
        sig_result = detect_all_signals_v11(window, params=params, tf="daily")
        if not sig_result['all']:
            continue
        
        seq_result = analyze_sequence_v11(sig_result['all'], params=params)
        best = seq_result.get('best_sequence')
        if not best:
            continue
        
        resonance = evaluate_full_resonance_v11(all_signals=sig_result['all'], ohlcv=window)
        decision = make_entry_decision_v11(resonance, seq_result, params)
        
        if decision['action'] != 'enter' or not decision.get('entry_price'):
            continue
        
        trade = Trade(
            symbol=symbol,
            direction=decision['direction'],
            entry_idx=cur_idx,
            entry_price=decision['entry_price'],
            sl=decision['sl'],
            tp=decision['tp'],
            rr_planned=decision.get('rr', 0),
            sequence_name=best['name'] if best else '',
            resonance_grade=decision['grade'],
            confidence=decision['confidence'],
        )
        open_positions[trade.direction] = trade
        if trade not in trades:
            trades.append(trade)
    
    # Close any remaining positions at market
    for direction, trade in list(open_positions.items()):
        trade.exit_idx = n - 1
        trade.exit_price = ohlcv[-1]['c']
        if trade.direction == 'bull':
            trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            trade.pnl_pct = (trade.entry_price - trade.exit_price) / trade.entry_price * 100
        trade.won = trade.pnl_pct > 0
        del open_positions[direction]
    
    return trades


def compute_stats(trades):
    if not trades:
        return {'n_trades': 0, 'win_rate': 0, 'avg_rr': 0, 'profit_factor': 0, 'max_dd': 0}
    
    wins = [t for t in trades if t.won]
    losses = [t for t in trades if not t.won]
    n = len(trades)
    n_wins = len(wins)
    wr = n_wins / n * 100 if n > 0 else 0
    
    avg_rr = sum(t.rr_planned for t in trades) / n if n > 0 else 0
    total_profit = sum(t.pnl_pct for t in wins) if wins else 0
    total_loss = abs(sum(t.pnl_pct for t in losses)) if losses else 1
    pf = total_profit / total_loss if total_loss > 0 else 0
    
    # Max drawdown
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t.pnl_pct
        if equity > peak:
            peak = equity
        dd = (peak - equity) / max(peak, 1)
        if dd > max_dd:
            max_dd = dd
    
    total_return = equity
    
    return {
        'n_trades': n,
        'n_wins': n_wins,
        'n_losses': n - n_wins,
        'win_rate': round(wr, 1),
        'avg_rr': round(avg_rr, 2),
        'profit_factor': round(pf, 2),
        'total_return_pct': round(total_return, 1),
        'max_drawdown_pct': round(max_dd * 100, 1),
    }


def main():
    # Get cached symbols
    symbols = sorted([
        f.stem.replace('_daily_300', '').replace('_', '.')
        for f in CACHE_DIR.glob('*_daily_300.json')
    ])
    
    print(f"V11 ROLLING BACKTEST — {len(symbols)} stocks available")
    print("=" * 70)
    
    # Run on first 50 stocks (time limit)
    limit = 50
    all_results = {}
    all_trades = []
    
    for idx, sym in enumerate(symbols[:limit]):
        t0 = time.time()
        ohlcv = load_cached_ohlcv(sym, 'daily', 300)
        if not ohlcv or len(ohlcv) < 100:
            continue
        
        phase = detect_market_phase(ohlcv)
        params = calc_stock_params(ohlcv, sym, phase=phase, tf="daily")
        
        trades = rolling_backtest_one_stock(ohlcv, sym, params)
        stats = compute_stats(trades)
        
        elapsed = time.time() - t0
        all_trades.extend(trades)
        
        if trades:
            print(f"  [{idx+1:3d}/{limit}] {sym:12s} | "
                  f"N={stats['n_trades']:2d} WR={stats['win_rate']:5.1f}% "
                  f"RR={stats['avg_rr']:.2f}x PF={stats['profit_factor']:.2f} "
                  f"Ret={stats['total_return_pct']:+.0f}% DD={stats['max_drawdown_pct']:.1f}% | "
                  f"{elapsed:.1f}s")
        else:
            print(f"  [{idx+1:3d}/{limit}] {sym:12s} | NO TRADES | {elapsed:.1f}s")
        
        all_results[sym] = {'trades': len(trades), 'stats': stats}
    
    # Overall stats
    overall = compute_stats(all_trades)
    print(f"\n{'='*70}")
    print(f"OVERALL — {len(all_results)} stocks analyzed, {overall['n_trades']} total trades")
    print(f"{'='*70}")
    print(f"  Win Rate:  {overall['win_rate']:.1f}%  ({overall['n_wins']}W / {overall['n_losses']}L)")
    print(f"  Avg RR:    {overall['avg_rr']:.2f}x")
    print(f"  PF:        {overall['profit_factor']:.2f}")
    print(f"  Return:    {overall['total_return_pct']:+.1f}%")
    print(f"  Max DD:    {overall['max_drawdown_pct']:.1f}%")
    
    if all_trades:
        # Grade distribution
        seq_counts = Counter(t.sequence_name for t in all_trades)
        print(f"\n  Sequence distribution:")
        for name, cnt in seq_counts.most_common():
            wr_this = sum(1 for t in all_trades if t.sequence_name == name and t.won) / max(sum(1 for t in all_trades if t.sequence_name == name), 1) * 100
            print(f"    {name:20s}: {cnt:3d} trades (WR={wr_this:.0f}%)")
    
    # Save
    Path('/root/.hermes/smc_opt_v11/baseline_rolling.json').write_text(
        json.dumps({'overall': overall, 'per_stock': all_results}, 
                   ensure_ascii=False, indent=2, default=str)
    )
    print(f"\nResults saved to smc_opt_v11/baseline_rolling.json")


if __name__ == '__main__':
    main()
