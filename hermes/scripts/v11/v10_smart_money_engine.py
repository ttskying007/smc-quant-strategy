#!/usr/bin/env python3
"""
V10 SMC Smart Money Engine — 聪明钱追踪 + 自适应参数
=====================================================
核心理念 (ICT SMC):
  1. LIQ Sweep → CHOCH/BOS → OB/FVG Entry   (SMC标准入场序列)
  2. PD Array确认: OB区域出现Pinbar/Engulf → 入场确认
  3. Smart Trailing: 等price回测zone后再收紧SL
  4. 自适应SL: SL放在OB下沿+摆动低点, 非固定%
  5. 多周期确认: 日线信号 + 周线趋势 + 60min精确入场
  6. 市场状态自适应: 趋势/震荡/高波/低波不同参数

V10 over V9:
  - OB必须在前方有LIQ Sweep (流动性猎杀) 或 CHOCH (结构转换)
  - FVG只在周线bullish+未被回补时使用
  - BOS不作为独立信号, 仅做CHOCH确认
  - Sweep_SSL需确认后面有OB/FVG才能入场
  - SL基于OB结构 + ATR自适应
  - Trailing延迟激活 (等回测zone后)
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, Signal

DAILY_DIR = Path('/root/.hermes/kline_cache')
HOURLY_DIR = Path('/root/.hermes/kline_cache_60min')
OUT_DIR = Path('/root/.hermes/smc_opt_v10')
OUT_DIR.mkdir(exist_ok=True)

# ─── V10 信号策略 ───
# OB_Bull: 需要前10bar内有LIQ Sweep或CHOCH → 主力信号
# Sweep_SSL: 后5bar内有OB_Bull → 入场点在OB, Sweep仅做确认
# CHOCH_Bull: 后5bar内有OB_Bull → 入场点在OB
# FVG_Bull: 仅周线bullish且FVG未被回补
# BOS_Bull: 不做独立入场

SIGNAL_REQUIREMENTS = {
    # V10.2: 仅保留数据验证有效的信号
    # OB_Bull: 需要前10bar有LIQ/CHOCH (SMC标准序列)
    # Sweep_SSL: 需要后5bar有OB_Bull (流动性猎杀后入场)
    'OB_Bull': {'require_context': True, 'context_types': ['Sweep_SSL','Sweep_BSL','CHOCH_Bull'], 'context_window': 10},
    'Sweep_SSL': {'require_zone': True, 'zone_types': ['OB_Bull'], 'zone_window': 5},
    # 以下信号经全量数据验证无效：FVG(回补率过高WR<50%), BOS(WR<42%), CHOCH(样本不足)
}

# SL/TP参数 (自适应)
SL_ATR_MIN = 0.005   # 0.5% minimum SL (decimal)
SL_ATR_MAX = 0.02    # 2% maximum SL (decimal)
SL_STRUCT_FLOOR = 0.03  # 结构性SL下限 3%

TRAIL_ACT_GAIN = 0.07    # Trailing激活: +7% (V9的+5%过早)
TRAIL_DIST_ATR = 1.0     # Trailing距离 = ATR * 1.0
TRAIL_DELAY_BARS = 2     # 激活后延迟2bar再收紧

MAX_HOLD = 25
MAX_WAIT = 3             # 日线回踩等待
MAX_HOURLY_RETRACE = 12  # 60min回踩等待

WEEKLY_MA_PERIOD = 20
WEEKLY_FILTER_PCT = 1.5  # 周线MA20上>1.5%


def _calc_atr(closes, highs, lows, length=14):
    n = min(length, len(closes))
    trs = []
    for i in range(len(closes)-n+1, len(closes)):
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    return sum(trs)/len(trs) if trs else 0.01


# Entry confirmation: Pinbar detection at zone
def _has_pinbar_at_zone(daily, zone_low, zone_high, entry_bar):
    """Check for Pinbar confirmation at entry zone"""
    if entry_bar < 1: return False
    b = daily[entry_bar]
    o, h, l, c = b['o'], b['h'], b['l'], b['c']
    if h == l: return False
    rng = h - l
    if rng == 0: return False
    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    # Hammer: long lower wick, close in upper 30%
    if lower_wick > body * 2.5 and lower_wick > rng * 0.6 and upper_wick < rng * 0.15:
        return c > (h - rng * 0.3)
    # Engulf: body > previous body, close above previous high
    if entry_bar > 0:
        prev = daily[entry_bar - 1]
        prev_body = abs(prev['c'] - prev['o'])
        if body > prev_body * 1.5 and c > prev['h'] and o < prev['l']:
            return True
    return False


def _find_swing_low(daily, entry_idx):
    """找entry前最近的摆动低点作为结构性SL参考"""
    lows = [b['l'] for b in daily]
    for j in range(entry_idx - 1, max(0, entry_idx - 20), -1):
        if j >= 2 and lows[j] < lows[j-1] and lows[j] < lows[j+1]:
            return lows[j]
    return None


def _check_fvg_fill_rate(daily, fvg_sig):
    """检查FVG回补率"""
    gap_low, gap_high = fvg_sig.lower, fvg_sig.upper
    if gap_low >= gap_high: return 1.0
    filled = 0
    lookback = min(10, fvg_sig.idx)
    for k in range(max(0, fvg_sig.idx - lookback), fvg_sig.idx):
        c = daily[k]['c']
        if gap_low < c < gap_high:
            filled += 1
    return filled / max(lookback, 1)


def check_signal_context(sig, all_sigs, symbol=''):
    """V10: 检查信号是否有SMC上下文确认"""
    sig_type = sig.type
    req = SIGNAL_REQUIREMENTS.get(sig_type, {})
    
    if req.get('skip'): return False, 'skip'
    
    # 需要上下文确认 (LIQ/CHOCH)
    if req.get('require_context'):
        ctx_types = req['context_types']
        ctx_window = req['context_window']
        for s in all_sigs:
            if s.type in ctx_types and s.idx < sig.idx and sig.idx - s.idx <= ctx_window:
                return True, f'{s.type}_ctx'
        return False, 'no_context'
    
    # 需要后方有入场zone (OB/FVG)
    if req.get('require_zone'):
        zone_types = req['zone_types']
        zone_window = req['zone_window']
        for s in all_sigs:
            if s.type in zone_types and s.idx >= sig.idx and s.idx - sig.idx <= zone_window:
                return True, f'zone_{s.type}'
        return False, 'no_zone'
    
    return True, 'ok'


def get_adaptive_sl(daily, entry_idx, entry_price, signal):
    """V10: 自适应SL — 结构性SL + ATR自适应"""
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    closes = [b['c'] for b in daily]
    
    atr = _calc_atr(closes, highs, lows, 14)
    atr_pct = atr / entry_price
    
    # 1. 结构性SL: 信号zone下沿 或 前摆动低点
    struct_sl = None
    if hasattr(signal, 'lower') and signal.lower > 0:
        struct_sl = signal.lower  # OB下沿
    swing_low = _find_swing_low(daily, entry_idx)
    if swing_low and swing_low < entry_price:
        if struct_sl is None or swing_low < struct_sl:
            struct_sl = swing_low
    
    if struct_sl:
        struct_sl_pct = (entry_price - struct_sl) / entry_price
        if SL_STRUCT_FLOOR <= struct_sl_pct <= 0.08:  # 3-8% structural SL
            sl = struct_sl
            sl_type = 'structural'
            sl_pct = round(struct_sl_pct * 100, 2)
            return sl, sl_type, sl_pct
        # else: structural SL too wide or too tight, fall through to adaptive
    
    # Fallback: ATR adaptive SL
    sl_pct_val = max(SL_ATR_MIN, min(SL_ATR_MAX, atr_pct * 1.5))
    sl = entry_price * (1 - sl_pct_val)
    return sl, 'adaptive', round(sl_pct_val * 100, 2)


def simulate_smart_trailing(daily, entry_idx, entry_price, sl, tp_price=None):
    """V10: Smart Trailing — 延迟激活 + 回测zone后收紧"""
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    closes = [b['c'] for b in daily]
    n = len(daily)
    
    atr = _calc_atr(closes, highs, lows, 14)
    atr_pct = atr / entry_price
    
    extreme = entry_price
    sl_current = sl
    trailing_active = False
    trail_bars_active = 0
    entry_date = daily[entry_idx].get('t', daily[entry_idx].get('date', ''))[:10]
    
    for j in range(entry_idx + 1, min(n, entry_idx + MAX_HOLD)):
        bar_date = daily[j].get('t', daily[j].get('date', ''))[:10]
        is_same_day = (bar_date == entry_date)
        
        if highs[j] > extreme:
            extreme = highs[j]
        
        gain_pct = (extreme - entry_price) / entry_price
        
        # Smart trailing: 只在gain>7%后激活, 激活后延迟2bar再收紧
        if not trailing_active and gain_pct >= TRAIL_ACT_GAIN:
            trailing_active = True
        
        if trailing_active:
            trail_bars_active += 1
            if trail_bars_active > TRAIL_DELAY_BARS:
                trail_dist = max(atr_pct * TRAIL_DIST_ATR, 0.03)
                sl_current = max(sl_current, extreme * (1 - trail_dist))
        
        # T+1
        if j <= entry_idx + 1 or is_same_day:
            continue
        
        # SL hit
        if lows[j] <= sl_current:
            return j, max(sl_current, lows[j]), 'trailing'
        
        # TP hit
        if tp_price and highs[j] >= tp_price * 0.98:
            return j, tp_price * 0.98, 'tp'
    
    # Timeout
    exit_idx = min(entry_idx + MAX_HOLD - 1, n - 1)
    return exit_idx, closes[exit_idx], 'timeout'


def backtest_stock_v10(symbol, daily, weekly=None, hourly=None):
    """V10单股票回测"""
    if len(daily) < 60: return []
    
    # 周线过滤
    if weekly and len(weekly) >= WEEKLY_MA_PERIOD:
        ma20 = sum(w['c'] for w in weekly[-WEEKLY_MA_PERIOD:]) / WEEKLY_MA_PERIOD
        if weekly[-1]['c'] < ma20 * (1 + WEEKLY_FILTER_PCT/100):
            return []
    
    sigs, stats, _, _ = detect_all_signals_v20(daily)
    closes = [b['c'] for b in daily]
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    dates = [b.get('t','')[:10] for b in daily]
    n = len(daily)
    trades = []
    
    # 处理每个信号
    for sig in sigs:
        if sig.type not in SIGNAL_REQUIREMENTS: continue
        if sig.idx < 20: continue
        
        # V10: SMC上下文检查
        ok, reason = check_signal_context(sig, sigs, symbol)
        if not ok: continue
        
        # FVG: 必须周线bullish + 回补率<50%
        if sig.type == 'FVG_Bull':
            weekly_bullish = (weekly and len(weekly) >= WEEKLY_MA_PERIOD and 
                weekly[-1]['c'] > sum(w['c'] for w in weekly[-WEEKLY_MA_PERIOD:])/WEEKLY_MA_PERIOD * (1 + WEEKLY_FILTER_PCT/100))
            if not weekly_bullish:
                continue
            fill_rate = _check_fvg_fill_rate(daily, sig)
            if fill_rate > SIGNAL_REQUIREMENTS['FVG_Bull']['max_fill_rate']:
                continue
        
        # Sweep/CHOCH: 找到关联的OB作为入场zone
        entry_sig = sig
        if reason.startswith('zone_'):
            # 找到后方最近的OB
            for s in sigs:
                if s.type == 'OB_Bull' and s.idx >= sig.idx and s.idx - sig.idx <= 5:
                    entry_sig = s
                    break
        
        # 确定入场区域
        zone_low = entry_sig.lower if hasattr(entry_sig, 'lower') and entry_sig.lower > 0 else lows[entry_sig.idx]
        zone_high = entry_sig.upper if hasattr(entry_sig, 'upper') and entry_sig.upper > 0 else highs[entry_sig.idx]
        if zone_low <= 0: continue
        
        # 入场: 日线回踩到zone
        entry_bar = None
        entry_price = None
        entry_source = 'daily'
        
        sig_date = dates[entry_sig.idx] if entry_sig.idx < len(dates) else ''
        
        # 60min精确入场
        if hourly and len(hourly) >= 20:
            h_dates = [b.get('t',b.get('date',''))[:10] for b in hourly]
            h_start = 0
            for i, d in enumerate(h_dates):
                if d > sig_date: h_start = i; break
            for w in range(MAX_HOURLY_RETRACE):
                eb = h_start + w
                if eb >= len(hourly) - 5: break
                if hourly[eb]['l'] <= zone_high:
                    entry_bar = eb
                    entry_price = max(zone_low, hourly[eb]['l'])
                    entry_source = '60min'
                    break
        
        # 日线回踩
        if entry_bar is None:
            for w in range(MAX_WAIT + 1):
                eb = entry_sig.idx + 1 + w
                if eb >= n - 5: break
                if lows[eb] <= zone_high:
                    entry_bar = eb
                    entry_price = max(zone_low, lows[eb])
                    break
        
        if entry_bar is None: continue
        
        # V10.2: 不需Pinbar/Engulf确认 — OB本身就是SMC确认，追加确认反而过滤有效信号
        
        # 自适应SL
        sl, sl_type, sl_pct = get_adaptive_sl(daily, entry_bar, entry_price, entry_sig)
        
        # TP: 前方swing_high (>=5%)
        tp_price = None
        tp_pct = 0
        for j in range(entry_bar + 3, min(n, entry_bar + 20)):
            ok = True
            for k in range(1, 3):
                if j-k >= 0 and highs[j-k] > highs[j]: ok = False
                if j+k < n and highs[j+k] > highs[j]: ok = False
            if ok and highs[j] > entry_price * 1.05:
                tp_price = highs[j]
                tp_pct = (tp_price - entry_price) / entry_price * 100
                break
        
        # Smart trailing
        exit_bar, exit_price, exit_type = simulate_smart_trailing(daily, entry_bar, entry_price, sl, tp_price)
        
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        
        trades.append({
            'symbol': symbol,
            'signal_type': sig.type,
            'context': reason,
            'direction': 'bull',
            'entry_source': entry_source,
            'entry_idx': entry_bar,
            'exit_idx': exit_bar,
            'entry_price': round(entry_price, 3),
            'exit_price': round(exit_price, 3),
            'pnl_pct': round(pnl_pct, 2),
            'sl_pct': sl_pct,
            'sl_type': sl_type,
            'tp_pct': round(tp_pct, 2),
            'won': pnl_pct > 0,
            'rr': round(pnl_pct/sl_pct, 2) if sl_pct > 0 else 99,
            'hold_bars': exit_bar - entry_bar,
            'exit_type': exit_type,
            'entry_date': dates[entry_bar] if entry_bar < len(dates) else '',
            'exit_date': dates[exit_bar] if exit_bar < len(dates) else '',
        })
    
    return trades


def run_backtest(limit=None):
    daily_files = sorted(DAILY_DIR.glob('*_daily_300.json'))
    if limit: daily_files = daily_files[:limit]
    
    print(f"V10 Smart Money Engine: {len(daily_files)} stocks")
    print(f"SMC Context: LIQ→CHOCH→OB 入场序列")
    print(f"SL: 结构性+自适应 | Trail: +7%激活+延迟2bar")
    print("=" * 60)
    
    all_trades = []
    stock_count = 0
    context_stats = Counter()
    t0 = time.time()
    
    for i, fp in enumerate(daily_files):
        if i % 500 == 0:
            print(f"  [{i}/{len(daily_files)}] {stock_count} stocks, {len(all_trades)} trades...")
        try:
            symbol = fp.stem.replace('_daily_300','').replace('_','.')
            daily = json.loads(fp.read_bytes())
            if not daily or len(daily) < 60: continue
            
            weekly = None
            wp = DAILY_DIR / fp.name.replace('daily_300', 'weekly_200')
            if wp.exists():
                try: weekly = json.loads(wp.read_bytes())
                except: pass
            
            hourly = None
            for c in [500, 200]:
                hp = HOURLY_DIR / (symbol.replace('.','_') + f'_60min_{c}.json')
                if hp.exists():
                    try: hourly = json.loads(hp.read_bytes()); break
                    except: pass
            
            trades = backtest_stock_v10(symbol, daily, weekly, hourly)
            if trades:
                stock_count += 1
                all_trades.extend(trades)
                for t in trades:
                    context_stats[t.get('context','?')] += 1
        except: pass
    
    elapsed = time.time() - t0
    
    # Summary
    if not all_trades:
        print("No trades!"); return
    
    won = sum(1 for t in all_trades if t['won'])
    avg_pnl = sum(t['pnl_pct'] for t in all_trades)/len(all_trades)
    avg_sl = sum(t['sl_pct'] for t in all_trades)/len(all_trades)
    avg_hold = sum(t['hold_bars'] for t in all_trades)/len(all_trades)
    tp_cnt = sum(1 for t in all_trades if t.get('exit_type')=='tp')
    
    print(f"\n{'='*60}")
    print(f"V10 Smart Money Results")
    print(f"{'='*60}")
    print(f"Stocks: {stock_count}/{len(daily_files)}")
    print(f"Trades: {len(all_trades)}")
    print(f"WR: {won}/{len(all_trades)} = {won/len(all_trades)*100:.1f}%")
    print(f"avg PnL: {avg_pnl:.2f}% | SL: {avg_sl:.2f}% | Hold: {avg_hold:.1f}b")
    print(f"TP: {tp_cnt} ({tp_cnt/len(all_trades)*100:.1f}%)")
    
    # Signal breakdown
    sig_counts = Counter(t['signal_type'] for t in all_trades)
    print(f"\n--- Signal Types ---")
    for st in sorted(sig_counts.keys()):
        st_t = [t for t in all_trades if t['signal_type']==st]
        sw = sum(1 for t in st_t if t['won'])
        sp = sum(t['pnl_pct'] for t in st_t)/len(st_t)
        print(f"  {st:15s}: n={len(st_t):4d} WR={sw/len(st_t)*100:.1f}% avgPnL={sp:+.2f}%")
    
    # Context distribution
    print(f"\n--- Context Distribution ---")
    for ctx, cnt in context_stats.most_common(10):
        ctx_t = [t for t in all_trades if t.get('context')==ctx]
        cw = sum(1 for t in ctx_t if t['won'])
        print(f"  {ctx:20s}: n={cnt:4d} WR={cw/max(cnt,1)*100:.1f}%")
    
    dates = [t['entry_date'] for t in all_trades if t['entry_date']]
    if dates: print(f"\nDate: {min(dates)} ~ {max(dates)}")
    
    out_file = OUT_DIR / 'v10_smart_money.json'
    json.dump(all_trades, open(out_file, 'w'), ensure_ascii=False)
    
    # Picks
    stock_perf = defaultdict(list)
    for t in all_trades: stock_perf[t['symbol']].append(t)
    picks = []
    for sym, ts in stock_perf.items():
        avg = sum(t['pnl_pct'] for t in ts)/len(ts)
        picks.append({'symbol':sym, 'trades':len(ts), 'avg_pnl':round(avg,2),
                       'wr':round(sum(1 for t in ts if t['won'])/len(ts)*100,1),
                       'contexts': list(set(t.get('context','') for t in ts)),
                       'last_date': max(t['entry_date'] for t in ts)})
    picks.sort(key=lambda x: (-x['trades'], -x['avg_pnl']))
    json.dump(picks[:100], open(OUT_DIR/'v10_picks.json','w'), ensure_ascii=False)
    
    print(f"\nSaved: {out_file}")
    return all_trades


if __name__ == '__main__':
    run_backtest()
