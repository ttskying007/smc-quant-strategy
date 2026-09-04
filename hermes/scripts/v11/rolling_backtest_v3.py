#!/usr/bin/env python3
"""V11 滚动回测 v3 — 加入趋势过滤提升Scout胜率

增强:
1. Scout入场需共振>=0.65 (更严格)
2. Scout入场需检查短期趋势方向一致性
3. Silver/Bronze保留下调门槛
4. 全量200只股票测试
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

MAX_STOCKS = 200
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 40
COOLDOWN = 15
SL_RANGE = [0.5, 0.7, 1.0, 1.5]
TP_RANGE = [2.0, 3.0, 4.0, 5.0]
SCOUT_MIN_RESONANCE = 0.65  # Scout需更高共振


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
    """检查短期趋势方向 — 用于Scout过滤"""
    if idx < lookback:
        return 'neutral', 0.0
    segment = ohlcv[idx-lookback:idx+1]
    start = segment[0]['c']
    end = segment[-1]['c']
    change = (end - start) / start * 100
    
    # EMA-like smoothing
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    current = ohlcv[idx]['c']
    ema_dist = (current - ema) / ema * 100
    
    if change > 1.5 and ema_dist > 0:
        return 'up', change
    elif change < -1.5 and ema_dist < 0:
        return 'down', abs(change)
    else:
        return 'neutral', 0


def analyze_at_point(ohlcv, all_signals, end_idx, params, tf='daily'):
    """分析给定点的入场机会"""
    sigs_before = [s for s in all_signals if s.get('idx', 0) <= end_idx]
    if len(sigs_before) < 3:
        return None
    
    seq_result = analyze_sequence_v11(sigs_before, params=params)
    best_seq = seq_result.get('best_sequence')
    if not best_seq:
        return None
    
    seq_name = best_seq.get('name', '')
    is_scout = 'SCOUT' in seq_name
    
    # Scout: 检查短期趋势
    if is_scout:
        trend_dir, trend_str = short_trend(ohlcv, end_idx)
        seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
        if trend_dir != 'neutral' and trend_dir != ('up' if seq_dir == 'bull' else 'down'):
            # 趋势违背 — 跳过Scout
            return None
        # Scout需更多信号确认
        if len(sigs_before) < 10:
            return None
    
    window = ohlcv[:end_idx + 1]
    tf_sequences = {tf: seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=sigs_before,
        tf_sequences=tf_sequences,
        ohlcv=window,
    )
    
    return {
        'seq_result': seq_result,
        'resonance': resonance,
        'seq_name': seq_name,
        'is_scout': is_scout,
        'n_sigs': len(sigs_before),
    }


def simulate_trades(ohlcv, all_signals, params):
    """滚动回测: 检测入场点+模拟持仓"""
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
        
        decision = make_entry_decision_v11(
            resonance, seq_result, params, tf_sequences=tf_sequences
        )
        
        if decision['action'] != 'enter':
            continue
        
        # Scout额外共振检查 (防止低共振Scout入场)
        if is_scout and resonance.total < SCOUT_MIN_RESONANCE:
            continue
        
        entry_price = decision.get('entry_price')
        direction = decision.get('direction', 'bull')
        sl_price = decision.get('sl')
        tp_price = decision.get('tp')
        
        if not entry_price or not sl_price or not tp_price:
            continue
        
        # Exit simulation
        if direction == 'bull':
            sl_cond = lambda bar: bar['l'] <= sl_price
            tp_cond = lambda bar: bar['h'] >= tp_price
        else:
            sl_cond = lambda bar: bar['h'] >= sl_price
            tp_cond = lambda bar: bar['l'] <= tp_price
        
        exit_idx, exit_price, won = -1, None, False
        for j in range(i + 1, min(i + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if tp_cond(bar): exit_idx, exit_price, won = j, tp_price, True; break
            if sl_cond(bar): exit_idx, exit_price, won = j, sl_price, False; break
        
        if exit_idx == -1:
            exit_idx = min(i + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            won = (exit_price > ohlcv[i]['c'] if direction == 'bull'
                   else exit_price < ohlcv[i]['c'])
        
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if direction == 'bull' else ((entry_price - exit_price) / entry_price * 100)
        actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl_price + 0.001) if direction == 'bull' else abs(exit_price - entry_price) / abs(sl_price - entry_price + 0.001)
        
        best_seq = seq_result.get('best_sequence', {})
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
    """单股票回测+参数扫描"""
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    
    if not all_signals or len(all_signals) < 5:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}
    
    best = {'sl_pct': 1.0, 'tp_pct': 3.0, 'n_trades': 0, 'score': 0}
    
    for sl_pct in SL_RANGE:
        for tp_pct in TP_RANGE:
            params = {**base_params, 'sl_pct': sl_pct, 'tp_pct': tp_pct}
            trades = simulate_trades(ohlcv, all_signals, params)
            if len(trades) < 3:
                continue
            
            wins = sum(1 for t in trades if t['won'])
            wr = wins / len(trades) * 100
            win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
            loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
            pf = win_pnl / loss_pnl if loss_pnl > 0 else 0
            avg_rr = sum(t['rr'] for t in trades) / len(trades)
            
            score = (wr / 100) ** 2 * avg_rr * min(2.0, pf) * min(1.5, len(trades) / 10)
            
            if score > best.get('score', 0):
                best = {
                    'sl_pct': sl_pct, 'tp_pct': tp_pct,
                    'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
                    'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
                    'profit_factor': round(pf, 2) if pf != float('inf') else 99.9,
                    'avg_pnl': round(sum(t['pnl_pct'] for t in trades) / len(trades), 2),
                    'total_pnl': round(sum(t['pnl_pct'] for t in trades), 2),
                    'score': round(score, 2),
                }
    
    if best['n_trades'] > 0:
        params = {**base_params, 'sl_pct': best['sl_pct'], 'tp_pct': best['tp_pct']}
        trades = simulate_trades(ohlcv, all_signals, params)
        elapsed = time.time() - t0
        return {
            'trades': trades, 'perf': best,
            'best_params': {'sl_pct': best['sl_pct'], 'tp_pct': best['tp_pct']},
            'n_signals': len(all_signals), 'phase': phase, 'elapsed': round(elapsed, 1),
        }
    
    return {'trades': [], 'n_signals': len(all_signals), 'phase': phase}


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V11 滚动回测 v3 (趋势过滤) — {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SKIP")
            continue
        
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', [])
        all_trades.extend(trades)
        
        if trades and 'perf' in result:
            p = result['perf']
            stock_results.append({
                'symbol': sym, **result['best_params'],
                **{k: p[k] for k in ['n_trades','wins','losses','win_rate','avg_rr',
                                      'profit_factor','avg_pnl','total_pnl','score']},
                'n_signals': result['n_signals'], 'phase': result['phase'],
            })
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SL={p['sl_pct']:.1f}% TP={p['tp_pct']:.1f}% "
                  f"trades={p['n_trades']:2d} WR={p['win_rate']:.0f}% RR={p['avg_rr']:.2f}x "
                  f"PF={p['profit_factor']:.1f} P&L={p['avg_pnl']:+.2f}% {result.get('elapsed',0):.1f}s")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} NO-TRADE sigs={result.get('n_signals',0)}")
        
        if (idx + 1) % 20 == 0:
            time.sleep(0.3)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"SUMMARY — {len(stock_results)} tradable, {total_time:.1f}s")
    print(f"{'='*80}")
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
        avg_rr = sum(t['rr'] for t in all_trades) / n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n
        
        print(f"\n  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
        print(f"  WR>=60%: {sum(1 for s in stock_results if s['win_rate']>=60)} stocks")
        print(f"  WR>=70%: {sum(1 for s in stock_results if s['win_rate']>=70)} stocks")
        
        seq_cnt = Counter(t.get('seq_name','?') for t in all_trades)
        print(f"  Seq dist: {dict(seq_cnt.most_common(10))}")
        
        sl_cnt = Counter(s['sl_pct'] for s in stock_results)
        tp_cnt = Counter(s['tp_pct'] for s in stock_results)
        print(f"  SL dist: {dict(sl_cnt.most_common())}")
        print(f"  TP dist: {dict(tp_cnt.most_common())}")
        
        sorted_s = sorted(stock_results, key=lambda s: s['score'], reverse=True)
        print(f"\n  TOP 5:")
        for s in sorted_s[:5]:
            print(f"    {s['symbol']:12s} SL={s['sl_pct']:.1f}% TP={s['tp_pct']:.1f}% "
                  f"WR={s['win_rate']:.0f}% RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} trades={s['n_trades']}")
    
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {'max_stocks': MAX_STOCKS},
        'summary': {
            'total_stocks': MAX_STOCKS, 'tradable': len(stock_results),
            'total_trades': len(all_trades),
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
        },
        'stocks': stock_results, 'all_trades': all_trades,
    }
    outpath = OUTPUT_DIR / 'backtest_v11_v3.json'
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
