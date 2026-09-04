#!/usr/bin/env python3
"""V446 frozen SSL-created bearish-IFVG role reversal conjunction.
Eligibility is rederived from raw bars before V444 outcomes are joined; one fixed replay only."""
import csv,json,statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
R=Path('/root/.hermes'); A=R/'smc_audit'; K=R/'kline_cache'; SRC=A/'v444_internal_liquidity_ifvg_frontier_latest.json'; L=A/'v446_ssl_created_ifvg_reversal_latest.json'; YEARS=('2023','2024','2025','2026')
def f(x):
 try:return float(x)
 except:return 0.0
def load(s):
 a=json.loads((K/f"{s.replace('.','_')}_daily_750.json").read_text()); o=[]
 for b in a:
  d=''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
  if d:o.append({'t':d,**{k:f(b.get(k)) for k in ('o','h','l','c')}})
 return sorted(o,key=lambda x:x['t'])
def lows(b):
 out=[]
 for i in range(3,len(b)-3):
  if all(b[j]['l']>b[i]['l'] for j in range(i-3,i+4) if j!=i):out.append((i,i+3,b[i]['l']))
 return out
def metrics(rows):
 if not rows:return {'n':0,'wr_pct':0,'avg_pnl_pct':0,'payoff_rr':0,'profit_factor':0}
 p=[f(x['pnl_pct']) for x in rows]; w=[x for x in p if x>0]; z=[x for x in p if x<=0]
 return {'n':len(p),'wr_pct':round(len(w)/len(p)*100,4),'avg_pnl_pct':round(sum(p)/len(p),4),'median_pnl_pct':round(statistics.median(p),4),'avg_win_pct':round(sum(w)/len(w),4) if w else 0,'avg_loss_pct':round(sum(z)/len(z),4) if z else 0,'payoff_rr':round((sum(w)/len(w))/abs(sum(z)/len(z)),4) if w and z and sum(z) else 0,'profit_factor':round(sum(w)/abs(sum(z)),4) if z and sum(z) else 0,'cum_pnl_pct':round(sum(p),4),'sl_pct':round(sum('SL' in x['exit_reason'] for x in rows)/len(rows)*100,4)}
def main():
 r=json.loads(SRC.read_text())
 with open(r['artifacts']['seeds']) as h: seeds=[x for x in csv.DictReader(h) if x['ontology']=='BEAR_IFVG_ROLE_REVERSAL']
 cache={}; eligible=[]; fails=Counter()
 for x in seeds:
  s=x['symbol']; cache.setdefault(s,(load(s),None)); b,_=cache[s]
  if cache[s][1] is None:cache[s]=(b,lows(b))
  ls=cache[s][1]; born=int(x['fvg_born_idx']); start=max(0,born-2)
  prior=[q for q in ls if q[1]<start and start-q[0]<=60]
  if not prior: fails['NO_CONFIRMED_SSL_REFERENCE']+=1;continue
  ref=prior[-1]; sweep=next((i for i in range(start,born+1) if b[i]['l']<ref[2]*.997),None)
  if sweep is None:fails['FVG_LEG_DID_NOT_RAID_SSL']+=1;continue
  y=dict(x);y.update({'ssl_ref_idx':ref[0],'ssl_confirm_idx':ref[1],'ssl_price':ref[2],'ssl_sweep_idx':sweep,'ssl_sweep_date':b[sweep]['t']})
  if not(ref[1]<sweep<=born<int(x['failure_idx'])<int(x['touch_idx'])<int(x['reclaim_idx'])<int(x['takeover_idx'])):fails['CHRONOLOGY']+=1;continue
  eligible.append(y)
 keys={(x['symbol'],x['eligible_entry_date']) for x in eligible}
 with open(r['artifacts']['trades']) as h: trades=[x for x in csv.DictReader(h) if x['ontology']=='BEAR_IFVG_ROLE_REVERSAL' and (x['symbol'],x['eligible_entry_date']) in keys]
 overall=metrics(trades); yearly={y:metrics([x for x in trades if x['entry_date'][:4]==y]) for y in YEARS}; t1=sum(x['exit_date']<=x['entry_date'] for x in trades)
 gate=overall['n']>=300 and overall['wr_pct']>=55 and overall['avg_pnl_pct']>=.5 and all(yearly[y]['n']>=40 and yearly[y]['wr_pct']>=50 and yearly[y]['avg_pnl_pct']>0 for y in YEARS) and t1==0
 outdir=A/f"v446_ssl_created_ifvg_reversal_no_write_{datetime.now():%Y%m%d_%H%M%S}";outdir.mkdir()
 fs=sorted({k for x in eligible for k in x});ft=sorted({k for x in trades for k in x})
 with (outdir/'v446_seeds.csv').open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fs);w.writeheader();w.writerows(eligible)
 with (outdir/'v446_trades.csv').open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=ft);w.writeheader();w.writerows(trades)
 out={'version':'V446_SSL_CREATED_BEAR_IFVG_ROLE_REVERSAL','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'frozen_contract':'confirmed 3/3 SSL reference -> bearish FVG creation leg raids SSL -> IFVG failure/retest/reclaim/hold from V444 -> unchanged frozen T+1 execution','pre_outcome_selection':True,'source_seed_count':len(seeds),'eligible_seed_count':len(eligible),'rejection_counts':dict(fails),'overall':overall,'yearly':yearly,'exit_reasons':dict(Counter(x['exit_reason'] for x in trades)),'t1_violations':t1,'promotion_gate_pass':gate,'decision':'SSL_CREATED_IFVG_PASS' if gate else 'SSL_CREATED_IFVG_FAIL__CLOSE_CONJUNCTION','artifacts':{'out_dir':str(outdir),'seeds':str(outdir/'v446_seeds.csv'),'trades':str(outdir/'v446_trades.csv'),'latest':str(L)}}
 text=json.dumps(out,ensure_ascii=False,indent=2);(outdir/'v446_report.json').write_text(text);L.write_text(text);print(text)
if __name__=='__main__':main()
