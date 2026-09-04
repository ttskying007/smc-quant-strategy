#!/usr/bin/env python3
"""V11 高效滚动回测 v2 — 单次信号检测 + 快速参数扫描

优化: 信号检测只做一次, SL/TP扫描只重算入场退出模拟
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import defaultdict, Counter
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

MAX_STOCKS = 100
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 40
COOLDOWN = 15

# 快速参数扫描 (减少组合数)
SL_RANGE = [0.5, 0.7, 1.0, 1.5, 2.0]
TP_RANGE = [2.0, 3.0, 4.0, 5.0]


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


def precompute_entries(ohlcv, all_signals, params):
    """预计算每个入场点的序列+共振信息
    
    Returns: list of entry candidates or None
    """
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    entries = [None] * n
    
    for i in range(ROLL_START, roll_end):
        sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
        if len(sigs_before) < 3:
            continue
        
        seq_result = analyze_sequence_v11(sigs_before, params=params)
        best_seq = seq_result.get('best_sequence')
        if not best_seq:
            continue
        
        # Skip scout with too few signals
        if 'SCOUT' in best_seq.get('name', '') and len(sigs_before) < 8:
            continue
        
        window = ohlcv[:i + 1]
        tf_sequences = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(
            all_signals=sigs_before,
            tf_sequences=tf_sequences,
            ohlcv=window,
        )
        
        entries[i] = {
            'seq_result': seq_result,
            'resonance': resonance,
            'n_sigs': len(sigs_before),
        }
    
    return entries


def simulate_trades(ohlcv, entries, sl_pct, tp_pct):
    """使用预计算的entry candidates模拟交易"""
    n = len(ohlcv)
    trades = []
    entered_bar = -999
    
    for i in range(ROLL_START, min(n - ROLL_END_OFFSET, n)):
        if i - entered_bar < COOLDOWN:
            continue
        
        entry = entries[i]
        if entry is None:
            continue
        
        seq_result = entry['seq_result']
        resonance = entry['resonance']
        params = {'sl_pct': sl_pct, 'tp_pct': tp_pct}
        tf_sequences = {'daily': seq_result}
        
        decision = make_entry_decision_v11(
            resonance, seq_result, params, tf_sequences=tf_sequences
        )
        
        if decision['action'] != 'enter':
            continue
        
        entry_price = decision.get('entry_price')
        direction = decision.get('direction', 'bull')
        sl_price = decision.get('sl')
        tp_price = decision.get('tp')
        
        if not entry_price or not sl_price or not tp_price:
            continue
        
        # Simulate exit
        if direction == 'bull':
            sl_check = lambda bar: bar['l'] <= sl_price
            tp_check = lambda bar: bar['h'] >= tp_price
        else:
            sl_check = lambda bar: bar['h'] >= sl_price
            tp_check = lambda bar: bar['l'] <= tp_price
        
        exit_idx = -1
        exit_price = None
        won = False
        
        for j in range(i + 1, min(i + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if tp_check(bar):
                exit_idx = j
                exit_price = tp_price
                won = True
                break
            if sl_check(bar):
                exit_idx = j
                exit_price = sl_price
                won = False
                break
        
        if exit_idx == -1:
            exit_idx = min(i + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            if direction == 'bull':
                won = exit_price > ohlcv[i]['c']
            else:
                won = exit_price < ohlcv[i]['c']
        
        # P&L
        if direction == 'bull':
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100
        
        actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl_price + 0.001) if direction == 'bull' else abs(exit_price - entry_price) / abs(sl_price - entry_price + 0.001)
        
        best_seq = seq_result.get('best_sequence', {})
        trades.append({
            'entry_idx': i,
            'exit_idx': exit_idx,
            'direction': direction,
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'sl': round(sl_price, 2),
            'tp': round(tp_price, 2),
            'pnl_pct': round(pnl_pct, 2),
            'won': won,
            'rr': round(actual_rr, 2),
            'seq_name': best_seq.get('name', 'Scout'),
            'resonance_grade': resonance.grade(),
            'confidence': decision['confidence'],
            'hold_bars': exit_idx - i,
        })
        
        entered_bar = i
    
    return trades


def backtest_stock(ohlcv, symbol):
    """Run full backtest with param scan on one stock"""
    t0 = time.time()
    
    # Phase detection
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    
    # One-shot signal detection (ONCE per stock)
    sig_result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_signals = sig_result['all']
    
    if not all_signals or len(all_signals) < 5:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}
    
    # Pre-compute entry candidates (ONCE per stock)
    entries = precompute_entries(ohlcv, all_signals, base_params)
    active_entries = sum(1 for e in entries if e is not None)
    
    if active_entries == 0:
        return {'trades': [], 'n_signals': len(all_signals), 'phase': phase, 'entries': 0}
    
    # Param scan: simulate trades for each SL/TP combo
    best = {'sl_pct': 1.0, 'tp_pct': 3.0, 'n_trades': 0, 'win_rate': 0, 'score': 0}
    
    for sl_pct in SL_RANGE:
        for tp_pct in TP_RANGE:
            trades = simulate_trades(ohlcv, entries, sl_pct, tp_pct)
            if len(trades) < 3:
                continue
            
            wins = sum(1 for t in trades if t['won'])
            losses = len(trades) - wins
            wr = wins / len(trades) * 100
            
            win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
            loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
            pf = win_pnl / loss_pnl if loss_pnl > 0 else 0
            avg_rr = sum(t['rr'] for t in trades) / len(trades)
            
            # Score: WR^2 * RR * min(PF,2) * trade_density
            score = (wr / 100) ** 2 * avg_rr * min(2.0, pf) * min(1.5, len(trades) / 10)
            
            if score > best.get('score', 0):
                best = {
                    'sl_pct': sl_pct, 'tp_pct': tp_pct,
                    'n_trades': len(trades), 'wins': wins, 'losses': losses,
                    'win_rate': round(wr, 1),
                    'avg_rr': round(avg_rr, 2),
                    'profit_factor': round(pf, 2) if pf != float('inf') else 99.9,
                    'avg_pnl': round(sum(t['pnl_pct'] for t in trades) / len(trades), 2),
                    'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
                    'score': round(score, 2),
                }
    
    # Run best params for full trade data
    if best['n_trades'] > 0:
        all_trades = simulate_trades(ohlcv, entries, best['sl_pct'], best['tp_pct'])
        elapsed = time.time() - t0
        return {
            'trades': all_trades,
            'best_params': {k: best[k] for k in ['sl_pct','tp_pct']},
            'perf': best,
            'n_signals': len(all_signals),
            'n_entries': active_entries,
            'phase': phase,
            'elapsed': round(elapsed, 1),
        }
    
    return {'trades': [], 'n_signals': len(all_signals), 'phase': phase, 'n_entries': active_entries}


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V11 滚动回测 v2 — {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"信号检测×1 + 参数扫描快速模拟 x{len(SL_RANGE)*len(TP_RANGE)}")
    print(f"{'='*80}")
    
    all_trades = []
    stock_results = []
    
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SKIP (no data)")
            continue
        
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', [])
        all_trades.extend(trades)
        
        if trades and 'perf' in result:
            p = result['perf']
            stock_results.append({
                'symbol': sym,
                **result['best_params'],
                **{k: p[k] for k in ['n_trades','wins','losses','win_rate','avg_rr',
                                      'profit_factor','avg_pnl','total_pnl','score']},
                'n_signals': result['n_signals'],
                'n_entries': result['n_entries'],
                'phase': result['phase'],
                'elapsed': result.get('elapsed', 0),
            })
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SL={p['sl_pct']:.1f}% TP={p['tp_pct']:.1f}% "
                  f"trades={p['n_trades']:2d} WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x "
                  f"PF={p['profit_factor']:.1f} P&L={p['avg_pnl']:+.2f}% {result.get('elapsed',0):.1f}s")
        else:
            n_sig = result.get('n_signals',0)
            n_ent = result.get('n_entries',0)
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} NO-TRADE sigs={n_sig} entries={n_ent}")
    
    total_time = time.time() - t_start
    
    # === SUMMARY ===
    print(f"\n{'='*80}")
    print(f"SUMMARY — {len(stock_results)} tradable out of {MAX_STOCKS}, {total_time:.1f}s")
    print(f"{'='*80}")
    
    n_traded = len(stock_results)
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
        
        print(f"\n  === AGGREGATE ({total} trades) ===")
        print(f"    Win Rate:     {wr:.1f}%")
        print(f"    W/L:          {wins}/{losses}")
        print(f"    Avg RR:       {avg_rr:.2f}x")
        print(f"    Avg P&L:      {avg_pnl:+.2f}%")
        print(f"    Total P&L:    {total_pnl:+.2f}%")
        print(f"    Profit Factor:{pf:.2f}")
        
        wr_60 = sum(1 for s in stock_results if s['win_rate'] >= 60)
        wr_70 = sum(1 for s in stock_results if s['win_rate'] >= 70)
        pf_2 = sum(1 for s in stock_results if s['profit_factor'] >= 2.0)
        print(f"\n  === QUALITY ({n_traded} stocks) ===")
        print(f"    WR>=60%: {wr_60} stocks")
        print(f"    WR>=70%: {wr_70} stocks")
        print(f"    PF>=2:   {pf_2} stocks")
        
        sorted_stocks = sorted(stock_results, key=lambda s: s['score'], reverse=True)
        print(f"\n  TOP 5:")
        for s in sorted_stocks[:5]:
            print(f"    {s['symbol']:12s} SL={s['sl_pct']:.1f}% TP={s['tp_pct']:.1f}% "
                  f"WR={s['win_rate']:.0f}% RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} "
                  f"trades={s['n_trades']} score={s['score']:.1f}")
        
        sl_cnt = Counter(s['sl_pct'] for s in stock_results)
        tp_cnt = Counter(s['tp_pct'] for s in stock_results)
        seq_cnt = Counter(t.get('seq_name','?') for t in all_trades)
        print(f"\n  SL dist: {dict(sl_cnt.most_common())}")
        print(f"  TP dist: {dict(tp_cnt.most_common())}")
        print(f"  Seq dist: {dict(seq_cnt.most_common(8))}")
    else:
        print("  No trades!")
    
    # Save
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {'max_stocks': MAX_STOCKS, 'sl_range': SL_RANGE, 'tp_range': TP_RANGE},
        'summary': {
            'total_stocks_analyzed': MAX_STOCKS,
            'tradable': n_traded,
            'total_trades': len(all_trades),
            'wins': sum(1 for t in all_trades if t['won']) if all_trades else 0,
            'losses': sum(1 for t in all_trades if not t['won']) if all_trades else 0,
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'avg_pnl': round(avg_pnl, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
        },
        'stocks': stock_results,
        'all_trades': all_trades,
    }
    outpath = OUTPUT_DIR / 'backtest_v11_v2.json'
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
