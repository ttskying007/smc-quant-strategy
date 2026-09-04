#!/usr/bin/env python3
"""
V28 — Confirmed Entry + Better Trailing + Swing Optimization
=============================================================
V27(566笔): WR=87.6%, RR=8.37x, PF=107 — 但FVG在confirmed_at之前1bar入场

V28修复:
  1. 使用confirmed_at入场 (非idx): FVG信号需在confirmed_at bar入场
  2. 优化trailing: 更细的区间, 降低门槛在0.5%保本
  3. 优化摆动SL: 降低最小摆动SL到0.10%, 放宽距离到30K线
  4. 阶段适应SL更精细
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
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v28')
OUTPUT_DIR.mkdir(exist_ok=True)

# V28: Wider swing SL parameters
SWING_MAX_DISTANCE = 30; SWING_SL_CAP = 0.5
MIN_VOL_RATIO = 0.7; MIN_FVG_GAP = 0.2
MAX_STOCKS = 200; MIN_BARS = 120; MAX_HOLD = 60

# V28: Phase-adaptive SL
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


def find_all_swing_lows(ohlcv, end_idx, lookback=60):
    """V28: Wider lookback for swing low detection"""
    if end_idx<3: return []
    start=max(0,end_idx-lookback); s=[]
    for i in range(end_idx-1,start,-1):
        b=ohlcv[i]; l=ohlcv[i-1] if i>start else None; r=ohlcv[i+1] if i<end_idx-1 else None
        lv=l['l'] if l else 9999; rv=r['l'] if r else 9999
        if b['l']<lv and b['l']<rv: s.append((i,b['l'],end_idx-i))
    return s


def find_best_swing_sl(ohlcv,end_idx,entry_price):
    """V28: Wider SL range (0.10%-0.70%)"""
    swings=find_all_swing_lows(ohlcv,end_idx)
    swings=[s for s in swings if s[2]<=SWING_MAX_DISTANCE]
    if not swings: return None
    best,bs=None,999
    for idx,price,dist in swings:
        capped=min(price,entry_price*(1-SWING_SL_CAP/100))
        sp=(entry_price-capped)/entry_price*100
        # V28: wider range
        if 0.10<=sp<=0.70:
            sc=abs(sp-0.35)*0.4+(dist/SWING_MAX_DISTANCE)*0.6
            if sc<bs: bs=sc; best={'sl_price':capped,'sl_pct':round(sp,2)}
    return best


def calc_initial_sl(ohlcv,end_idx,entry_price,signal_type,sl_fixed):
    fixed_sl=entry_price*(1-sl_fixed/100)
    sl_info=find_best_swing_sl(ohlcv,end_idx,entry_price)
    if sl_info is not None:
        return sl_info['sl_price'],sl_info['sl_pct'],'swing'
    if 'OB' in signal_type: return None,None,None
    return fixed_sl,sl_fixed,'fixed'


def calc_trailing_exit(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold=60):
    """
    V28: Smoother trailing with lower thresholds
    0.2% → SL entry-0.1%  (near breakeven)
    0.5% → SL entry+0.2%  (partial lock)
    1.0% → SL entry+0.5%  (breakeven+)
    2.0% → trail 1.0% below highest
    4.0% → trail 2.0% below highest
    """
    sl = initial_sl
    highest = entry_price
    exit_idx = -1; exit_price = None; won = False
    
    for j in range(entry_idx+1, min(entry_idx+max_hold+1, n)):
        bar = ohlcv[j]
        if bar['h'] > highest:
            highest = bar['h']
        gain_pct = (highest - entry_price) / entry_price * 100
        
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
            exit_idx = j
            exit_price = max(sl, bar['l'])
            won = exit_price > entry_price
            break
    
    if exit_idx == -1:
        exit_idx = min(entry_idx + max_hold, n - 1)
        exit_price = ohlcv[exit_idx]['c']
        won = exit_price > entry_price
    
    return exit_idx, exit_price, won


def evaluate_signal_entry(ohlcv, sig_idx, sig, all_sigs_up_to_idx, params, phase):
    """V28: Uses confirmed_at for entry"""
    n = len(ohlcv)
    sig_type = sig.get('type', '')
    if 'FVG' not in sig_type and 'OB' not in sig_type:
        return None
    
    if 'Bull' not in sig_type:
        return None
    
    signal_type = 'FVG' if 'FVG' in sig_type else 'OB'
    
    # V28: Use confirmed_at for entry (not idx)
    confirmed_at = sig.get('confirmed_at', sig_idx)
    entry_bar = max(sig_idx, confirmed_at)
    
    # Need at least 1 bar after entry for exit
    if entry_bar >= n - 2:
        return None
    
    # Volume check at signal bar
    if sig_idx > 30 and sig_idx < n:
        bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        av = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0)) 
                 for j in range(max(0, sig_idx-30), sig_idx)) / 30
        if bv < av * MIN_VOL_RATIO:
            return None
    
    # FVG quality check
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
    
    # Short-term trend at entry bar
    td, _ = short_trend(ohlcv, entry_bar)
    if td == 'down':
        return None
    
    # Weekly trend at entry bar
    weekly = synthesize_weekly(ohlcv[:entry_bar+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down':
            return None
    
    # Multi-cycle at entry bar  
    micro = short_trend(ohlcv, entry_bar, 8)
    meso = short_trend(ohlcv, entry_bar, 20)
    macro = short_trend(ohlcv, entry_bar, 40)
    uc = sum(1 for c in [micro, meso, macro] if c[0] == 'up')
    dc = sum(1 for c in [micro, meso, macro] if c[0] == 'down')
    if dc >= 2 or (uc == 1 and dc == 0):
        return None
    
    cd = 'ALL-UP' if uc == 3 else ('2UP-1NEUTRAL' if uc >= 2 else 'NEUTRAL')
    cm = CYCLE_SL_MULT.get(cd, 1.0)
    
    # Sequence at entry bar
    seq_r = analyze_sequence_v11(all_sigs_up_to_idx, params=params)
    best_seq = seq_r.get('best_sequence')
    if not best_seq:
        return None
    seq_name = best_seq.get('name', '')
    if 'SCOUT' not in seq_name:
        return None
    
    # Resonance at entry bar
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
    
    # V28: entry_price at entry_bar close
    entry_price = ohlcv[entry_bar]['c']
    
    # SL
    phase_params = PHASE_PARAMS.get(phase, {'sl': 0.3})
    actual_sl_val = phase_params['sl'] * cm
    init_sl, sl_pct_val, sl_type = calc_initial_sl(ohlcv, entry_bar, entry_price, signal_type, actual_sl_val)
    if init_sl is None:
        return None
    
    # Trailing exit
    exit_idx, exit_price, won = calc_trailing_exit(ohlcv, entry_bar, entry_price, init_sl, n, MAX_HOLD)
    
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
        'sl_type': sl_type,
        'sl_pct': round(sl_pct_val, 2),
        'signal_type': signal_type,
        'exit_method': 'trailing',
        'used_sl': actual_sl_val,
        'phase': phase,
        'cycle_detail': cd,
    }


def backtest_stock_v28(ohlcv, symbol):
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
        
        result = evaluate_signal_entry(ohlcv, sig_idx, sig, sigs_up_to, {**base_params}, phase)
        if result:
            # Avoid overlapping trades (cooldown-like)
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
    swing_cnt = sum(1 for t in trades if t.get('sl_type') == 'swing')
    
    return {
        'trades': trades,
        'perf': {
            'n_trades': len(trades), 'wins': wins, 'losses': len(trades) - wins,
            'win_rate': round(wr, 1), 'avg_rr': round(avg_rr, 2),
            'profit_factor': round(pf, 2) if pf < 999 else 999,
            'avg_pnl': round(avg_pnl, 2),
            'swing_sl_pct': round(swing_cnt / len(trades) * 100, 1),
            'phase': phase,
        }
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print("V28 — Confirmed Entry + Better Trailing")
    print(f"  200 stocks")
    print(f"{'='*80}")
    
    all_trades, stock_results = [], []
    t_start = time.time()
    phases_seen = Counter()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/200] {sym:12s} NO-DATA")
            continue
        
        result = backtest_stock_v28(ohlcv, sym)
        if result:
            p = result['perf']
            phases_seen[p['phase']] += 1
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            print(f"  [{idx+1:3d}/200] {sym:12s} n={p['n_trades']:2d} WR={p['win_rate']:.0f}% "
                  f"PF={p['profit_factor']:.0f} swing={p['swing_sl_pct']:.0f}%")
        else:
            print(f"  [{idx+1:3d}/200] {sym:12s} SKIP")
        
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
        sw = [t for t in all_trades if t.get('sl_type') == 'swing']
        sw_wr = sum(1 for t in sw if t['won']) / len(sw) * 100 if sw else 0
        holds = [t['hold_bars'] for t in all_trades]
        
        print(f"\n{'='*80}")
        print(f"V28 — {len(stock_results)}/{MAX_STOCKS} tradable | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | WR={sw_wr:.1f}%")
        print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        print(f"  Avg hold: {sum(holds)/len(holds):.1f} bars | Max: {max(holds)}")
        
        outpath = OUTPUT_DIR / 'backtest_v28.json'
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'config': {'version': 'V28', 'confirmed_entry': True},
            'summary': {
                'total_trades': n, 'tradable': len(stock_results),
                'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
                'profit_factor': round(pf, 2), 'avg_pnl': round(pnl, 2),
            },
            'stocks': stock_results, 'all_trades': all_trades,
        }, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")
    
    print(f"\n{'='*80}")
    print(f"{'V27 vs V28 COMPARISON':^80}")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
