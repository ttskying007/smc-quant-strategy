#!/usr/bin/env python3
"""
V36 — SMC Structural SL/TP
===========================
基于SMC结构的止盈止损方案，替代固定百分比SL

变更:
  1. calc_structural_sl (替换 calc_initial_sl)
     - FVG_Bull: SL = FVG下边界 (缺口填充=信号失效)
     - OB_Bull: SL = OB下边界 (跌破订单块=失效)
     - 摆动低点回退 (改进自V28)
     - ATR自适应保底
  2. calc_structural_tp (新增)
     - TP = 前方CHOCH_Bull break_level (最可靠结构阻力)
     - TP = 前方摆动高点 (次选)
     - 无结构TP时使用trailing (当前行为)
  3. calc_trailing_v36 (替换 calc_trailing_exit)
     - 有结构TP: 接近TP时收紧trailing
     - 无结构TP: 宽松trailing抓趋势
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v36')
OUTPUT_DIR.mkdir(exist_ok=True)

SWING_MAX_DISTANCE = 30; SWING_SL_CAP = 0.5
MIN_VOL_RATIO = 0.7; MIN_FVG_GAP = 0.2
MAX_STOCKS = 200; MIN_BARS = 120; MAX_HOLD = 60

PHASE_PARAMS = {'breakout':{'sl':0.3},'volatile':{'sl':0.5},
                'ranging':{'sl':0.8},'trending_up':{'sl':0.3},
                'trending_down':{'sl':0.5}}
CYCLE_SL_MULT = {'ALL-UP':0.8,'2UP-1NEUTRAL':1.0,'NEUTRAL':1.2}


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.','_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data)<MIN_BARS: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data


def short_trend(ohlcv, idx, lookback=10):
    if idx<lookback: return 'neutral',0
    seg=ohlcv[idx-lookback:idx+1]; s,e=seg[0]['c'],seg[-1]['c']
    change=(e-s)/s*100
    ema=sum(ohlcv[i]['c'] for i in range(idx-min(5,idx),idx+1))/min(6,idx+1)
    ema_d=(ohlcv[idx]['c']-ema)/ema*100
    if change>0.6 and ema_d>0: return 'up',change
    if change<-0.6 and ema_d<0: return 'down',abs(change)
    return 'neutral',0


def calc_atr(ohlcv, idx, period=14):
    """Simple ATR calculation for SL/TP volatility reference"""
    if idx < period + 1:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100
    trs = []
    for i in range(max(1, idx - period), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100  # ATR as %


def find_all_swing_lows(ohlcv, end_idx, lookback=60):
    if end_idx<3: return []
    start=max(0,end_idx-lookback); s=[]
    for i in range(end_idx-1,start,-1):
        b=ohlcv[i]; l=ohlcv[i-1] if i>start else None; r=ohlcv[i+1] if i<end_idx-1 else None
        lv=l['l'] if l else 9999; rv=r['l'] if r else 9999
        if b['l']<lv and b['l']<rv: s.append((i,b['l'],end_idx-i))
    return s


def find_best_swing_sl(ohlcv,end_idx,entry_price):
    swings=find_all_swing_lows(ohlcv,end_idx)
    swings=[s for s in swings if s[2]<=SWING_MAX_DISTANCE]
    if not swings: return None
    best,bs=None,999
    for idx,price,dist in swings:
        capped=min(price,entry_price*(1-SWING_SL_CAP/100))
        sp=(entry_price-capped)/entry_price*100
        if 0.10<=sp<=0.70:
            sc=abs(sp-0.35)*0.4+(dist/SWING_MAX_DISTANCE)*0.6
            if sc<bs: bs=sc; best={'sl_price':round(capped,4),'sl_pct':round(sp,2)}
    return best


def find_swing_high_forward(ohlcv, start_idx, lookahead=30):
    """Find the first swing high AFTER start_idx"""
    end = min(start_idx + lookahead, len(ohlcv) - 1)
    for i in range(start_idx + 1, end - 1):
        b = ohlcv[i]
        l = ohlcv[i-1] if i > start_idx else None
        r = ohlcv[i+1] if i < end - 1 else None
        hv = l['h'] if l else 0; rv = r['h'] if r else 0
        if b['h'] > hv and b['h'] > rv:
            return {'idx': i, 'price': b['h']}
    return None


def calc_structural_sl(ohlcv, entry_idx, entry_price, signal, all_signals):
    """
    基于SMC结构的止损计算
    Returns: (sl_price, sl_type_name, sl_pct)
    """
    sig_type = signal.get('type', '')
    
    # ── FVG_Bull: SL at FVG lower boundary ──
    if 'FVG_Bull' in sig_type:
        fvg_lower = signal.get('lower', 0)
        if fvg_lower > 0:
            sl_pct = (entry_price - fvg_lower) / entry_price * 100
            atr = calc_atr(ohlcv, entry_idx)
            max_sl = min(0.80, atr * 0.8)  # Cap at 0.80%
            if 0.08 <= sl_pct <= max_sl:
                sl_price = max(fvg_lower, entry_price * (1 - max_sl/100))
                return round(sl_price, 4), 'structure_fvg', round(sl_pct, 2)
    
    # ── OB_Bull: SL at OB lower boundary ──
    if 'OB_Bull' in sig_type:
        ob_lower = signal.get('lower', 0)
        if ob_lower > 0:
            sl_pct = (entry_price - ob_lower) / entry_price * 100
            if 0.08 <= sl_pct <= 1.0:
                return round(ob_lower, 4), 'structure_ob', round(sl_pct, 2)
    
    # ── Swing low fallback (improved V28 logic) ──
    swing = find_best_swing_sl(ohlcv, entry_idx, entry_price)
    if swing:
        return swing['sl_price'], 'swing', swing['sl_pct']
    
    # ── ATR-adaptive dynamic SL (保底) ──
    atr = calc_atr(ohlcv, entry_idx)
    dyn_sl_pct = max(0.15, min(0.80, atr * 0.3))
    return round(entry_price * (1 - dyn_sl_pct/100), 4), 'adaptive', round(dyn_sl_pct, 2)


def calc_structural_tp(ohlcv, entry_idx, entry_price, signal, all_signals):
    """
    基于SMC结构的止盈计算
    Returns: (tp_price, tp_type, tp_pct, tp_idx) or (None, None, None, None)
    """
    # ── 1. 前方CHOCH_Bull (最可靠的结构阻力) ──
    forward_choch = [s for s in all_signals
                     if 'CHOCH_Bull' in s.get('type', '')
                     and s.get('idx', 0) > entry_idx
                     and s.get('idx', 0) <= entry_idx + 60]
    if forward_choch:
        nearest = min(forward_choch, key=lambda s: s.get('idx', 0))
        tp_price = nearest.get('break_level', nearest.get('upper', 0))
        if tp_price > entry_price:
            tp_pct = (tp_price - entry_price) / entry_price * 100
            if tp_pct >= 0.5:  # 至少0.5%才有意义
                return round(tp_price, 4), 'choch', round(tp_pct, 2), nearest['idx']
    
    # ── 2. 前方摆动高点 ──
    swing_high = find_swing_high_forward(ohlcv, entry_idx)
    if swing_high and swing_high['price'] > entry_price:
        tp_pct = (swing_high['price'] - entry_price) / entry_price * 100
        if tp_pct >= 0.5:
            return round(swing_high['price'], 4), 'swing_high', round(tp_pct, 2), swing_high['idx']
    
    # ── 3. 无结构TP → 使用trailing ──
    return None, None, None, None


def calc_trailing_v36(ohlcv, entry_idx, entry_price, initial_sl,
                       structural_tp, n, max_hold=60):
    """
    V36: 结构感知的trailing
    - 有结构TP: 接近TP时收紧trailing, 到达TP时止盈
    - 无结构TP: 宽松trailing抓趋势
    """
    sl = initial_sl
    highest = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None
    
    for j in range(entry_idx+1, min(entry_idx+max_hold+1, n)):
        bar = ohlcv[j]
        if bar['h'] > highest:
            highest = bar['h']
        gain_pct = (highest - entry_price) / entry_price * 100
        
        # 有结构TP时的收紧逻辑
        if tp_price and highest >= tp_price * 0.95:
            # 接近结构阻力 → 收紧trailing
            sl = max(sl, entry_price * (1 + max(0.5, tp_pct * 0.3) / 100))
            if highest >= tp_price:
                # 到达TP → 直接止盈
                return j, tp_price, True
        else:
            # 无结构TP或远未到达 → 宽松trailing
            if gain_pct >= 4.0:
                sl = max(sl, highest * (1 - 2.0/100))
            elif gain_pct >= 2.0:
                sl = max(sl, highest * (1 - 1.0/100))
            elif gain_pct >= 1.0:
                sl = max(sl, entry_price * 1.005)
            elif gain_pct >= 0.5:
                sl = max(sl, entry_price * 1.002)
            elif gain_pct >= 0.2:
                sl = max(sl, entry_price * 0.999)
        
        if bar['l'] <= sl:
            exit_price = max(sl, bar['l'])
            return j, round(exit_price, 2), exit_price > entry_price
    
    # Max hold
    exit_idx = min(entry_idx + max_hold, n - 1)
    return exit_idx, round(ohlcv[exit_idx]['c'], 2), ohlcv[exit_idx]['c'] > entry_price


def evaluate_signal_entry(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals, params, phase):
    """V36: 使用结构SL/TP"""
    n = len(ohlcv)
    sig_type = sig.get('type', '')
    if 'FVG' not in sig_type and 'OB' not in sig_type and 'BreakerBlock' not in sig_type:
        return None
    if 'Bull' not in sig_type:
        return None
    
    # BreakerBlock-as-entry: requires FVG overlap (一击必中模型)
    if 'BreakerBlock' in sig_type:
        brk_meta = sig.get('metadata', {})
        if not brk_meta.get('has_fvg_overlap', False):
            return None  # 没有FVG重叠的一击必中不交易
        signal_type = 'BreakerBlock'
    
    confirmed_at = sig.get('confirmed_at', sig_idx)
    entry_bar = max(sig_idx, confirmed_at)
    if entry_bar >= n - 2:
        return None
    
    # Volume check
    if sig_idx > 30 and sig_idx < n:
        bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        av = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                 for j in range(max(0, sig_idx-30), sig_idx)) / 30
        if bv < av * MIN_VOL_RATIO:
            return None
    
    # FVG quality
    if 'FVG' in sig_type and sig_idx > 0 and sig_idx < n:
        bar = ohlcv[sig_idx]
        if bar['c'] <= bar['o']:
            return None
        upper = sig.get('upper', 0)
        lower = sig.get('lower', 0)
        if upper > 0 and lower > 0:
            gap_pct = (upper - lower) / lower * 100
            if gap_pct < MIN_FVG_GAP:
                return None
    
    # Trend filters (same as V28)
    td, _ = short_trend(ohlcv, entry_bar)
    if td == 'down':
        return None
    
    weekly = synthesize_weekly(ohlcv[:entry_bar+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down':
            return None
    
    micro = short_trend(ohlcv, entry_bar, 8)
    meso = short_trend(ohlcv, entry_bar, 20)
    macro = short_trend(ohlcv, entry_bar, 40)
    uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
    if dc >= 2 or (uc == 1 and dc == 0):
        return None
    
    cd = 'ALL-UP' if uc == 3 else ('2UP-1NEUTRAL' if uc >= 2 else 'NEUTRAL')
    cm = CYCLE_SL_MULT.get(cd, 1.0)
    
    # Sequence + Resonance (same as V28)
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None
    
    window = ohlcv[:entry_bar+1]
    tf_seq = {'daily': seq_r}
    res = evaluate_full_resonance_v11(
        all_signals=all_sigs_up_to_idx,
        tf_sequences=tf_seq,
        ohlcv=window
    )
    mr = 0.55 if uc >= 2 else 0.65
    if signal_type == 'OB':
        mr = max(mr, 0.70)
    if res.total < mr:
        return None
    
    dec = make_entry_decision_v11(res, seq_r, params, tf_sequences=tf_seq)
    if dec['action'] != 'enter':
        if uc >= 2 and res.total >= 0.50:
            pass
        else:
            return None
    
    entry_price = ohlcv[entry_bar]['c']
    
    # ── V36: 结构SL ──
    init_sl, sl_type_name, sl_pct_val = calc_structural_sl(
        ohlcv, entry_bar, entry_price, sig, all_signals)
    if init_sl is None:
        return None
    
    # ── V36: 结构TP ──
    tp_price, tp_type, tp_pct, tp_idx = calc_structural_tp(
        ohlcv, entry_bar, entry_price, sig, all_signals)
    
    # ── V36: 结构感知trailing ──
    exit_idx, exit_price, won = calc_trailing_v36(
        ohlcv, entry_bar, entry_price, init_sl,
        (tp_price, tp_type, tp_pct, tp_idx), n, MAX_HOLD)
    
    pnl = (exit_price - entry_price) / entry_price * 100
    actual_rr = abs(exit_price - entry_price) / abs(entry_price - init_sl) if entry_price != init_sl else 10
    
    return {
        'entry_idx': entry_bar,
        'sig_idx': sig_idx,
        'confirmed_at': confirmed_at,
        'exit_idx': exit_idx,
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'sl': round(init_sl, 2),
        'pnl_pct': round(pnl, 2),
        'won': won,
        'rr': round(actual_rr, 2),
        'hold_bars': exit_idx - entry_bar,
        'sl_type': sl_type_name,    # structure_fvg | structure_ob | swing | adaptive
        'sl_pct': round(sl_pct_val, 2),
        'tp_type': tp_type,         # choch | swing_high | None
        'tp_pct': round(tp_pct, 2) if tp_pct else None,
        'signal_type': signal_type,
        'exit_method': 'tp_hit' if tp_type and tp_price and exit_price >= tp_price else 'trailing',
        'used_sl': round(sl_pct_val, 2),
        'phase': phase,
        'cycle_detail': cd,
    }


def backtest_stock_v36(ohlcv, symbol):
    n = len(ohlcv)
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    
    if not all_signals or len(all_signals) < 3:
        return None
    
    trades = []
    used_bars = set()
    
    for sig in all_signals:
        sig_idx = sig.get('idx', 0)
        if sig_idx < 40 or sig_idx >= n - 10:
            continue
        
        sigs_up_to = [s for s in all_signals if s.get('idx', 0) <= sig_idx]
        
        result = evaluate_signal_entry(ohlcv, sig_idx, sig, sigs_up_to, all_signals, {**base_params}, phase)
        if result:
            if result['entry_idx'] in used_bars:
                continue
            used_bars.add(result['entry_idx'])
            trades.append(result)
    
    if len(trades) < 2:
        return None
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    wp = sum(t['pnl_pct'] for t in trades if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = wp / lp if lp > 0 else 999
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    
    # SL type breakdown
    sl_types = Counter(t.get('sl_type', 'unknown') for t in trades)
    tp_types = Counter(t.get('tp_type', 'none') for t in trades)
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2),
            'sl_types': dict(sl_types),
            'tp_types': dict(tp_types),
            'phase': phase,
        }
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print("V36 — SMC Structural SL/TP")
    print(f"  {MAX_STOCKS} stocks | SL: FVG下边界/OB下边界/摆动 | TP: CHOCH/摆动高点")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    sl_type_stats = Counter()
    tp_type_stats = Counter()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} NO-DATA")
            continue
        
        result = backtest_stock_v36(ohlcv, sym)
        if result:
            p = result['perf']
            for st, cnt in p['sl_types'].items():
                sl_type_stats[st] += cnt
            for tt, cnt in p['tp_types'].items():
                tp_type_stats[tt] += cnt
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} n={p['n_trades']:2d} "
                  f"WR={p['win_rate']:.0f}% PF={p['profit_factor']:.0f}")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SKIP")
        
        if (idx + 1) % 30 == 0:
            time.sleep(0.1)
    
    total_time = time.time() - t_start
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = wp / lp if lp > 0 else 999
        rr = sum(t['rr'] for t in all_trades) / n
        pnl = sum(t['pnl_pct'] for t in all_trades) / n
        holds = [t['hold_bars'] for t in all_trades]
        
        # SL type WR breakdown
        print(f"\n{'='*80}")
        print(f"V36 — {len(stock_results)}/{MAX_STOCKS} tradable | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars | Max: {max(holds)}")
        print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        
        print(f"\n  SL Type breakdown:")
        for st, cnt in sl_type_stats.most_common():
            st_trades = [t for t in all_trades if t.get('sl_type') == st]
            st_wr = sum(1 for t in st_trades if t['won']) / len(st_trades) * 100
            st_avg_pnl = sum(t['pnl_pct'] for t in st_trades) / len(st_trades)
            print(f"    {st:20s}: {cnt:4d} trades ({cnt/n*100:5.1f}%) | WR={st_wr:.1f}% | avgP&L={st_avg_pnl:+.2f}%")
        
        print(f"\n  TP Type breakdown:")
        for tt, cnt in tp_type_stats.most_common():
            if tt in ('none',) or tt == 'None':
                tt_trades = [t for t in all_trades if t.get('tp_type') is None]
            else:
                tt_trades = [t for t in all_trades if t.get('tp_type') == tt]
            if not tt_trades:
                continue
            tt_wr = sum(1 for t in tt_trades if t['won']) / len(tt_trades) * 100
            tt_avg_pnl = sum(t['pnl_pct'] for t in tt_trades) / len(tt_trades)
            lbl = str(tt) if tt else 'none'
            print(f"    {lbl:20s}: {len(tt_trades):4d} trades | WR={tt_wr:.1f}% | avgP&L={tt_avg_pnl:+.2f}%")
        
        # Save
        outpath = OUTPUT_DIR / 'backtest_v36.json'
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'config': {'version': 'V36', 'structural_sl_tp': True},
            'summary': {
                'total_trades': n, 'tradable': len(stock_results),
                'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
                'profit_factor': round(pf, 2), 'avg_pnl': round(pnl, 2),
                'sl_type_stats': dict(sl_type_stats),
                'tp_type_stats': dict(tp_type_stats),
            },
            'stocks': stock_results, 'all_trades': all_trades,
        }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")
    
    print(f"\n{'='*80}")
    print(f"{'V28 vs V36 COMPARISON':^80}")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
