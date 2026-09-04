#!/usr/bin/env python3
"""
V25 — Trailing Stop Exit Strategy
===================================
V23基线: WR=87.1%, RR=11.3x, TP固定3.0% — 可能过早止盈

V25创新:
  1. 动态止盈: 不再固定TP=3.0%, 用trailing stop
  2. 入场后: SL保持不变, TP随最高价上移
  3. 初始SL=摆动点(或0.3%), 每根K线后:
     - 如果bar.h > 入场价+0.5%: SL上移到入场价+0.2%
     - 如果bar.h > 入场价+1.0%: SL上移到入场价+0.5% (保本+)
     - 如果bar.h > 入场价+2.0%: SL上移到当前bar.h-1.0%(trail)
     - 持仓超过20K线: 强制退出
  4. 保留V23所有过滤 (摆动覆盖+阶段自适应+多周期)

预期: WR略降(86-87%), RR大幅提升(15-20x), PF~100+
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
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v25')
OUTPUT_DIR.mkdir(exist_ok=True)

SWING_MAX_DISTANCE = 20; SWING_SL_CAP = 0.5
MIN_VOL_RATIO = 0.8; MIN_FVG_GAP = 0.3
MIN_SWING_COVERAGE = 30
MAX_STOCKS = 200; MIN_BARS = 120; ROLL_START = 80
ROLL_END_OFFSET = 10; MAX_HOLD = 60; COOLDOWN = 15
PHASE_PARAMS = {'breakout':{'sl':0.3,'tp':3.0},'volatile':{'sl':0.5,'tp':5.0},
                'ranging':{'sl':0.7,'tp':3.0},'trending_up':{'sl':0.3,'tp':5.0},
                'trending_down':{'sl':0.5,'tp':5.0}}
CYCLE_SL_MULT = {'ALL-UP':1.0,'2UP-1NEUTRAL':1.0,'NEUTRAL':1.2}


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


def find_all_swing_lows(ohlcv, end_idx, lookback=50):
    if end_idx<3: return []
    start=max(0,end_idx-lookback); s=[]
    for i in range(end_idx-1,start,-1):
        b=ohlcv[i]; l=ohlcv[i-1] if i>start else None; r=ohlcv[i+1] if i<end_idx-1 else None
        lv=l['l'] if l else 9999; rv=r['l'] if r else 9999
        if b['l']<lv and b['l']<rv: s.append((i,b['l'],end_idx-i))
    return s

def find_all_swing_highs(ohlcv,end_idx,lookback=50):
    if end_idx<3: return []
    start=max(0,end_idx-lookback); s=[]
    for i in range(end_idx-1,start,-1):
        b=ohlcv[i]; l=ohlcv[i-1] if i>start else None; r=ohlcv[i+1] if i<end_idx-1 else None
        lv=l['h'] if l else 0; rv=r['h'] if r else 0
        if b['h']>lv and b['h']>rv: s.append((i,b['h'],end_idx-i))
    return s

def find_best_swing_sl(ohlcv,end_idx,entry_price):
    swings=find_all_swing_lows(ohlcv,end_idx)
    swings=[s for s in swings if s[2]<=SWING_MAX_DISTANCE]
    if not swings: return None
    best,bs=None,999
    for idx,price,dist in swings:
        capped=min(price,entry_price*(1-SWING_SL_CAP/100))
        sp=(entry_price-capped)/entry_price*100
        if 0.15<=sp<=0.7:
            sc=abs(sp-0.4)*0.5+(dist/SWING_MAX_DISTANCE)*0.5
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
    V25: 追踪止盈退出
    每根K线更新SL, 初始SL不变
    """
    sl = initial_sl  # 初始止损不变
    highest = entry_price
    exit_idx = -1; exit_price = None; won = False
    
    for j in range(entry_idx+1, min(entry_idx+max_hold+1, n)):
        bar = ohlcv[j]
        
        # Update highest
        if bar['h'] > highest:
            highest = bar['h']
        
        # V25 trailing: 按价格区域逐步上移SL
        gain_pct = (highest - entry_price) / entry_price * 100
        
        if gain_pct >= 1.5:
            # Trail: SL = 当前最高价 - 1.0%
            new_sl = highest * (1 - 1.0/100)
            sl = max(sl, new_sl)
        elif gain_pct >= 1.0:
            # 保本+: SL = 入场价 + 0.3%
            sl = max(sl, entry_price * 1.003)
        elif gain_pct >= 0.5:
            # 接近保本: SL = 入场价 - 0.1%
            sl = max(sl, entry_price * 0.999)
        
        # Check exit
        if bar['l'] <= sl:
            exit_idx = j
            exit_price = max(sl, bar['l'])  # 实际成交价近SL
            won = exit_price > entry_price
            break
    
    if exit_idx == -1:
        # Time exit
        exit_idx = min(entry_idx + max_hold, n - 1)
        exit_price = ohlcv[exit_idx]['c']
        won = exit_price > entry_price
    
    return exit_idx, exit_price, won


def get_entry_signal_info(seq_result):
    entry_sig=seq_result.get('entry_signal',{})
    fvg_entry=seq_result.get('fvg_entry')
    if fvg_entry and fvg_entry.get('idx') is not None: return fvg_entry['idx'],fvg_entry.get('type',''),fvg_entry
    return entry_sig.get('idx',0),entry_sig.get('type',''),entry_sig


def simulate_trades(ohlcv, all_signals, params, phase):
    n=len(ohlcv); roll_end=n-ROLL_END_OFFSET
    trades=[]; entered_bar=-999
    phase_params=PHASE_PARAMS.get(phase,{'sl':0.3,'tp':3.0})
    sl_fixed=phase_params['sl']
    swing_count=0; fixed_count=0
    
    for i in range(ROLL_START, roll_end):
        if i-entered_bar<COOLDOWN: continue
        sigs=[s for s in all_signals if s.get('idx',0)<=i]
        if len(sigs)<3: continue
        seq_r=analyze_sequence_v11(sigs,params=params)
        best=seq_r.get('best_sequence')
        if not best: continue
        sn=best.get('name',''); sc='SCOUT' in sn; sd='bull' if 'LONG' in sn else 'bear'
        if sd!='bull' or not sc: continue
        
        sig_idx,sig_type,sig=get_entry_signal_info(seq_r)
        if sig_idx==0: sig_idx=i
        
        if sig_idx<n-1 and sig_idx>30:
            bv=ohlcv[sig_idx].get('v',ohlcv[sig_idx].get('vol',0))
            av=sum(ohlcv[j].get('v',ohlcv[j].get('vol',0)) for j in range(max(0,sig_idx-30),sig_idx))/30
            if bv<av*MIN_VOL_RATIO: continue
        
        st=sig.get('type',sig_type)
        if 'FVG' in st and sig_idx>0 and sig_idx<n:
            bar=ohlcv[sig_idx]
            if bar['c']<=bar['o']: continue
            up=sig.get('upper',0); lo=sig.get('lower',0)
            if up>0 and lo>0 and (up-lo)/lo*100<MIN_FVG_GAP: continue
        
        if len(sigs)<8: continue
        td,_=short_trend(ohlcv,i)
        if td=='down': continue
        
        weekly=synthesize_weekly(ohlcv[:i+1])
        if len(weekly)>=3 and weekly_trend(weekly,lookback=min(5,len(weekly)))=='down': continue
        
        signal_type='FVG' if 'FVG' in st else 'OB'
        
        micro=short_trend(ohlcv,i,8); meso=short_trend(ohlcv,i,20); macro=short_trend(ohlcv,i,40)
        uc=sum(1 for c in [micro,meso,macro] if c[0]=='up')
        dc=sum(1 for c in [micro,meso,macro] if c[0]=='down')
        if dc>=2 or (uc==1 and dc==0): continue
        
        cd='ALL-UP' if uc==3 else ('2UP-1NEUTRAL' if uc>=2 else 'NEUTRAL')
        cm=CYCLE_SL_MULT.get(cd,1.0)
        
        window=ohlcv[:i+1]; tf_seq={'daily':seq_r}
        res=evaluate_full_resonance_v11(all_signals=sigs,tf_sequences=tf_seq,ohlcv=window)
        mr=0.55 if uc>=2 else 0.65
        if signal_type=='OB': mr=max(mr,0.70)
        if res.total<mr: continue
        
        dec=make_entry_decision_v11(res,seq_r,params,tf_sequences=tf_seq)
        if dec['action']!='enter': continue
        entry_price=dec.get('entry_price')
        if not entry_price: continue
        
        actual_sl_val=sl_fixed*cm
        init_sl,sl_pct_val,sl_type=calc_initial_sl(ohlcv,i,entry_price,signal_type,actual_sl_val)
        if init_sl is None: continue  # OB without swing
        
        if sl_type=='swing': swing_count+=1
        else: fixed_count+=1
        
        # V25: Trailing exit instead of fixed TP
        exit_idx, exit_price, won = calc_trailing_exit(ohlcv, i, entry_price, init_sl, n, MAX_HOLD)
        
        pnl=(exit_price-entry_price)/entry_price*100
        actual_rr=abs(exit_price-entry_price)/abs(entry_price-init_sl) if entry_price!=init_sl else 10
        
        trades.append({'entry_idx':i,'exit_idx':exit_idx,'entry_price':round(entry_price,2),
                      'exit_price':round(exit_price,2),'sl':round(init_sl,2),
                      'pnl_pct':round(pnl,2),'won':won,'rr':round(actual_rr,2),
                      'hold_bars':exit_idx-i,'sl_type':sl_type,'sl_pct':round(sl_pct_val,2),
                      'signal_type':signal_type,'exit_method':'trailing',
                      'used_sl':actual_sl_val})
        entered_bar=i
    
    total=swing_count+fixed_count
    swing_pct=swing_count/total*100 if total else 0
    return trades, swing_pct


def main():
    symbols=sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
    print(f"{'='*80}")
    print("V25 — Trailing Stop Exit Strategy")
    print(f"  200 stocks | Dynamic SL trail | No fixed TP")
    print(f"{'='*80}")
    
    all_trades,stock_results=[],[]; t_start=time.time()
    for idx,sym in enumerate(symbols[:MAX_STOCKS]):
        ohlcv=load_ohlcv(sym)
        if not ohlcv: continue
        phase=detect_market_phase(ohlcv)
        base=calc_stock_params(ohlcv,sym,phase=phase,tf='daily')
        sigs=detect_all_signals_v11(ohlcv,params=base,tf='daily')['all']
        if not sigs or len(sigs)<5:
            print(f"  [{idx+1:3d}/200] {sym:12s} NO-TRADE")
            continue
        trades,sp=simulate_trades(ohlcv,sigs,{**base},phase)
        if sp<MIN_SWING_COVERAGE or len(trades)<2:
            print(f"  [{idx+1:3d}/200] {sym:12s} SKIP(swing={sp:.0f}%)")
            continue
        wins=sum(1 for t in trades if t['won'])
        wr=wins/len(trades)*100
        wp=sum(t['pnl_pct'] for t in trades if t['won'])
        lp=abs(sum(t['pnl_pct'] for t in trades if not t['won']))
        pf=wp/lp if lp>0 else 999
        all_trades.extend(trades)
        stock_results.append({'symbol':sym,'n_trades':len(trades),'win_rate':round(wr,1),
                             'avg_rr':round(sum(t['rr'] for t in trades)/len(trades),2),
                             'profit_factor':round(pf,1),'swing_sl_pct':round(sp,1),
                             'avg_pnl':round(sum(t['pnl_pct'] for t in trades)/len(trades),2)})
        print(f"  [{idx+1:3d}/200] {sym:12s} n={len(trades):2d} WR={wr:.0f}% PF={pf:.0f} swing={sp:.0f}%")
        if (idx+1)%30==0: time.sleep(0.3)
    
    total_time=time.time()-t_start
    
    if all_trades:
        n=len(all_trades); wins=sum(1 for t in all_trades if t['won'])
        wr=wins/n*100
        wp=sum(t['pnl_pct'] for t in all_trades if t['won'])
        lp=abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf=wp/lp if lp>0 else 999
        rr=sum(t['rr'] for t in all_trades)/n
        pnl=sum(t['pnl_pct'] for t in all_trades)/n
        sw=[t for t in all_trades if t.get('sl_type')=='swing']
        sw_wr=sum(1 for t in sw if t['won'])/len(sw)*100 if sw else 0
        
        print(f"\n{'='*80}")
        print(f"V25 — {len(stock_results)} tradable | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
        print(f"  Swing SL: {len(sw)}/{n} ({len(sw)/n*100:.0f}%) | WR={sw_wr:.1f}%")
        print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}")
        
        # P&L distribution
        print(f"\n  P&L Distribution:")
        for bucket in [(-5,0),(0,2),(2,5),(5,10),(10,20),(20,50)]:
            subset=[t for t in all_trades if bucket[0]<=t['pnl_pct']<bucket[1]]
            if subset: print(f"    {bucket[0]:+}% to {bucket[1]:+}%: {len(subset):3d} trades")
        
        outpath=OUTPUT_DIR/'backtest_v25.json'
        json.dump({'timestamp':datetime.now().isoformat(),'config':{'version':'V25','trailing':True},
                   'summary':{'total_trades':n,'tradable':len(stock_results),
                              'win_rate':round(wr,1),'avg_rr':round(rr,2),
                              'profit_factor':round(pf,2),'avg_pnl':round(pnl,2)},
                   'stocks':stock_results,'all_trades':all_trades},
                  open(outpath,'w'),ensure_ascii=False,indent=2,default=str)
        print(f"\n  Saved: {outpath}")
    
    print(f"\n{'='*80}")
    print(f"{'COMPARE WITH V23':^80}")
    print(f"{'='*80}")
    print(f"  V23: WR=87.1% RR=11.3x PF=95.1 P&L=+5.81% (fixed TP)")
    print(f"  V25: WR={wr:.1f}% RR={rr:.2f}x PF={pf:.0f} P&L={pnl:+.2f}% (trailing)")

if __name__=='__main__':
    main()
