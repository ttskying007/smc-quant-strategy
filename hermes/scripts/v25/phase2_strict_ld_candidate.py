#!/usr/bin/env python3
"""Build Phase2 strict L→D candidate trades from the isolated generator.

This script does NOT touch front-end or production files. It materializes the
best full-market strict L→D candidate found by the Phase2 repair pass:

  SSL sweep -> bullish displacement -> FVG demand -> reclaim entry

Candidate gate:
  - zone_type = FVG_Demand only (OB buckets were negative expectancy)
  - rr_target = 0.8 (best avg PnL while keeping WR in the recovered 60%+ band)
  - 6% <= risk_pct <= 8% (full-market best quality band)
  - strict T+1 simulation inherited from phase2_strict_ld_backtest.simulate()

Output is a self-contained audit JSON for promotion review; production sync is
intentionally deferred until this candidate is accepted.
"""
import json
import importlib.util
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path('/root/.hermes/scripts/v25/phase2_strict_ld_backtest.py')
OUT = Path('/root/.hermes/smc_opt_v25/phase2_strict_ld_candidate_v1.json')

spec = importlib.util.spec_from_file_location('ld', BASE)
ld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ld)

CANDIDATE = {
    'name': 'Phase2_Strict_LD_FVG_RR08_Risk6_8',
    'definition_version': 'Phase2_LD_v2_candidate_v1',
    'sequence': 'SSL_SWEEP -> BULL_DISPLACEMENT -> FVG_DEMAND -> RECLAIM_ENTRY',
    'filters': {
        'zone_type': 'FVG_Demand',
        'rr_target': 0.8,
        'risk_pct_min': 6.0,
        'risk_pct_max': 8.0,
    },
}


def keep(t):
    return (
        t.get('zone_type') == 'FVG_Demand'
        and abs(float(t.get('rr_target', 0)) - 0.8) < 1e-9
        and 6.0 <= float(t.get('risk_pct', 999)) <= 8.0
    )


def date_order_ok(t):
    keys = ['liq_date', 'confirm_date', 'zone_date', 'entry_date', 'exit_date']
    # zone can form at/near displacement; hard temporal contract is L <= zone <= entry <= exit and L <= confirm <= entry.
    try:
        return (
            str(t['liq_date']) <= str(t['zone_date']) <= str(t['entry_date']) <= str(t['exit_date'])
            and str(t['liq_date']) <= str(t['confirm_date']) <= str(t['entry_date']) <= str(t['exit_date'])
        )
    except Exception:
        return False


def bucket(ts, fn):
    g = defaultdict(list)
    for t in ts:
        g[fn(t)].append(t)
    return {str(k): ld.metrics(v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def main():
    files = sorted(ld.KLINE_DIR.glob('*_daily_750.json'))
    all_trades = []
    for i, kf in enumerate(files, 1):
        all_trades.extend(t for t in ld.replay_file(kf) if keep(t))
        if i % 500 == 0:
            print(f'  {i}/{len(files)} candidate_trades={len(all_trades)}', flush=True)

    # annotate candidate version without mutating generator semantics
    for t in all_trades:
        t['candidate_name'] = CANDIDATE['name']
        t['definition_version'] = CANDIDATE['definition_version']
        t['sequence'] = CANDIDATE['sequence']
        t['promotion_scope'] = 'AUDIT_ONLY_NOT_FRONTEND_SYNCED'

    semantic_failures = [t for t in all_trades if not date_order_ok(t)]
    same_day_exits = [t for t in all_trades if str(t.get('entry_date')) == str(t.get('exit_date'))]
    missing = Counter()
    required = ['symbol','liq_date','confirm_date','zone_date','entry_date','exit_date','zone_type','zone_low','zone_high','entry_price','sl','tp1','risk_pct','retrace_pct','exit_reason','pnl_pct']
    for t in all_trades:
        for k in required:
            if t.get(k) in (None, ''):
                missing[k] += 1

    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'n_stocks': len(files),
        'candidate': CANDIDATE,
        'metrics': ld.metrics(all_trades),
        'audit': {
            'required_fields': required,
            'missing_field_counts': dict(missing),
            'semantic_order_fail_count': len(semantic_failures),
            'same_day_exit_count': len(same_day_exits),
            't_plus_1_pass': len(same_day_exits) == 0,
            'semantic_order_pass': len(semantic_failures) == 0,
            'frontend_synced': False,
            'production_synced': False,
        },
        'buckets': {
            'risk_bin': bucket(all_trades, lambda t: '6_7' if t['risk_pct'] < 7 else '7_8'),
            'retrace_bin': bucket(all_trades, lambda t: 'a_<30' if t['retrace_pct'] < 30 else ('b_30_60' if t['retrace_pct'] < 60 else ('c_60_90' if t['retrace_pct'] < 90 else 'd_90_100'))),
            'exit_reason': bucket(all_trades, lambda t: t['exit_reason']),
            'year': bucket(all_trades, lambda t: str(t['entry_date'])[:4]),
        },
        'trades': all_trades,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ['generated_at','n_stocks','candidate','metrics','audit','buckets']}, ensure_ascii=False, indent=2))
    print('Saved:', OUT)


if __name__ == '__main__':
    main()
