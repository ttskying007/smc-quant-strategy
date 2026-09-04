#!/usr/bin/env python3
"""V521 exact scanner-time materialization for V517/V519.

Reads only the current committed daily epoch. It emits a PENDING_NEXT_OPEN row
only when the response-confirmation is on the committed market date. It never
uses historical replay trades/candidates as live picks. The next-open price
validation is intentionally deferred to the next committed session.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes'); KD=ROOT/'kline_cache'; MON=ROOT/'smc_monitor'; AUD=ROOT/'smc_audit'
V517=AUD/'v517_daily_effort_result_absorption_seed_gate_latest.json'; V520=AUD/'v520_daily_effort_result_absorption_independent_metric_audit_latest.json'
OUT=AUD/f'v521_daily_effort_result_absorption_scanner_time_dry_run_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v521_daily_effort_result_absorption_scanner_time_dry_run_latest.json'
LEFT=RIGHT=3; LOOKBACK=20; BREACH=.003; RANK=.80; BUFFER=.99

def n(x:Any):
    try:
        z=float(x);return z if z>0 else None
    except (TypeError,ValueError):return None
def d(x:Any):
    s=''.join(c for c in str(x or '') if c.isdigit());return s[:8] if len(s)>=8 else ''
def bars(p:Path):
    try:raw=json.loads(p.read_text())
    except Exception:return []
    z=[]
    for r in raw if isinstance(raw,list) else []:
        date=d(r.get('t') or r.get('date') or r.get('day'));q=[n(r.get(k)) for k in ('o','h','l','c','v')]
        if date and all(v is not None for v in q):z.append({'d':date,'o':q[0],'h':q[1],'l':q[2],'c':q[3],'v':q[4]})
    return sorted(z,key=lambda x:x['d'])
def pivot_low(b,j):
    if j<LEFT or j+RIGHT>=len(b):return False
    return b[j]['l']<min(b[x]['l'] for x in range(j-LEFT,j)) and b[j]['l']<=min(b[x]['l'] for x in range(j+1,j+RIGHT+1))
def unmitigated_anchors(b,sweep):
    anchors=[]
    for j in range(sweep-RIGHT-1,LEFT-1,-1):
        if not pivot_low(b,j):continue
        ssl=b[j]['l']
        if not any(b[k]['l']<=ssl for k in range(j+RIGHT+1,sweep)):anchors.append(j)
    return anchors
def canonical_anchor(b,sweep):
    """Nearest prior confirmed, unmitigated SSL swept and reclaimed by `sweep`."""
    for j in unmitigated_anchors(b,sweep):
        ssl=b[j]['l']
        if b[sweep]['l']<=ssl*(1-BREACH) and b[sweep]['c']>ssl:return j
    return None
def pivot_high(b,j):
    if j<LEFT or j+RIGHT>=len(b):return False
    return b[j]['h']>max(b[x]['h'] for x in range(j-LEFT,j)) and b[j]['h']>=max(b[x]['h'] for x in range(j+1,j+RIGHT+1))
def target(b,sweep,minimum):
    # The first prior confirmed high still above the completed response is the
    # nearest unconsumed structural upside objective.
    for j in range(sweep-RIGHT-1,LEFT-1,-1):
        if pivot_high(b,j) and b[j]['h']>minimum:return j,b[j]['h']
    return None
def candidate(sym,b,market_date):
    # response must be final completed bar, so all source data is known at scan time.
    if len(b)<max(LOOKBACK,LEFT+RIGHT+2):return None
    r=len(b)-1
    if b[r]['d']!=market_date:return None
    sweep=r-1; swing=canonical_anchor(b,sweep)
    if swing is None:return None
    if not pivot_low(b,swing):return None
    prior=[b[k]['v'] for k in range(sweep-LOOKBACK,sweep)]
    vol_rank=sum(v<=b[sweep]['v'] for v in prior)/LOOKBACK
    if not (b[sweep]['l']<=b[swing]['l']*(1-BREACH) and b[sweep]['c']>b[swing]['l'] and vol_rank>=RANK and b[r]['c']>b[sweep]['h']):return None
    t=target(b,sweep,max(b[r]['h'], b[r]['c']))
    if t is None:return None
    j,price=t
    return {'symbol':sym,'ontology':'DAILY_EFFORT_RESULT_ABSORPTION','scanner_contract_version':'V3_PRIOR_CONFIRMED_CANONICAL_SSL','state':'PENDING_NEXT_OPEN','response_date':b[r]['d'],'swing_idx':swing,'swing_date':b[swing]['d'],'swing_confirm_date':b[swing+RIGHT]['d'],'swing_to_sweep_bars':sweep-swing,'canonical_anchor_rule':'NEAREST_PRIOR_CONFIRMED_UNMITIGATED_SSL_SWEPT_AND_RECLAIMED','sweep_idx':sweep,'response_idx':r,'sweep_date':b[sweep]['d'],'sweep_low':round(b[sweep]['l'],6),'sweep_high':round(b[sweep]['h'],6),'stop':round(b[sweep]['l']*BUFFER,6),'target_swing_date':b[j]['d'],'target':round(price,6),'prior20_volume_rank':round(vol_rank,6),'acceptance_at_next_open':'accept only if the exact next eligible-session opening quote is > stop and < target; then BUY_VALID; otherwise reject without fallback','causal_trace':'prior_confirmed_unmitigated_swing_low -> high_volume_SSL_sweep_reclaim -> response_close_breaks_sweep_high -> pending_next_open'}

def diagnostic_progress(sym,b,market_date):
    """Outcome-blind current-date funnel for observability only.

    A row appears only after a currently visible confirmed swing low. It is never
    a pending order or a trade: `furthest_stage` says exactly which next causal
    condition has not yet passed on the committed market date.
    """
    if len(b)<max(LOOKBACK,LEFT+RIGHT+2):return None
    r=len(b)-1
    if b[r]['d']!=market_date:return None
    sweep=r-1; anchors=unmitigated_anchors(b,sweep)
    if not anchors:return None
    canonical=canonical_anchor(b,sweep)
    swing=canonical if canonical is not None else anchors[0]
    row={'symbol':sym,'response_date':b[r]['d'],'sweep_date':b[sweep]['d'],
         'swing_date':b[swing]['d'],'swing_confirm_date':b[swing+RIGHT]['d'],
         'swing_low':round(b[swing]['l'],6),'swing_to_sweep_bars':sweep-swing,
         'canonical_anchor_rule':'NEAREST_PRIOR_CONFIRMED_UNMITIGATED_SSL_SWEPT_AND_RECLAIMED',
         'anchor_is_swept_reclaimed':canonical is not None,
         'sweep_low':round(b[sweep]['l'],6),'sweep_high':round(b[sweep]['h'],6),
         'response_close':round(b[r]['c'],6),'tradable':False,
         'trade_action':'RESEARCH_BLOCKED_NOT_EXECUTABLE'}
    if canonical is None:
        if b[sweep]['l']<=b[swing]['l']*(1-BREACH):
            row.update(furthest_stage='SSL_BREACH',next_required='SWEEP_CLOSE_RECLAIM_ABOVE_SWING_LOW')
        else:
            row.update(furthest_stage='CONFIRMED_SWING_LOW',next_required='SSL_BREACH_AT_LEAST_0.3_PCT')
        return row
    prior=[b[k]['v'] for k in range(sweep-LOOKBACK,sweep)]
    vol_rank=sum(v<=b[sweep]['v'] for v in prior)/LOOKBACK
    row['prior20_volume_rank']=round(vol_rank,6)
    if vol_rank<RANK:
        row.update(furthest_stage='SWEEP_RECLAIM',next_required='SWEEP_VOLUME_TOP_QUINTILE')
        return row
    if not b[r]['c']>b[sweep]['h']:
        row.update(furthest_stage='HIGH_VOLUME_SWEEP_RECLAIM',next_required='RESPONSE_CLOSE_BREAKS_SWEEP_HIGH')
        return row
    t=target(b,sweep,max(b[r]['h'],b[r]['c']))
    if t is None:
        row.update(furthest_stage='RESPONSE_BREAK',next_required='UNCONSUMED_STRUCTURAL_UPSIDE_TARGET')
        return row
    j,price=t
    row.update(furthest_stage='FULL_CURRENT_SETUP',next_required='EXACT_NEXT_SESSION_OPEN_AND_RELEASE_LICENSE',target_swing_date=b[j]['d'],target=round(price,6))
    return row
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    g=json.loads(V517.read_text());a=json.loads(V520.read_text());manifest=json.loads((MON/'kline_epoch_current.json').read_text())
    md=d(manifest.get('market_date'))
    admission_eligible = g.get('support_gate_pass') and a.get('audit_pass') and manifest.get('status')=='COMMITTED'
    rows=[];partial_rows=[];seen=0;fresh=0
    funnel={'fresh_on_committed_epoch':0,'confirmed_swing_low':0,'ssl_breach':0,'sweep_reclaim':0,'high_volume_sweep_reclaim':0,'response_break':0,'full_current_setup':0}
    for p in sorted(KD.glob('*_daily_750.json')):
        stem=p.name.replace('_daily_750.json','')
        try:code,ex=stem.rsplit('_',1)
        except ValueError:continue
        b=bars(p);seen+=1
        is_fresh=bool(b and b[-1]['d']==md)
        if is_fresh:
            fresh+=1;funnel['fresh_on_committed_epoch']+=1
        sym=f'{code}.{ex}'
        progress=diagnostic_progress(sym,b,md)
        if progress:
            partial_rows.append(progress)
            stage=progress['furthest_stage']
            funnel['confirmed_swing_low']+=1
            if stage in ('SSL_BREACH','SWEEP_RECLAIM','HIGH_VOLUME_SWEEP_RECLAIM','RESPONSE_BREAK','FULL_CURRENT_SETUP'):funnel['ssl_breach']+=1
            if stage in ('SWEEP_RECLAIM','HIGH_VOLUME_SWEEP_RECLAIM','RESPONSE_BREAK','FULL_CURRENT_SETUP'):funnel['sweep_reclaim']+=1
            if stage in ('HIGH_VOLUME_SWEEP_RECLAIM','RESPONSE_BREAK','FULL_CURRENT_SETUP'):funnel['high_volume_sweep_reclaim']+=1
            if stage in ('RESPONSE_BREAK','FULL_CURRENT_SETUP'):funnel['response_break']+=1
            if stage == 'FULL_CURRENT_SETUP':funnel['full_current_setup']+=1
        r=candidate(sym,b,md)
        if r:rows.append(r)
    blocked_by={'v517_support_gate':bool(g.get('support_gate_pass')),'v520_independent_audit':bool(a.get('audit_pass')),'committed_epoch':manifest.get('status')=='COMMITTED'}
    decision=(
        'V521_PENDING_NEXT_OPEN_ROWS__AWAIT_NEXT_COMMITTED_OPEN_VALIDATION' if rows and admission_eligible else
        'V521_CURRENT_CANDIDATES_BLOCKED_BY_RESEARCH_GATE__NO_PRODUCTION_WRITE' if rows else
        'V521_NO_CURRENT_PENDING_ROWS__NO_HISTORICAL_FALLBACK'
    )
    report={'version':'V521_DAILY_EFFORT_RESULT_ABSORPTION_SCANNER_TIME_DRY_RUN_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'epoch_id':manifest.get('epoch_id'),'market_date':md,'files_seen':seen,'files_on_committed_date':fresh,'contract':g['frozen_contract'],'scanner_contract':'only response_date == committed market_date; scanner emits outcome-blind current candidates only; production admission requires independent research/release gates; next-open acceptance checks are required before BUY_VALID','admission_eligible':bool(admission_eligible),'pending_next_open_count':len(rows),'buy_valid_count':0,'rows':rows,'diagnostic_funnel':{'contract':'current-date only; every partial row is outcome-blind, non-executable and not a pending order','counts':funnel,'partial_rows':partial_rows,'full_current_setup_count':funnel['full_current_setup'],'release_blocker':('V520_INDEPENDENT_METRIC_AUDIT_FAILED' if not a.get('audit_pass') else None)},'invariants':{'all_rows_response_on_market_date':all(x['response_date']==md for x in rows),'all_partial_rows_response_on_market_date':all(x['response_date']==md for x in partial_rows),'no_historical_trade_source':True,'no_outcome_fields':all(not any(k in x for k in ('pnl','exit','mfe','mae','entry_price')) for x in rows+partial_rows),'all_production_writes_false':True},'blocked_by':blocked_by,'decision':decision,'artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'v517':str(V517),'v520':str(V520)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v521_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
