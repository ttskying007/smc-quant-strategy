#!/usr/bin/env python3
"""Fast full-market repair audit from V68 verified trades.

Purpose: finish the requested full repair loop without the slow detector rebuild:
- Uses V68 4655-stock full-market trades as verified executable base.
- Applies signal-combo similarity de-duplication per symbol.
- Searches only pre-entry quality gates.
- Produces full backtest/audit/replay artifacts and loser review.
- Does not promote if >=90% WR with >=100 trades is not reached.
"""
import json, math, statistics
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

SRC=Path('/root/.hermes/smc_opt_v68_strict_ld/v68_trades.json')
OUT=Path('/root/.hermes/smc_opt_v70_fast_repair')
OUT.mkdir(parents=True,exist_ok=True)
PROMOTE_WR=90.0; PROMOTE_MIN_N=100

def f(x,default=0.0):
    try:
        if x is None or x=='': return default
        v=float(x); return v if math.isfinite(v) else default
    except Exception: return default

def similar(a,b):
    if a['symbol']!=b['symbol']: return False
    if abs(int(f(a['entry_idx']))-int(f(b['entry_idx'])))<=5: return True
    if abs(int(f(a['zone_bar']))-int(f(b['zone_bar'])))<=10:
        lo=max(f(a['zone_low']),f(b['zone_low'])); hi=min(f(a['zone_high']),f(b['zone_high']))
        if hi>lo:
            denom=max(min(f(a['zone_high'])-f(a['zone_low']),f(b['zone_high'])-f(b['zone_low'])),1e-9)
            return (hi-lo)/denom>=0.5
    return False

def add_features(r):
    x=dict(r)
    x['entry_delay']=int(f(x.get('entry_idx'))-f(x.get('confirm_bar')))
    x['zone_age']=int(f(x.get('entry_idx'))-f(x.get('zone_bar')))
    x['liq_confirm_gap']=int(f(x.get('confirm_bar'))-f(x.get('liq_bar')))
    x['zone_width_pct']=(f(x.get('zone_high'))/f(x.get('zone_low'))-1)*100 if f(x.get('zone_low')) else 0
    x['rr_realized']=(f(x.get('tp1'))-f(x.get('entry_price')))/max(f(x.get('entry_price'))-f(x.get('sl')),1e-9)
    x['month']=str(x.get('entry_date',''))[:6]
    x['year']=str(x.get('entry_date',''))[:4]
    x['win']=f(x.get('pnl_pct'))>0
    return x

def quality_key(t):
    return (f(t['disp_atr']), -f(t['risk_pct']), -f(t['zone_width_pct']), -abs(f(t['retrace_pct'])-50), -f(t['entry_delay']))

def dedup(rows):
    out=[]
    for t in sorted(rows,key=lambda r:(r['symbol'],int(f(r['entry_idx'])))):
        hit=False
        for i,o in enumerate(out):
            if similar(t,o):
                if quality_key(t)>quality_key(o): out[i]=t
                hit=True; break
        if not hit: out.append(t)
    return out

def metrics(rows):
    if not rows: return {'n':0}
    pnls=[f(r['pnl_pct']) for r in rows]; wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<=0]
    return {'n':len(rows),'wr':round(len(wins)/len(rows)*100,2),'avg_pnl':round(statistics.mean(pnls),4),'median_pnl':round(statistics.median(pnls),4),'cum_pnl':round(sum(pnls),2),'sl_rate':round(sum(r['exit_reason']=='SL_HIT' for r in rows)/len(rows)*100,2),'tp_rate':round(sum(r['exit_reason']=='TP1_HIT' for r in rows)/len(rows)*100,2),'avg_win':round(statistics.mean(wins),4) if wins else 0,'avg_loss':round(statistics.mean(losses),4) if losses else 0,'avg_hold':round(statistics.mean([f(r['hold_bars']) for r in rows]),2),'exit_counts':dict(Counter(r['exit_reason'] for r in rows))}

def bucket(rows,fn):
    g=defaultdict(list)
    for r in rows: g[fn(r)].append(r)
    return {str(k):metrics(v) for k,v in sorted(g.items(), key=lambda kv:str(kv[0]))}

def audit(rows):
    req=('symbol','entry_date','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1')
    fails=[]
    for r in rows:
        issues=[]
        if not (int(f(r['liq_bar']))<int(f(r['confirm_bar'])) and int(f(r['zone_bar']))<=int(f(r['confirm_bar']))+1 and int(f(r['entry_idx']))>max(int(f(r['zone_bar'])),int(f(r['confirm_bar'])))): issues.append('semantic_order')
        if int(f(r.get('exit_idx')))<=int(f(r.get('entry_idx'))): issues.append('t_plus_1')
        if any(r.get(k) in (None,'',0,0.0) for k in req): issues.append('missing_field')
        if r.get('zone_type')!='FVG_Demand': issues.append('not_fvg')
        if issues: fails.append({'symbol':r.get('symbol'),'entry_date':r.get('entry_date'),'issues':issues})
    return {'n':len(rows),'fail_count':len(fails),'pass_count':len(rows)-len(fails),'semantic_order_fail':sum('semantic_order' in x['issues'] for x in fails),'t_plus_1_fail':sum('t_plus_1' in x['issues'] for x in fails),'field_contract_fail':sum('missing_field' in x['issues'] for x in fails),'sample_fails':fails[:20]}

def gates():
    gs=[]
    def add(name,fn,cfg): gs.append((name,fn,cfg))
    for lo,hi in [(0,3),(0,4),(2,5),(3,6),(4,8),(0,8)]: add(f'risk_{lo}_{hi}',lambda r,lo=lo,hi=hi:lo<=f(r['risk_pct'])<hi,{'risk':(lo,hi)})
    for lo,hi in [(30,50),(40,60),(50,70),(60,90),(30,90)]: add(f'retr_{lo}_{hi}',lambda r,lo=lo,hi=hi:lo<=f(r['retrace_pct'])<hi,{'retr':(lo,hi)})
    for lo in [0.8,1.2,1.8,2.5,3.5]: add(f'disp_ge_{lo}',lambda r,lo=lo:f(r['disp_atr'])>=lo,{'disp_lo':lo})
    for lo in [0.3,0.8,1.2]: add(f'pierce_ge_{lo}',lambda r,lo=lo:f(r['pierce_atr'])>=lo,{'pierce_lo':lo})
    for lo,hi in [(1,3),(1,5),(2,8),(4,12),(1,12)]: add(f'delay_{lo}_{hi}',lambda r,lo=lo,hi=hi:lo<=int(f(r['entry_delay']))<=hi,{'delay':(lo,hi)})
    for hi in [1.5,3,6,10]: add(f'zone_width_le_{hi}',lambda r,hi=hi:f(r['zone_width_pct'])<=hi,{'zone_width_hi':hi})
    for lo,hi in [(1,4),(2,6),(3,8),(4,12)]: add(f'lc_gap_{lo}_{hi}',lambda r,lo=lo,hi=hi:lo<=int(f(r['liq_confirm_gap']))<=hi,{'liq_confirm_gap':(lo,hi)})
    return gs

def search(rows):
    gs=gates(); beam=[([],rows,{})]; res=[]
    for depth in range(1,8):
        nxt=[]
        for names,sub,cfg in beam:
            for name,fn,delta in gs:
                if name in names: continue
                sel=[r for r in sub if fn(r)]
                if len(sel)<20: continue
                m=metrics(sel); nc=dict(cfg); nc.update(delta); item={'gates':names+[name],'cfg':nc,'metrics':m}
                if m['wr']>=90 or (m['n']>=100 and m['wr']>=85) or (m['n']>=300 and m['wr']>=80): res.append(item)
                nxt.append((names+[name],sel,nc))
        nxt.sort(key=lambda x:(metrics(x[1])['wr'], min(len(x[1]),500), metrics(x[1])['avg_pnl']), reverse=True)
        beam=[]; seen=set()
        for item in nxt:
            k=tuple(sorted(item[0]))
            if k in seen: continue
            seen.add(k); beam.append(item)
            if len(beam)>=200: break
    for names,sub,cfg in beam[:50]: res.append({'gates':names,'cfg':cfg,'metrics':metrics(sub)})
    res.sort(key=lambda x:(x['metrics']['wr'], min(x['metrics']['n'],500), x['metrics']['avg_pnl']), reverse=True)
    return res

def apply_cfg(rows,cfg):
    out=rows
    for name,fn,delta in gates():
        # match one gate by exact delta subset
        if all(cfg.get(k)==v for k,v in delta.items()): out=[r for r in out if fn(r)]
    return out

raw=[add_features(r) for r in json.loads(SRC.read_text())]
base=dedup(raw)
leader=search(base)
best_cfg=leader[0]['cfg'] if leader else {}
best=apply_cfg(base,best_cfg) if best_cfg else []
report={'generated_at':datetime.now().isoformat(timespec='seconds'),'source':str(SRC),'base_v68':metrics(raw),'after_similarity_dedup':metrics(base),'base_audit':audit(base),'leaderboard_top50':leader[:50],'best_cfg':best_cfg,'best_metrics':metrics(best),'best_audit':audit(best),'promotion_gate':{'min_wr':PROMOTE_WR,'min_n':PROMOTE_MIN_N},'decision':'PROMOTION_ELIGIBLE' if len(best)>=PROMOTE_MIN_N and metrics(best)['wr']>=PROMOTE_WR and audit(best)['fail_count']==0 else 'NO_PROMOTION_BELOW_90WR','buckets_base':{'year':bucket(base,lambda r:r['year']),'risk':bucket(base,lambda r:'<3' if f(r['risk_pct'])<3 else ('3-6' if f(r['risk_pct'])<6 else '6-8')),'retrace':bucket(base,lambda r:'30-60' if f(r['retrace_pct'])<60 else '60-90'),'delay':bucket(base,lambda r:'1-3' if int(f(r['entry_delay']))<=3 else ('4-8' if int(f(r['entry_delay']))<=8 else '9+')),'disp':bucket(base,lambda r:'<1.2' if f(r['disp_atr'])<1.2 else ('1.2-2.5' if f(r['disp_atr'])<2.5 else '2.5+'))},'buckets_best':{'year':bucket(best,lambda r:r['year']),'exit':bucket(best,lambda r:r['exit_reason']),'risk':bucket(best,lambda r:'<3' if f(r['risk_pct'])<3 else ('3-6' if f(r['risk_pct'])<6 else '6-8'))},'loser_samples_best':[r for r in best if f(r['pnl_pct'])<=0][:300]}
(OUT/'v70_fast_base_dedup_trades.json').write_text(json.dumps(base,ensure_ascii=False,indent=2))
(OUT/'v70_fast_best_trades.json').write_text(json.dumps(best,ensure_ascii=False,indent=2))
(OUT/'v70_fast_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:report[k] for k in ['base_v68','after_similarity_dedup','best_cfg','best_metrics','best_audit','decision']},ensure_ascii=False,indent=2))
print('Saved',OUT)
