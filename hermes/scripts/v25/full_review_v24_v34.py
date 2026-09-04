#!/usr/bin/env python3
import json, statistics, math, os
from pathlib import Path

def load(p): return json.loads(Path(p).read_text()) if Path(p).exists() else []
def f(x,d=0.0):
    try: return float(x)
    except: return d

def met(rows):
    n=len(rows); w=sum(1 for t in rows if f(t.get('pnl_pct'))>0 or t.get('won') is True); sl=sum(1 for t in rows if 'SL' in str(t.get('exit_reason','')).upper())
    return {'n':n,'wins':w,'wr':round(w/max(n,1)*100,1),'sl':sl,'sl_rate':round(sl/max(n,1)*100,1),'avg_pnl':round(sum(f(t.get('pnl_pct')) for t in rows)/max(n,1),2),'total_pnl':round(sum(f(t.get('pnl_pct')) for t in rows),2)}
def group(rows,keyfn):
    out={}
    for t in rows: out.setdefault(keyfn(t),[]).append(t)
    return {str(k):met(v) for k,v in sorted(out.items(), key=lambda kv: str(kv[0]))}
def quant(vals):
    vals=[v for v in vals if v is not None]
    if not vals: return {}
    vals=sorted(vals)
    def q(p): return vals[min(len(vals)-1, max(0,int(round((len(vals)-1)*p))))]
    return {'avg':round(sum(vals)/len(vals),2),'p50':round(q(.5),2),'p75':round(q(.75),2),'p90':round(q(.9),2),'max':round(vals[-1],2)}

v24=load('/root/.hermes/smc_opt_v24/v24_trades.json')
v34=load('/root/.hermes/smc_opt_v34d_final/v34_trades.json')
report={'files':{'v24':'/root/.hermes/smc_opt_v24/v24_trades.json','v34d':'/root/.hermes/smc_opt_v34d_final/v34_trades.json'},'metrics':{'v24':met(v24),'v34d':met(v34)}}
# V24 pathology
report['v24_pathology']={
 'by_zone_type':group(v24,lambda t:t.get('zone_type','?')),
 'by_conf_type':group(v24,lambda t:t.get('conf_type','?')),
 'by_regime':group(v24,lambda t:t.get('regime','?')),
 'by_ctx_score':group(v24,lambda t:t.get('ctx_score','?')),
 'zone_age':{'all':quant([f(t.get('zone_age'),None) for t in v24]), 'sl':quant([f(t.get('zone_age'),None) for t in v24 if 'SL' in str(t.get('exit_reason','')).upper()])},
 'entry_to_zone_pct':{'all':quant([f(t.get('entry_to_zone_pct'),None) for t in v24]), 'sl':quant([f(t.get('entry_to_zone_pct'),None) for t in v24 if 'SL' in str(t.get('exit_reason','')).upper()])},
 'bos_dist_pct':{'all':quant([f(t.get('bos_dist_pct'),None) for t in v24]), 'sl':quant([f(t.get('bos_dist_pct'),None) for t in v24 if 'SL' in str(t.get('exit_reason','')).upper()])},
 'hold_bars':{'all':quant([f(t.get('hold_bars'),None) for t in v24]), 'sl':quant([f(t.get('hold_bars'),None) for t in v24 if 'SL' in str(t.get('exit_reason','')).upper()])},
 'sl_first_bar':sum(1 for t in v24 if 'SL' in str(t.get('exit_reason','')).upper() and int(t.get('hold_bars',999))<=1),
 'sl_le_3bar':sum(1 for t in v24 if 'SL' in str(t.get('exit_reason','')).upper() and int(t.get('hold_bars',999))<=3),
 'ctx_seq_contains_no_ssl':sum(1 for t in v24 if 'SSL' not in str(t.get('ctx_seq','')) and 'Sweep' not in str(t.get('ctx_seq',''))),
 'ctx_seq_contains_pinbar_onlyish':sum(1 for t in v24 if 'Pinbar' in str(t.get('ctx_seq','')) and 'CHOCH' not in str(t.get('ctx_seq',''))),
}
report['v34d_pathology']={
 'by_exit':group(v34,lambda t:t.get('exit_reason','?')),
 'by_market':group(v34,lambda t:t.get('market_state','?')),
 'struct_to_confirm':quant([t.get('audit_chain',{}).get('time_gaps',{}).get('struct_to_confirm') for t in v34]),
 'zone_width_pct':quant([(f(t.get('zone_high'))-f(t.get('zone_low')))/max(f(t.get('zone_low')),1)*100 for t in v34]),
 'entry_over_zone_high_pct':quant([(f(t.get('entry_price'))/max(f(t.get('zone_high')),1)-1)*100 for t in v34]),
}
# Signal coverage status manual by code audit
report['signal_coverage']={
 'BOS/CHOCH':'V34D uses LuxAlgo leg displayStructure crossover/crossunder; closer than V24/V32 but not independently diffed against exact user Pine file in this run.',
 'MSS':'Implemented as CHOCH + recent SSL sweep + displacement; this is a local rule, not a direct Pine primitive; still needs exact script-level assertion if user Pine defines MSS differently.',
 'OB':'V34D fixed to LuxAlgo storeOrderBlock semantics for trading; V24/V32 old OB not valid for V34 structure.',
 'FVG':'Available only from smc_core_pine_like; V34D trading currently disables FVG entries. Need revalidate before using.',
 'BPR':'Available only from smc_core_pine_like; V34D trading disables BPR. Needs O(n) optimized and exact Pine parity.',
 'BRK/BreakerBlock':'Not implemented in V34D trading core. Old V11 has Breaker/Rejection concepts but not part of current audited engine.',
 'EQL/EQH':'Available in smc_core_pine_like; V34D sweep uses swing pivots only, not EQL/EQH pools. Needs merge.',
 'LV':'Available as simple displacement candle in smc_core_pine_like; not exact Lux/Pine liquidity void parity; not used by V34D trading.',
 'OTE':'Available as chart zone from structure in smc_core_pine_like; not used by V34D trading; exact swing anchor needs review.',
 'PB/Pinbar':'Only entry confirmation in engine; user preference says PB is confirmation, not standalone signal. V24 violated this by using Pinbar in ctx_seq.',
 'RB/RejectionBlock':'Not in V34D trading core. Old V11 has rejection block but not audited.',
 'Sweep':'V34D uses LuxAlgo swing-pivot sweep, wick through + close reclaim. Does not yet include EQL/EQH pool sweeps.'
}
Path('/root/.hermes/smc_opt_v34d_final/full_review_20260522.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
