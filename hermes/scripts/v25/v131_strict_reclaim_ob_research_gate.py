#!/usr/bin/env python3
from __future__ import annotations
import csv,json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
SRC=Path('/root/.hermes/smc_audit/v129_v128_exit_target_diagnostic_20260622/v129_v128_target_exit_all.csv')
OUT=Path('/root/.hermes/smc_audit/v131_strict_reclaim_ob_research_gate_20260624')
OUT.mkdir(parents=True, exist_ok=True)
def num(x,d=0.0):
    try:
        if x in (None,''): return d
        return float(x)
    except Exception: return d
def dk(x): return str(x or '').replace('-','')[:8]
def met(rs):
    rs=list(rs); n=len(rs)
    if not n: return {'n':0,'wr':0,'avg':0,'loss':0,'hard':0,'cum':0}
    vals=[num(r.get('v129_pnl_pct')) for r in rs]
    hard=[r for r in rs if 'BREAK' in str(r.get('v129_exit_reason')) or 'DAMAGE' in str(r.get('v129_exit_reason'))]
    return {'n':n,'wr':round(sum(x>0 for x in vals)/n*100,2),'avg':round(sum(vals)/n,4),'loss':round(sum(x<=0 for x in vals)/n*100,2),'hard':round(len(hard)/n*100,2),'cum':round(sum(vals),4)}
def bucket(rs,key):
    g=defaultdict(list)
    for r in rs:g[str(key(r))].append(r)
    return {k:met(v) for k,v in sorted(g.items())}
rows=list(csv.DictReader(SRC.open(newline='',encoding='utf-8')))
def pass_gate(r):
    return (0.6<=num(r.get('v129_target_rr'))<=1.2 and r.get('combo_family')=='CONTINUATION' and r.get('market_state')!='RECOVERY'
        and num(r.get('reclaim_close_above_zone_pct'))>=0.5 and num(r.get('entry_chase_above_zone_pct'))<=5 and num(r.get('touch_to_reclaim_bars'))<=3
        and r.get('poi_source')=='DEMAND_OB' and num(r.get('v85_zone_width_pct'))<=3 and num(r.get('reclaim_close_pos'))>=0.8
        and dk(r.get('entry_date'))!=dk(r.get('v129_exit_date')))
passed=[r for r in rows if pass_gate(r)]
recent=[r for r in passed if 0<=num(r.get('bars_since_entry'),9999)<=45]
summary={'decision':'V131_RESEARCH_ONLY_STRICT_RECLAIM_OB_GATE_NO_PRODUCTION_WRITE','run_at':datetime.now().isoformat(timespec='seconds'),'input_rows':len(rows),'pass_rows':len(passed),'recent45_rows':len(recent),'gate':{'base':'V130 target_rr 0.6~1.2 + CONTINUATION + non-RECOVERY + reclaim_above>=0.5 + chase<=5 + lag<=3','poi_source':'DEMAND_OB','v85_zone_width_pct':'<=3','reclaim_close_pos':'>=0.8','t1':'exit_date!=entry_date'},'overall':met(passed),'recent45':met(recent),'by_year':bucket(passed,lambda r:dk(r.get('entry_date'))[:4]),'by_month':bucket(passed,lambda r:dk(r.get('entry_date'))[:6]),'by_market_state':bucket(passed,lambda r:r.get('market_state')),'by_exit_reason':bucket(passed,lambda r:r.get('v129_exit_reason')),'t1_violations':sum(1 for r in passed if dk(r.get('entry_date'))==dk(r.get('v129_exit_date'))),'years_n_lt_10':[k for k,m in bucket(passed,lambda r:dk(r.get('entry_date'))[:4]).items() if m['n']<10],'negative_years':[k for k,m in bucket(passed,lambda r:dk(r.get('entry_date'))[:4]).items() if m['avg']<=0]}
fields=sorted({k for r in passed for k in r})
for name,data in [('v131_pass_all.csv',passed),('v131_pass_recent45.csv',recent),('v131_losses.csv',[r for r in passed if num(r.get('v129_pnl_pct'))<=0])]:
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(data)
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# V131 strict reclaim OB research gate','',f"Decision: `{summary['decision']}`。只做研究候选，不写生产。",'', '## Metrics','|slice|n|WR|Avg|Loss|HardExit|Cum|','|---|---:|---:|---:|---:|---:|---:|']
for name,m in [('ALL',summary['overall']),('recent45',summary['recent45'])]: lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss']}|{m['hard']}|{m['cum']}|")
for title,key in [('By year','by_year'),('By month','by_month'),('By market_state','by_market_state'),('By exit_reason','by_exit_reason')]:
    lines+=['',f'## {title}','|key|n|WR|Avg|Loss|HardExit|Cum|','|---|---:|---:|---:|---:|---:|---:|']
    for k,m in summary[key].items(): lines.append(f"|{k}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss']}|{m['hard']}|{m['cum']}|")
lines+=['','## Decision notes',f"- negative_years: `{summary['negative_years']}`",f"- years_n_lt_10: `{summary['years_n_lt_10']}`",'- 结论：质量显著改善，但全量仅62笔、年度样本不足；只能作为V132候选生成器方向，不得生产晋级。','', '## Files',f'- {OUT}/summary.json',f'- {OUT}/v131_pass_all.csv',f'- {OUT}/v131_pass_recent45.csv',f'- {OUT}/v131_losses.csv']
(OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'out':str(OUT),'summary':summary},ensure_ascii=False,indent=2))
