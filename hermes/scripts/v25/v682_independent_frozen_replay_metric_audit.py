#!/usr/bin/env python3
"""V682 independent audit of the one and only V681 frozen replay artifact."""
import csv, hashlib, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'
V680=AUD/'v680_frozen_v678_v679_identity_comparison_latest.json'; V681=AUD/'v681_single_frozen_t1_structure_replay_latest.json'
FIELDS=('symbol','weekly_permission_time','daily_ssl_time','daily_break_time','daily_ob_time','daily_first_touch_time','h60_ssl_time','h60_break_time','h60_ob_time','h60_hold_time')
def ident(r):return tuple(r.get(k,'') for k in FIELDS)
def date(v):return ''.join(c for c in str(v) if c.isdigit())[:8]
def main():
    gate=json.loads(V680.read_text()); rep=json.loads(V681.read_text())
    rows=list(csv.DictReader(open(rep['artifact'],newline='',encoding='utf-8')))
    frozen=[r for r in csv.DictReader(open(gate['v678_artifact'],newline='',encoding='utf-8')) if r.get('terminal')=='SEED_READY']
    rset,fset={ident(x) for x in rows},{ident(x) for x in frozen}
    closed=[r for r in rows if r.get('status')=='CLOSED']; wins=[r for r in closed if float(r['net_pnl_pct'])>0]; losses=[r for r in closed if float(r['net_pnl_pct'])<=0]
    pnl=[float(r['net_pnl_pct']) for r in closed]; profit=sum(x for x in pnl if x>0); loss=-sum(x for x in pnl if x<0)
    years=defaultdict(list)
    for r in closed:years[date(r['entry_time'])[:4]].append(float(r['net_pnl_pct']))
    annual={y:{'n':len(x),'net_wr_pct':100*sum(v>0 for v in x)/len(x),'avg_net_pct':sum(x)/len(x)} for y,x in sorted(years.items())}
    t1=[r for r in closed if date(r['exit_time'])<=date(r['entry_time'])]
    bad_bounds=[r for r in closed if not(float(r['entry_price'])>float(r['stop_price']) and float(r['entry_price'])<float(r['target_price']))]
    reason=Counter(r.get('exit_reason','') for r in closed); statuses=Counter(r.get('status','') for r in rows)
    metric={'closed_n':len(closed),'net_wr_pct':100*len(wins)/len(closed) if closed else 0,'avg_net_pnl_pct':sum(pnl)/len(pnl) if pnl else 0,'profit_factor':profit/loss if loss else None,'payoff':(sum(float(r['net_pnl_pct']) for r in wins)/len(wins))/(-sum(float(r['net_pnl_pct']) for r in losses)/len(losses)) if wins and losses else None}
    checks={'frozen_identity_exact':rset==fset and len(rows)==len(frozen),'no_duplicate_replay_identity':len(rows)==len(rset),'t1_zero':not t1,'all_closed_bounds_valid':not bad_bounds,'recomputed_status_counts_match':dict(statuses)==rep['status_counts'],'recomputed_closed_n_match':metric['closed_n']==rep['closed_n'],'recomputed_metrics_match':all(abs(metric[k]-rep[k])<1e-9 for k in ('net_wr_pct','avg_net_pnl_pct','profit_factor','payoff'))}
    out={'version':'V682_INDEPENDENT_FROZEN_REPLAY_METRIC_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'v681_artifact':rep['artifact'],'rows':len(rows),'identity_hash':hashlib.sha256('\n'.join('|'.join(x) for x in sorted(rset)).encode()).hexdigest(),'status_counts':dict(statuses),'exit_reason_counts':dict(reason),'metrics':metric,'yearly':annual,'t1_violation_count':len(t1),'bound_violation_count':len(bad_bounds),'checks':checks,'decision':'V682_INDEPENDENT_AUDIT_CONFIRMS_V681_GATE_FAIL__CLOSE_ONTOLOGY__EMPTY_BOOK' if all(checks.values()) else 'V682_AUDIT_CONTRACT_FAILURE__EMPTY_BOOK'}
    text=json.dumps(out,ensure_ascii=False,indent=2);(AUD/'v682_independent_frozen_replay_metric_audit_latest.json').write_text(text);print(text)
if __name__=='__main__':main()
