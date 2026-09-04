#!/usr/bin/env python3
"""Completion audit for V47/V46.1 unfinished SMC work items.

Checks the six previously-open items against current code, outputs, and frontend
contracts. This is a status audit only; it does not mutate strategy outputs.
"""
from __future__ import annotations
import json, pathlib, re, time, urllib.request, collections
ROOT=pathlib.Path('/root/.hermes')
SCRIPTS=ROOT/'scripts'
V25=SCRIPTS/'v25'
OUT=ROOT/'smc_opt_v46_1_layered_3y'
V47=ROOT/'smc_opt_v47_candidate'
AUD=ROOT/'smc_audit'

def load(p, default=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return default

def text(path):
    try: return pathlib.Path(path).read_text(errors='ignore')
    except Exception: return ''

def http_json(path):
    try: return json.loads(urllib.request.urlopen('http://127.0.0.1:8890'+path,timeout=20).read())
    except Exception as e: return {'__error__':repr(e)}

def has_regex(paths, pat):
    rx=re.compile(pat,re.I|re.S)
    hits=[]
    for p in paths:
        t=text(p)
        if rx.search(t): hits.append(str(p))
    return hits

def metrics(rows):
    if not rows: return {}
    def f(x):
        try: return float(x or 0)
        except Exception: return 0.0
    n=len(rows); wins=sum(f(r.get('pnl_pct'))>0 for r in rows); sl=sum('SL' in str(r.get('exit_reason','')) for r in rows)
    return {'n':n,'wr':round(wins/n*100,2),'sl_rate':round(sl/n*100,2),'avg_pnl':round(sum(f(r.get('pnl_pct')) for r in rows)/n,3)}

def main():
    py=list(V25.glob('*.py'))+[SCRIPTS/'smc_unified.py']
    full=load(AUD/'v47_full_audit.json',{}) or {}
    trade=load(AUD/'v47_trade_autopsy.json',{}) or {}
    exp=load(AUD/'v47_entry_sl_exit_experiments.json',{}) or {}
    trades=load(OUT/'v46_1_trades.json',[]) or []
    picks=http_json('/api/picks')
    picks_all=http_json('/api/picks?include_reject=1')
    kline=http_json('/api/kline_full?symbol=600519.SH&tf=daily&ver=V46_1')

    items={}
    # 1 production entry zone_mid/deeper: accept V47 candidate evidence if present;
    # V46.1 remains production active, so report both current and candidate.
    entry_hits=has_regex(py, r'zone_mid|entry_zone_mid|E2_ZONE_MID|E3_RAW_LOW|deeper_retrace|raw_zone_low.*entry')
    v47_a=load(V47/'v47_trade_autopsy.json',{}) or {}
    avg_entry=(trade.get('summary') or {}).get('avg_entry_zone_pos')
    v47_entry=(v47_a.get('summary') or {}).get('avg_entry_zone_pos')
    items['1_entry_zone_mid_or_deeper_productionized']={
        'status':'COMPLETE_CANDIDATE' if (V47/'v47_trades.json').exists() and v47_entry is not None and v47_entry < 0.75 else 'NOT_COMPLETE',
        'evidence':{'code_hits':entry_hits[:10],'v46_avg_entry_zone_pos':avg_entry,'v47_avg_entry_zone_pos':v47_entry,'experiment_exists':bool(exp.get('experiments'))}
    }
    # 2 structural SL productionized: candidate must carry structural rule and improve fake SL.
    sl_hits=has_regex(py, r'structural_sl|S2_STRUCTURAL|S3_STRUCTURAL|raw_zone_low.*sl|sl.*raw_zone_low|STRUCTURAL_CAP|STRUCTURAL_RAW_SWEEP')
    fake=(trade.get('summary') or {}).get('fake_sl_rate'); sl_dist=(trade.get('summary') or {}).get('avg_sl_dist_pct')
    v47_fake=(v47_a.get('summary') or {}).get('fake_sl_rate')
    v47_rows=(load(V47/'v47_trades.json',[]) or []) if (V47/'v47_trades.json').exists() else []
    v47_struct_sl=sum(1 for r in v47_rows if r.get('sl_rule_v47')=='STRUCTURAL_RAW_SWEEP')
    items['2_structural_sl_productionized']={
        'status':'COMPLETE_CANDIDATE' if v47_rows and v47_struct_sl==len(v47_rows) and v47_fake is not None and v47_fake < fake else 'NOT_COMPLETE',
        'evidence':{'code_hits':sl_hits[:10],'v46_fake_sl_rate':fake,'v46_avg_sl_dist_pct':sl_dist,'v47_fake_sl_rate':v47_fake,'v47_structural_sl':f'{v47_struct_sl}/{len(v47_rows)}'}
    }
    # 3 runner/liquidity exit productionized: candidate must reduce sold-early materially.
    exit_hits=has_regex(py, r'STRUCTURE_RUNNER|LIQUIDITY_TARGET|runner|liquidity.*target|mfe_capture|sold_early')
    sold=(trade.get('summary') or {}).get('sold_early_rate'); cap=(trade.get('summary') or {}).get('avg_mfe_capture')
    v47_sold=(v47_a.get('summary') or {}).get('sold_early_rate'); v47_cap=(v47_a.get('summary') or {}).get('avg_mfe_capture')
    items['3_runner_liquidity_exit_productionized']={
        'status':'COMPLETE_CANDIDATE' if v47_rows and v47_sold is not None and v47_sold < 55 else 'NOT_COMPLETE',
        'evidence':{'code_hits':exit_hits[:10],'v46_sold_early_rate':sold,'v46_avg_mfe_capture':cap,'v47_sold_early_rate':v47_sold,'v47_avg_mfe_capture':v47_cap}
    }
    # 4 Pine-like FVG dedicated audit: existing generic audit says lux fvgs=0; need dedicated file/section.
    pine_hits=has_regex(py, r'pine.*fvg|fvg.*pine|FVG_NOT_PINE|gap_low.*gap_high')
    signal_counts=(full.get('summary') or {}).get('signal_counts') or {}
    fvg_tr=[t for t in trades if 'FVG' in str(t.get('zone_type'))]
    fvg_gap=sum(1 for t in fvg_tr if (t.get('gap_low') is not None or t.get('raw_zone_low') is not None) and (t.get('gap_high') is not None or t.get('raw_zone_high') is not None))
    dedicated=any('fvg' in p.name.lower() and 'audit' in p.name.lower() for p in V25.glob('*fvg*.py'))
    fvg_audit=load(AUD/'v47_pine_fvg_audit.json',{}) or {}
    v47_fvg=((fvg_audit.get('v47') or {}).get('n_fvg') or 0)
    v47_fvg_fail=((fvg_audit.get('v47') or {}).get('failure_counts') or {})
    items['4_pine_like_fvg_dedicated_audit']={
        'status':'COMPLETE_CANDIDATE' if dedicated and v47_fvg>0 and not v47_fvg_fail else ('PARTIAL' if dedicated else 'NOT_COMPLETE'),
        'evidence':{'code_hits':pine_hits[:10],'dedicated_audit_file':dedicated,'generic_signal_audit_fvgs':signal_counts.get('fvgs'),'fvg_trades_with_bounds':f'{fvg_gap}/{len(fvg_tr)}','v47_fvg_audit_n':v47_fvg,'v47_fvg_failures':v47_fvg_fail}
    }
    # 5 wave BOS/CHOCH/MSS unified with wave layer.
    wave_break_hits=has_regex(py, r'wave_structure|wave.*BOS|wave.*CHOCH|wave.*MSS|BOS.*wave|CHOCH.*wave|MSS.*wave')
    kobs=[s for s in (kline.get('signals_list') or []) if s.get('family')=='ob'] if isinstance(kline,dict) else []
    kb=[s for s in (kline.get('signals_list') or []) if s.get('family') in ('bos','choch','mss')] if isinstance(kline,dict) else []
    wave_struct_labels=sum(1 for s in kb if s.get('wave_turn_label') or s.get('wave_ref_idx') or 'wave' in str(s.get('pivot_rule','')).lower())
    items['5_wave_structure_breaks_unified']={
        'status':'COMPLETE' if wave_break_hits and kb and wave_struct_labels==len(kb) else 'NOT_COMPLETE',
        'evidence':{'code_hits':wave_break_hits[:10],'kline_bos_choch_mss':len(kb),'wave_labeled_structure_breaks':wave_struct_labels,'kline_ob_missing_wave':sum(1 for s in kobs if not s.get('wave_turn_label'))}
    }
    # 6 full new candidate rebuild after entry/sl/exit productionized.
    v47_prod_dirs=[p for p in ROOT.glob('smc_opt_v47*') if p.is_dir() and p.stat().st_mtime > (OUT/'v46_1_validation_summary.json').stat().st_mtime]
    items['6_new_v47_full_rebuild_after_production_changes']={
        'status':'COMPLETE' if v47_prod_dirs else 'NOT_COMPLETE',
        'evidence':{'newer_v47_output_dirs':[str(p) for p in v47_prod_dirs], 'current_output':'v46_1_layered_3y', 'current_trades':len(trades), 'current_metrics':(load(OUT/'v46_1_validation_summary.json',{}) or {}).get('metrics')}
    }

    result={'generated_at':time.strftime('%F %T'),'items':items,'summary':collections.Counter(v['status'] for v in items.values())}
    AUD.mkdir(parents=True,exist_ok=True)
    (AUD/'v47_unfinished_completion_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
