#!/usr/bin/env python3
"""Fast ex-ante filter search over V68 after V70 root-cause feature extraction."""
import json, importlib.util, itertools
from pathlib import Path
spec=importlib.util.spec_from_file_location('audit','/root/.hermes/scripts/v25/v70_sl_root_cause_audit.py')
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
raw=json.loads(Path('/root/.hermes/smc_opt_v68_strict_ld/v68_trades.json').read_text())
rows=[]
for i,t in enumerate(raw,1):
    r=a.classify_trade(t)
    if r: rows.append(r)
    if i%1000==0: print('features',i,flush=True)
Path('/root/.hermes/smc_opt_v70_root_cause/v70_classified_all.json').write_text(json.dumps(rows,ensure_ascii=False))

def m(rs):
    if not rs: return {'n':0}
    return {'n':len(rs),'wr':round(sum(r['pnl_pct']>0 for r in rs)/len(rs)*100,2),'avg':round(sum(r['pnl_pct'] for r in rs)/len(rs),4),'sl':round(sum(r['exit_reason']=='SL_HIT' for r in rs)/len(rs)*100,2)}
filters={
 'not_down':lambda r:r['trend_state'] not in ('TREND_DOWN','DOWN_60'),
 'trend_up':lambda r:r['trend_state']=='TREND_UP',
 'range_or_up':lambda r:r['trend_state'] in ('TREND_UP','RANGE_TRANSITION'),
 'delay3_8':lambda r:3<=r['delay_confirm']<=8,
 'delay4_8':lambda r:4<=r['delay_confirm']<=8,
 'delay3_6':lambda r:3<=r['delay_confirm']<=6,
 'not_high_zone':lambda r:r['entry_zone_pos']<70,
 'mid_low_zone':lambda r:r['entry_zone_pos']<60,
 'not_deep_pierce':lambda r:r['entry_bar_zone_pierce']<100,
 'risk_lt6':lambda r:r['risk_pct']<6,
 'risk_lt4':lambda r:r['risk_pct']<4,
 'risk_3_6':lambda r:3<=r['risk_pct']<6,
 'retr30_60':lambda r:r['retrace_pct']<60,
 'disp_ge1':lambda r:r['disp_atr']>=1.0,
 'disp_ge1_5':lambda r:r['disp_atr']>=1.5,
 'pierce_ge0_3':lambda r:r['pierce_atr']>=0.3,
 'pos60_lt75':lambda r:r['pos60']<75,
 'above_ma20':lambda r:r['above_ma20'],
 'above_ma60':lambda r:r['above_ma60'],
 'not_ext_up':lambda r:r['trend_state']!='EXTENDED_UP',
}
res=[]; keys=list(filters)
for size in range(1,7):
    for combo in itertools.combinations(keys,size):
        rs=[r for r in rows if all(filters[k](r) for k in combo)]
        mt=m(rs)
        if mt['n']>=20 and (mt['wr']>=75 or (mt['n']>=100 and mt['wr']>=68)):
            res.append({'combo':combo,**mt})
res.sort(key=lambda x:(x['wr'],min(x['n'],500),x['avg']), reverse=True)
report={'base':m(rows),'top':res[:100],'passed_90':[x for x in res if x['wr']>=90 and x['n']>=20]}
Path('/root/.hermes/smc_opt_v70_root_cause/v70_exante_filter_search.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print(json.dumps({'base':report['base'],'passed_90_count':len(report['passed_90']),'top20':report['top'][:20]},ensure_ascii=False,indent=2,default=str))
