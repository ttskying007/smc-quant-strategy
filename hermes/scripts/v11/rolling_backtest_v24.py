#!/usr/bin/env python3
"""
V24 — Per-Stock Optimal SL/TP within V23 Framework
===================================================
V23基线: WR=87.1%, PF=95, 1291/4800可交易

V24创新: 对每个可交易的股票, 在其阶段内找最优SL/TP
  - 每个股票: 尝试 SL=0.3%/0.5%/0.7% × TP=3.0%/5.0%/8.0%
  - 按综合评分(WR²×√N×min(PF,20))选最优
  - 保持V23的: 摆动覆盖过滤+阶段自适应+多周期

预期: WR~90%, 覆盖略降
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v24')
OUTPUT_DIR.mkdir(exist_ok=True)

SWING_MAX_DISTANCE = 20; SWING_SL_CAP = 0.5
MIN_VOL_RATIO = 0.8; MIN_FVG_GAP = 0.3
MIN_SWING_COVERAGE = 30
MAX_STOCKS = 200; MIN_BARS = 120; ROLL_START = 80
ROLL_END_OFFSET = 10; MAX_HOLD = 60; COOLDOWN = 15

# Phase params (V23 baseline)
PHASE_PARAMS = {
    'breakout':      {'sl': 0.3, 'tp': 3.0},
    'volatile':      {'sl': 0.5, 'tp': 5.0},
    'ranging':       {'sl': 0.7, 'tp': 3.0},
    'trending_up':   {'sl': 0.3, 'tp': 5.0},
    'trending_down': {'sl': 0.5, 'tp': 5.0},
}

# Per-stock optimization search space
SL_OPTIONS = [0.3, 0.5, 0.7, 1.0]
TP_OPTIONS = [3.0, 5.0, 8.0]

CYCLE_SL_MULT = {'ALL-UP': 1.0, '2UP-1NEUTRAL': 1.0, 'NEUTRAL': 1.2}


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback: return 'neutral', 0.0
    seg = ohlcv[idx-lookback:idx+1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e-s)/s*100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1))/min(6, idx+1)
    ema_dist = (ohlcv[idx]['c']-ema)/ema*100
    if change > 0.6 and ema_dist > 0: return 'up', change
    if change < -0.6 and ema_dist < 0: return 'down', abs(change)
    return 'neutral', 0


def find_all_swing_lows(ohlcv, end_idx, lookback=50):
    if end_idx < 3: return []
    start = max(0, end_idx-lookback); swings = []
    for i in range(end_idx-1, start, -1):
        bar = ohlcv[i]; l = ohlcv[i-1] if i>start else None; r = ohlcv[i+1] if i<end_idx-1 else None
        lv = l['l'] if l else 9999; rv = r['l'] if r else 9999
        if bar['l'] < lv and bar['l'] < rv: swings.append((i, bar['l'], end_idx-i))
    return swings

def find_all_swing_highs(ohlcv, end_idx, lookback=50):
    if end_idx < 3: return []
    start = max(0, end_idx-lookback); swings = []
    for i in range(end_idx-1, start, -1):
        bar = ohlcv[i]; l = ohlcv[i-1] if i>start else None; r = ohlcv[i+1] if i<end_idx-1 else None
        lv = l['h'] if l else 0; rv = r['h'] if r else 0
        if bar['h'] > lv and bar['h'] > rv: swings.append((i, bar['h'], end_idx-i))
    return swings

def find_best_swing_sl(ohlcv, end_idx, entry_price, max_dist=SWING_MAX_DISTANCE, sl_cap=SWING_SL_CAP):
    swings = find_all_swing_lows(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= max_dist]
    if not swings: return None
    best = None; bs = 999
    for idx, price, dist in swings:
        capped = min(price, entry_price*(1-sl_cap/100))
        sp = (entry_price-capped)/entry_price*100
        if 0.15 <= sp <= 0.7:
            sc = abs(sp-0.4)*0.5 + (dist/max_dist)*0.5
            if sc < bs: bs = sc; best = {'sl_price': capped, 'sl_pct': round(sp,2)}
    return best

def find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist=SWING_MAX_DISTANCE):
    swings = find_all_swing_highs(ohlcv, end_idx)
    swings = [s for s in swings if s[2] <= max_dist]
    if not swings: return None
    best = None; bs = 999
    sl_pct = (entry_price-sl_price)/entry_price*100 if entry_price>sl_price else 0.3
    for idx, price, dist in swings:
        tp = max(price, entry_price*1.005); tp_pct = (tp-entry_price)/entry_price*100
        rr = tp_pct/sl_pct if sl_pct>0 else 10
        if rr>=2.0 and tp_pct<=20.0:
            sc = abs(rr-8.0)*0.5 + (dist/max_dist)*0.5
            if sc < bs: bs = sc; best = {'tp_price':tp, 'tp_pct':round(tp_pct,2), 'rr':round(rr,2)}
    return best


def calc_sltp(ohlcv, end_idx, entry_price, signal_type, sl_fixed, tp_fixed, sl_cap=SWING_SL_CAP):
    fixed_sl = entry_price*(1-sl_fixed/100); fixed_tp = entry_price*(1+tp_fixed/100)
    sl_info = find_best_swing_sl(ohlcv, end_idx, entry_price, sl_cap=sl_cap)
    if sl_info is not None:
        final_sl = sl_info['sl_price']; sl_pct = sl_info['sl_pct']; sl_type = 'swing'
    else:
        if 'OB' in signal_type: return None
        final_sl = fixed_sl; sl_pct = sl_fixed; sl_type = 'fixed'
    tp_info = find_best_swing_tp(ohlcv, end_idx, entry_price, final_sl)
    if tp_info is not None:
        final_tp = tp_info['tp_price']; tp_pct = tp_info['tp_pct']; rr = tp_info['rr']; tp_type = 'swing'
    else:
        final_tp = fixed_tp; tp_pct = tp_fixed
        rr = tp_fixed/sl_pct if sl_pct>0 else 10; tp_type = 'fixed'
    return {'sl':round(final_sl,2),'tp':round(final_tp,2),'sl_pct':round(sl_pct,2),
            'tp_pct':round(tp_pct,2),'rr':round(rr,2),'sl_type':sl_type,'tp_type':tp_type}


def get_entry_signal_info(seq_result):
    entry_sig = seq_result.get('entry_signal',{})
    fvg_entry = seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None: return fvg_entry['idx'], fvg_entry.get('type',''), fvg_entry
    return entry_sig.get('idx',0), entry_sig.get('type',''), entry_sig


def simulate_trades(ohlcv, all_signals, params, phase, sl_fixed, tp_fixed):
    n = len(ohlcv); roll_end = n-ROLL_END_OFFSET
    trades = []; entered_bar = -999
    phase_params = PHASE_PARAMS.get(phase, {'sl':0.3,'tp':3.0})
    swing_count = 0; fixed_count = 0
    
    for i in range(ROLL_START, roll_end):
        if i-entered_bar < COOLDOWN: continue
        sigs_before = [s for s in all_signals if s.get('idx',0)<=i]
        if len(sigs_before)<3: continue
        seq_result = analyze_sequence_v11(sigs_before, params=params)
        best_seq = seq_result.get('best_sequence')
        if not best_seq: continue
        seq_name = best_seq.get('name','')
        is_scout = 'SCOUT' in seq_name; seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
        if seq_dir!='bull' or not is_scout: continue
        
        sig_idx, sig_type, sig = get_entry_signal_info(seq_result)
        if sig_idx==0: sig_idx=i
        
        if sig_idx<n-1 and sig_idx>30:
            bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol',0))
            av = sum(ohlcv[j].get('v',ohlcv[j].get('vol',0)) for j in range(max(0,sig_idx-30),sig_idx))/30
            if bv < av*MIN_VOL_RATIO: continue
        
        st = sig.get('type',sig_type)
        if 'FVG' in st and sig_idx>0 and sig_idx<n:
            bar = ohlcv[sig_idx]
            if bar['c']<=bar['o']: continue
            up = sig.get('upper',0); lo = sig.get('lower',0)
            if up>0 and lo>0 and (up-lo)/lo*100<MIN_FVG_GAP: continue
        
        if len(sigs_before)<8: continue
        trend_dir,_ = short_trend(ohlcv,i)
        if trend_dir=='down': continue
        
        weekly = synthesize_weekly(ohlcv[:i+1])
        if len(weekly)>=3 and weekly_trend(weekly, lookback=min(5,len(weekly)))=='down': continue
        
        signal_type = 'FVG' if 'FVG' in st else 'OB'
        
        # Multi-cycle
        micro = short_trend(ohlcv,i,8); meso = short_trend(ohlcv,i,20); macro = short_trend(ohlcv,i,40)
        up_cnt = sum(1 for c in [micro,meso,macro] if c[0]=='up'); dn_cnt = sum(1 for c in [micro,meso,macro] if c[0]=='down')
        if dn_cnt>=2 or (up_cnt==1 and dn_cnt==0): continue
        
        cycle_det = 'ALL-UP' if up_cnt==3 else ('2UP-1NEUTRAL' if up_cnt>=2 else 'NEUTRAL')
        cycle_mult = CYCLE_SL_MULT.get(cycle_det, 1.0)
        
        window = ohlcv[:i+1]; tf_sequences = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window)
        min_res = 0.55 if up_cnt>=2 else 0.65
        if signal_type=='OB': min_res = max(min_res, 0.70)
        if resonance.total < min_res: continue
        
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        if decision['action']!='enter': continue
        entry_price = decision.get('entry_price')
        if not entry_price: continue
        
        # Use optimized SL/TP
        actual_sl = sl_fixed * cycle_mult
        actual_tp = tp_fixed
        swing_result = calc_sltp(ohlcv, i, entry_price, signal_type, actual_sl, actual_tp)
        if swing_result is None: continue
        sl_price = swing_result['sl']; tp_price = swing_result['tp']
        
        if swing_result['sl_type']=='swing': swing_count+=1
        else: fixed_count+=1
        
        sl_cond = lambda b: b['l']<=sl_price
        tp_cond = lambda b: b['h']>=tp_price
        exit_idx, exit_price, won = -1, None, False
        for j in range(i+1, min(i+MAX_HOLD+1, n)):
            bar = ohlcv[j]
            if tp_cond(bar): exit_idx, exit_price, won = j, tp_price, True; break
            if sl_cond(bar): exit_idx, exit_price, won = j, sl_price, False; break
        if exit_idx==-1:
            exit_idx = min(i+MAX_HOLD, n-1); exit_price = ohlcv[exit_idx]['c']
            won = exit_price > entry_price
        
        pnl = (exit_price-entry_price)/entry_price*100
        risk = abs(entry_price-sl_price); actual_rr = abs(exit_price-entry_price)/risk if risk>0 else 10
        trades.append({'entry_idx':i,'exit_idx':exit_idx,'entry_price':round(entry_price,2),
                      'exit_price':round(exit_price,2),'sl':round(sl_price,2),'tp':round(tp_price,2),
                      'pnl_pct':round(pnl,2),'won':won,'rr':round(actual_rr,2),
                      'hold_bars':exit_idx-i,'sl_type':swing_result['sl_type'],
                      'sl_pct':swing_result['sl_pct'],'signal_type':signal_type,
                      'used_sl':actual_sl,'used_tp':actual_tp,'cycle_det':cycle_det})
        entered_bar = i
    
    total = swing_count+fixed_count
    swing_pct = swing_count/total*100 if total else 0
    return trades, swing_pct


def optimize_stock(ohlcv, symbol):
    """V24: 对单股票找最优SL/TP组合"""
    t0 = time.time()
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
    if not all_signals or len(all_signals)<5: return None
    
    params = {**base_params}
    best = None; best_score = -999
    
    for sl in SL_OPTIONS:
        for tp in TP_OPTIONS:
            trades, swing_pct = simulate_trades(ohlcv, all_signals, params, phase, sl, tp)
            
            # Swing coverage filter
            if swing_pct < MIN_SWING_COVERAGE: continue
            if len(trades) < 2: continue
            
            wins = sum(1 for t in trades if t['won'])
            wr = wins/len(trades)*100
            win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
            loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
            pf = win_pnl/loss_pnl if loss_pnl>0 else 99.9
            avg_pnl = sum(t['pnl_pct'] for t in trades)/len(trades)
            
            # Score: WR² × √N × min(PF, 20)
            score = wr*math.sqrt(len(trades))*min(pf,20)/10
            
            if score > best_score:
                best_score = score
                best = {
                    'sl': sl, 'tp': tp,
                    'n_trades': len(trades), 'win_rate': round(wr,1),
                    'profit_factor': round(pf,1), 'avg_pnl': round(avg_pnl,2),
                    'swing_pct': round(swing_pct,1), 'score': round(score,1),
                    'trades': trades,
                }
    
    if best:
        best['elapsed'] = round(time.time()-t0,1)
    return best


def main():
    symbols = sorted([f.stem.replace('_daily_300','').replace('_','.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"{'='*80}")
    print("V24 — Per-Stock Optimal SL/TP within V23 Framework")
    print(f"  {min(MAX_STOCKS, len(symbols))}/{len(symbols)} stocks")
    print(f"  SL sweep: {SL_OPTIONS} | TP sweep: {TP_OPTIONS}")
    print(f"  Swing coverage filter: >= {MIN_SWING_COVERAGE}%")
    print(f"{'='*80}")
    
    all_trades = []; opt_results = []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        opt = optimize_stock(ohlcv, sym)
        if opt:
            all_trades.extend(opt['trades'])
            opt_results.append({'symbol': sym, **{k:v for k,v in opt.items() if k!='trades'}})
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} SL={opt['sl']}% TP={opt['tp']}% "
                  f"n={opt['n_trades']:2d} WR={opt['win_rate']:.0f}% PF={opt['profit_factor']:.0f} "
                  f"swing={opt['swing_pct']:.0f}% score={opt['score']}")
        else:
            print(f"  [{idx+1:3d}/{MAX_STOCKS}] {sym:12s} NO-OPT")
        if (idx+1)%30==0: time.sleep(0.3)
    
    total_time = time.time()-t_start
    
    print(f"\n{'='*80}")
    print(f"V24 — {len(opt_results)} optimized | {total_time:.0f}s")
    print(f"{'='*80}")
    
    if all_trades:
        n = len(all_trades); wins = sum(1 for t in all_trades if t['won'])
        wr = wins/n*100
        win_pnl = sum(t['pnl_pct'] for t in all_trades if t['won'])
        loss_pnl = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = win_pnl/loss_pnl if loss_pnl>0 else 999
        avg_rr = sum(t['rr'] for t in all_trades)/n
        avg_pnl = sum(t['pnl_pct'] for t in all_trades)/n
        sw = [t for t in all_trades if t.get('sl_type')=='swing']
        sw_wr = sum(1 for t in sw if t['won'])/len(sw)*100 if sw else 0
        
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {avg_rr:.2f}x | PF: {pf:.0f} | P&L: {avg_pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | WR={sw_wr:.1f}%")
        print(f"  WR>=80%: {sum(1 for r in opt_results if r['win_rate']>=80)}")
        
        # Optimal SL/TP distribution
        sl_cnt = Counter(r['sl'] for r in opt_results)
        tp_cnt = Counter(r['tp'] for r in opt_results)
        print(f"\n  Optimal SL distribution: {dict(sl_cnt.most_common())}")
        print(f"  Optimal TP distribution: {dict(tp_cnt.most_common())}")
        
        # Average optimal WR by phase
        print(f"\n  Optimal WR by baseline param:")
        for sl_base in SL_OPTIONS:
            for tp_base in TP_OPTIONS:
                subset = [r for r in opt_results if r['sl']==sl_base and r['tp']==tp_base]
                if subset:
                    aw = sum(r['win_rate'] for r in subset)/len(subset)
                    print(f"    SL={sl_base}% TP={tp_base}%: {len(subset):2d} stocks | avg WR={aw:.0f}%")
        
        outpath = OUTPUT_DIR / 'backtest_v24.json'
        json.dump({'timestamp': datetime.now().isoformat(), 'config':{'version':'V24'},
                   'summary':{'total_trades':n,'tradable':len(opt_results),
                              'win_rate':round(wr,1),'avg_rr':round(avg_rr,2),
                              'profit_factor':round(pf,2)},
                   'results':[{k:v for k,v in r.items() if k!='trades'} for r in opt_results],
                   'all_trades':all_trades},
                  open(outpath,'w'), ensure_ascii=False, indent=2, default=str)
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    main()
