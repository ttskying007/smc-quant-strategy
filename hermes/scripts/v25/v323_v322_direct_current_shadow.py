#!/usr/bin/env python3
"""V323 no-write shadow materialization for V322 current direct rows.

V322 found exactly one non-overlap current-actionable row if the historically
validated V246 industry addback is applied directly to V164 scanner BUY rows.
This script materializes it as SHADOW_ONLY and runs executable T+1 status replay.
It does not claim production promotion.
"""
from __future__ import annotations

import json, math
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes')
AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
V322=AUD/'v322_current_scanner_contract_recompute_latest.json'
OUT=AUD/f"v323_v322_direct_current_shadow_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST=AUD/'v323_v322_direct_current_shadow_latest.json'

def sf(x:Any, default=None):
    try:
        if x in (None,''): return default
        v=float(x); return default if math.isnan(v) or math.isinf(v) else v
    except Exception: return default

def dkey(v:Any)->str:
    s=''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s)>=8 else ''

def load_json(p:Path, default:Any):
    try: return json.loads(p.read_text())
    except Exception: return default

def load_bars(sym:str):
    if not sym or '.' not in sym: return []
    code,ex=sym.split('.')
    p=KDIR/f'{code}_{ex}_daily_750.json'
    data=load_json(p,[])
    out=[]
    for b in data if isinstance(data,list) else []:
        t=dkey(b.get('t') or b.get('date') or b.get('day'))
        o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
        if t and None not in (o,h,l,c): out.append({'t':t,'o':o,'h':h,'l':l,'c':c})
    return sorted(out,key=lambda x:x['t'])

def pct(a,b): return None if a is None or b in (None,0) else (a/b-1)*100

def replay_status(r:dict[str,Any]):
    sym=str(r.get('symbol') or ''); ed=dkey(r.get('entry_date'))
    entry=sf(r.get('entry_price')) or sf(r.get('price'))
    sl=sf(r.get('sl')) or sf(r.get('sl_price'))
    if not sl:
        zl=sf(r.get('zone_low') or r.get('dz_low'))
        sl=zl*0.99 if zl else None
    if not entry or not sl or sl>=entry: return {'status':'INVALID_CONTRACT'}
    risk=entry-sl; tp=entry+risk*1.5
    bars=load_bars(sym); idx=next((i for i,b in enumerate(bars) if b['t']==ed),None)
    if idx is None: return {'status':'NO_KLINE_ENTRY_DATE'}
    best=-1e18; worst=1e18
    max_hold=10
    path=bars[idx+1:min(len(bars),idx+1+max_hold)]
    for i,b in enumerate(path,1):
        best=max(best,b['h']); worst=min(worst,b['l'])
        if b['o']<=sl:
            return finish('GAP_SL','CLOSED',b,b['o'],entry,sl,tp,i,best,worst,risk)
        if b['l']<=sl:
            return finish('SL','CLOSED',b,sl,entry,sl,tp,i,best,worst,risk)
        if b['h']>=tp:
            return finish('TP','CLOSED',b,tp,entry,sl,tp,i,best,worst,risk)
    if len(path)>=max_hold:
        b=path[-1]; best=max(best,b['h']); worst=min(worst,b['l'])
        return finish('TIME','CLOSED',b,b['c'],entry,sl,tp,len(path),best,worst,risk)
    if path:
        b=path[-1]; best=max(best,b['h']); worst=min(worst,b['l'])
        return finish('OPEN_MARK','OPEN',b,b['c'],entry,sl,tp,len(path),best,worst,risk)
    return {'status':'PENDING_T1','entry_price':entry,'sl':sl,'tp':tp}

def finish(reason,status,b,price,entry,sl,tp,hold,best,worst,risk):
    return {'status':status,'exit_reason':reason,'mark_date':b['t'],'mark_price':round(price,4),'entry_price':round(entry,4),'sl':round(sl,4),'tp':round(tp,4),'hold_bars':hold,'pnl_pct':round(pct(price,entry),4),'mfe_pct':round(pct(best,entry),4),'mae_pct':round(pct(worst,entry),4),'mfe_r':round((best-entry)/risk,4),'mae_r':round((worst-entry)/risk,4),'same_day_exit_violation':False}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    v322=load_json(V322,{})
    rows=load_json(Path(v322.get('artifacts',{}).get('direct_rows','')),[])
    actionable=[]
    for r in rows:
        if r.get('v322_actionable_actual10') and not r.get('v322_any_history_overlap'):
            x={k:r.get(k) for k in ['symbol','entry_date','entry_price','zone_low','zone_high','sl','sl_price','risk_pct','market_state','event_type','poi_source','v132_reclaim_class','v132_bull_count_3','v85_zone_width_pct','entry_chase_above_zone_pct','v244_industry','v244_ind_strong1_pct','v236_br_above_ma20','v322_actual_bars_since_entry']}
            x.update({'version':'V323_SHADOW_ONLY','shadow_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'trade_action':'SHADOW_MONITOR_ONLY','promotion_eligible':False,'promotion_blocker':'DIRECT_CURRENT_ROW_NOT_HISTORICALLY_VALIDATED_AS_V246_EXACT_ROUTE; V167 exact historical quality below production gate'})
            x['t1_replay_status']=replay_status(r)
            actionable.append(x)
    report={'version':'V323_V322_DIRECT_CURRENT_SHADOW_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_v322':str(V322),'shadow_rows':len(actionable),'rows':actionable,'decision':'V323_SHADOW_ROW_MATERIALIZED_NO_PRODUCTION_PROMOTION' if actionable else 'V323_NO_SHADOW_ROWS','artifacts':{'report':str(OUT/'v323_report.json'),'rows':str(OUT/'v323_shadow_rows.json'),'latest':str(LATEST)}}
    json.dump(report,open(OUT/'v323_report.json','w'),ensure_ascii=False,indent=2)
    json.dump(actionable,open(OUT/'v323_shadow_rows.json','w'),ensure_ascii=False,indent=2)
    json.dump(report,open(LATEST,'w'),ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
