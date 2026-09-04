#!/usr/bin/env python3
import json
from pathlib import Path
OUT=Path('/root/.hermes/smc_opt_v35')

def load(p): return json.loads(Path(p).read_text()) if Path(p).exists() else []
def f(x):
    try:return float(x)
    except:return 0.0
def met(rows):
    n=len(rows); w=sum(1 for t in rows if f(t.get('pnl_pct'))>0); sl=sum(1 for t in rows if 'SL' in str(t.get('exit_reason','')))
    return {'n':n,'wr':round(w/max(n,1)*100,1),'sl':sl,'sl_rate':round(sl/max(n,1)*100,1),'avg_pnl':round(sum(f(t.get('pnl_pct')) for t in rows)/max(n,1),2),'total_pnl':round(sum(f(t.get('pnl_pct')) for t in rows),2)}
def group(rows,k):
    d={}
    for t in rows: d.setdefault(t.get(k,'?'),[]).append(t)
    return {kk:met(v) for kk,v in sorted(d.items())}

def q(vals):
    vals=sorted([v for v in vals if v is not None])
    if not vals:return {}
    def pct(p): return vals[min(len(vals)-1,round((len(vals)-1)*p))]
    return {'avg':round(sum(vals)/len(vals),2),'p50':round(pct(.5),2),'p75':round(pct(.75),2),'p90':round(pct(.9),2),'max':round(vals[-1],2)}

v34=load('/root/.hermes/smc_opt_v34d_final/v34_trades.json')
v35=load('/root/.hermes/smc_opt_v35/v35_trades.json')
sl=[t for t in v35 if 'SL' in str(t.get('exit_reason',''))]
report={
 'p2_entry_exit_attribution':{
   'v34d_clean_baseline':met(v34),
   'v35_add_fvg_bpr_test':met(v35),
   'v35_by_zone_type':group(v35,'zone_type'),
   'v35_by_market_state':group(v35,'market_state'),
   'v35_by_conf_type':group(v35,'conf_type'),
   'sl_trades':[{**{k:t.get(k) for k in ['symbol','zone_type','entry_date','signal_date','exit_reason','pnl_pct','entry_price','zone_low','zone_high','risk_pct','conf_type','market_state']},
                 'zone_width_pct':round((f(t.get('zone_high'))-f(t.get('zone_low')))/max(f(t.get('zone_low')),1)*100,2),
                 'entry_over_zone_high_pct':round((f(t.get('entry_price'))/max(f(t.get('zone_high')),1)-1)*100,2),
                 'gaps':t.get('audit_chain',{}).get('time_gaps',{})} for t in sl],
   'quantiles':{
     'zone_width_pct':q([(f(t.get('zone_high'))-f(t.get('zone_low')))/max(f(t.get('zone_low')),1)*100 for t in v35]),
     'entry_over_zone_high_pct':q([(f(t.get('entry_price'))/max(f(t.get('zone_high')),1)-1)*100 for t in v35]),
     'struct_to_confirm':q([t.get('audit_chain',{}).get('time_gaps',{}).get('struct_to_confirm') for t in v35]),
     'hold_bars_sl':q([f(t.get('hold_bars')) for t in sl])
   },
   'root_cause':'FVG reintroduction polluted the clean baseline: FVG n=14 WR57.1 SL35.7; TREND_UP entries n=7 WR42.9 SL57.1. OB-only V34D remains best validated result.'
 },
 'p3_unresolved':[
   {'item':'Exact user Pine diff','status':'not_done','impact':'Cannot claim 100% Pine parity for BOS/CHOCH/MSS without TradingView/exported Pine event list.'},
   {'item':'FVG trading','status':'quarantined','impact':'Adding current FVG worsens WR 85.7→66.7 and SL 14.3→28.6.'},
   {'item':'BPR trading','status':'quarantined','impact':'No validated profitable BPR sample; semantics still too broad.'},
   {'item':'EQL/EQH sweep pool','status':'not_merged','impact':'May miss true liquidity sweeps; must merge into sweep source before enabling trades.'},
   {'item':'BRK/RB','status':'missing','impact':'Cannot show/trade these as audited signals.'},
   {'item':'LV/OTE','status':'display_only_or_disabled','impact':'Definitions exist but not exact enough for entry decisions.'},
   {'item':'Coverage','status':'low','impact':'V34D clean baseline only 7 trades; need expand via audited EQL/EQH + strict FVG, not old V24 context strings.'}
 ],
 'p4_fix_decision':{
   'tested_v35_add_fvg_bpr':'failed_quality_gate',
   'final_active_engine':'V34D_LUX_OB_QUALITY',
   'reason':'Only OB same-event chain satisfies quality gate. FVG/BPR remain quarantined until Pine parity and profitable standalone validation.',
   'frontend_sync_required':{'active_trade_file':'/root/.hermes/smc_opt_v34d_final/v34_trades.json','active_pick_file':'/root/.hermes/smc_opt_v34d_final/v34_picks.json','v35_diagnostics':'/root/.hermes/smc_opt_v35'}
 }
}
(OUT/'p2_p3_p4_diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
