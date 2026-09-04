#!/usr/bin/env python3
from __future__ import annotations
import json, csv
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

ROOT=Path('/root/.hermes')
IN=ROOT/'smc_audit/v122_shadow_parallel_poi_generator_20260620/parallel_poi_candidates_dedup.csv'
OUT=ROOT/'smc_audit/v123_source_specific_contract_search_20260620'
OUT.mkdir(parents=True,exist_ok=True)

def ds(s): return ''.join(ch for ch in str(s or '') if ch.isdigit())[:8]

def load():
    df=pd.read_csv(IN, dtype=str).fillna('')
    for c in ['pnl_pct','risk_pct','v85_zone_width_pct','hold_bars','source_mid_body_atr','source_gap_atr','ob_fvg_overlap_pct']:
        df[c]=pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    df=df[df['entry_date'].map(ds)!=df['exit_date'].map(ds)].copy()
    df['ym']=df['entry_date'].map(lambda x: ds(x)[:6])
    return df

def metrics(d:pd.DataFrame)->Dict[str,Any]:
    n=len(d)
    if n==0: return {'n':0,'wr':0,'avg':0,'sl':0,'tp':0,'cum':0}
    pnl=d['pnl_pct']
    return {'n':int(n),'wr':round(float((pnl>0).mean()*100),2),'avg':round(float(pnl.mean()),4),'sl':round(float(((d['exit_reason'].str.contains('EXIT_POI_CLOSE_BREAK',na=False)) | (pnl<-0.8)).mean()*100),2),'tp':round(float(d['exit_reason'].str.contains('TAKE_PROFIT',na=False).mean()*100),2),'cum':round(float(pnl.sum()),2)}

def stab(d:pd.DataFrame)->Dict[str,Any]:
    ms=[]
    for _,g in d.groupby('ym'):
        ms.append(metrics(g))
    return {'months':len(ms),'stable3':sum(1 for x in ms if x['n']>=3 and x['wr']>=60),'months_n_ge_3':sum(1 for x in ms if x['n']>=3),'stable5':sum(1 for x in ms if x['n']>=5 and x['wr']>=60),'months_n_ge_5':sum(1 for x in ms if x['n']>=5),'bad5':sum(1 for x in ms if x['n']>=5 and x['wr']<50)}

def pack(source,name,d,min_n):
    if len(d)<min_n: return None
    m=metrics(d); st=stab(d)
    score=round(m['wr']+min(m['n'],1000)/100+st['stable5']*2-st['bad5']*3+max(m['avg'],-5)*4-m['sl']*0.2,4)
    return {'source':source,'name':name,**m,**st,'score':score}

def add(out, source, name, d, min_n):
    x=pack(source,name,d,min_n)
    if x: out.append(x)

def search_demand(df):
    d=df[df.poi_source=='DEMAND_OB']; out=[]
    for rr in [(0.8,1.2),(0.8,1.5),(1.0,1.5),(1.0,1.8),(1.2,2.0)]:
      br=d[(d.risk_pct>=rr[0])&(d.risk_pct<=rr[1])]
      for ww in [(0.8,1.3),(1.0,1.6),(1.2,1.8),(0.8,1.8)]:
        bw=br[(br.v85_zone_width_pct>=ww[0])&(br.v85_zone_width_pct<=ww[1])]
        for hm in [1,2,3]:
          bh=bw[(bw.hold_bars<=hm)&(bw.v83_takeover_type=='HOLD_ABOVE_POI')]
          for fam in ['ALL','CONTINUATION','REVERSAL']:
            bf=bh if fam=='ALL' else bh[bh.combo_family==fam]
            for st in ['ALL','BULL_CONTINUATION','RECOVERY','MIXED','BEAR_RISK','DISTRIBUTION']:
              bs=bf if st=='ALL' else bf[bf.market_state==st]
              add(out,'DEMAND_OB',f'risk{rr[0]}-{rr[1]}|width{ww[0]}-{ww[1]}|hold<={hm}|{fam}|{st}',bs,100)
    base=d[(d.v85_zone_width_pct>1.0)&(d.v85_zone_width_pct<=1.6)&(d.risk_pct>1.0)&(d.risk_pct<=1.5)&(d.hold_bars<=2)&(d.v83_takeover_type=='HOLD_ABOVE_POI')]
    add(out,'DEMAND_OB','V86_BASELINE risk1-1.5|width1-1.6|hold<=2',base,50)
    return sorted(out,key=lambda x:(-x['score'],-x['wr'],-x['avg'],-x['n']))

def search_fvg(df):
    d=df[df.poi_source=='FVG_Demand']; out=[]
    for mid in [0.35,0.65,1.0,1.3]:
      bm=d[d.source_mid_body_atr>=mid]
      for gap in [0.2,0.5,0.8,1.2]:
        bg=bm[bm.source_gap_atr>=gap]
        for rr in [(0.5,2.0),(0.8,2.5),(1.0,3.0),(1.0,1.8)]:
          br=bg[(bg.risk_pct>=rr[0])&(bg.risk_pct<=rr[1])]
          for ww in [(0.5,1.5),(0.8,2.0),(1.0,2.5),(1.2,3.0)]:
            bw=br[(br.v85_zone_width_pct>=ww[0])&(br.v85_zone_width_pct<=ww[1])]
            for hm in [1,2,3]:
              bh=bw[(bw.hold_bars<=hm)&(bw.v83_takeover_type=='HOLD_ABOVE_POI')]
              for fam in ['ALL','CONTINUATION','REVERSAL']:
                bf=bh if fam=='ALL' else bh[bh.combo_family==fam]
                add(out,'FVG_Demand',f'mid>={mid}|gap>={gap}|risk{rr[0]}-{rr[1]}|width{ww[0]}-{ww[1]}|hold<={hm}|{fam}',bf,80)
    return sorted(out,key=lambda x:(-x['score'],-x['wr'],-x['avg'],-x['n']))

def search_combo(df):
    d=df[df.poi_source=='OB+FVG']; out=[]
    for ov in [20,40,60,80]:
      bo=d[d.ob_fvg_overlap_pct>=ov]
      for ww in [(0.3,1.2),(0.5,1.6),(0.8,2.0)]:
        bw=bo[(bo.v85_zone_width_pct>=ww[0])&(bo.v85_zone_width_pct<=ww[1])]
        for rr in [(0.5,2.0),(0.8,2.5),(1.0,3.0)]:
          br=bw[(bw.risk_pct>=rr[0])&(bw.risk_pct<=rr[1])]
          for hm in [1,2,3]:
            bh=br[(br.hold_bars<=hm)&(br.v83_takeover_type=='HOLD_ABOVE_POI')]
            for fam in ['ALL','REVERSAL','CONTINUATION']:
              bf=bh if fam=='ALL' else bh[bh.combo_family==fam]
              for st in ['ALL','RECOVERY','DISTRIBUTION','MIXED','BEAR_RISK']:
                bs=bf if st=='ALL' else bf[bf.market_state==st]
                add(out,'OB+FVG',f'overlap>={ov}|width{ww[0]}-{ww[1]}|risk{rr[0]}-{rr[1]}|hold<={hm}|{fam}|{st}',bs,20)
    return sorted(out,key=lambda x:(-x['score'],-x['wr'],-x['avg'],-x['n']))

def write(path, rows):
    fields=['source','name','n','wr','avg','sl','tp','cum','months','stable3','months_n_ge_3','stable5','months_n_ge_5','bad5','score']
    pd.DataFrame(rows, columns=fields).to_csv(path,index=False)

def table(title,rows):
    lines=[f'## {title}','|rank|contract|n|WR|Avg|SL|stable5|bad5|score|','|---:|---|---:|---:|---:|---:|---:|---:|---:|']
    for i,r in enumerate(rows[:12],1): lines.append(f"|{i}|`{r['name']}`|{r['n']}|{r['wr']}|{r['avg']}|{r['sl']}|{r['stable5']}/{r['months_n_ge_5']}|{r['bad5']}|{r['score']}|")
    lines.append(''); return lines

def main():
    df=load(); by={s:metrics(g) for s,g in df.groupby('poi_source')}
    demand=search_demand(df); fvg=search_fvg(df); combo=search_combo(df)
    write(OUT/'demand_ob_contracts.csv',demand); write(OUT/'fvg_demand_contracts.csv',fvg); write(OUT/'ob_fvg_contracts.csv',combo)
    summary={'decision':'READ_ONLY_SOURCE_SPECIFIC_CONTRACT_SEARCH_DONE_NO_CHANGE','input':str(IN),'dedup_rows':int(len(df)),'t1_violations':0,'by_source':by,'best_contracts':{'DEMAND_OB':demand[:20],'FVG_Demand':fvg[:20],'OB+FVG':combo[:20]},'reclaim_strength_note':'V122 persisted CSV lacks zone_high/reclaim_idx; V123 searched source displacement/gap/risk/width/hold/overlap only. Reclaim-strength requires persisting zone/reclaim fields in the parallel generator before production proof.','no_production_change':True,'v116_remains_shadow':True}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# V123 Source-specific Contract Search 只读审计','', 'Decision: `READ_ONLY_SOURCE_SPECIFIC_CONTRACT_SEARCH_DONE_NO_CHANGE`。未改生产、未调TP/SL、V116继续shadow。','',f'Input rows: {len(df)}; T+1 violations: 0.','','## 1. V122 base by source','|source|n|WR|Avg|SL|TP|Cum|','|---|---:|---:|---:|---:|---:|---:|']
    for s,m in by.items(): lines.append(f"|{s}|{m['n']}|{m['wr']}|{m['avg']}|{m['sl']}|{m['tp']}|{m['cum']}|")
    lines.append('')
    lines+=table('2. DEMAND_OB source-specific contracts',demand)
    lines+=table('3. FVG_Demand source-specific contracts',fvg)
    lines+=table('4. OB+FVG source-specific contracts',combo)
    lines+=['## 5. 字段约束','- V122持久CSV没有 `zone_high/reclaim_idx`，本轮不能严谨搜索 reclaim_strength。','- 本轮先完成 source displacement / gap_atr / risk / width / hold / overlap 合同搜索。','- reclaim_strength 不得用猜测字段替代；下一步若要验证，需让并行生成器持久化 `zone_low/zone_high/touch_idx/reclaim_idx/entry_idx` 后重跑。','','## 6. 结论','1. `DEMAND_OB` 仍是当前最稳主源，最优合同围绕低risk、窄width、短hold。','2. `FVG_Demand` 需要 source_mid_body_atr + source_gap_atr + risk/width/hold 的独立合同；裸FVG不能生产。','3. `OB+FVG` 只能小样本shadow，重点看 REVERSAL/RECOVERY/DISTRIBUTION 窄子族，不能因 overlap 直接上线。','4. `CONTINUATION` 继续shadow分层，不能整体放开。','5. V116继续shadow，等待source-specific合同稳定和字段闭环。']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'out':str(OUT),'decision':summary['decision'],'dedup_rows':len(df),'top':{k:v[:3] for k,v in summary['best_contracts'].items()}},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
