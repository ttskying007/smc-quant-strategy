#!/usr/bin/env python3
"""V385 no-write replay of V384's predeclared behavior-cohort states."""
from __future__ import annotations
import csv, json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
V381=AUD/'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'; V384=AUD/'v384_pit_behavior_cohort_data_gate_latest.json'
OUT=AUD/f'v385_pit_behavior_cohort_outcome_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'; LATEST=AUD/'v385_pit_behavior_cohort_outcome_replay_latest.json'
STATES=('COHORT_CONFIRMS','COHORT_MIXED','COHORT_REJECTS')
def stats(rows):
 y=defaultdict(list)
 for r in rows:y[r['entry_date'][:4]].append(float(r['pnl_pct']))
 yearly={k:{'n':len(v),'wr':round(sum(x>0 for x in v)/len(v)*100,4),'avg_pnl':round(sum(v)/len(v),4)} for k,v in sorted(y.items())}
 p=[float(r['pnl_pct']) for r in rows]
 return {'n':len(rows),'wr':round(sum(x>0 for x in p)/len(p)*100,4) if p else 0,'avg_pnl':round(sum(p)/len(p),4) if p else 0,'sl_pct':round(sum(r['exit_reason']=='SL_HIT' for r in rows)/len(rows)*100,4) if rows else 0,'yearly':yearly,'min_year_n':min((v['n'] for v in yearly.values()),default=0),'min_year_wr':min((v['wr'] for v in yearly.values()),default=0)}
def main():
 OUT.mkdir(parents=True,exist_ok=True); g=json.loads(V384.read_text())
 if g['decision']!='PIT_BEHAVIOR_COHORT_GATE_PASS__OUTCOME_REPLAY_ALLOWED':raise RuntimeError('V384 gate failed')
 with open(g['artifacts']['features'],newline='') as h:feature={(r['symbol'],r['hold_time']):r for r in csv.DictReader(h)}
 r381=json.loads(V381.read_text())
 with open(r381['artifacts']['trades'],newline='') as h:trades=[{**r,**feature[(r['symbol'],r['hold_time'])]} for r in csv.DictReader(h)]
 base=stats(trades); groups={s:[r for r in trades if r['pit_cohort_state']==s] for s in STATES}; result={s:stats(groups[s]) for s in STATES}
 # Frozen discovery bar: strong effect must be broad, economic, and stable before a full candidate-level rerun.
 checks={s:{'n>=300':m['n']>=300,'each_year_n>=40':m['min_year_n']>=40,'wr_uplift>=5pp':m['wr']-base['wr']>=5,'avg_uplift>=1pp':m['avg_pnl']-base['avg_pnl']>=1,'min_year_wr_uplift>=3pp':m['min_year_wr']-base['min_year_wr']>=3} for s,m in result.items()}
 promising=[s for s,c in checks.items() if all(c.values())]
 with (OUT/'v385_rows.csv').open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=list(trades[0]));w.writeheader();w.writerows(trades)
 report={'version':'V385_PIT_BEHAVIOR_COHORT_OUTCOME_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'contract':'V384 frozen 20-session behavior-neighbor cohort state at hold close; V381 executions bucketed afterward only; no threshold search','baseline':base,'states':result,'discovery_gate':checks,'decision':'COHORT_CONTEXT_INFORMATION_FOUND__CANDIDATE_LEVEL_REPLAY_REQUIRED' if promising else 'NO_CONTEXT_INFORMATION__BEHAVIOR_COHORT_BRANCH_CLOSED','promising_states':promising,'audit':{'v381_rows':len(trades),'feature_join_complete':len(trades)==4832,'feature_time_not_after_hold':all(r['feature_cutoff']==r['hold_time'] for r in trades),'state_counts':dict(Counter(r['pit_cohort_state'] for r in trades))},'artifacts':{'rows':str(OUT/'v385_rows.csv'),'latest':str(LATEST)}}
 text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v385_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
