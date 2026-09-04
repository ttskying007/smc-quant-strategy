#!/usr/bin/env python3
"""
V9 SMC Multi-Timeframe Engine — 日线信号 + 周线趋势 + 60min精确入场
=================================================================
架构:
  1. 日线: FVG_Bull / OB_Bull / CHOCH_Bull 信号检测 → 定义入场区域
  2. 周线: MA20趋势过滤 (bullish only, close > MA20 by 2%)
  3. 60min: 在日线信号区域内寻找精确入场时机
  4. SL: entry-based ATR自适应 (3-8%)
  5. TP: 前方swing_high/CHOCH (日线可达, 60min不可达)
  6. Trailing: +5%激活, 追踪距离ATR*0.8
  7. T+1: 跳过同日exit

信号类型扩展 (V9):
  - OB_Bull: 主信号 (WR=99.8%日线)
  - FVG_Bull: 辅助信号 (IMB间隙)
  - CHOCH_Bull: 结构转换信号
  - BOS_Bull: 突破信号
  - Sweep_SSL: 流动性猎杀
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, Signal

# ─── 配置 ───
DAILY_DIR = Path('/root/.hermes/kline_cache')
HOURLY_DIR = Path('/root/.hermes/kline_cache_60min')
OUT_DIR = Path('/root/.hermes/smc_opt_v9')
OUT_DIR.mkdir(exist_ok=True)

# 信号白名单 (V9: 扩展)
TRADE_SIGNALS = {'OB_Bull', 'FVG_Bull', 'CHOCH_Bull', 'BOS_Bull', 'Sweep_SSL'}

# 入场参数
MAX_WAIT_DAILY = 3      # 日线等待回踩最大bar数
MAX_WAIT_HOURLY = 8     # 60min等待回踩最大bar数
MIN_HOLD = 1            # 最小持有bar数

# SL/TP参数
SL_PCT_MIN = 3.0        # SL下限
SL_PCT_MAX = 8.0        # SL上限
SL_ATR_MUL = 2.0        # SL = ATR * mul
TRAIL_ACT_PCT = 5.0     # Trailing激活阈值
TRAIL_DIST_MUL = 0.8    # Trailing距离 = ATR * mul
TP_MIN_PCT = 5.0        # TP最小目标

# 周线过滤
WEEKLY_MA_PERIOD = 20
WEEKLY_FILTER_PCT = 2.0   # 价格须在MA20上>2%

# 60min入场
USE_60MIN = True          # 启用60min精确入场
MAX_60MIN_RETRACE = 12    # 60min回踩最大等待bar数


def _calc_atr(closes, highs, lows, length=14):
    """计算ATR"""
    n = min(length, len(closes))
    trs = []
    for i in range(len(closes) - n + 1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    return sum(trs) / len(trs) if trs else 0.01


def check_weekly_trend(weekly):
    """周线趋势过滤: close > MA20 * (1 + 2%)"""
    if not weekly or len(weekly) < WEEKLY_MA_PERIOD:
        return True  # 无周线数据则不过滤
    ma20 = sum(w['c'] for w in weekly[-WEEKLY_MA_PERIOD:]) / WEEKLY_MA_PERIOD
    return weekly[-1]['c'] > ma20 * (1 + WEEKLY_FILTER_PCT / 100)


def find_daily_entry(daily, zone_low, zone_high, sig_idx):
    """在日线上寻找回踩入场"""
    n = len(daily)
    closes = [b['c'] for b in daily]
    lows = [b['l'] for b in daily]
    
    for w in range(MAX_WAIT_DAILY + 1):
        eb = sig_idx + 1 + w
        if eb >= n - 5:
            break
        if lows[eb] <= zone_high:  # 触及入场区域
            return eb, max(zone_low, lows[eb])
    return None, None


def find_hourly_entry(hourly, zone_low, zone_high, daily_sig_date):
    """在60min上寻找精确入场 (日线信号日期之后)"""
    if not hourly or len(hourly) < 20:
        return None, None
    
    lows = [b['l'] for b in hourly]
    highs = [b['h'] for b in hourly]
    dates = [b.get('t', b.get('date', ''))[:10] for b in hourly]
    
    # 找到日线信号日期之后的第一个60min bar
    start_idx = 0
    for i, d in enumerate(dates):
        if d > daily_sig_date:
            start_idx = i
            break
    
    for w in range(MAX_60MIN_RETRACE):
        eb = start_idx + w
        if eb >= len(hourly) - 5:
            break
        if lows[eb] <= zone_high:
            return eb, max(zone_low, lows[eb])
    return None, None


def find_tp_target(daily, entry_idx, entry_price):
    """寻找TP目标: 前方swing_high (日线可达)"""
    highs = [b['h'] for b in daily]
    n = len(daily)
    
    for j in range(entry_idx + 3, min(n, entry_idx + 30)):
        if j < 3:
            continue
        # 简单摆动高点检测
        is_swing = True
        for k in range(1, 4):
            if j - k >= 0 and highs[j - k] > highs[j]:
                is_swing = False
            if j + k < n and highs[j + k] > highs[j]:
                is_swing = False
        if is_swing and highs[j] > entry_price * (1 + TP_MIN_PCT / 100):
            tp_pct = (highs[j] - entry_price) / entry_price * 100
            return highs[j], tp_pct, j
    return None, 0, None


def simulate_exit(daily, entry_idx, entry_price, sl, tp_price=None):
    """模拟trailing退出"""
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    closes = [b['c'] for b in daily]
    n = len(daily)
    
    atr_pct = _calc_atr(closes, highs, lows, 14) / closes[entry_idx] * 100
    trail_dist = max(2.0, atr_pct * TRAIL_DIST_MUL)  # Trailing距离百分比
    
    extreme = entry_price
    sl_current = sl
    trail_active = False
    entry_date = daily[entry_idx].get('t', daily[entry_idx].get('date', ''))[:10]
    
    for j in range(entry_idx + 1, min(n, entry_idx + 30)):
        bar_date = daily[j].get('t', daily[j].get('date', ''))[:10]
        is_same_day = (bar_date == entry_date and bar_date != '')
        
        if highs[j] > extreme:
            extreme = highs[j]
        
        gain_pct = (extreme - entry_price) / entry_price * 100
        
        # 激活trailing
        if not trail_active and gain_pct >= TRAIL_ACT_PCT:
            trail_active = True
        
        if trail_active:
            sl_current = max(sl_current, extreme * (1 - trail_dist / 100))
        
        # T+1跳过同日
        if j <= entry_idx + MIN_HOLD or is_same_day:
            continue
        
        # SL触发
        if lows[j] <= sl_current:
            return j, max(sl_current, lows[j]), 'trailing'
        
        # TP触发
        if tp_price and highs[j] >= tp_price * 0.98:
            return j, tp_price * 0.98, 'tp'
    
    # 超时退出
    exit_idx = min(entry_idx + 29, n - 1)
    return exit_idx, closes[exit_idx], 'timeout'


def backtest_stock_mtf(symbol, daily, weekly=None, hourly=None):
    """
    多周期联动回测单只股票
    
    Returns: list of trade dicts
    """
    if len(daily) < 60:
        return []
    
    # 周线趋势过滤
    if weekly and len(weekly) >= WEEKLY_MA_PERIOD:
        if not check_weekly_trend(weekly):
            return []
    
    # 日线信号检测
    sigs, stats, _, _ = detect_all_signals_v20(daily)
    
    closes = [b['c'] for b in daily]
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    dates = [b.get('t', '')[:10] for b in daily]
    n = len(daily)
    
    trades = []
    
    # 筛选交易信号
    trade_sigs = [s for s in sigs if s.type in TRADE_SIGNALS and s.idx > 20]
    
    for sig in trade_sigs:
        si = sig.idx
        sig_type = sig.type
        zone_low = sig.lower if hasattr(sig, 'lower') and sig.lower > 0 else lows[si]
        zone_high = sig.upper if hasattr(sig, 'upper') and sig.upper > 0 else highs[si]
        
        if zone_low <= 0:
            continue
        
        # 入场: 优先60min精确入场, 否则日线回踩
        entry_bar = None
        entry_price = None
        entry_source = 'daily'
        
        sig_date = dates[si] if si < len(dates) else ''
        
        if USE_60MIN and hourly and len(hourly) >= 20:
            h_entry, h_price = find_hourly_entry(hourly, zone_low, zone_high, sig_date)
            if h_entry is not None:
                entry_bar = h_entry
                entry_price = h_price
                entry_source = '60min'
        
        if entry_bar is None:
            d_entry, d_price = find_daily_entry(daily, zone_low, zone_high, si)
            if d_entry is None:
                continue
            entry_bar = d_entry
            entry_price = d_price
        
        if entry_bar >= n - 5:
            continue
        
        # SL计算
        atr_pct = _calc_atr(closes, highs, lows, 14) / closes[entry_bar] * 100
        sl_pct = max(SL_PCT_MIN, min(SL_PCT_MAX, atr_pct * SL_ATR_MUL))
        sl = entry_price * (1 - sl_pct / 100)
        
        # TP目标
        tp_price, tp_pct, tp_idx = find_tp_target(daily, entry_bar, entry_price)
        
        # 模拟退出
        exit_bar, exit_price, exit_type = simulate_exit(daily, entry_bar, entry_price, sl, tp_price)
        
        # 计算结果
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        hold_bars = exit_bar - entry_bar
        won = pnl_pct > 0
        actual_sl_pct = (entry_price - sl) / entry_price * 100
        rr = pnl_pct / actual_sl_pct if actual_sl_pct > 0.001 else 99
        
        trades.append({
            'symbol': symbol,
            'signal_type': sig_type,
            'direction': 'bull',
            'entry_source': entry_source,
            'entry_idx': entry_bar,
            'exit_idx': exit_bar,
            'entry_price': round(entry_price, 3),
            'exit_price': round(exit_price, 3),
            'sl': round(sl, 3),
            'pnl_pct': round(pnl_pct, 2),
            'sl_pct': round(actual_sl_pct, 2),
            'tp_pct': round(tp_pct, 2) if tp_pct else 0,
            'won': won,
            'rr': round(rr, 2),
            'hold_bars': hold_bars,
            'exit_type': exit_type,
            'entry_date': dates[entry_bar] if entry_bar < len(dates) else '',
            'exit_date': dates[exit_bar] if exit_bar < len(dates) else '',
        })
    
    return trades


def run_full_backtest(limit=None):
    """全量多周期回测"""
    daily_files = sorted(DAILY_DIR.glob('*_daily_300.json'))
    if limit:
        daily_files = daily_files[:limit]
    
    print(f"V9 MTF Backtest: {len(daily_files)} stocks")
    print(f"Signals: {TRADE_SIGNALS}")
    print(f"SL: {SL_PCT_MIN}-{SL_PCT_MAX}%, Trailing: +{TRAIL_ACT_PCT}% act, ATR*{TRAIL_DIST_MUL} dist")
    print(f"60min entry: {'ON' if USE_60MIN else 'OFF'}")
    print("=" * 60)
    
    all_trades = []
    stock_count = 0
    signal_counts = Counter()
    entry_sources = Counter()
    t0 = time.time()
    
    for i, fp in enumerate(daily_files):
        if i % 500 == 0:
            print(f"  [{i}/{len(daily_files)}] {stock_count} stocks, {len(all_trades)} trades...")
        
        try:
            symbol = fp.stem.replace('_daily_300', '').replace('_', '.')
            daily = json.loads(fp.read_bytes())
            if not daily or len(daily) < 60:
                continue
            
            # 加载周线
            weekly = None
            wp = DAILY_DIR / fp.name.replace('daily_300', 'weekly_200')
            if wp.exists():
                try:
                    weekly = json.loads(wp.read_bytes())
                except:
                    pass
            
            # 加载60min
            hourly = None
            if USE_60MIN:
                for count in [500, 200]:
                    hname = f"{symbol.replace('.','_')}_60min_{count}.json"
                    hp = HOURLY_DIR / hname
                    if hp.exists():
                        try:
                            hourly = json.loads(hp.read_bytes())
                            break
                        except:
                            pass
            
            trades = backtest_stock_mtf(symbol, daily, weekly, hourly)
            if trades:
                stock_count += 1
                all_trades.extend(trades)
                for t in trades:
                    signal_counts[t['signal_type']] += 1
                    entry_sources[t['entry_source']] += 1
        except Exception as e:
            pass
    
    elapsed = time.time() - t0
    print(f"\nDone: {stock_count} stocks, {len(all_trades)} trades in {elapsed:.0f}s")
    
    # 汇总
    if not all_trades:
        print("No trades!")
        return
    
    won = sum(1 for t in all_trades if t['won'])
    lose = len(all_trades) - won
    avg_pnl = sum(t['pnl_pct'] for t in all_trades) / len(all_trades)
    avg_sl = sum(t['sl_pct'] for t in all_trades) / len(all_trades)
    avg_rr = sum(t['rr'] for t in all_trades) / len(all_trades)
    avg_hold = sum(t['hold_bars'] for t in all_trades) / len(all_trades)
    cum_pnl = sum(t['pnl_pct'] for t in all_trades)
    
    print(f"\n{'='*60}")
    print(f"V9 Multi-Timeframe Results")
    print(f"{'='*60}")
    print(f"Stocks: {stock_count}/{len(daily_files)}")
    print(f"Trades: {len(all_trades)}")
    print(f"WR: {won}/{len(all_trades)} = {won/len(all_trades)*100:.1f}%  (Losses: {lose})")
    print(f"avg PnL: {avg_pnl:.2f}%")
    print(f"avg SL: {avg_sl:.2f}%")
    print(f"avg RR: {avg_rr:.1f}")
    print(f"avg Hold: {avg_hold:.1f} bars")
    print(f"cum PnL: {cum_pnl:.1f}%")
    
    # 按信号类型
    print(f"\n--- Signal Type Breakdown ---")
    for st in sorted(signal_counts.keys()):
        st_trades = [t for t in all_trades if t['signal_type'] == st]
        if not st_trades:
            continue
        st_won = sum(1 for t in st_trades if t['won'])
        st_pnl = sum(t['pnl_pct'] for t in st_trades) / len(st_trades)
        st_rr = sum(t['rr'] for t in st_trades) / len(st_trades)
        tp_count = sum(1 for t in st_trades if t.get('exit_type') == 'tp')
        print(f"  {st:15s}: n={len(st_trades):5d} WR={st_won/len(st_trades)*100:.1f}% avgPnL={st_pnl:+.2f}% avgRR={st_rr:.1f} TP={tp_count}")
    
    # 按入场来源
    print(f"\n--- Entry Source ---")
    for es in sorted(entry_sources.keys()):
        es_trades = [t for t in all_trades if t['entry_source'] == es]
        es_won = sum(1 for t in es_trades if t['won'])
        es_pnl = sum(t['pnl_pct'] for t in es_trades) / len(es_trades)
        print(f"  {es:10s}: n={len(es_trades):5d} WR={es_won/len(es_trades)*100:.1f}% avgPnL={es_pnl:+.2f}%")
    
    # 退出方式
    tp_count = sum(1 for t in all_trades if t.get('exit_type') == 'tp')
    trail_count = sum(1 for t in all_trades if t.get('exit_type') == 'trailing')
    print(f"\n--- Exit Method ---")
    print(f"  TP: {tp_count} ({tp_count/len(all_trades)*100:.1f}%)")
    print(f"  Trailing: {trail_count} ({trail_count/len(all_trades)*100:.1f}%)")
    
    # 日期范围
    all_dates = [t['entry_date'] for t in all_trades if t['entry_date']]
    if all_dates:
        print(f"\nDate range: {min(all_dates)} ~ {max(all_dates)}")
    
    # 保存
    out_file = OUT_DIR / 'v9_mtf_full.json'
    json.dump(all_trades, open(out_file, 'w'), ensure_ascii=False)
    
    # 选股: top 50 by avg PnL
    stock_perf = defaultdict(list)
    for t in all_trades:
        stock_perf[t['symbol']].append(t)
    
    picks = []
    for sym, ts in stock_perf.items():
        avg = sum(t['pnl_pct'] for t in ts) / len(ts)
        picks.append({
            'symbol': sym,
            'trades': len(ts),
            'avg_pnl': round(avg, 2),
            'wr': round(sum(1 for t in ts if t['won']) / len(ts) * 100, 1),
            'signals': list(set(t['signal_type'] for t in ts)),
            'last_signal_date': max(t['entry_date'] for t in ts),
        })
    picks.sort(key=lambda x: (-x['trades'], -x['avg_pnl']))
    
    picks_file = OUT_DIR / 'v9_picks.json'
    json.dump(picks[:100], open(picks_file, 'w'), ensure_ascii=False, indent=2)
    
    print(f"\nSaved: {out_file} ({len(all_trades)} trades)")
    print(f"Picks: {picks_file} ({min(100, len(picks))} stocks)")
    
    return all_trades


if __name__ == '__main__':
    run_full_backtest()
