#!/usr/bin/env python3
"""V66 release gate."""
from __future__ import annotations
import json, urllib.request, time
from pathlib import Path
ROOT=Path('/root/.hermes')
OUT=ROOT/'smc_audit/v66_release_gate.json'
OUTMD=ROOT/'smc_audit/v66_release_gate.md'

def load(p,d=None):
    try:return json.loads(Path(p).read_text())
    except Exception:return d

def main():
    q=load(ROOT/'smc_audit/v66_quality_metrics.json',{}) or {}
    prov=load(ROOT/'smc_audit/v66_trade_provenance_audit.json',{}) or {}
    seq=load(ROOT/'smc_audit/v66_signal_sequence_audit.json',{}) or {}
    closed=load(ROOT/'smc_audit/v66_closed_loop_90d_review.json',{}) or {}
    bias=load(ROOT/'smc_audit/v66_sample_bias_audit.json',{}) or {}
    t1=load(ROOT/'smc_audit/v66_t1_audit.json',{}) or {}
    live=load(ROOT/'smc_audit/v66_live_execution_audit.json',{}) or {}
    live_checks=live.get('checks',{}) if isinstance(live,dict) else {}
    watch_count=(bias.get('funnel',{}) or {}).get('near_zone_watch_count',0)+(bias.get('funnel',{}) or {}).get('watch_only_count',0)
    active_count=(bias.get('funnel',{}) or {}).get('active_entry_count',0)
    checks={
        'trade_file_exists':(ROOT/'smc_opt_v66/v66_trades.json').exists(),
        'pick_file_exists':(ROOT/'smc_opt_v66/v66_picks.json').exists(),
        'signal_snapshot_exists':(ROOT/'smc_opt_v50_signal/v50_signal_snapshot.json').exists(),
        't1_no_same_day_exit': t1.get('pass') is True,
        'live_t1_no_same_day_fill': live_checks.get('live_t1_no_same_day_fill') is True,
        'ledger_t1_no_same_day_buy': live_checks.get('ledger_t1_no_same_day_buy') is True,
        'live_open_zone_complete': live_checks.get('open_zone_complete') is True,
        'live_open_cost_line_complete': live_checks.get('open_cost_line_complete') is True,
        'live_open_vol_class_complete': live_checks.get('open_vol_class_complete') is True,
        'live_open_zone_valid': live_checks.get('open_zone_valid') is True,
        'live_watch_only_has_reason': live_checks.get('watch_only_has_reason') is True,
        'live_production_reviews_clean_only': live_checks.get('production_reviews_clean_only') is True,
        'live_production_closed_positions_clean_only': live_checks.get('production_closed_positions_clean_only') is True,
        'provenance_fatal_count_zero':prov.get('summary',{}).get('fatal_count')==0,
        'sequence_violations_zero':seq.get('summary',{}).get('violation_count')==0,
        'hold_over_90_zero':q.get('hold_over_90')==0,
        'small_win_below_2_zero':q.get('small_win_below_2')==0,
        'loss_inside_1pct_zero':q.get('loss_inside_1pct')==0,
        'win_rr_below_2r_zero':q.get('win_rr_below_2r')==0,
        'avg_90d_capture_min_024': closed.get('summary',{}).get('avg_90d_capture',0)>=0.24,
        'sample_not_too_narrow': active_count > 1 or watch_count >= 100,
        'live_clean_provenance_complete': live_checks.get('clean_provenance_complete') is True,
    }
    failed=[k for k,v in checks.items() if not v]
    out={'pass':not failed,'failed_checks':failed,'checks':checks,'quality':q,'closed_loop_summary':closed.get('summary',{}),'bias_flags':bias.get('bias_flags',[]),'live_execution_summary':live,'provenance_summary':prov.get('summary',{}),'sequence_summary':seq.get('summary',{})}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    OUTMD.write_text('# V66 Release Gate\n\n```json\n'+json.dumps(out,ensure_ascii=False,indent=2)+'\n```\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
