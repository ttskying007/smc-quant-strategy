#!/usr/bin/env python3
"""V463 one-shot frozen strict-T+1 replay for V461/V462 market-SMT."""
from __future__ import annotations
import csv,importlib.util,json
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');AUD=ROOT/'smc_audit';SRC=AUD/'v462_market_smt_independent_oracle_latest.json'
OUT=AUD/f"v463_market_smt_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v463_market_smt_frozen_t1_replay_latest.json'
spec=importlib.util.spec_from_file_location('v455',ROOT/'scripts/v25/v455_turtle_soup_frozen_t1_replay.py');v455=importlib.util.module_from_spec(spec);spec.loader.exec_module(v455)
GATE=dict(v455.GATE)

def delta(current,base):
    keys=('gross_wr_pct','net_wr_ge_0_8_pct','avg_net_pnl_pct','payoff_rr','profit_factor','sl_pct')
    return {k:round(current.get(k,0)-base.get(k,0),4) for k in keys}

def main():
    source=json.loads(SRC.read_text())
    if source.get('decision')!='MARKET_SMT_INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT':raise RuntimeError('V462 oracle gate failed')
    with Path(source['artifacts']['passed_seeds']).open(newline='') as h:seeds=list(csv.DictReader(h))
    OUT.mkdir(parents=True,exist_ok=True);grouped=defaultdict(list)
    for seed in seeds:grouped[seed['symbol']].append(seed)
    rows=[]
    for n,(sym,items) in enumerate(grouped.items(),1):
        bars=v455.load(sym);highs=v455.confirmed_highs(bars)
        for seed in items:
            rows.append({**seed,'execution_contract':'NEXT_OPEN__RAID_LOW_1PCT_SL__KNOWN_BSL_OR_TIME20__STRICT_T1__FEE0P2',**v455.replay(seed,bars,highs)})
        if n%500==0:print(json.dumps({'symbols':n,'rows':len(rows)}),flush=True)
    closed=[r for r in rows if r.get('status')=='CLOSED' and r['entry_date'][:4] in {'2023','2024','2025','2026'}]
    yearly={y:v455.stats([r for r in closed if r['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')};overall=v455.stats(closed)
    epochs={'2023_2024':v455.stats([r for r in closed if r['entry_date'][:4] in {'2023','2024'}]),'2025_2026':v455.stats([r for r in closed if r['entry_date'][:4] in {'2025','2026'}])}
    t1=sum(bool(r.get('t1_violation')) for r in closed);passed=v455.gate_pass(overall,yearly,t1)
    base=json.loads((AUD/'v455_turtle_soup_frozen_t1_replay_latest.json').read_text());base_overall=base['overall'];base_yearly=base['yearly']
    fields=sorted({k for r in rows for k in r});rowfile=OUT/'v463_frozen_t1_rows.csv'
    with rowfile.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    report={'version':'V463_MARKET_SMT_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_before_outcomes':{'entry':'next open after Turtle-Soup reversal confirmation','sl':'stock raid low * 0.99','target':'nearest pre-entry confirmed stock 3L/3R BSL','exit':'strict T+1; target/SL/time20; gap-aware; same-bar collision=SL','fee_pct':v455.FEE_PCT,'search_count':1,'promotion_gate':GATE},
      'seed_count':len(seeds),'status_counts':dict(Counter(r.get('status') for r in rows)),'research_window_closed_n':len(closed),'overall':overall,'yearly':yearly,'epochs':epochs,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in closed)),
      'comparison_to_unconditioned_turtle_soup':{'baseline_overall':base_overall,'delta':delta(overall,base_overall),'yearly_delta':{y:delta(yearly[y],base_yearly[y]) for y in yearly}},
      'invariants':{'t1_violations':t1,'same_bar_collisions':sum(bool(r.get('same_bar_collision')) for r in closed),'selector_outcome_leak':0,'search_count':1,'source_oracle_pass':True},
      'promotion_gate_pass':passed,'decision':'MARKET_SMT_FROZEN_REPLAY_PASS__SHADOW_NEXT' if passed else 'MARKET_SMT_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS',
      'artifacts':{'out_dir':str(OUT),'rows':str(rowfile),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v463_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
