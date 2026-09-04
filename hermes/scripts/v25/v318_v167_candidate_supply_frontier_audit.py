#!/usr/bin/env python3
"""V318 no-write audit: scanner-time candidate supply frontier from V167 source.

V315-V317 proved V185 row-level filters/exit overlays cannot promote. This changes
information content: start from the broader V167 scanner-time candidate supply
(793 trades) and search non-leaking pre-entry gates plus executable T+1 exits.
No production/frontend/watchlist writes.
"""
from __future__ import annotations

import importlib.util
import json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_opt_v167_exact_scanner_gate' / 'v167_trades.json'
AUDIT = ROOT / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTDIR = AUDIT / f'v318_v167_candidate_supply_frontier_no_write_{TS}'
LATEST = AUDIT / 'v318_v167_candidate_supply_frontier_latest.json'
V315_PATH = ROOT / 'scripts/v25/v315_v185_preentry_structural_frontier_audit.py'
V316_PATH = ROOT / 'scripts/v25/v316_v185_exit_mechanism_frontier_audit.py'

GATE = {'n_min': 300, 'min_year_n_min': 40, 'wr_min': 87.0, 'avg_min': 6.8, 'year_wr_min': 84.0, 'micro_max': 1.0}
EXIT_CONFIGS = [
    {'name': 'SOURCE_MATERIALIZED_1P5R_H10'},
    {'name': 'FULL_TP1.0R_H10', 'r_tp': 1.0, 'max_hold': 10},
    {'name': 'FULL_TP1.2R_H10', 'r_tp': 1.2, 'max_hold': 10},
    {'name': 'FULL_TP1.5R_H10', 'r_tp': 1.5, 'max_hold': 10},
    {'name': 'FULL_TP1.0R_H15', 'r_tp': 1.0, 'max_hold': 15},
    {'name': 'FULL_TP1.2R_H15', 'r_tp': 1.2, 'max_hold': 15},
]


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

v315 = load_mod('v315_for_v318', V315_PATH)
v316 = load_mod('v316_for_v318', V316_PATH)

def fnum(x, default=None):
    if x is None or x == '': return default
    try:
        if isinstance(x, bool): return default
        v = float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default

def dkey(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''

def materialized(r):
    return {
        'symbol': r.get('symbol'), 'entry_date': dkey(r.get('entry_date')), 'exit_date': dkey(r.get('exit_date')),
        'exit_reason': r.get('exit_reason'), 'pnl_pct': fnum(r.get('pnl_pct'), 0.0),
        'same_day_exit_violation': dkey(r.get('entry_date')) == dkey(r.get('exit_date')),
        'cfg': 'SOURCE_MATERIALIZED_1P5R_H10',
    }

def metrics(rows):
    n=len(rows)
    if not n: return {'n':0}
    pnls=[fnum(r.get('pnl_pct'),0.0) for r in rows]
    yrs=defaultdict(list)
    for r,p in zip(rows,pnls): yrs[str(r.get('entry_date') or '')[:4]].append(p)
    yc={y:len(v) for y,v in sorted(yrs.items()) if y}
    yw={y:round(sum(p>=0.8 for p in v)/len(v)*100,4) for y,v in sorted(yrs.items()) if y}
    m={
        'n':n,'wr':round(sum(p>=0.8 for p in pnls)/n*100,4),'gross_wr':round(sum(p>0 for p in pnls)/n*100,4),
        'avg':round(mean(pnls),4),'median':round(median(pnls),4),'loss_pct':round(sum(p<0 for p in pnls)/n*100,4),
        'micro_profit_pct':round(sum(0<p<0.8 for p in pnls)/n*100,4),'min_year_n':min(yc.values()) if yc else 0,
        'year_counts':yc,'year_wr':yw,'all_year_wr_min':round(min(yw.values()),4) if yw else 0,
        'same_day_exit_violations':sum(1 for r in rows if r.get('same_day_exit_violation')),
        'exit_counts':dict(Counter(str(r.get('exit_reason') or '') for r in rows)),
    }
    m['gate_status']='PRODUCTION_PASS' if (m['same_day_exit_violations']==0 and m['n']>=GATE['n_min'] and m['min_year_n']>=GATE['min_year_n_min'] and m['wr']>=GATE['wr_min'] and m['avg']>=GATE['avg_min'] and m['all_year_wr_min']>=GATE['year_wr_min'] and m['micro_profit_pct']<=GATE['micro_max']) else 'FAIL'
    return m

def cond_ok(fs, conds):
    for name,op,th in conds:
        v=fs.get(name)
        if v is None: return False
        if op=='<=' and not v<=th: return False
        if op=='>=' and not v>=th: return False
    return True

def parse_rule(rule):
    out=[]
    for part in rule.split(' AND '):
        if '<=' in part:
            a,b=part.split('<='); out.append((a,'<=',float(b)))
        elif '>=' in part:
            a,b=part.split('>='); out.append((a,'>=',float(b)))
    return out

def selected_indices(feats, conds):
    return [i for i,fs in feats.items() if cond_ok(fs, conds)]

def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    trades=json.load(open(SRC))
    feats={i:v315.derive_preentry(r) for i,r in enumerate(trades)}
    safe=sorted({k for fs in feats.values() for k,v in fs.items() if isinstance(v,(int,float)) and not isinstance(v,bool)})
    rows_by_cfg={'SOURCE_MATERIALIZED_1P5R_H10':[materialized(r) for r in trades]}
    for cfg in EXIT_CONFIGS[1:]:
        sim=[v316.simulate(r,cfg) for r in trades]
        rows_by_cfg[cfg['name']]=[x for x in sim if x is not None]
    full_cfg_metrics={name:metrics(rows) for name,rows in rows_by_cfg.items()}

    singles=[]
    quantiles=(0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85)
    for name in safe:
        vals=sorted(fs.get(name) for fs in feats.values() if isinstance(fs.get(name),(int,float)))
        if len(vals)<650: continue
        for q in quantiles:
            th=vals[int((len(vals)-1)*q)]
            for op in ('<=','>='):
                conds=[(name,op,th)]
                idxs=selected_indices(feats,conds)
                if len(idxs)<300: continue
                for cfg_name,cfg_rows in rows_by_cfg.items():
                    if len(cfg_rows)!=len(trades): continue
                    m=metrics([cfg_rows[i] for i in idxs]); m['rule']=f'{name}{op}{round(th,6)}'; m['selected_n']=len(idxs); m['cfg']=cfg_name; singles.append(m)
    top_single_rules=[]
    seen=set()
    for m in sorted(singles,key=lambda x:(x['gate_status']=='PRODUCTION_PASS',x['wr'],x['avg'],x['all_year_wr_min'],x['n']),reverse=True):
        key=m['rule']
        if key not in seen:
            seen.add(key); top_single_rules.append(key)
        if len(top_single_rules)>=80: break
    pairs=[]; parsed=[parse_rule(r)[0] for r in top_single_rules]
    seenp=set()
    for i in range(len(parsed)):
        for j in range(i+1,len(parsed)):
            if parsed[i][0]==parsed[j][0]: continue
            key=tuple(sorted([parsed[i],parsed[j]]))
            if key in seenp: continue
            seenp.add(key); conds=[parsed[i],parsed[j]]
            idxs=selected_indices(feats,conds)
            if len(idxs)<300: continue
            rule=' AND '.join(f'{a}{b}{round(c,6)}' for a,b,c in conds)
            for cfg_name,cfg_rows in rows_by_cfg.items():
                if len(cfg_rows)!=len(trades): continue
                m=metrics([cfg_rows[k] for k in idxs]); m['rule']=rule; m['selected_n']=len(idxs); m['cfg']=cfg_name; pairs.append(m)
    allc=singles+pairs
    ranked=sorted(allc,key=lambda x:(x['gate_status']=='PRODUCTION_PASS',x['wr'],x['avg'],x['all_year_wr_min'],x['n']),reverse=True)
    pass_rows=[x for x in ranked if x['gate_status']=='PRODUCTION_PASS']
    best=ranked[0] if ranked else {}
    best_rows=[]
    if best:
        idxs=selected_indices(feats,parse_rule(best['rule']))
        best_rows=[rows_by_cfg[best['cfg']][i] for i in idxs]
    report={
        'version':'V318_V167_CANDIDATE_SUPPLY_FRONTIER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
        'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
        'input':str(SRC),'gate':GATE,'exit_configs':EXIT_CONFIGS,
        'baseline_full_source_by_exit':full_cfg_metrics,
        'coverage':{'source_trades':len(trades),'safe_features':len(safe),'single_results':len(singles),'pair_results':len(pairs),'kline_found_rows':sum(1 for fs in feats.values() if fs.get('kline_found')==1)},
        'production_pass_count':len(pass_rows),'production_pass_top20':pass_rows[:20],'frontier_top30':ranked[:30],
        'best_policy':best,'best_rows_path':str(OUTDIR/'v318_best_rows.json'),
        'decision':'V318_CANDIDATE_SUPPLY_PASS__REQUIRES_CURRENT_SCANNER_SMOKE' if pass_rows else 'NO_V318_CANDIDATE_SUPPLY_PROMOTION__KEEP_V185',
        'artifacts':{'report':str(OUTDIR/'v318_report.json'),'all_results':str(OUTDIR/'v318_all_results.json'),'best_rows':str(OUTDIR/'v318_best_rows.json'),'latest':str(LATEST)},
    }
    json.dump(report,open(OUTDIR/'v318_report.json','w'),ensure_ascii=False,indent=2)
    json.dump(ranked,open(OUTDIR/'v318_all_results.json','w'),ensure_ascii=False,indent=2)
    json.dump(best_rows,open(OUTDIR/'v318_best_rows.json','w'),ensure_ascii=False,indent=2)
    json.dump(report,open(LATEST,'w'),ensure_ascii=False,indent=2)
    print(json.dumps({'latest':str(LATEST),'baseline_full_source_by_exit':full_cfg_metrics,'coverage':report['coverage'],'production_pass_count':len(pass_rows),'decision':report['decision'],'best_policy':best},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
