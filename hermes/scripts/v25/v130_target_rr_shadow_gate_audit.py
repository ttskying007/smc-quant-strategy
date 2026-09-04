#!/usr/bin/env python3
from __future__ import annotations
import csv,json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
ROOT=Path('/root/.hermes')
SRC=ROOT/'smc_audit/v129_v128_exit_target_diagnostic_20260622/v129_v128_target_exit_all.csv'
OUT=ROOT/'smc_audit/v130_target_rr_shadow_gate_20260624'
OUT.mkdir(parents=True, exist_ok=True)
def num(x, default=0.0):
    try:
        if x in (None,''): return default
        return float(x)
    except Exception: return default
def dk(x): return str(x or '').replace('-','')[:8]
def met(rows):
    rows=list(rows); n=len(rows)
    if not n: return {'n':0,'wr':0,'avg':0,'loss':0,'hard':0,'cum':0}
    vals=[num(r.get('v129_pnl_pct')) for r in rows]
    hard=[r for r in rows if 'BREAK' in str(r.get('v129_exit_reason')) or 'DAMAGE' in str(r.get('v129_exit_reason')) or str(r.get('v129_exit_reason')).startswith('SL')]
    return {'n':n,'wr':round(sum(x>0 for x in vals)/n*100,2),'avg':round(sum(vals)/n,4),'loss':round(sum(x<=0 for x in vals)/n*100,2),'hard':round(len(hard)/n*100,2),'cum':round(sum(vals),4)}
def bucket(rows, key):
    g=defaultdict(list)
    for r in rows: g[str(key(r))].append(r)
    return {k:met(v) for k,v in sorted(g.items())}
def pass_v130(r):
    # diagnostic gate only: target must be meaningful but not too far, entry cannot chase too far,
    # and reclaim must close back above zone with non-leaking known target exit semantics.
    rr=num(r.get('v129_target_rr'))
    return (
        0.6 <= rr <= 1.2
        and r.get('combo_family') == 'CONTINUATION'
        and r.get('market_state') != 'RECOVERY'
        and num(r.get('reclaim_close_above_zone_pct')) >= 0.5
        and num(r.get('entry_chase_above_zone_pct')) <= 5.0
        and num(r.get('touch_to_reclaim_bars')) <= 3
        and dk(r.get('entry_date')) != dk(r.get('v129_exit_date'))
    )
rows=[]
with SRC.open(newline='',encoding='utf-8') as f:
    rows=list(csv.DictReader(f))
passed=[r for r in rows if pass_v130(r)]
recent=[r for r in passed if 0<=num(r.get('bars_since_entry'),9999)<=45]
summary={
 'decision':'V130_DIAGNOSTIC_ONLY_TARGET_RR_SHADOW_GATE_NO_PRODUCTION_WRITE',
 'run_at':datetime.now().isoformat(timespec='seconds'),
 'input_rows':len(rows),'pass_rows':len(passed),'recent45_pass_rows':len(recent),
 'gate':{
   'v129_target_rr':'0.6<=RR<=1.2', 'combo_family':'CONTINUATION', 'market_state':'!=RECOVERY',
   'reclaim_close_above_zone_pct':'>=0.5', 'entry_chase_above_zone_pct':'<=5.0', 'touch_to_reclaim_bars':'<=3', 't1':'exit_date!=entry_date'
 },
 'overall':met(passed),'recent45':met(recent),
 'by_year':bucket(passed, lambda r:dk(r.get('entry_date'))[:4]),
 'by_month':bucket(passed, lambda r:dk(r.get('entry_date'))[:6]),
 'by_source':bucket(passed, lambda r:r.get('poi_source')),
 'by_market_state':bucket(passed, lambda r:r.get('market_state')),
 'by_exit_reason':bucket(passed, lambda r:r.get('v129_exit_reason')),
 't1_violations':sum(1 for r in passed if dk(r.get('entry_date'))==dk(r.get('v129_exit_date'))),
 'negative_years_n_ge_30':[k for k,m in bucket(passed, lambda r:dk(r.get('entry_date'))[:4]).items() if m['n']>=30 and m['avg']<=0],
 'negative_months_n_ge_30':[k for k,m in bucket(passed, lambda r:dk(r.get('entry_date'))[:6]).items() if m['n']>=30 and m['avg']<=0],
}
fields=sorted({k for r in passed for k in r.keys()})
for name,data in [('v130_pass_all.csv',passed),('v130_pass_recent45.csv',recent),('v130_pass_losses.csv',sorted([r for r in passed if num(r.get('v129_pnl_pct'))<=0], key=lambda r:num(r.get('v129_pnl_pct')))[:300])]:
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(data)
(OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),encoding='utf-8')
lines=['# V130 target-RR shadow gate audit','',f"Decision: `{summary['decision']}`。只做shadow门禁审计，不写生产。",'', '## Gate', '|字段|规则|','|---|---|']
for k,v in summary['gate'].items(): lines.append(f'|{k}|{v}|')
lines += ['', '## Metrics', '|slice|n|WR|Avg|Loss|HardExit|Cum|','|---|---:|---:|---:|---:|---:|---:|']
for name,m in [('ALL',summary['overall']),('recent45',summary['recent45'])]: lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss']}|{m['hard']}|{m['cum']}|")
for title,key in [('By source','by_source'),('By year','by_year'),('By market_state','by_market_state'),('By exit_reason','by_exit_reason')]:
    lines += ['', f'## {title}', '|key|n|WR|Avg|Loss|HardExit|Cum|','|---|---:|---:|---:|---:|---:|---:|']
    for k,m in summary[key].items(): lines.append(f"|{k}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss']}|{m['hard']}|{m['cum']}|")
lines += ['', '## Stability failures', f"- negative_years_n_ge_30: `{summary['negative_years_n_ge_30']}`", f"- negative_months_n_ge_30: `{summary['negative_months_n_ge_30']}`", f"- T+1 violations: `{summary['t1_violations']}`", '', '## Files', f'- {OUT}/summary.json', f'- {OUT}/v130_pass_all.csv', f'- {OUT}/v130_pass_recent45.csv', f'- {OUT}/v130_pass_losses.csv']
(OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'out':str(OUT),'summary':summary}, ensure_ascii=False, indent=2))
