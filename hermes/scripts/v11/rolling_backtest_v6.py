#!/usr/bin/env python3
"""
V11 回测 v6 — 信号级入场 + 多层质量过滤
==============================

核心改动 (vs v5/v3 rolling per-bar):
  1. 不在每根bar滚动检测, 而在每个信号点检查入场
  2. Bull-only (跳过bear)
  3. 仅Scout (单一FVG/OB信号) — 入场最早, WR最高
  4. 阶段过滤: 仅breakout/volatile可交易
  5. 趋势确认: 20-bar EMA斜率 > 0
  6. K线确认: 信号bar后下一根bar收在预期方向
  7. 信号时效: 仅最近120根K线内的信号
  8. 固定参数 SL=0.5% TP=5.0%
  9. 冷启动: 出清后跳过15根K线
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
MAX_HOLD = 60
COOLDOWN = 15
SL_FIXED = 0.5
TP_FIXED = 5.0


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


def detect_phase(ohlcv, idx=None):
    """检测当前市场阶段"""
    window = ohlcv[:idx + 1] if idx else ohlcv
    if len(window) < 60:
        return 'neutral'
    return detect_market_phase(window)


def ema_slope(ohlcv, idx, period=20):
    """计算EMA斜率（%变化）"""
    if idx < period:
        return 0.0
    prices = [ohlcv[i]['c'] for i in range(idx - period, idx + 1)]
    ema = sum(prices) / len(prices)
    ema_prev = sum(prices[:-1]) / len(prices[:-1])
    return (ema - ema_prev) / ema_prev * 100


def avg_volume(ohlcv, idx, period=30):
    """计算平均成交量"""
    start = max(0, idx - period + 1)
    vols = [ohlcv[i].get('v', ohlcv[i].get('vol', 0)) for i in range(start, idx + 1)]
    return sum(vols) / len(vols) if vols else 0


def bar_volume(ohlcv, idx):
    return ohlcv[idx].get('v', ohlcv[idx].get('vol', 0))


def check_bar_close(ohlcv, idx, direction='bull'):
    """检查信号bar的收盘是否在预期方向"""
    if idx < 0 or idx >= len(ohlcv) - 1:
        return False
    bar = ohlcv[idx]
    prev = ohlcv[idx - 1] if idx > 0 else bar
    if direction == 'bull':
        return bar['c'] > prev['c'] and bar['c'] > bar['o']  # bullish close
    else:
        return bar['c'] < prev['c'] and bar['c'] < bar['o']


def check_signal_quality(sig, ohlcv, signals_up_to_idx):
    """检查单个信号的质量"""
    sig_type = sig.get('type', '')
    direction = sig.get('direction', 'bull')
    idx = sig.get('idx', -1)
    
    # 方向过滤: 仅bull
    if direction != 'bull':
        return False, 'not_bull'
    
    # 仅FVG和OB信号
    if 'FVG' not in sig_type and 'OB' not in sig_type:
        return False, 'not_scout'
    
    # 信号时效: 仅最近120根K线
    if idx < len(ohlcv) - 120:
        return False, 'stale'
    
    # K线确认: 信号bar需要收涨
    if not check_bar_close(ohlcv, idx, 'bull'):
        return False, 'bar_not_bull'
    
    # 成交量确认
    vol = bar_volume(ohlcv, idx)
    avg_vol = avg_volume(ohlcv, idx)
    if vol < avg_vol * 0.8:
        return False, 'low_volume'
    
    # 趋势确认: EMA斜率
    slope = ema_slope(ohlcv, idx)
    if slope < 0:
        return False, 'bear_trend'
    
    # 信号密度: 附近有其他bull信号加分, 但不强制
    nearby = [s for s in signals_up_to_idx
              if s.get('direction') == 'bull'
              and abs(s.get('idx', -1) - idx) <= 8
              and s.get('type') != sig_type]
    
    signal_cluster = len(nearby) >= 1
    
    return True, 'good' if signal_cluster else 'weak_cluster'


def simulate_one_trade(ohlcv, entry_idx, sl_pct, tp_pct, direction='bull'):
    """模拟一笔交易"""
    n = len(ohlcv)
    entry_idx = entry_idx + 1  # 下一根bar开盘入场
    
    if entry_idx >= n - 1:
        return None
    
    entry_price = ohlcv[entry_idx]['o']
    if direction == 'bull':
        sl_price = entry_price * (1 - sl_pct / 100)
        tp_price = entry_price * (1 + tp_pct / 100)
    else:
        sl_price = entry_price * (1 + sl_pct / 100)
        tp_price = entry_price * (1 - tp_pct / 100)
    
    for j in range(entry_idx, min(entry_idx + MAX_HOLD, n)):
        bar = ohlcv[j]
        if direction == 'bull':
            if bar['h'] >= tp_price:
                return j, tp_price, True, tp_pct
            if bar['l'] <= sl_price:
                return j, sl_price, False, -sl_pct
        else:
            if bar['l'] <= tp_price:
                return j, tp_price, True, tp_pct
            if bar['h'] >= sl_price:
                return j, sl_price, False, -sl_pct
    
    # 超时, 按收盘价出场
    exit_idx = min(entry_idx + MAX_HOLD, n - 1)
    exit_price = ohlcv[exit_idx]['c']
    if direction == 'bull':
        won = exit_price > entry_price
        pnl = (exit_price - entry_price) / entry_price * 100
    else:
        won = exit_price < entry_price
        pnl = (entry_price - exit_price) / entry_price * 100
    
    return exit_idx, exit_price, won, round(pnl, 2)


def backtest_stock_v6(ohlcv, symbol):
    """V6信号级回测"""
    t0 = time.time()
    n = len(ohlcv)
    
    # 阶段过滤
    phase = detect_market_phase(ohlcv)
    if phase not in ('breakout', 'volatile', 'breakout_phase'):
        return {'trades': [], 'n_signals': 0, 'phase': phase}
    
    # 信号检测 (一次)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_signals = result['all']
    
    if not all_signals or len(all_signals) < 3:
        return {'trades': [], 'n_signals': len(all_signals) if all_signals else 0, 'phase': phase}
    
    # 按信号idx排序
    all_signals.sort(key=lambda s: s.get('idx', 0))
    
    # 遍历每个信号, 检查是否入场
    trades = []
    cooldown_until = -1
    
    for si, sig in enumerate(all_signals):
        idx = sig.get('idx', 0)
        
        # 冷启动
        if idx <= cooldown_until:
            continue
        
        # 信号质量检查
        signals_before = all_signals[:si + 1]
        ok, reason = check_signal_quality(sig, ohlcv, signals_before)
        if not ok:
            continue
        
        # 模拟交易
        trade = simulate_one_trade(ohlcv, idx, SL_FIXED, TP_FIXED)
        if trade is None:
            continue
        
        exit_idx, exit_price, won, pnl = trade
        
        # 计算RR
        entry_price = ohlcv[idx + 1]['o'] if idx + 1 < n else ohlcv[idx]['c']
        rr = pnl / SL_FIXED if won else -pnl / SL_FIXED
        
        trades.append({
            'entry_idx': idx,
            'exit_idx': exit_idx,
            'direction': 'bull',
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'pnl_pct': round(pnl, 2),
            'won': won,
            'rr': round(rr, 2),
            'sig_type': sig.get('type', '?'),
            'phase': phase,
            'hold_bars': exit_idx - idx - 1,
        })
        
        cooldown_until = exit_idx + COOLDOWN
    
    elapsed = time.time() - t0
    
    if len(trades) < 2:
        return {'trades': [], 'n_signals': len(all_signals), 'phase': phase}
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
    loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 0
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
        'elapsed': round(elapsed, 1),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print(f"V11 回测 v6 — 信号级入场 + 多层过滤 ({min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks)")
    print(f"{'='*80}")
    
    all_results, all_trades = [], []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SKIP")
            continue
        
        result = backtest_stock_v6(ohlcv, sym)
        trades = result.get('trades', [])
        perf = result.get('perf', {})
        
        if trades:
            all_trades.extend(trades)
            all_results.append({
                'symbol': sym, 'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED,
                **perf, 'n_signals': result.get('n_signals', 0),
                'phase': result.get('phase', '?'),
            })
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} trades={perf['n_trades']:2d} "
                  f"WR={perf['win_rate']:.0f}% RR={perf['avg_rr']:.1f}x "
                  f"PF={perf['profit_factor']:.1f} P&L={perf['avg_pnl']:+.2f}% "
                  f"phase={result.get('phase','?')} | {result.get('elapsed',0):.1f}s")
        else:
            sigs = result.get('n_signals', 0)
            phase_r = result.get('phase', '?')
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} NO-TRADE sigs={sigs} phase={phase_r}")
        
        if (idx + 1) % 30 == 0:
            time.sleep(0.3)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"SUMMARY — {len(all_results)} tradable out of {MAX_STOCKS}, {total_time:.1f}s")
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
        print(f"  WR>=60%: {sum(1 for s in all_results if s['win_rate']>=60)} stocks")
        print(f"  WR>=70%: {sum(1 for s in all_results if s['win_rate']>=70)} stocks")
        print(f"  WR>=80%: {sum(1 for s in all_results if s['win_rate']>=80)} stocks")
        
        sig_cnt = Counter(t.get('sig_type','?') for t in all_trades)
        print(f"  Signal dist: {dict(sig_cnt.most_common(8))}")
        
        hold_cnt = Counter(t.get('hold_bars',0) for t in all_trades)
        print(f"  Avg hold bars: {sum(t['hold_bars'] for t in all_trades)/n:.1f}")
        
        ph_cnt = Counter(s['phase'] for s in all_results)
        print(f"  Phase dist: {dict(ph_cnt.most_common())}")
        
        print(f"\n  TOP 10 by WR:")
        sorted_r = sorted(all_results, key=lambda s: s['win_rate'], reverse=True)
        for s in sorted_r[:10]:
            print(f"    {s['symbol']:12s} WR={s['win_rate']:.0f}% RR={s['avg_rr']:.1f}x "
                  f"PF={s['profit_factor']:.1f} trades={s['n_trades']} phase={s['phase']}")
        
        print(f"\n  TOP 10 by Trade Count:")
        sorted_r2 = sorted(all_results, key=lambda s: s['n_trades'], reverse=True)
        for s in sorted_r2[:10]:
            print(f"    {s['symbol']:12s} trades={s['n_trades']:2d} WR={s['win_rate']:.0f}% "
                  f"RR={s['avg_rr']:.1f}x PF={s['profit_factor']:.1f} phase={s['phase']}")
    
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {'max_stocks': MAX_STOCKS, 'sl_pct': SL_FIXED, 'tp_pct': TP_FIXED},
        'summary': {
            'total_stocks': MAX_STOCKS, 'tradable': len(all_results),
            'total_trades': len(all_trades),
            'win_rate': round(wr, 1) if all_trades else 0,
            'avg_rr': round(avg_rr, 2) if all_trades else 0,
            'profit_factor': round(pf, 2) if all_trades else 0,
            'avg_pnl': round(avg_pnl, 2) if all_trades else 0,
        },
        'stocks': all_results, 'all_trades': all_trades,
    }
    outpath = OUTPUT_DIR / 'backtest_v11_v6.json'
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  Saved: {outpath}")


if __name__ == '__main__':
    main()
