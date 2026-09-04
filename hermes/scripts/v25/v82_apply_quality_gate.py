#!/usr/bin/env python3
import json
from collections import defaultdict
from pathlib import Path
from v82_smart_money_quality_gate import enrich_v82_features, passes_v82_quality_gate, f

SRC=Path('/root/.hermes/smc_opt_v81_contextual_smc_generator/v81_candidates.json')
OUT=Path('/root/.hermes/smc_opt_v82_smart_money_quality_gate')
OUT.mkdir(parents=True, exist_ok=True)

def metrics(rows):
    rs=list(rows)
    if not rs:
        return {'n':0,'wr':0,'avg_pnl':0,'cum':0,'poi_break_rate':0,'trend_damage_rate':0,'tp_rate':0}
    vals=[f(r.get('pnl_pct')) for r in rs]
    n=len(rs)
    return {
        'n':n,
        'wr':round(sum(v>0 for v in vals)/n*100,2),
        'avg_pnl':round(sum(vals)/n,4),
        'cum':round(sum(vals),2),
        'poi_break_rate':round(sum(r.get('exit_reason')=='EXIT_POI_CLOSE_BREAK' for r in rs)/n*100,2),
        'trend_damage_rate':round(sum(r.get('exit_reason')=='EXIT_TREND_STRUCTURE_DAMAGE' for r in rs)/n*100,2),
        'tp_rate':round(sum(r.get('exit_reason')=='TAKE_PROFIT_LIQUIDITY_TARGET' for r in rs)/n*100,2),
    }

def bucket(rows,key):
    g=defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k:metrics(v) for k,v in sorted(g.items())}

def main():
    rows=json.loads(SRC.read_text())
    annotated=[]; selected=[]
    for r in rows:
        nr=enrich_v82_features(r)
        nr['v82_quality_gate']=passes_v82_quality_gate(nr)
        annotated.append(nr)
        if nr['v82_quality_gate']:
            selected.append(nr)
    report={
        'engine':'V82_SMART_MONEY_QUALITY_GATE',
        'source':str(SRC),
        'rules':{
            'market_state':'BULL_CONTINUATION/BEAR_RISK/DISTRIBUTION/MIXED only; RECOVERY/ACCUMULATION blocked until true demand validation is rebuilt',
            'pd_zone':'DEEP_DISCOUNT only',
            'risk_pct':'1.5 < entry-zone_low <= 4.0%',
            'zone_width_pct':'0.5 < zone width <= 3.0%',
            'reclaim_lag':'touch then later reclaim, lag >= 2 bars',
            'target_rr':'>= 1.0',
            'prior_buffer':'-5% <= zone_low vs prior_structure_low <= 5%'
        },
        'metrics':{'v81_all':metrics(rows),'v82_selected':metrics(selected)},
        'year':bucket(selected, lambda r: str(r.get('entry_date',''))[:4]),
        'story':bucket(selected, lambda r: r.get('story')),
        'market_state':bucket(selected, lambda r: r.get('market_state')),
        't1_violations':sum(1 for r in selected if str(r.get('entry_date'))==str(r.get('exit_date'))),
        'field_audit':{
            'missing_select_date':sum(1 for r in selected if not r.get('select_date')),
            'missing_join_date':sum(1 for r in selected if not r.get('join_date')),
            'missing_zone':sum(1 for r in selected if not (r.get('zone_low') and r.get('zone_high'))),
            'missing_cost_line':sum(1 for r in selected if not r.get('smart_money_cost')),
            'missing_volatility':sum(1 for r in selected if not r.get('volatility_pct')),
        }
    }
    (OUT/'v82_annotated_candidates.json').write_text(json.dumps(annotated,ensure_ascii=False))
    (OUT/'v82_selected_candidates.json').write_text(json.dumps(selected,ensure_ascii=False))
    (OUT/'v82_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':
    main()
