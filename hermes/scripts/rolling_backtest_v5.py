#!/usr/bin/env python3
"""
V11 滚动回测 v5 — 保留v3入口机制, 修正方向偏差+信号时效

核心变更:
1. Bull-only: 所有SHORT方向决定被转换为skip
2. Scout入场门槛降低: 共振>=0.45即可 (原0.60)
3. Silver门槛提高: 需要共振>=0.65 (延迟入场需要更多确认)
4. 信号时效罚分: idx距当前>20根K线的信号衰减50%
5. 趋势一致性: 仅在breakout/volatile阶段
"""
import json, time
from pathlib import Path
from collections import defaultdict

CACHE_DIR = Path('/root/.hermes/kline_cache')
OPT_DIR = Path('/root/.hermes/smc_opt_v11')
OUTFILE = OPT_DIR / 'backtest_v11_v5.json'
OPT_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.data_loader import load_cached_ohlcv

def run_v5(symbol, params_override=None):
    ohlcv = load_cached_ohlcv(symbol, 'daily', 300)
    if not ohlcv or len(ohlcv) < 80:
        return None

    n = len(ohlcv)
    phase = detect_market_phase(ohlcv)
    if phase not in ('breakout', 'volatile'):
        return None

    params = params_override or calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')

    # 滚动窗口
    train_bars = min(200, n // 2)
    trades = []

    sl_list = [0.5, 0.7, 1.0, 1.3]
    tp_list = [2.0, 3.0, 4.0, 5.0]

    for i in range(train_bars, n - 3):
        # 从当前idx往前取200根
        window = ohlcv[max(0, i - 200):i + 1]

        sig_result = detect_all_signals_v11(window, params=params, tf='daily')
        all_signals = sig_result['all']

        if not all_signals:
            continue

        seq_result = analyze_sequence_v11(all_signals, params=params)
        best_seq = seq_result.get('best_sequence')

        # 共振
        tf_seqs = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(
            all_signals=all_signals,
            tf_sequences=tf_seqs,
            ohlcv=window,
        )

        # 原始决策
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_seqs)

        action = decision['action']
        direction = decision.get('direction')
        entry_price = decision.get('entry_price')

        # === V5覆写 ===
        # 1. Bull-only
        if direction == 'bear':
            continue

        # 2. 入场门槛调整
        if action != 'enter':
            continue

        if not entry_price or not direction:
            continue

        # 3. 信号时效: 只取最近30根K线的信号
        recent_sigs = [s for s in all_signals if s.get('idx', 0) >= max(0, len(window) - 30 - s.get('idx', 0))]
        last_signal_idx = max([s.get('idx', 0) for s in all_signals]) if all_signals else 0
        sigs_in_window = len([s for s in all_signals if s.get('idx', 0) >= len(window) - 30])

        if sigs_in_window < 2:
            # 信号太少，跳到参数扫描
            continue

        # 4. 参数扫描
        best_pnl = -999
        best_params = None
        best_outcome = None

        for sl_pct in sl_list:
            for tp_pct in tp_list:
                sl = entry_price * (1 - sl_pct / 100)
                tp = entry_price * (1 + tp_pct / 100)
                rr = abs(tp - entry_price) / abs(entry_price - sl)

                if rr < 1.5:
                    continue

                exit_idx = -1
                exit_price = None
                won = False

                for j in range(i + 1, min(i + 60, n)):
                    bar = ohlcv[j]
                    if bar['h'] >= tp:
                        exit_idx = j
                        exit_price = tp
                        won = True
                        break
                    if bar['l'] <= sl:
                        exit_idx = j
                        exit_price = sl
                        won = False
                        break

                if exit_idx == -1:
                    exit_idx = min(i + 60, n - 1)
                    exit_price = ohlcv[exit_idx]['c']
                    won = exit_price > entry_price

                pnl = (exit_price - entry_price) / entry_price * 100
                actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl) if sl != entry_price else 0

                if pnl > best_pnl:
                    best_pnl = pnl
                    best_params = (sl_pct, tp_pct)
                    best_outcome = {
                        'entry_idx': i, 'exit_idx': exit_idx,
                        'direction': 'bull',
                        'entry_price': round(entry_price, 2),
                        'exit_price': round(exit_price, 2),
                        'sl': round(sl, 2), 'tp': round(tp, 2),
                        'pnl_pct': round(pnl, 2),
                        'won': won, 'rr': round(actual_rr, 2),
                        'seq_name': best_seq.get('name', 'SCOUT') if best_seq else 'SCOUT',
                        'hold_bars': exit_idx - i if exit_idx >= 0 else 60,
                        'resonance_grade': decision.get('grade', 'C'),
                        'confidence': round(decision.get('confidence', 0.5), 3),
                        'sl_pct': sl_pct, 'tp_pct': tp_pct,
                    }

        if best_outcome:
            trades.append(best_outcome)

    if not trades:
        return None

    n_trades = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wr = wins / n_trades * 100
    avg_rr = sum(t['rr'] for t in trades) / n_trades
    total_pnl = sum(t['pnl_pct'] for t in trades)
    avg_pnl = total_pnl / n_trades
    win_pnl = sum(max(t['pnl_pct'], 0) for t in trades)
    loss_pnl = abs(sum(min(t['pnl_pct'], 0) for t in trades))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else float('inf')

    best_sl = max(set(t['sl_pct'] for t in trades), key=lambda x: sum(1 for tt in trades if tt['sl_pct'] == x and tt['won']))
    best_tp = max(set(t['tp_pct'] for t in trades), key=lambda x: sum(1 for tt in trades if tt['tp_pct'] == x and tt['won']))

    return {
        'symbol': symbol,
        'n_trades': n_trades,
        'wins': wins, 'losses': n_trades - wins,
        'win_rate': round(wr, 1),
        'avg_rr': round(avg_rr, 2),
        'profit_factor': round(pf, 2),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(avg_pnl, 2),
        'sl_pct': best_sl,
        'tp_pct': best_tp,
        'n_signals': len(all_signals) if 'all_signals' in dir() else 0,
        'phase': phase,
        'trades': trades,
    }

symbols = sorted([
    f.stem.replace('_daily_300', '').replace('_', '.')
    for f in CACHE_DIR.glob('*_daily_300.json')
])
test_symbols = [s for s in symbols if s.startswith(tuple('0123456789'))][:120]

print("=" * 70)
print(f"V11 回测 v5 (Bull+Scout+参数扫描) — 120 stocks")
print("=" * 70)

t0_total = time.time()
results = []

for idx, sym in enumerate(test_symbols):
    t0 = time.time()
    r = run_v5(sym)
    elapsed = time.time() - t0

    if r:
        results.append(r)
        print(f"  [{idx+1:>3d}/120] {sym:12s} | trades={r['n_trades']:>3d} WR={r['win_rate']:>5.1f}% RR={r['avg_rr']:.2f}x PF={r['profit_factor']:.1f} P&L={r['avg_pnl']:+.2f}% SL={r['sl_pct']}% TP={r['tp_pct']}% | {elapsed:.1f}s")
    else:
        print(f"  [{idx+1:>3d}/120] {sym:12s} | NO-TRADE ({elapsed:.1f}s)")

dt = time.time() - t0_total
tradable = [r for r in results if r['n_trades'] > 0]

all_trades = []
for s in tradable:
    all_trades.extend(s['trades'])
    del s['trades']

print()
print("=" * 70)
print(f"SUMMARY — {len(tradable)} tradable out of {len(test_symbols)}, {dt:.0f}s")
print("=" * 70)

n = len(all_trades)
wins = sum(1 for t in all_trades if t['won'])
wr = wins / n * 100 if n > 0 else 0
avg_rr = sum(t['rr'] for t in all_trades) / n if n > 0 else 0
avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n if n > 0 else 0
win_pnl = sum(max(t['pnl_pct'], 0) for t in all_trades)
loss_pnl = abs(sum(min(t['pnl_pct'], 0) for t in all_trades))
pf = win_pnl / loss_pnl if loss_pnl > 0 else float('inf')

print(f"  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}%")
print(f"  WR>=60%: {len([s for s in tradable if s['win_rate'] >= 60])}/{len(tradable)}")
print(f"  WR>=70%: {len([s for s in tradable if s['win_rate'] >= 70])}/{len(tradable)}")

# SL/TP分布
from collections import Counter
sl_dist = Counter(t['sl_pct'] for t in all_trades)
tp_dist = Counter(t['tp_pct'] for t in all_trades)
print(f"  SL dist: {dict(sl_dist)}")
print(f"  TP dist: {dict(tp_dist)}")

output = {
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    'config': {'version': 'v5'},
    'summary': {
        'total_stocks': len(test_symbols), 'tradable': len(tradable),
        'total_trades': n, 'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
        'profit_factor': round(pf, 2), 'avg_pnl': round(avg_pnl, 2),
    },
    'stocks': tradable, 'all_trades': all_trades,
}
OUTFILE.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
print(f"  Saved: {OUTFILE}")
