#!/usr/bin/env python3
"""V65 sample bias / filter funnel audit."""
from __future__ import annotations
import json, collections
from pathlib import Path
ROOT=Path('/root/.hermes')
SNAP=ROOT/'smc_opt_v50_signal/v50_signal_snapshot.json'
TR=ROOT/'smc_opt_v65/v65_trades.json'
PICKS=ROOT/'smc_opt_v65/v65_picks.json'
OUT=ROOT/'smc_audit/v65_sample_bias_audit.json'

def main():
    snap=json.loads(SNAP.read_text()) if SNAP.exists() else {}
    tr=json.loads(TR.read_text()) if TR.exists() else []
    picks=json.loads(PICKS.read_text()) if PICKS.exists() else []
    fam=collections.Counter()
    for sigs in snap.values(): fam.update(s.get('family') for s in sigs)
    trade_syms={t.get('symbol') for t in tr}
    active=[p for p in picks if p.get('pick_scope')=='ACTIVE_ENTRY']
    reject={
        'snapshot_symbols_without_trade': len(set(snap)-trade_syms),
        'trade_symbols': len(trade_syms),
        'active_entry_count': len(active),
        'near_zone_watch_count': sum(1 for p in picks if p.get('pick_scope')=='NEAR_ZONE_WATCH'),
        'post_entry_monitor_count': sum(1 for p in picks if p.get('pick_scope')=='POST_ENTRY_MONITOR'),
        'expired_review_count': sum(1 for p in picks if p.get('pick_scope')=='EXPIRED_REVIEW'),
    }
    out={'raw_signal_count':sum(fam.values()),'raw_signal_family_counts':dict(fam),'snapshot_symbol_count':len(snap),'trade_count':len(tr),'pick_count':len(picks),'pick_scope_counts':dict(collections.Counter(p.get('pick_scope') for p in picks)),'funnel':reject,'bias_flags':[]}
    if len(active)<=1 and out['funnel'].get('near_zone_watch_count',0) < 100:
        out['bias_flags'].append('ACTIVE_ENTRY_TOO_NARROW')
    if len(tr)<50:
        out['bias_flags'].append('TRADE_SAMPLE_BELOW_50')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
