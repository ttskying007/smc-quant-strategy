#!/usr/bin/env python3
"""V11 高效批量回测引擎 — 全量4800股票P&L追踪

Key differences from rolling backtest:
1. One-shot signal detection (fast)
2. Forward simulation with SL/TP tracking
3. Per-stock P&L, WR, RR, PF calculation
4. API throttling built in
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/root/.hermes/scripts')

from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v11')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_STOCKS = 50  # Start with 50, increase after validation


def load_ohlcv(symbol, period='daily', count=300):
    """Load cached OHLCV with format compatibility"""
    fname = f"{symbol.replace('.', '_')}_{period}_{count}.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < 60:
        return None
    # Normalize t→date
    for bar in data:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    return data


def simulate_trade(ohlcv, entry_idx, direction, sl_price, tp_price, max_hold=60):
    """Simulate a trade from entry_idx+1 until SL/TP hit or max_hold bars"""
    n = len(ohlcv)
    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]
        if direction == 'bull':
            if bar['h'] >= tp_price:
                return j, tp_price, True
            if bar['l'] <= sl_price:
                return j, sl_price, False
        else:
            if bar['l'] <= tp_price:
                return j, tp_price, True
            if bar['h'] >= sl_price:
                return j, sl_price, False
    # Expired: close at last price
    exit_idx = min(entry_idx + max_hold, n - 1)
    exit_price = ohlcv[exit_idx]['c']
    if direction == 'bull':
        won = exit_price > ohlcv[entry_idx]['c']  # use close of entry bar as reference
    else:
        won = exit_price < ohlcv[entry_idx]['c']
    return exit_idx, exit_price, won


def calc_pnl(entry_price, exit_price, direction):
    """Calculate P&L percentage"""
    if direction == 'bull':
        return (exit_price - entry_price) / entry_price * 100
    else:
        return (entry_price - exit_price) / entry_price * 100


def calc_rr(entry_price, sl_price, tp_price, direction):
    """Calculate expected risk/reward ratio"""
    if direction == 'bull':
        risk = entry_price - sl_price
        reward = tp_price - entry_price
    else:
        risk = sl_price - entry_price
        reward = entry_price - tp_price
    if risk <= 0:
        return 0
    return reward / risk


def backtest_stock(ohlcv, symbol):
    """Run V11 backtest on one stock — single-shot + forward simulation"""
    n = len(ohlcv)
    
    # 1. Adaptive params
    phase = detect_market_phase(ohlcv)
    params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    
    # 2. One-shot signal detection (full dataset)
    sig_result = detect_all_signals_v11(ohlcv, params=params, tf='daily')
    all_signals = sig_result['all']
    
    if not all_signals:
        return {'trades': [], 'symbol': symbol, 'phase': phase, 'params': params, 'signals': 0}
    
    # 3. Sequence analysis (full dataset)
    seq_result = analyze_sequence_v11(all_signals, params=params)
    best_seq = seq_result.get('best_sequence')
    
    # 4. Resonance & entry decision
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=all_signals,
        tf_sequences=tf_sequences,
        ohlcv=ohlcv,
    )
    decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
    
    # 5. Simulate trade if enter
    trades = []
    if decision['action'] == 'enter' and decision.get('entry_price'):
        entry_price = decision['entry_price']
        direction = decision.get('direction', 'bull')
        sl_price = decision.get('sl')
        tp_price = decision.get('tp')
        
        if sl_price and tp_price and entry_price:
            # Find the right entry_idx from signals
            entry_sig = seq_result.get('entry_signal', {})
            entry_idx = entry_sig.get('idx', len(ohlcv) - 1) if isinstance(entry_sig, dict) else len(ohlcv) - 1
            
            # Make sure entry_idx is reasonable
            if entry_idx < 10 or entry_idx >= n - 3:
                entry_idx = n - 5
            
            exit_idx, exit_price, won = simulate_trade(ohlcv, entry_idx, direction, sl_price, tp_price)
            pnl_pct = calc_pnl(entry_price, exit_price, direction)
            actual_rr = calc_rr(entry_price, sl_price, tp_price, direction)
            
            trades.append({
                'symbol': symbol,
                'direction': direction,
                'seq_name': best_seq['name'] if best_seq else 'Scout',
                'entry_idx': entry_idx,
                'entry_price': round(entry_price, 2),
                'exit_idx': exit_idx,
                'exit_price': round(exit_price, 2),
                'sl': round(sl_price, 2),
                'tp': round(tp_price, 2),
                'pnl_pct': round(pnl_pct, 2),
                'won': won,
                'rr': round(actual_rr, 2),
                'resonance_grade': decision['grade'],
                'confidence': decision['confidence'],
                'phase': phase,
            })
    
    return {
        'trades': trades,
        'symbol': symbol,
        'phase': phase,
        'params': params,
        'signals': len(all_signals),
        'sequence': best_seq['name'] if best_seq else None,
        'resonance_grade': resonance.grade(),
        'resonance_total': resonance.total,
        'decision_action': decision['action'],
        'decision_grade': decision['grade'],
    }


def main():
    # Get cached stock list
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V11 批量回测 — {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"{'='*80}")
    
    results = []
    all_trades = []
    
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        t0 = time.time()
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SKIP (no data)")
            continue
        
        result = backtest_stock(ohlcv, sym)
        n_trades = len(result['trades'])
        all_trades.extend(result['trades'])
        
        elapsed = time.time() - t0
        seq_s = result['sequence'] or 'NONE'
        dec_s = result['decision_action']
        res_s = f"{result['resonance_grade']}({result['resonance_total']:.3f})"
        
        if n_trades > 0:
            t = result['trades'][0]
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} seq={seq_s:16s} res={res_s:10s} dec={dec_s:6s} "
                  f"pnl={t['pnl_pct']:+.2f}% won={'W' if t['won'] else 'L'} rr={t['rr']:.2f}x {elapsed:.1f}s")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} seq={seq_s:16s} res={res_s:10s} dec={dec_s:6s} "
                  f"no-trade {elapsed:.1f}s")
        
        results.append(result)
        
        # Rate limiting: pause every 10 stocks
        if (idx + 1) % 10 == 0:
            time.sleep(0.5)
    
    total_time = time.time() - t_start
    
    # === SUMMARY ===
    print(f"\n{'='*80}")
    print(f"SUMMARY — {len(results)} stocks, {total_time:.1f}s")
    print(f"{'='*80}")
    
    trades_df = all_trades
    n_trades_total = len(trades_df)
    n_wins = sum(1 for t in trades_df if t['won'])
    n_losses = n_trades_total - n_wins
    
    if n_trades_total > 0:
        win_rate = n_wins / n_trades_total * 100
        avg_pnl = sum(t['pnl_pct'] for t in trades_df) / n_trades_total
        avg_rr = sum(t['rr'] for t in trades_df) / n_trades_total
        total_pnl = sum(t['pnl_pct'] for t in trades_df)
        
        win_pnl = sum(t['pnl_pct'] for t in trades_df if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in trades_df if not t['won']))
        profit_factor = win_pnl / loss_pnl if loss_pnl > 0 else float('inf')
        
        print(f"  Total Trades: {n_trades_total}")
        print(f"  Wins: {n_wins}  Losses: {n_losses}")
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  Avg P&L: {avg_pnl:+.2f}%")
        print(f"  Avg RR: {avg_rr:.2f}x")
        print(f"  Total P&L: {total_pnl:+.2f}%")
        print(f"  Profit Factor: {profit_factor:.2f}")
    else:
        print(f"  No trades generated")
    
    # Decision distribution
    from collections import Counter
    dec_counts = Counter(r['decision_action'] for r in results)
    print(f"\n  Decision Distribution:")
    for k, v in dec_counts.most_common():
        print(f"    {k:10s}: {v:3d} ({v/len(results)*100:.0f}%)")
    
    # Sequence distribution
    seq_counts = Counter(r['sequence'] or 'NONE' for r in results)
    print(f"\n  Sequence Distribution:")
    for k, v in seq_counts.most_common()[:10]:
        print(f"    {k:20s}: {v:3d}")
    
    # Save
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {'max_stocks': MAX_STOCKS, 'version': 'v11.1.1'},
        'summary': {
            'total_stocks': len(results),
            'total_trades': n_trades_total,
            'wins': n_wins,
            'losses': n_losses,
            'win_rate': round(win_rate, 1) if n_trades_total > 0 else 0,
            'avg_rr': round(avg_rr, 2) if n_trades_total > 0 else 0,
            'profit_factor': round(profit_factor, 2) if n_trades_total > 0 else 0,
        },
        'trades': trades_df,
        'details': results,
    }
    outpath = OUTPUT_DIR / 'backtest_v11_results.json'
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
