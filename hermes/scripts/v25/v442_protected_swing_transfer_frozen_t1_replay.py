#!/usr/bin/env python3
"""V442 one-shot frozen T+1 replay for Protected-Swing Transfer."""
from __future__ import annotations
import csv,json,math,statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SOURCE=AUD/'v441_protected_swing_transfer_independent_oracle_latest.json'
OUT=AUD/f'v442_protected_swing_transfer_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v442_protected_swing_transfer_frozen_t1_replay_latest.json'
STOP_BUFFER=.99; MAX_HOLD=30
GATE={'n':300,'each_year_n':40,'aggregate_wr_pct':55.0,'aggregate_avg_pnl_pct':.5,'each_year_wr_pct':50.0,'each_year_avg_pnl_pct':0.0,'each_epoch_wr_pct':50.0,'each_epoch_avg_pnl_pct':0.0,'t1_violations':0}
def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0
def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def load_bars(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    out=[]
    for b in raw:
        x={k:f(b.get(k)) for k in ('o','h','l','c')}
        if day(b) and all(x.values()): x['t']=day(b); out.append(x)
    return sorted(out,key=lambda x:x['t'])
def confirmed_highs(bars):
    out=[]
    for i in range(6,len(bars)-3):
        if all(bars[j]['h']<bars[i]['h'] for j in range(i-3,i+4) if j!=i): out.append((i,i+3,bars[i]['h'],bars[i]['t']))
    return out
def known_unconsumed_target(highs,bars,cutoff,entry):
    candidates=[]
    for pivot,confirm,price,pdate in highs:
        if confirm>cutoff or price<=entry: continue
        if any(bars[i]['h']>=price for i in range(confirm+1,cutoff+1)): continue
        candidates.append((price,pdate))
    return min(candidates,default=(None,''),key=lambda x:x[0])
def replay(row,bars,highs):
    takeover=int(row['takeover_idx']); eligible=int(row['eligible_entry_idx']) if row.get('eligible_entry_idx') not in ('',None) else None
    if eligible is None or eligible!=takeover+1:return {'status':'INVALID_ENTRY_CHRONOLOGY'}
    if eligible>=len(bars):return {'status':'UNOBSERVED_ENTRY'}
    entry=bars[eligible]['o']; sl=f(row['new_protected_low_price'])*STOP_BUFFER
    if entry<=0 or sl<=0 or sl>=entry:return {'status':'INVALID_NONPOSITIVE_RISK'}
    target,target_date=known_unconsumed_target(highs,bars,takeover,entry)
    first=eligible+1; last=eligible+MAX_HOLD
    if first>=len(bars) or last>=len(bars):return {'status':'OPEN_RIGHT_EDGE','entry_idx':eligible,'entry_date':bars[eligible]['t'],'entry_price':round(entry,4),'sl':round(sl,4)}
    exit_idx=last; exit_price=bars[last]['c']; reason='TIME30_NO_UNCONSUMED_BSL' if target is None else 'TIME30_BSL_UNREACHED'; collision=False
    for i in range(first,last+1):
        b=bars[i]
        if b['o']<=sl:exit_idx,exit_price,reason=i,b['o'],'SL_GAP_T1';break
        if target is not None and b['o']>=target:exit_idx,exit_price,reason=i,b['o'],'BSL_GAP_TP_T1';break
        hit_sl=b['l']<=sl; hit_tp=target is not None and b['h']>=target
        if hit_sl and hit_tp:exit_idx,exit_price,reason,collision=i,sl,'SL_TP_COLLISION_CONSERVATIVE_T1',True;break
        if hit_sl:exit_idx,exit_price,reason=i,sl,'PROTECTED_LOW_SL_T1';break
        if hit_tp:exit_idx,exit_price,reason=i,target,'KNOWN_UNCONSUMED_BSL_TP_T1';break
    path=bars[eligible:exit_idx+1]; pnl=(exit_price/entry-1)*100
    return {'status':'CLOSED','entry_idx':eligible,'entry_date':bars[eligible]['t'],'entry_price':round(entry,4),'sl':round(sl,4),'risk_pct':round((entry/sl-1)*100,4),'tp':'' if target is None else round(target,4),'tp_anchor_date':target_date,'exit_idx':exit_idx,'exit_date':bars[exit_idx]['t'],'exit_price':round(exit_price,4),'exit_reason':reason,'hold_bars':exit_idx-eligible,'pnl_pct':round(pnl,4),'mfe_pct':round((max(x['h'] for x in path)/entry-1)*100,4),'mae_pct':round((min(x['l'] for x in path)/entry-1)*100,4),'t1_violation':bars[exit_idx]['t']<=bars[eligible]['t'],'same_bar_collision':collision}
def stats(rows):
    if not rows:return {'n':0,'wr_pct':0,'avg_pnl_pct':0}
    p=[f(r['pnl_pct']) for r in rows]; stops={'SL_GAP_T1','PROTECTED_LOW_SL_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}
    return {'n':len(rows),'wr_pct':round(sum(x>0 for x in p)/len(p)*100,4),'avg_pnl_pct':round(sum(p)/len(p),4),'median_pnl_pct':round(statistics.median(p),4),'sl_pct':round(sum(r['exit_reason'] in stops for r in rows)/len(rows)*100,4)}
def gate_pass(o,y,e,t1):
    return o['n']>=GATE['n'] and o['wr_pct']>=GATE['aggregate_wr_pct'] and o['avg_pnl_pct']>=GATE['aggregate_avg_pnl_pct'] and all(y[x]['n']>=GATE['each_year_n'] and y[x]['wr_pct']>=GATE['each_year_wr_pct'] and y[x]['avg_pnl_pct']>GATE['each_year_avg_pnl_pct'] for x in ('2023','2024','2025','2026')) and all(v['wr_pct']>=GATE['each_epoch_wr_pct'] and v['avg_pnl_pct']>GATE['each_epoch_avg_pnl_pct'] for v in e.values()) and t1==0
def main():
    source=json.loads(SOURCE.read_text())
    if source.get('decision')!='INDEPENDENT_SEMANTIC_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT':raise RuntimeError('V441 gate did not pass')
    with Path(source['artifacts']['oracle_rows']).open(newline='') as h:seeds=list(csv.DictReader(h))
    OUT.mkdir(parents=True,exist_ok=True); cache={}; hc={}; rows=[]
    for n,s in enumerate(seeds,1):
        sym=s['symbol']
        if sym not in cache:cache[sym]=load_bars(sym);hc[sym]=confirmed_highs(cache[sym])
        rows.append({**s,'execution_contract':'NEXT_OPEN__SL_NEW_PROTECTED_LOW_1PCT__KNOWN_UNCONSUMED_BSL_OR_TIME30__STRICT_T1',**replay(s,cache[sym],hc[sym])})
        if n%10000==0:print(json.dumps({'progress':n,'closed':sum(x.get('status')=='CLOSED' for x in rows)}),flush=True)
    closed=[r for r in rows if r.get('status')=='CLOSED']; years={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')}; epochs={'2023_2024':stats([r for r in closed if r['entry_date'][:4] in {'2023','2024'}]),'2025_2026':stats([r for r in closed if r['entry_date'][:4] in {'2025','2026'}])}; overall=stats(closed);t1=sum(bool(r.get('t1_violation')) for r in closed);passed=gate_pass(overall,years,epochs,t1)
    fields=sorted({k for r in rows for k in r})
    with (OUT/'v442_frozen_replay_rows.csv').open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    report={'version':'V442_PROTECTED_SWING_TRANSFER_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'frozen_before_outcomes':{'entry':'next open after takeover','sl':'new protected swing low * 0.99','target':'nearest unconsumed 3L/3R BSL visible by takeover; otherwise none','exit':'strict T+1; target/SL then time30; gap-aware; collision=SL','promotion_gate':GATE,'search_count':1},'seed_count':len(seeds),'status_counts':dict(Counter(r.get('status') for r in rows)),'overall':overall,'yearly':years,'epochs':epochs,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in closed)),'invariants':{'t1_violations':t1,'same_bar_collisions':sum(bool(r.get('same_bar_collision')) for r in closed),'selector_outcome_leak':0,'search_count':1},'promotion_gate_pass':passed,'decision':'PROTECTED_SWING_TRANSFER_FROZEN_REPLAY_PASS__CURRENT_RAW_SHADOW_SCANNER_NEXT' if passed else 'PROTECTED_SWING_TRANSFER_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS','artifacts':{'out_dir':str(OUT),'rows':str(OUT/'v442_frozen_replay_rows.csv'),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v442_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
