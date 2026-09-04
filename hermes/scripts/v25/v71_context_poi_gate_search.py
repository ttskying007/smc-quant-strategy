#!/usr/bin/env python3
"""Mine non-leaking V71 Context→POI gates from state audit output."""
from __future__ import annotations
import json, itertools
from pathlib import Path

ROOT=Path('/root/.hermes')
IN=ROOT/'smc_opt_v71_context_poi'/'v71_context_poi_state_audit.json'
OUT=ROOT/'smc_opt_v71_context_poi'/'v71_context_poi_gate_search.json'
MD=ROOT/'smc_opt_v71_context_poi'/'v71_context_poi_gate_search.md'

def metrics(rs):
    if not rs: return None
    return {'n':len(rs),'wr':round(sum(x['won'] for x in rs)/len(rs)*100,2),'avg':round(sum(x['pnl_pct'] for x in rs)/len(rs),4),'sl':round(sum(x['exit_reason']=='SL_HIT' for x in rs)/len(rs)*100,2)}

def main():
    rows=json.loads(IN.read_text())['rows']
    preds={
      'valid_story': lambda x:x['story_valid'],
      'has_reaction': lambda x:x['poi_reclaim_before_entry'],
      'discount_or_ote': lambda x:x['pd_zone'] in ('OTE_DISCOUNT','DISCOUNT'),
      'ote_only': lambda x:x['pd_zone']=='OTE_DISCOUNT',
      'no_close_below_poi': lambda x:not x['poi_closed_below_before_entry'],
      'continuation_model': lambda x:x['smc_story']=='CONTINUATION_BOS_PULLBACK_TO_DEMAND',
      'reversal_model': lambda x:x['smc_story']=='REVERSAL_SSL_CHOCH_TO_DEMAND',
      'up_ctx': lambda x:x['market_context']=='UP_CONTINUATION_CONTEXT',
      'range_ctx': lambda x:x['market_context']=='RANGE_OR_TRANSITION_CONTEXT',
      'down_reversal_ctx': lambda x:x['market_context']=='DOWN_REVERSAL_NEEDED_CONTEXT',
      'down_danger_ctx': lambda x:x['market_context']=='DOWN_CONTINUATION_DANGER',
      'struct_bos': lambda x:x['struct_event']=='BOS_CONTINUATION',
      'struct_choch': lambda x:x['struct_event']=='CHOCH_REVERSAL',
      'ssl_sweep': lambda x:x.get('ssl_sweep') is True,
      'bounce_ge_2': lambda x:x.get('pre_entry_bounce_pct',0)>=2,
      'entry_pos_21_50': lambda x:21<=x.get('entry_pos_pct',999)<=50,
      'zone_pos_21_50': lambda x:21<=x.get('zone_pos_pct',999)<=50,
      'ret20_pos': lambda x:x.get('ret20',0)>0,
      'ret20_neg': lambda x:x.get('ret20',0)<0,
    }
    results=[]
    keys=list(preds)
    for L in range(1,6):
        for combo in itertools.combinations(keys,L):
            rs=[x for x in rows if all(preds[k](x) for k in combo)]
            m=metrics(rs)
            if not m or m['n']<50: continue
            if m['wr']>=70 or (m['wr']>=65 and m['avg']>=2.5):
                results.append({'combo':combo,'metrics':m})
    # remove strict supersets with identical population/metrics unless WR improves.
    results=sorted(results,key=lambda x:(x['metrics']['wr'],x['metrics']['avg'],x['metrics']['n'],-len(x['combo'])),reverse=True)
    kept=[]
    for r in results:
        s=set(r['combo']); m=r['metrics']
        redundant=False
        for k in kept:
            if set(k['combo']).issubset(s) and k['metrics']==m:
                redundant=True; break
        if not redundant:
            kept.append(r)
        if len(kept)>=60: break
    report={'source':str(IN),'n_rows':len(rows),'top_gates':kept}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    lines=['# V71 Context→POI Gate Search','','| rank | gate | n | WR | avg | SL率 |','|---:|---|---:|---:|---:|---:|']
    for i,r in enumerate(kept[:40],1):
        m=r['metrics']; lines.append(f"| {i} | {' + '.join(r['combo'])} | {m['n']} | {m['wr']} | {m['avg']} | {m['sl']} |")
    MD.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'top':kept[:12],'outputs':{'json':str(OUT),'md':str(MD)}},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
