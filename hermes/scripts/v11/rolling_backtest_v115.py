#!/usr/bin/env python3
"""
V11.5 — Scout-only + 周线趋势过滤 + 修复版信号质量
===================================================
基于V11.3(v7引擎) + V11.4(修复) + 周线趋势过滤

核心改进:
1. Scout-only (FVG/OB单信号) — 已验证WR最高
2. 修复first_signal字段bug — 信号质量过滤正常生效
3. 周线趋势过滤 — 周线下跌趋势不做多
4. FVG优先入场 — 序列用FVG不是OB

预期: WR~75%, 覆盖~90只/200
"""
import json, sys, time, math, logging
from pathlib import Path
from collections import Counter
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

MAX_STOCKS = 200
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 40
COOLDOWN = 15
SL_FIXED = 0.5
TP_FIXED = 5.0
SCOUT_MIN_RESONANCE = 0.65


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
    if change > 0.8 and ema_dist > 0:
        return 'up', change
    elif change < -0.8 and ema_dist < 0:
        return 'down', abs(change)
    return 'neutral', 0


def get_entry_signal_info(seq_result):
    """从seq_result中正确提取入场信号信息"""
    entry_sig = seq_result.get('entry_signal', {})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None:
        return fvg_entry.get('idx', 0), fvg_entry.get('type', ''), fvg_entry
    return entry_sig.get('idx', 0), entry_sig.get('type', ''), entry_sig


def analyze_at_point(ohlcv, all_signals, end_idx, params):
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
    
    # === Bull-only ===
    if seq_dir != 'bull':
        return None
    
    # === Scout-only ===
    if not is_scout:
        return None
    
    # === 信号质量检查 (修复版) ===
    sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
    if sig_idx == 0 and not sig_type:
        sig_idx = end_idx
    
    # 成交量确认
    if sig_idx < len(ohlcv) - 1 and sig_idx > 30:
        bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[i].get('v', ohlcv[i].get('vol', 0))
                       for i in range(max(0, sig_idx-30), sig_idx)) / 30
        if bar_vol < avg_vol * 0.8:
            return None
    
    # FVG收阳确认
    sig_type_check = sig.get('type', sig_type)
    if 'FVG' in sig_type_check and sig_idx > 0 and sig_idx < len(ohlcv):
        bar = ohlcv[sig_idx]
        if bar['c'] <= bar['o']:
            return None
    
    # FVG gap size
    if 'FVG' in sig_type_check:
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct < 0.3:
                return None
    
    # 日线趋势检查
    trend_dir, trend_str = short_trend(ohlcv, end_idx)
    if trend_dir != 'neutral' and trend_dir != 'up':
        return None
    if len(sigs_before) < 10:
        return None
    
    # === [V11.5] 周线趋势过滤 ===
    weekly = synthesize_weekly(ohlcv[:end_idx+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down':  # 周线下跌趋势不做多
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
    }


def simulate_trades(ohlcv, all_signals, params):
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN:
            continue
        
        entry_info = analyze_at_point(ohlcv, all_signals, i, params)
        if entry_info is None:
            continue
        
        seq_result = entry_info['seq_result']
        resonance = entry_info['resonance']
        is_scout = entry_info['is_scout']
        tf_sequences = {'daily': seq_result}
        best_seq = entry_info['best_seq']
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action'] != 'enter':
            continue
        if is_scout and resonance.total < SCOUT_MIN_RESONANCE:
            continue
        
        entry_price = decision.get('entry_price')
        direction = 'bull'
        sl_price = decision.get('sl')
        tp_price = decision.get('tp')
        
        if not entry_price or not sl_price or not tp_price:
            continue
        
        sl_cond = lambda bar: bar['l'] <= sl_price
        tp_cond = lambda bar: bar['h'] >= tp_price
        
        exit_idx, exit_price, won = -1, None, False
        for j in range(i + 1, min(i + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if tp_cond(bar): exit_idx, exit_price, won = j, tp_price, True; break
            if sl_cond(bar): exit_idx, exit_price, won = j, sl_price, False; break
        
        if exit_idx == -1:
            exit_idx = min(i + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            won = exit_price > ohlcv[i]['c']
        
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl_price + 0.001)
        
        trades.append({
            'entry_idx': i, 'exit_idx': exit_idx, 'direction': direction,
            'entry_price': round(entry_price, 2), 'exit_price': round(exit_price, 2),
            'sl': round(sl_price, 2), 'tp': round(tp_price, 2),
            'pnl_pct': round(pnl_pct, 2), 'won': won, 'rr': round(actual_rr, 2),
            'seq_name': best_seq.get('name', 'Scout'),
            'resonance_grade': resonance.grade(),
            'confidence': decision['confidence'],
            'hold_bars': exit_idx - i,
        })
        entered_bar = i
    
    return trades


def backtest_stock(ohlcv, symbol):
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    
    if not all_signals or len(all_signals) < 5:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}
    
    params = {**base_params, 'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED}
    trades = simulate_trades(ohlcv, all_signals, params)
    
    if len(trades) < 2:
        return {'trades': [], 'n_signals': len(all_signals), 'phase': phase}
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
    loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2), 'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
        },
        'n_signals': len(all_signals), 'phase': phase,
        'elapsed': round(time.time() - t0, 1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V11.5 回测 -- Scout-only + 周线趋势过滤 + 信号质量修复")
    print(f"  {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"  SL={SL_FIXED}% TP={TP_FIXED}% Scout共振>={SCOUT_MIN_RESONANCE}")
    print(f"  周线下跌趋势不做多 | 信号质量过滤(成交量/FVG收阳/gap)")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            continue
        
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', [])
        perf = result.get('perf', {})
        
        if trades:
            all_trades.extend(trades)
            stock_results.append({
                'symbol': sym, 'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED,
                **perf, 'n_signals': result.get('n_signals', 0),
                'phase': result.get('phase', '?'),
            })
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"trades={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% "
                  f"RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} "
                  f"P&L={perf['avg_pnl']:+.2f}% {result.get('phase','?')} | "
                  f"{result.get('elapsed',0):.1f}s")
        else:
            sigs = result.get('n_signals', 0)
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} "
                  f"NO-TRADE sigs={sigs} phase={result.get('phase','?')}")
        
        if (idx + 1) % 30 == 0:
            time.sleep(0.3)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"V11.5 SUMMARY — {len(stock_results)} tradable out of {MAX_STOCKS}")
    print(f"  Time: {total_time:.1f}s")
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
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | "
              f"PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
        print(f"  WR>=60%: {sum(1 for s in stock_results if s['win_rate']>=60)} stocks")
        print(f"  WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} stocks")
        print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)} stocks")
        
        seq_cnt = Counter(t.get('seq_name','?') for t in all_trades)
        print(f"  Seq dist: {dict(seq_cnt.most_common(5))}")
        
        hold_avg = sum(t['hold_bars'] for t in all_trades) / n
        print(f"  Avg hold bars: {hold_avg:.1f}")
        
        print(f"\n  TOP 10 by WR:")
        for s in sorted(stock_results, key=lambda x: x['win_rate'], reverse=True)[:10]:
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% RR={s['avg_rr']:.1f}x "
                  f"PF={s['profit_factor']:.1f} trades={s['n_trades']} phase={s['phase']}")
    
    outpath = OUTPUT_DIR / 'backtest_v11_v115.json'
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {'version': 'V11.5', 'max_stocks': MAX_STOCKS, 'sl': SL_FIXED, 'tp': TP_FIXED},
        'summary': {
            'total_stocks': MAX_STOCKS, 'tradable': len(stock_results),
            'total_trades': len(all_trades),
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
            'avg_pnl': round(avg_pnl, 2) if all_trades else 0,
        },
        'stocks': stock_results, 'all_trades': all_trades,
    }
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
