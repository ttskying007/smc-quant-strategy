#!/usr/bin/env python3
"""V65 loss-review gate on V64.

V64 reaches 83% WR. V65 is a sustainability-focused loss review:
- keep only OB continuation as direct continuation trade
- keep REENTRY only when range is not over-extended and breakout body is sufficient
This targets V64's 45 losses without using outcome fields in the gate.
"""
from __future__ import annotations
import json, pathlib, collections
from datetime import datetime
ROOT=pathlib.Path('/root/.hermes'); OUT=ROOT/'smc_opt_v65'; OUT.mkdir(exist_ok=True)
SRC=OUT/'v65_source_v64_trades.json'

def f(x,d=0.0):
    try: return float(x)
    except Exception: return d

def load(p,d=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return d

def pass_v65(t):
    fam=t.get('v59_setup_family'); d=t.get('breakout_quality_detail') or {}; tr=d.get('trend_ctx') or {}
    reasons=[]
    if fam=='CONTINUATION_SETUP':
        if t.get('zone_type')!='OB_Bull': reasons.append('CONT_NOT_OB_DIRECT_TRADE')
        return not reasons,reasons,1.0 if not reasons else 0.0
    if fam=='REENTRY_SETUP':
        if tr.get('range_atr',999)>5: reasons.append('REENTRY_RANGE_ATR_GT_5')
        if f(d.get('body_ratio'))<0.3: reasons.append('REENTRY_BODY_LT_0_3')
        return not reasons,reasons,0.75 if not reasons else 0.0
    reasons.append('UNKNOWN_FAMILY')
    return False,reasons,0.0

def metrics(rows,weighted=False):
    if not rows: return {'n_trades':0}
    wins=[r for r in rows if f(r.get('pnl_pct'))>0]; losses=[r for r in rows if f(r.get('pnl_pct'))<=0]
    weights=[f(r.get('position_size_mult_v65',r.get('position_size_mult_v64',1))) if weighted else 1 for r in rows]
    total=sum(f(r.get('pnl_pct'))*w for r,w in zip(rows,weights)); denom=sum(weights) or 1
    return {'n_trades':len(rows),'n_wins':len(wins),'n_losses':len(losses),'raw_wr':round(len(wins)/len(rows)*100,2),'avg_pnl':round(total/denom,3),'total_pnl':round(total,2),'avg_realized_r':round(sum(f(r.get('realized_r')) for r in rows)/len(rows),3)}

def main():
    src=load(SRC,[]) or []
    kept=[]; rejected=[]; watch=[]
    for t in src:
        ok,reasons,size=pass_v65(t)
        nt=dict(t); nt['engine']='V65_LOSS_REVIEW_GATE'; nt['definition_version']='V65_LOSS_REVIEW_GATE'; nt['v65_gate_reasons']=reasons; nt['position_size_mult_v65']=size
        # Ensure canonical zone fields from raw_zone_
        if nt.get('zone_low') is None and nt.get('raw_zone_low'):
            nt['zone_low']=nt['raw_zone_low']
        if nt.get('zone_high') is None and nt.get('raw_zone_high'):
            nt['zone_high']=nt['raw_zone_high']
        if nt.get('tp1') is None:
            nt['tp1']=nt.get('tp1_design_price_v59') or nt.get('tp1_design_price_v56') or nt.get('tp1_design_price_v55') or nt.get('tp1')
        if nt.get('tp2') is None:
            nt['tp2']=nt.get('tp2_design_price_v59') or nt.get('tp2_design_price_v56') or nt.get('tp2_design_price_v55') or nt.get('tp2')
        # entry_zone_position
        if nt.get('entry_zone_position') is None and nt.get('zone_low') and nt.get('zone_high') and nt.get('entry_price'):
            try:
                zl,zh,ep=float(nt['zone_low']),float(nt['zone_high']),float(nt['entry_price'])
                if zh>zl:
                    nt['entry_zone_position']=round((ep-zl)/(zh-zl),4)
            except: pass
        if ok: kept.append(nt)
        else:
            nt['reject_reason']=';'.join(reasons)
            if nt.get('v59_setup_family')=='CONTINUATION_SETUP': nt['pick_scope']='V65_WATCH_ONLY'; watch.append(nt)
            else: nt['pick_scope']='REJECTED_V65_LOSS_REVIEW_GATE'; rejected.append(nt)
    picks=[]
    for t in kept:
        active=t.get('entry_date','')>='2026-01-01'
        picks.append({'symbol':t.get('symbol'),'name':t.get('name',''),'entry_date':t.get('entry_date'),'price':t.get('entry_price'),'entry_price':t.get('entry_price'),'sl':t.get('sl'),'risk_pct':t.get('risk_pct'),'tp1':t.get('tp1_design_price_v59') or t.get('tp1'),'tp2':t.get('tp2_design_price_v59') or t.get('tp2'),'zone_type':t.get('zone_type'),'conf_type':t.get('conf_type'),'breakout_quality_score':t.get('breakout_quality_score'),'quality_tier':t.get('quality_tier'),'v59_setup_family':t.get('v59_setup_family'),'position_size_mult_v65':t.get('position_size_mult_v65'),'pnl_pct':t.get('pnl_pct'),'exit_reason':t.get('exit_reason'),'pick_scope':'ACTIVE_ENTRY' if active else 'EXPIRED_REVIEW','is_active_pick':active,'score':t.get('breakout_quality_score')})
    report={'generated_at':datetime.now().isoformat(timespec='seconds'),'profile':'V65 loss-review gate on V64','source':'v64_trades.json','n_source':len(src),'n_trades':len(kept),'n_rejected':len(rejected),'n_watch_only':len(watch),'n_picks':len(picks),'metrics':metrics(kept),'metrics_weighted':metrics(kept,True),'family_counts':dict(collections.Counter(t.get('v59_setup_family') for t in kept)),'tier_counts':dict(collections.Counter(t.get('quality_tier') for t in kept)),'reject_counts':dict(collections.Counter((r.get('reject_reason') or '') for r in rejected+watch)),'exit_counts':dict(collections.Counter(t.get('exit_reason') for t in kept))}
    for name,data in {'v65_trades.json':kept,'v65_rejected.json':rejected,'v65_watch_only.json':watch,'v65_picks.json':picks,'v65_report.json':report}.items():
        (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
