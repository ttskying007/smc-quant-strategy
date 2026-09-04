#!/usr/bin/env python3
"""V568 one frozen strict-T+1 replay for V566 after independent identity pass."""
from __future__ import annotations
import csv, gzip, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; DAILY=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/daily'
V566=AUD/'v566_daily_hl_opening_bsl_acceptance_retest_seed_latest.json'; V567=AUD/'v567_v566_independent_identity_oracle_latest.json'
OUT=AUD/f'v568_v566_frozen_strict_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v568_v566_frozen_strict_t1_replay_latest.json'; FEE=0.20; HOLD=20
GATE={'n_min':1000,'year_n_min':300,'wr_pct_min':55.0,'avg_net_pct_min':0.5,'pf_min':1.15,'payoff_min':0.7,'every_year_avg_net_positive':True,'t1_violations':0}

def f(x:Any)->float|None:
    try:
        v=float(x); return v if math.isfinite(v) and v>0 else None
    except (TypeError,ValueError): return None

def bars(sym:str)->list[dict[str,Any]]:
    try:
        with gzip.open(DAILY/f'{sym.replace(".","_")}_daily.json.gz','rt',encoding='utf-8') as h: raw=json.load(h)
    except (OSError,ValueError): return []
    out=[]
    for x in raw if isinstance(raw,list) else []:
        d=str(x.get('d') or x.get('t') or '')[:8]; z=[f(x.get(k)) for k in ('o','h','l','c')]
        if len(d)==8 and all(q is not None for q in z): out.append({'d':d,'o':z[0],'h':z[1],'l':z[2],'c':z[3]})
    return sorted(out,key=lambda x:x['d'])

def confirmed_highs(xs:list[dict[str,Any]])->list[tuple[int,int,float]]:
    out=[]
    for i in range(3,len(xs)-3):
        if xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4]):out.append((i,i+3,xs[i]['h']))
    return out

def target_for(xs:list[dict[str,Any]],signal_i:int,entry:float,stop:float)->float|None:
    # All target pivots and their non-consumption proof are visible at signal close.
    rr_floor=entry+(entry-stop)*1.5
    cands=[]
    for pivot,confirm,price in confirmed_highs(xs):
        if confirm>signal_i or price<rr_floor:continue
        if any(x['h']>=price for x in xs[confirm+1:signal_i+1]):continue
        cands.append(price)
    return min(cands) if cands else None

def close_trade(xs:list[dict[str,Any]],entry_i:int,entry:float,stop:float,target:float)->dict[str,Any]:
    # entry_i is D+1. Start exit checks D+2: no same-day A-share sell.
    last=min(len(xs)-1,entry_i+HOLD)
    for i in range(entry_i+1,last+1):
        b=xs[i]
        if b['o']<=stop:return {'exit_i':i,'exit_date':b['d'],'exit_price':b['o'],'exit_reason':'SL_GAP_T1'}
        if b['o']>=target:return {'exit_i':i,'exit_date':b['d'],'exit_price':b['o'],'exit_reason':'TP_GAP_T1'}
        if b['l']<=stop and b['h']>=target:return {'exit_i':i,'exit_date':b['d'],'exit_price':stop,'exit_reason':'SL_TP_COLLISION_CONSERVATIVE_T1'}
        if b['l']<=stop:return {'exit_i':i,'exit_date':b['d'],'exit_price':stop,'exit_reason':'SL_T1'}
        if b['h']>=target:return {'exit_i':i,'exit_date':b['d'],'exit_price':target,'exit_reason':'TP_STRUCTURAL_T1'}
    b=xs[last];return {'exit_i':last,'exit_date':b['d'],'exit_price':b['c'],'exit_reason':'TIME20'}

def metrics(rows:list[dict[str,Any]])->dict[str,Any]:
    if not rows:return {'n':0,'wr_pct':0.0,'avg_net_pct':0.0,'profit_factor':0.0,'payoff':0.0}
    p=[r['net_pnl_pct'] for r in rows]; wins=[x for x in p if x>0]; losses=[x for x in p if x<=0]
    gain=sum(wins); loss=abs(sum(losses));return {'n':len(rows),'wr_pct':round(100*len(wins)/len(rows),4),'avg_net_pct':round(mean(p),4),'profit_factor':round(gain/loss,4) if loss else None,'payoff':round(mean(wins)/abs(mean(losses)),4) if wins and losses else None,'total_net_pct':round(sum(p),4),'avg_win_pct':round(mean(wins),4) if wins else None,'avg_loss_pct':round(mean(losses),4) if losses else None}

def main()->None:
    check=json.loads(V567.read_text())
    if check['decision']!='V567_IDENTITY_PASS__ONE_FROZEN_STRICT_T1_REPLAY_AUTHORIZED':raise RuntimeError('V567 identity gate not passed')
    meta=json.loads(V566.read_text()); seed=Path(meta['artifacts']['seeds'])
    with seed.open(newline='',encoding='utf-8') as h: seeds=list(csv.DictReader(h))
    bysym=defaultdict(list)
    for r in seeds:bysym[r['symbol']].append(r)
    OUT.mkdir(parents=True,exist_ok=False); rows=[]; skipped=Counter(); t1=0
    for n,(sym,items) in enumerate(sorted(bysym.items()),1):
        xs=bars(sym); ix={x['d']:i for i,x in enumerate(xs)}; busy_until=-1
        for seedrow in sorted(items,key=lambda r:(r['eligible_entry_date'],r['signal_date'])):
            signal_i=ix.get(seedrow['signal_date']); entry_i=ix.get(seedrow['eligible_entry_date'])
            if signal_i is None or entry_i is None or entry_i!=signal_i+1:skipped['NO_EXACT_NEXT_DAILY_OPEN']+=1;continue
            if entry_i<=busy_until:skipped['SERIAL_SYMBOL_POSITION_OPEN']+=1;continue
            if entry_i+1>=len(xs):skipped['NO_T1_FORWARD_BAR']+=1;continue
            entry=xs[entry_i]['o']; stop=float(seedrow['bsl_retest_low'])*.997
            if not (0<stop<entry):skipped['INVALID_STRUCTURAL_STOP']+=1;continue
            target=target_for(xs,signal_i,entry,stop)
            if target is None:skipped['NO_UNCONSUMED_PREENTRY_TARGET_RR_1_5']+=1;continue
            result=close_trade(xs,entry_i,entry,stop,target)
            if result['exit_i']<=entry_i:t1+=1;raise RuntimeError('T+1 violation')
            busy_until=result['exit_i']; net=(result['exit_price']/entry-1)*100-FEE
            rows.append({'symbol':sym,'signal_date':seedrow['signal_date'],'entry_date':xs[entry_i]['d'],'entry_price':round(entry,8),'stop_price':round(stop,8),'target_price':round(target,8),'planned_rr':round((target-entry)/(entry-stop),6),'exit_date':result['exit_date'],'exit_price':round(result['exit_price'],8),'exit_reason':result['exit_reason'],'hold_bars':result['exit_i']-entry_i,'net_pnl_pct':round(net,6),'execution_contract':'D_PLUS_1_OPEN__M15_RETEST_LOW_0P3PCT_SL__PREENTRY_UNCONSUMED_DAILY_SWING_TP__STRICT_T1__TIME20__FEE0P2'})
        if n%1000==0:print(json.dumps({'symbols':n,'closed_trades':len(rows)}),flush=True)
    total=metrics(rows); yearly={y:metrics([r for r in rows if r['entry_date'].startswith(y)]) for y in ('2025','2026')}; exits=Counter(r['exit_reason'] for r in rows)
    checks={'n>=1000':total['n']>=GATE['n_min'],'each_year_n>=300':all(yearly[y]['n']>=GATE['year_n_min'] for y in yearly),'wr>=55':total['wr_pct']>=GATE['wr_pct_min'],'avg_net>=0.5':total['avg_net_pct']>=GATE['avg_net_pct_min'],'pf>=1.15':total['profit_factor'] is not None and total['profit_factor']>=GATE['pf_min'],'payoff>=0.7':total['payoff'] is not None and total['payoff']>=GATE['payoff_min'],'each_year_avg_net>0':all(yearly[y]['avg_net_pct']>0 for y in yearly),'t1_violations==0':t1==0}
    trades=OUT/'v568_frozen_t1_trades.csv'; fields=list(rows[0]) if rows else ['symbol']
    with trades.open('w',newline='',encoding='utf-8') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    rep={'version':'V568_V566_FROZEN_STRICT_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_contract':'V566 frozen seeds after V567 exact independent identity pass; same-source Sina raw daily exits only.','frozen_execution_contract':'entry=D+1 open; SL=M15 BSL-retest low*0.997; TP=nearest pre-signal confirmed and unconsumed daily 3L/3R high with RR>=1.5; exits start D+2; gap-aware; same-bar collision=SL; time20; fee=0.20%; serial symbol positions.','seed_count':len(seeds),'closed_trade_count':len(rows),'skip_counts':dict(skipped),'overall':total,'yearly':yearly,'exit_reason_counts':dict(exits),'promotion_gate':GATE,'promotion_checks':checks,'invariants':{'oracle_identity_pass':True,'all_targets_preentry':all(r['planned_rr']>=1.5 for r in rows),'t1_violations':t1,'all_writes_false':True,'search_count':1},'decision':'V568_RESEARCH_GATE_PASS__INDEPENDENT_METRIC_AUDIT_REQUIRED' if all(checks.values()) else 'V568_FROZEN_REPLAY_GATE_FAIL__CLOSE_V566_ONTOLOGY_NO_VARIANTS','artifacts':{'out_dir':str(OUT),'trades':str(trades),'latest':str(LATEST),'v566':str(V566),'v567':str(V567)}}
    text=json.dumps(rep,ensure_ascii=False,indent=2);(OUT/'v568_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
