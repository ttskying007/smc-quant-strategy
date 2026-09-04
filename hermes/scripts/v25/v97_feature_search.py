#!/usr/bin/env python3
from __future__ import annotations
import json, itertools
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List
from v91_shadow_zone_entry_scanner import num
ROWS=json.loads(Path('/root/.hermes/smc_opt_v97_structural_rr_contract/v97_structural_trades.json').read_text())
prod=[r for r in ROWS if r.get('production_grade')=='A_PRODUCTION']
def f(x:Any,d:float=0.0)->float: return num(x,d)
def met(rs):
 n=len(rs); wins=sum(1 for r in rs if f(r.get('pnl_pct'))>0); sl=sum(1 for r in rs if r.get('exit_reason')=='SL_HIT')
 return {'n':n,'wr':round(wins/n*100,2) if n else 0,'sl':round(sl/n*100,2) if n else 0,'avg':round(sum(f(r.get('pnl_pct')) for r in rs)/n,4) if n else 0,'cum':round(sum(f(r.get('pnl_pct')) for r in rs),2),'tp2':round(sum(f(r.get('tp2_rr')) for r in rs)/n,3) if n else 0}
def bval(r,feat):
 if feat=='risk_bin':
  v=f(r.get('risk_pct'))
  if v<0.7:return '<0.7'
  if v<0.9:return '0.7-0.9'
  if v<1.1:return '0.9-1.1'
  if v<1.3:return '1.1-1.3'
  return '>=1.3'
 if feat=='zone_width_bin':
  v=f(r.get('v85_zone_width_pct') or r.get('volatility_pct'))
  if v<0.5:return '<0.5'
  if v<0.8:return '0.5-0.8'
  if v<1.2:return '0.8-1.2'
  if v<1.8:return '1.2-1.8'
  if v<2.5:return '1.8-2.5'
  return '>=2.5'
 if feat=='tp2_bin':
  v=f(r.get('tp2_rr'))
  if v<5.5:return '5-5.5'
  if v<6.5:return '5.5-6.5'
  if v<8:return '6.5-8'
  if v<12:return '8-12'
  return '>=12'
 if feat=='tp3_bin':
  v=f(r.get('tp3_rr'))
  if v<8.5:return '8-8.5'
  if v<10:return '8.5-10'
  if v<14:return '10-14'
  return '>=14'
 if feat=='zone_pos_bin':
  ep=f(r.get('entry_price')); zl=f(r.get('zone_low')); zh=f(r.get('zone_high'))
  v=(ep-zl)/(zh-zl) if zh>zl else -1
  if v<0:return 'NA'
  if v<0.25:return 'low_q'
  if v<0.5:return 'mid_low'
  if v<0.75:return 'mid_high'
  return 'high_q'
 return str(r.get(feat) or 'EMPTY')
features=['market_state','pd_zone','event_type','v85_path','v90_recovery_substate','v91_gate_reason','risk_bin','zone_width_bin','tp2_bin','tp3_bin','zone_pos_bin']
print('BASE',met(prod))
for feat in features:
 groups=defaultdict(list)
 for r in prod: groups[bval(r,feat)].append(r)
 arr=[]
 for k,rs in groups.items():
  if len(rs)>=50:
   m=met(rs); m['feat']=feat; m['val']=k; arr.append(m)
 print('\nFEATURE',feat)
 for m in sorted(arr,key=lambda x:(-x['wr'],-x['n']))[:20]: print(json.dumps(m,ensure_ascii=False))
# brute force selected allowed sets
preds=[]
# single value predicates with min 200
for feat in features:
 vals=sorted(set(bval(r,feat) for r in prod))
 for v in vals:
  preds.append((f'{feat}={v}', lambda r,feat=feat,v=v: bval(r,feat)==v))
# range/group predicates manually
manual=[
 ('market_state in BULL/MIXED/ACC',lambda r:bval(r,'market_state') in ['BULL_CONTINUATION','MIXED','ACCUMULATION']),
 ('market_state in BULL/MIXED/DEEP?',lambda r:bval(r,'market_state') in ['BULL_CONTINUATION','MIXED']),
 ('pd_zone=DEEP_DISCOUNT',lambda r:bval(r,'pd_zone')=='DEEP_DISCOUNT'),
 ('tp2<12',lambda r:f(r.get('tp2_rr'))<12),
 ('tp2 5.5-12',lambda r:5.5<=f(r.get('tp2_rr'))<12),
 ('tp2 5-8',lambda r:5<=f(r.get('tp2_rr'))<8),
 ('risk 0.7-1.3',lambda r:0.7<=f(r.get('risk_pct'))<1.3),
 ('risk <1.3',lambda r:f(r.get('risk_pct'))<1.3),
 ('zone_width <0.8',lambda r:f(r.get('v85_zone_width_pct') or r.get('volatility_pct'))<0.8),
 ('zone_width >=2.5',lambda r:f(r.get('v85_zone_width_pct') or r.get('volatility_pct'))>=2.5),
 ('zone_width outside 0.8-2.5',lambda r:not (0.8<=f(r.get('v85_zone_width_pct') or r.get('volatility_pct'))<=2.5)),
 ('zone_pos high',lambda r:bval(r,'zone_pos_bin')=='high_q'),
 ('zone_pos mid/high',lambda r:bval(r,'zone_pos_bin') in ['mid_high','high_q']),
 ('event BOS',lambda r:bval(r,'event_type')=='BOS_CONTINUATION'),
 ('event SSL_CHOCH',lambda r:bval(r,'event_type')=='SSL_SWEEP_CHOCH_REVERSAL'),
 ('v91_gate RISK',lambda r:bval(r,'v91_gate_reason')=='RISK'),
]
preds=manual
best=[]
for L in range(1,5):
 for combo in itertools.combinations(preds,L):
  rs=[r for r in prod if all(fn(r) for _,fn in combo)]
  if len(rs)>=300:
   m=met(rs); m['rule']=' AND '.join(name for name,_ in combo); best.append(m)
print('\nBEST_COMBOS')
for m in sorted(best,key=lambda x:(-x['wr'],-x['avg'],-x['n']))[:50]: print(json.dumps(m,ensure_ascii=False))
