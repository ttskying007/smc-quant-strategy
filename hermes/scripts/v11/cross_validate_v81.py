#!/usr/bin/env python3
"""
SMC V8.1 — 全量股票×全周期×全信号 交叉验证
==========================================
改进:
  1. 全4905只股票, 非抽样
  2. 每只股票的FULL 300-bar范围回测所有信号
  3. 时间分段: 前半段(bar0-149) vs 后半段(bar150-299) → 检测信号衰减
  4. 市场状态分段: 周线Bull vs Bear → 检测信号在不同市场下的表现
  5. 输出: per_stock_best, per_signal_decay, per_regime_perf
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)
PICKS_FILE = OUT / 'LD_picks_v6.json'

# Config
MAX_WAIT = 3; SL_ATR_MUL = 1.5; ACT_ATR_MUL = 1.0; DIST_ATR_MUL = 0.7; MIN_HOLD = 2
SIGNAL_TYPES = ['OB_Bull','BOS_Bull→FVG_Bull','CHOCH_Bull→FVG_Bull',
                'Sweep_SSL→FVG_Bull','EQL→FVG_Bull','MSS_Bull→FVG_Bull',
                'Sweep_SSL→Pinbar_Bull','EQL→Pinbar_Bull']

def load_ohlcv(sym):
    for f in [sym.replace('.','_')+'_daily_300.json', sym+'_daily_300.json']:
        p = KLINE/f
        if p.exists(): return json.loads(p.read_bytes())
    return None

def load_weekly(sym):
    for f in [sym.replace('.','_')+'_weekly_200.json']:
        p = KLINE/f
        if p.exists(): return json.loads(p.read_bytes())
    return None

def calc_atr(daily, l=14):
    n=len(daily)
    if n<l+1: return daily[-1]['c']*0.03
    return sum(max(daily[i]['h']-daily[i]['l'],abs(daily[i]['h']-daily[i-1]['c']),abs(daily[i]['l']-daily[i-1]['c'])) for i in range(max(1,n-l),n))/l

def sim(daily, eb, zl, em):
    n=len(daily); atr=calc_atr(daily); ap=sum(b['c'] for b in daily[-20:])/min(20,n)
    atr_p=atr/ap if ap>0 else 0.03
    sl_p=max(0.03,atr_p*SL_ATR_MUL); td=max(0.015,min(0.04,atr_p*DIST_ATR_MUL))
    if em=='retrace':
        r=-1
        for k in range(eb+1,min(eb+MAX_WAIT+1,n)):
            if daily[k]['l']<=zl: r=k; break
        if r<0: return None
        ae=r; ep=zl
    else:
        ae=eb+1
        if ae>=n-2: return None
        ep=daily[ae]['o']
    sl=zl*(1-sl_p); ta=ep*(1+max(0.02,atr_p*ACT_ATR_MUL)); hwm=ep; tr=False; pts=ep*(1-td)
    for k in range(ae+1,min(ae+25,n)):
        bk=daily[k]; bh=k-ae
        if bh>MIN_HOLD and tr and bk['l']<=pts: return (pts-ep)/ep*100,True,bh
        if bk['h']>hwm: hwm=bk['h']
        if not tr and hwm>=ta: tr=True
        if tr and bh>MIN_HOLD: pts=hwm*(1-td)
        if bk['l']<=sl: return (sl-ep)/ep*100,False,bh
    ek=min(ae+20,n-1); return (daily[ek]['c']-ep)/ep*100,daily[ek]['c']>ep,ek-ae

# ═══ MAIN ═══
print("="*80)
print("  SMC V8.1 — 全量 Stock×Time×Signal 交叉验证")
print("="*80)

picks_data = json.loads(PICKS_FILE.read_bytes())
all_picks = picks_data.get('picks',[])
picks_by_sym = defaultdict(list)
for p in all_picks:
    sym = p['symbol'].replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    picks_by_sym[sym].append(p)

stock_count = len(picks_by_sym)
print(f"  {stock_count} stocks, {len(all_picks)} picks")

# Results
per_stock_signal = defaultdict(lambda: defaultdict(list))      # sym→sig→[(pnl,won,hold,bar)]
per_stock_signal_h1 = defaultdict(lambda: defaultdict(list))   # first half
per_stock_signal_h2 = defaultdict(lambda: defaultdict(list))   # second half
per_stock_signal_bull = defaultdict(lambda: defaultdict(list)) # weekly bull
per_stock_signal_bear = defaultdict(lambda: defaultdict(list)) # weekly bear

t0=time.time(); processed=0; total=0

for sym, picks in picks_by_sym.items():
    daily = load_ohlcv(sym)
    if daily is None or len(daily)<100: continue
    n=len(daily); mid=n//2
    
    # Weekly regime
    weekly = load_weekly(sym)
    weekly_bull_bars = set()
    if weekly and len(weekly)>=20:
        for i, w in enumerate(weekly):
            if i>=19:
                ma20=sum(weekly[j]['c'] for j in range(i-19,i+1))/20
                if w['c']>ma20*1.02:
                    # Map weekly bar to daily bars (approximate: 5 daily per weekly)
                    for d in range(i*5, min((i+1)*5, n)):
                        weekly_bull_bars.add(d)
    
    sigs_by_type = defaultdict(list)
    for p in picks:
        sig=p.get('signal','?'); zb=p.get('zone_bar',0)
        zl=p.get('zone_low',p.get('entry_price',0)); em=p.get('entry_mode','immediate')
        if zl>0 and zb<n: sigs_by_type[sig].append((zb,zl,em))
    
    for sig, sigs in sigs_by_type.items():
        for zb, zl, em in sigs:
            r = sim(daily, zb, zl, em)
            if r:
                pnl,won,hold=r; total+=1
                per_stock_signal[sym][sig].append((pnl,won,hold,zb))
                if zb<mid: per_stock_signal_h1[sym][sig].append((pnl,won,hold,zb))
                else: per_stock_signal_h2[sym][sig].append((pnl,won,hold,zb))
                if zb in weekly_bull_bars: per_stock_signal_bull[sym][sig].append((pnl,won,hold,zb))
                else: per_stock_signal_bear[sym][sig].append((pnl,won,hold,zb))
    
    processed+=1
    if processed%500==0:
        print(f"  [{processed}/{stock_count}] {time.time()-t0:.0f}s trades={total:,}")

# ═══ Aggregate ═══
def agg(pnls):
    if not pnls: return {'n':0,'wr':0,'avg':0,'cum':0}
    n=len(pnls); wins=sum(1 for p in pnls if p[1])
    return {'n':n,'wr':round(wins/n*100,1),'avg':round(sum(p[0] for p in pnls)/n,2),'cum':round(sum(p[0] for p in pnls),2)}

# Per-stock best
stock_best={}
for sym,sigs in per_stock_signal.items():
    best_sig,best_score=None,-999
    for sig,pnls in sigs.items():
        a=agg(pnls)
        if a['n']>=2 and a['wr']>=50:
            sc=a['avg']*a['wr']/100*min(a['n'],15)
            if sc>best_score: best_score=sc; best_sig=sig
    if best_sig: stock_best[sym]={'best_signal':best_sig,'all':{sig:agg(p) for sig,p in sigs.items()},**agg(sigs[best_sig])}

# Time decay: H1 vs H2 per signal
signal_h1h2={}
for sig in SIGNAL_TYPES:
    h1=[]; h2=[]
    for sym in per_stock_signal_h1:
        h1.extend(per_stock_signal_h1[sym].get(sig,[]))
        h2.extend(per_stock_signal_h2[sym].get(sig,[]))
    signal_h1h2[sig]={'H1':agg(h1),'H2':agg(h2),
                      'decay':round(agg(h2)['avg']-agg(h1)['avg'],2) if agg(h1)['n']>=5 else 0}

# Regime: Bull vs Bear per signal
signal_regime={}
for sig in SIGNAL_TYPES:
    bull=[]; bear=[]
    for sym in per_stock_signal_bull:
        bull.extend(per_stock_signal_bull[sym].get(sig,[]))
        bear.extend(per_stock_signal_bear[sym].get(sig,[]))
    signal_regime[sig]={'bull':agg(bull),'bear':agg(bear),
                        'delta':round(agg(bull)['avg']-agg(bear)['avg'],2) if agg(bull)['n']>=5 else 0}

# ═══ Output ═══
output={'meta':{'version':'V8.1','date':time.strftime('%Y-%m-%d %H:%M'),
                'stocks':processed,'total_trades':total,'elapsed':round(time.time()-t0)},
        'stock_best':stock_best,
        'signal_h1h2':signal_h1h2,
        'signal_regime':signal_regime}

outf=OUT/'cross_validation_v81.json'
json.dump(output,open(outf,'w'),ensure_ascii=False)
print(f"\n  Output: {outf} ({outf.stat().st_size//1024}KB)")

# ═══ Report ═══
print(f"\n{'='*80}")
print(f"  SIGNAL TIME DECAY (H1→H2)")
print(f"{'='*80}")
print(f"  {'Signal':<32s} {'H1_n':>6s} {'H1_WR':>7s} {'H1_avg':>8s} {'H2_n':>6s} {'H2_WR':>7s} {'H2_avg':>8s} {'Decay':>8s}")
for sig,d in sorted(signal_h1h2.items()):
    h1=d['H1']; h2=d['H2']
    print(f"  {sig:<32s} {h1['n']:>6d} {h1['wr']:>6.1f}% {h1['avg']:>+7.2f}% {h2['n']:>6d} {h2['wr']:>6.1f}% {h2['avg']:>+7.2f}% {d['decay']:>+7.2f}%")

print(f"\n{'='*80}")
print(f"  SIGNAL BY MARKET REGIME (Weekly Bull vs Bear)")
print(f"{'='*80}")
print(f"  {'Signal':<32s} {'Bull_n':>6s} {'Bull_WR':>7s} {'Bull_avg':>8s} {'Bear_n':>6s} {'Bear_WR':>7s} {'Bear_avg':>8s} {'Δ':>8s}")
for sig,d in sorted(signal_regime.items()):
    b=d['bull']; be=d['bear']
    print(f"  {sig:<32s} {b['n']:>6d} {b['wr']:>6.1f}% {b['avg']:>+7.2f}% {be['n']:>6d} {be['wr']:>6.1f}% {be['avg']:>+7.2f}% {d['delta']:>+7.2f}%")

print(f"\n{'='*80}")
print(f"  PER-STOCK SIGNAL DISTRIBUTION ({len(stock_best)} stocks)")
print(f"{'='*80}")
dist=Counter(s['best_signal'] for s in stock_best.values())
for sig,cnt in dist.most_common():
    print(f"  {sig}: {cnt} ({cnt/len(stock_best)*100:.1f}%)")

# Top non-OB stocks  
non_ob=[(sym,s) for sym,s in stock_best.items() if 'OB_Bull' not in s['best_signal']]
print(f"\n  Non-OB best ({len(non_ob)} stocks):")
for sym,s in sorted(non_ob,key=lambda x:-x[1]['avg'])[:20]:
    print(f"  {sym:<12s} → {s['best_signal']:<30s} n={s['n']:>3d} WR={s['wr']:>5.1f}% avg={s['avg']:>+6.2f}%")

elapsed=time.time()-t0
print(f"\n{'='*80}")
print(f"  V8.1 Complete — {elapsed:.0f}s — {processed} stocks — {total:,} trades")
print(f"{'='*80}")
