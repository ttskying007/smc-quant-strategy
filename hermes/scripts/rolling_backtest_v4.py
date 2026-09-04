#!/usr/bin/env python3
"""
V11 滚动回测 v4 — Bull-only + Scout质量过滤 + 趋势验证

核心变更 (vs v3):
1. Bull-only: 去掉所有SHORT方向 (bear WR=40%不可靠)
2. Scout强化: 仅信号strength>=4.0 + confidence>=0.65才入场
3. 趋势过滤: 只在breakout/volatile阶段入场
4. 信号新鲜度: 只考虑最近60根K线的信号
5. SILVER/Bronze保留但降权: 不强制序列等级
"""
import json, time
from pathlib import Path
from collections import defaultdict

CACHE_DIR = Path('/root/.hermes/kline_cache')
OPT_DIR = Path('/root/.hermes/smc_opt_v11')
OUTFILE = OPT_DIR / 'backtest_v11_v4.json'
OPT_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.data_loader import load_cached_ohlcv

def run_backtest_v4(symbol='', params_override=None):
    ohlcv = load_cached_ohlcv(symbol, 'daily', 300)
    if not ohlcv or len(ohlcv) < 60:
        return None

    n = len(ohlcv)
    phase = detect_market_phase(ohlcv)
    params = params_override or calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')

    # 趋势过滤: 只在breakout/volatile阶段
    if phase not in ('breakout', 'volatile'):
        return None

    # 只考虑后半段数据 (信号新鲜度)
    train_start = max(0, n - 120)
    ohlcv_latest = ohlcv[train_start:]

    # 更新参数 (基于后半段)
    phase2 = detect_market_phase(ohlcv_latest)
    params2 = params_override or calc_stock_params(ohlcv_latest, symbol, phase=phase2, tf='daily')

    # 全量信号检测
    sig_result = detect_all_signals_v11(ohlcv_latest, params=params2, tf='daily')
    all_signals = sig_result['all']

    if not all_signals:
        return None

    n_latest = len(ohlcv_latest)

    # 序列
    seq_result = analyze_sequence_v11(all_signals, params=params2)
    best_seq = seq_result.get('best_sequence')

    # 共振
    tf_seqs = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=all_signals,
        tf_sequences=tf_seqs,
        ohlcv=ohlcv_latest,
    )

    # 入场决策
    decision = make_entry_decision_v11(resonance, seq_result, params2, tf_sequences=tf_seqs)

    # === 自定义入场逻辑 ===
    sl_pct = params2.get('sl_pct', 0.5)
    tp_pct = params2.get('tp_pct', 3.0)
    score_min = params2.get('score_min', 2.5)

    # 只在最近30根K线中找信号
    min_idx = max(0, n_latest - 30 - 5)

    trades = []
    for i in range(min_idx, n_latest - 3):
        window = ohlcv_latest[max(0, i-200):i+1]
        if len(window) < 30:
            continue

        sigs_before = [s for s in all_signals if s.get('idx', 0) < i]

        # 筛选高质量信号
        strong_sigs = [s for s in sigs_before if
                      s.get('strength', 0) >= 4.0 and
                      s.get('confidence', 0) >= 0.65 and
                      s.get('direction') == 'bull']

        if not strong_sigs:
            continue

        # 取最近最强的信号
        best_sig = max(strong_sigs, key=lambda s: s.get('strength', 0))

        if best_sig.get('idx', 0) > i - 20:  # 信号在20根K线内
            direction = 'bull'
            entry_price = ohlcv_latest[i]['c']

            # 自适应SL/TP
            sl = entry_price * (1 - sl_pct / 100)
            tp = entry_price * (1 + tp_pct / 100)

            rr = abs(tp - entry_price) / abs(entry_price - sl) if sl != entry_price else 0
            if rr < 1.5:
                # 扩大TP
                tp = entry_price * (1 + tp_pct * 2 / 100)
                rr = abs(tp - entry_price) / abs(entry_price - sl)

            # 模拟持仓
            exit_idx = -1
            exit_price = None
            won = False

            for j in range(i + 1, min(i + 60, n_latest)):
                bar = ohlcv_latest[j]
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
                exit_idx = min(i + 60, n_latest - 1)
                exit_price = ohlcv_latest[exit_idx]['c']
                won = exit_price > entry_price

            pnl = (exit_price - entry_price) / entry_price * 100
            actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl) if sl != entry_price else 0

            trades.append({
                'entry_idx': i,
                'exit_idx': exit_idx,
                'direction': direction,
                'entry_price': round(entry_price, 2),
                'exit_price': round(exit_price, 2),
                'sl': round(sl, 2),
                'tp': round(tp, 2),
                'pnl_pct': round(pnl, 2),
                'won': won,
                'rr': round(actual_rr, 2),
                'seq_name': best_sig.get('type', 'FVG_Bull'),
                'signal_strength': best_sig.get('strength', 0),
                'hold_bars': exit_idx - i if exit_idx >= 0 else 60,
                'idx_diff': i - best_sig.get('idx', i),
            })

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

    return {
        'symbol': symbol,
        'n_trades': n_trades,
        'wins': wins,
        'losses': n_trades - wins,
        'win_rate': round(wr, 1),
        'avg_rr': round(avg_rr, 2),
        'profit_factor': round(pf, 2),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(avg_pnl, 2),
        'sl_pct': sl_pct,
        'tp_pct': tp_pct,
        'n_signals': len(all_signals),
        'phase': phase2,
        'trades': trades,
    }


# Main
all_stocks = []
symbols = sorted([
    f.stem.replace('_daily_300', '').replace('_', '.')
    for f in CACHE_DIR.glob('*_daily_300.json')
])

# Take first 120 stocks
test_symbols = [s for s in symbols if s.startswith(tuple('0123456789'))][:120]

print("=" * 70)
print(f"V11 滚动回测 v4 (Bull-only+Scout优化) — {len(test_symbols)} stocks")
print("=" * 70)

t0_total = time.time()

for idx, sym in enumerate(test_symbols):
    t0 = time.time()
    result = run_backtest_v4(symbol=sym)

    elapsed = time.time() - t0
    if result:
        all_stocks.append(result)
        sigs = result['n_signals']
        line = f"  [{idx+1:>3d}/{len(test_symbols)}] {sym:12s} | trades={result['n_trades']:>3d} WR={result['win_rate']:>5.1f}% RR={result['avg_rr']:.2f}x PF={result['profit_factor']:.1f} P&L={result['avg_pnl']:+.2f}% | {elapsed:.1f}s"
        print(line)
    else:
        print(f"  [{idx+1:>3d}/{len(test_symbols)}] {sym:12s} | NO-TRADE ({elapsed:.1f}s)")

t_total = time.time() - t_total
tradable = [s for s in all_stocks if s['n_trades'] > 0]

print()
print("=" * 70)
print(f"SUMMARY — {len(tradable)} tradable out of {len(test_symbols)}, {t_total:.1f}s")
print("=" * 70)

all_trades = []
for s in tradable:
    all_trades.extend(s['trades'])
    del s['trades']  # keep compact

n = len(all_trades)
wins = sum(1 for t in all_trades if t['won'])
wr = wins / n * 100 if n > 0 else 0
avg_rr = sum(t['rr'] for t in all_trades) / n if n > 0 else 0
avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n if n > 0 else 0
win_pnl = sum(max(t['pnl_pct'], 0) for t in all_trades)
loss_pnl = abs(sum(min(t['pnl_pct'], 0) for t in all_trades))
pf = win_pnl / loss_pnl if loss_pnl > 0 else float('inf')
total_pnl = sum(t['pnl_pct'] for t in all_trades)

print(f"  Trades: {n} | WR: {wr:.1f}% | Avg RR: {avg_rr:.2f}x | PF: {pf:.2f} | Avg P&L: {avg_pnl:+.2f}% | Total P&L: {total_pnl:+.2f}%")

high_wr = [s for s in tradable if s['win_rate'] >= 60]
print(f"  WR>=60%: {len(high_wr)}/{len(tradable)} stocks")
print(f"  WR>=70%: {len([s for s in tradable if s['win_rate'] >= 70])}/{len(tradable)} stocks")

# Save
output = {
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    'config': {'version': 'v4', 'bull_only': True, 'strength_min': 4.0, 'conf_min': 0.65},
    'summary': {
        'total_stocks': len(test_symbols),
        'tradable': len(tradable),
        'total_trades': n,
        'win_rate': round(wr, 1),
        'avg_rr': round(avg_rr, 2),
        'profit_factor': round(pf, 2),
        'avg_pnl': round(avg_pnl, 2),
        'total_pnl': round(total_pnl, 2),
    },
    'stocks': tradable,
    'all_trades': all_trades,
}
OUTFILE.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
print(f"  Saved: {OUTFILE}")
