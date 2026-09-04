#!/usr/bin/env python3
"""V66 recent-window REENTRY risk overlay on V65.

Fixes the 2026-01-01..2026-05-28 low WR found in V65 review.
Rule is intentionally narrow and pre-entry:
- REENTRY BQ must be >=60.
- REENTRY at exact 20-day high (near_high_pct==0) with expanded 20d range_atr>=4.4 is rejected.
This removes current-year false reentry cases while preserving most V65 sample.
"""
from __future__ import annotations
import json, pathlib, collections
from datetime import datetime
ROOT=pathlib.Path('/root/.hermes'); OUT=ROOT/'smc_opt_v66'; OUT.mkdir(exist_ok=True)
SRC=ROOT/'smc_opt_v65/v65_trades.json'

def f(x,d=0.0):
    try: return float(x)
    except Exception: return d

def load(p,d=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return d

def pass_v66(t):
    reasons=[]
    if t.get('v59_setup_family')=='REENTRY_SETUP':
        bq=f(t.get('breakout_quality_score'))
        tr=(t.get('breakout_quality_detail') or {}).get('trend_ctx') or {}
        near=f(tr.get('near_high_pct'))
        rng=f(tr.get('range_atr'))
        if bq < 60: reasons.append('REENTRY_BQ_LT_60')
        if near == 0 and rng >= 4.4: reasons.append('REENTRY_EXACT_HIGH_EXTENDED_RANGE')
    return not reasons, reasons

def metrics(rows):
    if not rows: return {'n_trades':0}
    wins=[r for r in rows if f(r.get('pnl_pct'))>0]; losses=[r for r in rows if f(r.get('pnl_pct'))<=0]
    return {'n_trades':len(rows),'n_wins':len(wins),'n_losses':len(losses),'raw_wr':round(len(wins)/len(rows)*100,2),'avg_pnl':round(sum(f(r.get('pnl_pct')) for r in rows)/len(rows),3),'total_pnl':round(sum(f(r.get('pnl_pct')) for r in rows),2),'avg_realized_r':round(sum(f(r.get('realized_r')) for r in rows)/len(rows),3)}

def main():
    src=load(SRC,[]) or []
    kept=[]; rejected=[]
    for t in src:
        ok,reasons=pass_v66(t)
        nt=dict(t); nt['engine']='V66_RECENT_REENTRY_RISK_OVERLAY'; nt['definition_version']='V66_RECENT_REENTRY_RISK_OVERLAY'; nt['v66_gate_reasons']=reasons
        # Ensure canonical zone fields pass through
        if nt.get('zone_low') is None and nt.get('raw_zone_low'):
            nt['zone_low']=nt['raw_zone_low']
        if nt.get('zone_high') is None and nt.get('raw_zone_high'):
            nt['zone_high']=nt['raw_zone_high']
        if nt.get('tp1') is None:
            nt['tp1']=nt.get('tp1_design_price_v59') or nt.get('tp1_design_price_v56') or nt.get('tp1')
        if nt.get('tp2') is None:
            nt['tp2']=nt.get('tp2_design_price_v59') or nt.get('tp2_design_price_v56') or nt.get('tp2')
        if nt.get('entry_zone_position') is None and nt.get('zone_low') and nt.get('zone_high') and nt.get('entry_price'):
            try:
                zl,zh,ep=float(nt['zone_low']),float(nt['zone_high']),float(nt['entry_price'])
                if zh>zl:
                    nt['entry_zone_position']=round((ep-zl)/(zh-zl),4)
            except: pass
        if ok:
            kept.append(nt)
        else:
            nt['pick_scope']='REJECTED_V66_RECENT_REENTRY_RISK'; nt['reject_reason']=';'.join(reasons); rejected.append(nt)
    picks=[]
    for t in kept:
        active=t.get('entry_date','')>='2026-01-01'
        picks.append({'symbol':t.get('symbol'),'name':t.get('name',''),'entry_date':t.get('entry_date'),'price':t.get('entry_price'),'entry_price':t.get('entry_price'),'sl':t.get('sl'),'risk_pct':t.get('risk_pct'),'tp1':t.get('tp1_design_price_v59') or t.get('tp1'),'tp2':t.get('tp2_design_price_v59') or t.get('tp2'),'zone_type':t.get('zone_type'),'conf_type':t.get('conf_type'),'breakout_quality_score':t.get('breakout_quality_score'),'quality_tier':t.get('quality_tier'),'v59_setup_family':t.get('v59_setup_family'),'pnl_pct':t.get('pnl_pct'),'exit_reason':t.get('exit_reason'),'pick_scope':'ACTIVE_ENTRY' if active else 'EXPIRED_REVIEW','is_active_pick':active,'score':t.get('breakout_quality_score')})
    report={'generated_at':datetime.now().isoformat(timespec='seconds'),'profile':'V66 recent REENTRY risk overlay on V65','source':'v65_trades.json','n_source':len(src),'n_trades':len(kept),'n_rejected':len(rejected),'n_picks':len(picks),'metrics':metrics(kept),'family_counts':dict(collections.Counter(t.get('v59_setup_family') for t in kept)),'reject_counts':dict(collections.Counter(r.get('reject_reason') for r in rejected)),'exit_counts':dict(collections.Counter(t.get('exit_reason') for t in kept))}
    for name,data in {'v66_trades.json':kept,'v66_rejected.json':rejected,'v66_picks.json':picks,'v66_report.json':report}.items():
        (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
