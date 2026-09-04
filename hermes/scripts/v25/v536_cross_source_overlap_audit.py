#!/usr/bin/env python3
"""Read-only bar-by-bar overlap reconciliation between isolated provider namespaces.

The report is evidence only. It never changes either source and never authorizes
cross-provider substitution, even when prices happen to match.
"""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw'
AUDIT = ROOT / 'smc_audit'


def load(path: Path) -> list[dict]:
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='000001.SZ')
    parser.add_argument('--frame', default='m15')
    parser.add_argument('--left', default='baostock')
    parser.add_argument('--right', default='sina')
    args = parser.parse_args()
    base = args.symbol.replace('.', '_')
    left = load(RAW / args.left / args.frame / f'{base}_{args.frame}.json.gz')
    right = load(RAW / args.right / args.frame / f'{base}_{args.frame}.json.gz')
    a, b = {x['t']: x for x in left}, {x['t']: x for x in right}
    common = sorted(set(a) & set(b))
    if not common:
        raise SystemExit('no same-slot overlap; sources remain uncomparable')
    fields = ('o', 'h', 'l', 'c', 'v')
    deltas = {field: [abs(float(a[t][field]) - float(b[t][field])) for t in common] for field in fields}
    mismatch = {field: sum(delta > (1e-8 if field != 'v' else 0.5) for delta in values) for field, values in deltas.items()}
    result = {'version': 'V536_CROSS_SOURCE_OVERLAP_RECONCILIATION_V1', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'substitution_authorized': False, 'symbol': args.symbol, 'frame': args.frame, 'left_source': args.left, 'right_source': args.right, 'left_adjustment': left[0]['adjustment'], 'right_adjustment': right[0]['adjustment'], 'left_bars': len(left), 'right_bars': len(right), 'common_same_slot_bars': len(common), 'common_start': common[0], 'common_end': common[-1], 'absolute_delta_max': {field: max(values) for field, values in deltas.items()}, 'mismatch_counts': mismatch, 'contract_decision': 'OVERLAP_RECORDED__SOURCES_REMAIN_ISOLATED', 'promotion_decision': 'NO_PROMOTION__RIGHT_SOURCE_PARTIAL_RANGE'}
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    for path in (AUDIT / f'v536_cross_source_overlap_{args.left}_{args.right}_{args.frame}_{stamp}.json', AUDIT / f'v536_cross_source_overlap_{args.left}_{args.right}_{args.frame}_latest.json'):
        tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2)); tmp.replace(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
