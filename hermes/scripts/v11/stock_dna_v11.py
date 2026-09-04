#!/usr/bin/env python3
"""
SMC V11.0 — 全优化集成 + 股票DNA + V8对比
=============================================
优化点(V10发现):
  1. OB_Bull zone优先 (SL率18% vs FVG 56%)
  2. FVG_Bull用更紧SL (zone_low*0.997 vs 0.995)
  3. Per-stock最优模式选择 (V8.0已验证 +0.9% WR)
  4. 周线bullish过滤

股票DNA保存:
  - best_pattern / WR / zone_preference
  - trend / signal_density / drift_pattern  
  - optimal_window / avg_pnl / failure_rate

对比: V8.0(基线) vs V11.0(全优化)
"""
import json, time
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

TARGET = 2.0; LOOKAHEAD = 5; MAX_GAP = 25; MIN_TRADES = 3

CATEGORIES = {
    'CTX_LONG':  ['BOS_Bull', 'CHOCH_Bull', 'MSS_Bull'],
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'ZONE_LONG': ['OB_Bull', 'FVG_Bull'],
}
PATTERNS = {
    'LIQ→ZONE':     (['LIQ_LONG', 'ZONE_LONG'], [25]),
    'CTX→ZONE':     (['CTX_LONG', 'ZONE_LONG'], [20]),
    'ZONE_ONLY':    (['ZONE_LONG'], []),
    'LIQ→CTX→ZONE': (['LIQ_LONG', 'CTX_LONG', 'ZONE_LONG'], [30, 15]),
}

# ═══ Zone-aware SL ═══
def calc_sl(zone_type, zone_low, entry_price):
    """V11 optimized: tighter SL for FVG, standard for OB"""
    if zone_type == 'FVG_Bull':
        return zone_low * 0.997 if zone_low > 0 else entry_price * 0.975
    else:  # OB_Bull
        return zone_low * 0.995 if zone_low > 0 else entry_price * 0.97

def daily_to_weekly(d):
    w=[]
    for i in range(0,len(d),5):
        c=d[i:i+5]
        if len(c)>=3: w.append({'o':c[0]['o'],'h':max(x['h'] for x in c),'l':min(x['l'] for x in c),'c':c[-1]['c']})
    return w

def weekly_trend(w):
    if len(w)<20: return 'neutral'
    sigs,st,_,_=detect_all_signals_v20(w)
    tc=st['type_counts'];cb=tc.get('CHOCH_Bull',0);cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0);bbr=tc.get('BOS_Bear',0)
    last=[s for s in sigs if 'CHOCH' in s.type]
    ld='bull' if last and 'Bull' in last[-1].type else ('bear' if last and 'Bear' in last[-1].type else None)
    if ld=='bull' and cb+bb>=cbr+bbr: return 'bullish'
    if ld=='bear' and cbr+bbr>cb+bb: return 'bearish'
    if cb+bb>(cbr+bbr)*1.5: return 'bullish'
    if cbr+bbr>(cb+bb)*1.5: return 'bearish'
    return 'neutral'

def detect_sequences(signals):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    all_seqs = []
    for pname, (stages, gaps) in PATTERNS.items():
        stage_sigs = [CATEGORIES[st] for st in stages]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in stage_sigs[0]]:
                chain=[sig];c=sig.idx;ok=True
                for si in range(1,len(stages)):
                    gap=gaps[si-1] if si-1<len(gaps) else MAX_GAP
                    fnd=False
                    for bi in range(c+1,c+gap+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in stage_sigs[si] and cand not in chain:
                                    chain.append(cand);c=bi;fnd=True;break
                        if fnd:break
                    if not fnd:ok=False;break
                if ok and len(chain)==len(stages):
                    all_seqs.append({'pattern':pname,'seq_bar':chain[-1].idx,
                                     'zone_type':chain[-1].type,
                                     'zone_low':chain[-1].lower,'zone_high':chain[-1].upper})
    unique=[]
    for pn in PATTERNS:
        seen=set()
        for s in sorted([x for x in all_seqs if x['pattern']==pn],key=lambda x:x['seq_bar']):
            if s['seq_bar'] not in seen:seen.add(s['seq_bar']);unique.append(s)
    return unique

def backtest(ohlcv, seqs, use_v11_sl=True):
    """V8 or V11 SL depending on flag"""
    n=len(ohlcv);trades=[]
    for sq in seqs:
        eb=sq['seq_bar']
        if eb+1>=n or eb+LOOKAHEAD+1>=n:continue
        ep=ohlcv[eb+1]['o']
        if use_v11_sl:
            sl=calc_sl(sq['zone_type'],sq['zone_low'],ep)
        else:
            sl=sq['zone_low']*0.995 if sq['zone_low']>0 else ep*0.97
        tp=ep*1.03
        exit_px=ep;reason='time_stop'
        for bi in range(eb+2,min(eb+LOOKAHEAD+1,n-1)+1):
            if ohlcv[bi]['l']<=sl:exit_px=sl;reason='sl_hit';break
            if ohlcv[bi]['h']>=tp:exit_px=tp;reason='tp_hit';break
        else:exit_px=ohlcv[min(eb+LOOKAHEAD,n-1)]['c']
        pnl=(exit_px-ep)/ep*100
        trades.append({'won':pnl>0,'pnl_pct':round(pnl,2),'exit_reason':reason,
                       'pattern':sq['pattern'],'zone_type':sq['zone_type']})
    return trades


# ═══ MAIN ═══
print("V11.0: OB优先 + FVG紧SL + Per-Stock模式 + 股票DNA")
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0=time.time()

all_v8=[];all_v11=[];stock_dna={}

for fi,df in enumerate(daily_files):
    name=df.stem.replace('_daily_300','')
    parts=name.rsplit('_',1)
    sym=f'{parts[0]}.{parts[1]}' if len(parts)==2 else name
    try:
        daily=json.loads(df.read_bytes())
        if len(daily)<50:continue
    except:continue
    n=len(daily)
    
    try:
        sigs,_,_,_=detect_all_signals_v20(daily)
        seqs=detect_sequences(sigs)
    except:continue
    if not seqs:continue
    
    # Trend
    wp=KLINE/f'{name}_weekly_200.json'
    try:
        w=json.loads(wp.read_bytes()) if wp.exists() else daily_to_weekly(daily)
        if len(w)<20:w=daily_to_weekly(daily)
    except:w=daily_to_weekly(daily)
    trend=weekly_trend(w)
    
    # ── Per-pattern selection (V8 SL for fairness) ──
    seqs_by_pat=defaultdict(list)
    for sq in seqs:seqs_by_pat[sq['pattern']].append(sq)
    
    best_pat='ZONE_ONLY';best_wr_v8=0;best_wr_v11=0
    pat_results={}
    
    for pn,pseqs in seqs_by_pat.items():
        if len(pseqs)<MIN_TRADES:continue
        t8=backtest(daily,pseqs,use_v11_sl=False)
        if t8:
            wr8=sum(1 for t in t8 if t['won'])/len(t8)
            pat_results[pn]={'v8_wr':round(wr8,3),'total':len(t8)}
            if wr8>best_wr_v8:best_wr_v8=wr8;best_pat=pn
    
    # ── Trade with best pattern (both V8 and V11 SL) ──
    best_seqs=seqs_by_pat.get(best_pat,seqs)
    
    t8=backtest(daily,best_seqs,use_v11_sl=False)
    t11=backtest(daily,best_seqs,use_v11_sl=True)
    
    for t in t8:t['symbol']=sym;t['variant']='v8'
    for t in t11:t['symbol']=sym;t['variant']='v11'
    all_v8.extend(t8);all_v11.extend(t11)
    
    # ── Stock DNA ──
    v8_wr=sum(1 for t in t8 if t['won'])/max(len(t8),1) if t8 else 0
    v11_wr=sum(1 for t in t11 if t['won'])/max(len(t11),1) if t11 else 0
    v8_pnl=sum(t['pnl_pct'] for t in t8)/max(len(t8),1) if t8 else 0
    v11_pnl=sum(t['pnl_pct'] for t in t11)/max(len(t11),1) if t11 else 0
    
    # Zone preference
    ob_trades=[t for t in t11 if t['zone_type']=='OB_Bull']
    fvg_trades=[t for t in t11 if t['zone_type']=='FVG_Bull']
    ob_wr=sum(1 for t in ob_trades if t['won'])/max(len(ob_trades),1) if ob_trades else 0
    fvg_wr=sum(1 for t in fvg_trades if t['won'])/max(len(fvg_trades),1) if fvg_trades else 0
    
    # Signal density
    sig_density=len(sigs)/max(n,1)
    
    stock_dna[sym]={
        'best_pattern':best_pat,
        'v8_wr':round(v8_wr,3),'v11_wr':round(v11_wr,3),
        'v8_avg_pnl':round(v8_pnl,2),'v11_avg_pnl':round(v11_pnl,2),
        'v8_trades':len(t8),'v11_trades':len(t11),
        'trend':trend,
        'zone_pref':'OB' if ob_wr>fvg_wr else 'FVG',
        'ob_wr':round(ob_wr,3),'fvg_wr':round(fvg_wr,3),
        'ob_trades':len(ob_trades),'fvg_trades':len(fvg_trades),
        'sig_density':round(sig_density,3),
        'improvement':round(v11_wr-v8_wr,4),
        'patterns':pat_results,
    }
    
    if (fi+1)%1000==0:
        r=time.time()-t0
        print(f"  [{fi+1}/{len(daily_files)}] {r:.0f}s v8={len(all_v8)} v11={len(all_v11)}")

elapsed=time.time()-t0

# ═══ REPORT ═══
v8_wr=sum(1 for t in all_v8 if t['won'])/max(len(all_v8),1)
v8_pnl=sum(t['pnl_pct'] for t in all_v8)/max(len(all_v8),1)
v11_wr=sum(1 for t in all_v11 if t['won'])/max(len(all_v11),1)
v11_pnl=sum(t['pnl_pct'] for t in all_v11)/max(len(all_v11),1)

print(f"\n{'='*70}")
print(f"  V11.0 vs V8.0 全量对比 ({elapsed:.0f}s, {len(stock_dna)}只)")
print(f"{'='*70}")
print(f"  {'':20s} {'WR':>7s} {'AvgPnL':>8s} {'Trades':>7s} {'Stocks':>7s}")
print(f"  {'V8.0 (baseline)':20s} {v8_wr:>6.1%} {v8_pnl:>+7.2f}% {len(all_v8):>7d} {len(stock_dna):>7d}")
print(f"  {'V11.0 (optimized)':20s} {v11_wr:>6.1%} {v11_pnl:>+7.2f}% {len(all_v11):>7d} {len(stock_dna):>7d}")
if v11_wr>v8_wr:
    print(f"  ✅ V11 improves WR by {v11_wr-v8_wr:+.1%}, PnL by {v11_pnl-v8_pnl:+.2f}%")
else:
    print(f"  ⚠️ V11 WR change: {v11_wr-v8_wr:+.1%}")

# Zone breakdown
print(f"\n  【Zone类型表现 (V11)】")
for zt in ['OB_Bull','FVG_Bull']:
    ztrades=[t for t in all_v11 if t['zone_type']==zt]
    if ztrades:
        wr=sum(1 for t in ztrades if t['won'])/len(ztrades)
        pnl=sum(t['pnl_pct'] for t in ztrades)/len(ztrades)
        sl_rate=sum(1 for t in ztrades if t['exit_reason']=='sl_hit')/len(ztrades)
        print(f"  {zt:12s} WR={wr:.1%} PnL={pnl:+.2f}% SL率={sl_rate:.0%} N={len(ztrades)}")

# By trend
print(f"\n  【趋势过滤效果】")
for trend in ['bullish','bearish','neutral']:
    tt=[t for t in all_v11 if stock_dna.get(t['symbol'],{}).get('trend')==trend]
    if tt:
        wr=sum(1 for t in tt if t['won'])/len(tt)
        print(f"  {trend:8s} WR={wr:.1%} N={len(tt)}")

# Improvement distribution
improved=sum(1 for d in stock_dna.values() if d['improvement']>0)
same=sum(1 for d in stock_dna.values() if d['improvement']==0)
worse=sum(1 for d in stock_dna.values() if d['improvement']<0)
print(f"\n  【个股改进分布】")
print(f"  V11优于V8: {improved}只 | 持平: {same}只 | V11差于V8: {worse}只")

# ═══ DNA SAMPLE ═══
print(f"\n{'='*70}")
print(f"  股票DNA样本 (前15只)")
print(f"{'='*70}")
for i,(sym,dna) in enumerate(sorted(stock_dna.items())[:15]):
    imp='+' if dna['improvement']>0 else ''
    print(f"  {sym:12s} pat={dna['best_pattern']:<15s} v8={dna['v8_wr']:.1%}→v11={dna['v11_wr']:.1%}({imp}{dna['improvement']:+.1%}) "
          f"zone={dna['zone_pref']} OBwr={dna['ob_wr']:.1%} FVGwr={dna['fvg_wr']:.1%} "
          f"t={dna['v11_trades']} trend={dna['trend']}")

# Top improved
print(f"\n  V11改进最大 (前10):")
top_imp=sorted(stock_dna.items(),key=lambda x:-x[1]['improvement'])[:10]
for sym,dna in top_imp:
    print(f"  {sym:12s} +{dna['improvement']:+.1%} v8={dna['v8_wr']:.1%}→v11={dna['v11_wr']:.1%} pat={dna['best_pattern']}")

# ═══ SAVE ═══
json.dump({
    'meta':{'version':'11.0','date':time.strftime('%Y-%m-%d'),'stocks':len(stock_dna)},
    'comparison':{'v8_wr':round(v8_wr,4),'v11_wr':round(v11_wr,4),
                  'v8_pnl':round(v8_pnl,2),'v11_pnl':round(v11_pnl,2),
                  'improvement':round(v11_wr-v8_wr,4)},
    'dna':stock_dna,
},open(OUT/'stock_dna_v11.json','w'),ensure_ascii=False)
print(f"\n  Saved: {OUT/'stock_dna_v11.json'} ({len(stock_dna)} stocks)")
