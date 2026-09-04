#!/usr/bin/env python3
"""V123 fast read-only source-specific contract search from V122 persisted dedup rows.

No production writes. No API/frontend/watchlist changes. No TP/SL tuning.
"""
from __future__ import annotations

import csv, json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

ROOT=Path('/root/.hermes')
IN=ROOT/'smc_audit/v122_shadow_parallel_poi_generator_20260620/parallel_poi_candidates_dedup.csv'
OUT=ROOT/'smc_audit/v123_source_specific_contract_search_20260620'
OUT.mkdir(parents=True, exist_ok=True)
Row=Dict[str,Any]

def f(x:Any, default:float=0.0)->float:
    try:
        if x in (None,''): return default
        return float(x)
    except Exception:
        return default

def ds(x:Any)->str:
    return ''.join(ch for ch in str(x or '') if ch.isdigit())[:8]

def load_rows()->List[Row]:
    with IN.open(newline='',encoding='utf-8') as fh:
        rows=list(csv.DictReader(fh))
    for r in rows:
        r['is_t1_violation']=ds(r.get('entry_date'))==ds(r.get('exit_date'))
        r['combo_family']=r.get('combo_family') or ('CONTINUATION' if r.get('event_type')=='BOS_CONTINUATION' else 'REVERSAL')
    return [r for r in rows if not r['is_t1_violation']]

def metrics(rows:Iterable[Row])->Dict[str,Any]:
    rs=list(rows); n=len(rs)
    if not n: return {'n':0,'wr':0,'avg':0,'sl':0,'tp':0,'cum':0}
    vals=[f(r.get('pnl_pct')) for r in rs]
    return {'n':n,'wr':round(sum(x>0 for x in vals)/n*100,2),'avg':round(sum(vals)/n,4),'sl':round(sum(('EXIT_POI_CLOSE_BREAK' in str(r.get('exit_reason')) or x<-0.8) for r,x in zip(rs,vals))/n*100,2),'tp':round(sum('TAKE_PROFIT' in str(r.get('exit_reason')) for r in rs)/n*100,2),'cum':round(sum(vals),2)}

def stability(rows:List[Row])->Dict[str,Any]:
    by=defaultdict(list); yy=defaultdict(list)
    for r in rows:
        d=ds(r.get('entry_date')); by[d[:6]].append(r); yy[d[:4]].append(r)
    mm={k:metrics(v) for k,v in sorted(by.items())}; yym={k:metrics(v) for k,v in sorted(yy.items())}
    return {'months':len(mm),'stable3':sum(1 for x in mm.values() if x['n']>=3 and x['wr']>=60),'months_n_ge_3':sum(1 for x in mm.values() if x['n']>=3),'stable5':sum(1 for x in mm.values() if x['n']>=5 and x['wr']>=60),'months_n_ge_5':sum(1 for x in mm.values() if x['n']>=5),'bad5':sum(1 for x in mm.values() if x['n']>=5 and x['wr']<50),'by_year':yym}

def inr(x:float, lo:float, hi:float|None)->bool:
    return x>=lo and (hi is None or x<=hi)

def pack(name:str, source:str, hit:List[Row], min_n:int)->Dict[str,Any]|None:
    if len(hit)<min_n: return None
    m=metrics(hit); st=stability(hit)
    score=round(m['wr']+min(m['n'],1000)/100+st['stable5']*2-st['bad5']*3+max(m['avg'],-5)*4-m['sl']*0.2,4)
    return {'source':source,'name':name,**m,**st,'score':score}

def search(rows:List[Row], source:str)->List[Dict[str,Any]]:
    out=[]; src=[r for r in rows if r.get('poi_source')==source]
    if source=='DEMAND_OB':
        for rr in [(0.8,1.2),(0.8,1.5),(1.0,1.5),(1.0,1.8),(1.2,2.0)]:
          for ww in [(0.8,1.3),(1.0,1.6),(1.2,1.8),(0.8,1.8)]:
           for hm in [1,2,3]:
            for fam in ['ALL','CONTINUATION','REVERSAL']:
             for st in ['ALL','BULL_CONTINUATION','RECOVERY','MIXED','BEAR_RISK','DISTRIBUTION']:
                name=f'risk{rr[0]}-{rr[1]}|width{ww[0]}-{ww[1]}|hold<={hm}|{fam}|{st}'
                hit=[r for r in src if inr(f(r.get('risk_pct')), *rr) and inr(f(r.get('v85_zone_width_pct')), *ww) and f(r.get('hold_bars'))<=hm and r.get('v83_takeover_type')=='HOLD_ABOVE_POI' and (fam=='ALL' or r.get('combo_family')==fam) and (st=='ALL' or r.get('market_state')==st)]
                c=pack(name,source,hit,100)
                if c: out.append(c)
        hit=[r for r in src if 1.0<f(r.get('v85_zone_width_pct'))<=1.6 and 1.0<f(r.get('risk_pct'))<=1.5 and f(r.get('hold_bars'))<=2 and r.get('v83_takeover_type')=='HOLD_ABOVE_POI']
        c=pack('V86_BASELINE risk1-1.5|width1-1.6|hold<=2',source,hit,50)
        if c: out.append(c)
    elif source=='FVG_Demand':
        for mid in [0.35,0.65,1.0,1.3]:
         for gap in [0.2,0.5,0.8,1.2]:
          for rr in [(0.5,2.0),(0.8,2.5),(1.0,3.0),(1.0,1.8)]:
           for ww in [(0.5,1.5),(0.8,2.0),(1.0,2.5),(1.2,3.0)]:
            for hm in [1,2,3]:
             for fam in ['ALL','CONTINUATION','REVERSAL']:
                name=f'mid>={mid}|gap>={gap}|risk{rr[0]}-{rr[1]}|width{ww[0]}-{ww[1]}|hold<={hm}|{fam}'
                hit=[r for r in src if f(r.get('source_mid_body_atr'))>=mid and f(r.get('source_gap_atr'))>=gap and inr(f(r.get('risk_pct')), *rr) and inr(f(r.get('v85_zone_width_pct')), *ww) and f(r.get('hold_bars'))<=hm and r.get('v83_takeover_type')=='HOLD_ABOVE_POI' and (fam=='ALL' or r.get('combo_family')==fam)]
                c=pack(name,source,hit,80)
                if c: out.append(c)
    else:
        for ov in [20,40,60,80]:
         for ww in [(0.3,1.2),(0.5,1.6),(0.8,2.0)]:
          for rr in [(0.5,2.0),(0.8,2.5),(1.0,3.0)]:
           for hm in [1,2,3]:
            for fam in ['ALL','REVERSAL','CONTINUATION']:
             for st in ['ALL','RECOVERY','DISTRIBUTION','MIXED','BEAR_RISK']:
                name=f'overlap>={ov}|width{ww[0]}-{ww[1]}|risk{rr[0]}-{rr[1]}|hold<={hm}|{fam}|{st}'
                hit=[r for r in src if f(r.get('ob_fvg_overlap_pct'))>=ov and inr(f(r.get('v85_zone_width_pct')), *ww) and inr(f(r.get('risk_pct')), *rr) and f(r.get('hold_bars'))<=hm and r.get('v83_takeover_type')=='HOLD_ABOVE_POI' and (fam=='ALL' or r.get('combo_family')==fam) and (st=='ALL' or r.get('market_state')==st)]
                c=pack(name,source,hit,20)
                if c: out.append(c)
    return sorted(out,key=lambda x:(-x['score'],-x['wr'],-x['avg'],-x['n']))

def write_csv(path:Path, rows:List[Dict[str,Any]]):
    fields=['source','name','n','wr','avg','sl','tp','cum','months','stable3','months_n_ge_3','stable5','months_n_ge_5','bad5','score']
    with path.open('w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def table(title, rows, limit=12):
    lines=[f'## {title}','|rank|contract|n|WR|Avg|SL|stable5|bad5|score|','|---:|---|---:|---:|---:|---:|---:|---:|---:|']
    for i,r in enumerate(rows[:limit],1): lines.append(f"|{i}|`{r['name']}`|{r['n']}|{r['wr']}|{r['avg']}|{r['sl']}|{r['stable5']}/{r['months_n_ge_5']}|{r['bad5']}|{r['score']}|")
    lines.append(''); return lines

def main():
    rows=load_rows(); by={s:metrics([r for r in rows if r.get('poi_source')==s]) for s in sorted({r.get('poi_source') for r in rows})}
    demand=search(rows,'DEMAND_OB'); fvg=search(rows,'FVG_Demand'); combo=search(rows,'OB+FVG')
    write_csv(OUT/'demand_ob_contracts.csv',demand); write_csv(OUT/'fvg_demand_contracts.csv',fvg); write_csv(OUT/'ob_fvg_contracts.csv',combo)
    summary={'decision':'READ_ONLY_SOURCE_SPECIFIC_CONTRACT_SEARCH_DONE_NO_CHANGE','input':str(IN),'dedup_rows':len(rows),'t1_violations':0,'by_source':by,'best_contracts':{'DEMAND_OB':demand[:20],'FVG_Demand':fvg[:20],'OB+FVG':combo[:20]},'reclaim_strength_note':'V122 persisted CSV does not contain zone_high/reclaim_idx; V123 searched source displacement/gap/risk/width/hold/overlap. Reclaim-strength needs V122 field persistence before production proof.','no_production_change':True,'v116_remains_shadow':True}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# V123 Source-specific Contract Search 只读审计','', 'Decision: `READ_ONLY_SOURCE_SPECIFIC_CONTRACT_SEARCH_DONE_NO_CHANGE`。未改生产、未调TP/SL、V116继续shadow。','',f"Input rows: {len(rows)}; T+1 violations: 0.",'','## 1. V122 base by source','|source|n|WR|Avg|SL|TP|Cum|','|---|---:|---:|---:|---:|---:|---:|']
    for s,m in by.items(): lines.append(f"|{s}|{m['n']}|{m['wr']}|{m['avg']}|{m['sl']}|{m['tp']}|{m['cum']}|")
    lines.append('')
    lines+=table('2. DEMAND_OB source-specific contracts',demand)
    lines+=table('3. FVG_Demand source-specific contracts',fvg)
    lines+=table('4. OB+FVG source-specific contracts',combo)
    lines+=['## 5. 字段约束','- V122持久CSV没有 `zone_high/reclaim_idx`，本轮不能严谨搜索 reclaim_strength；本轮先完成 source displacement / gap_atr / risk / width / hold / overlap 合同搜索。','- reclaim_strength 不得用猜测字段替代；下一步若要验证，需让并行生成器持久化 `zone_low/zone_high/touch_idx/reclaim_idx/entry_idx` 后重跑。','','## 6. 结论','1. `DEMAND_OB` 仍是当前最稳主源，最优合同围绕低risk、窄width、短hold。','2. `FVG_Demand` 需要 source_mid_body_atr + source_gap_atr + risk/width/hold 的独立合同；裸FVG不能生产。','3. `OB+FVG` 只能小样本shadow，重点看 REVERSAL/RECOVERY/DISTRIBUTION 窄子族，不能因 overlap 直接上线。','4. `CONTINUATION` 继续shadow分层，不能整体放开。','5. V116继续shadow，等待source-specific合同稳定和字段闭环。']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'out':str(OUT),'decision':summary['decision'],'dedup_rows':len(rows),'top':{k:v[:3] for k,v in summary['best_contracts'].items()}},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
