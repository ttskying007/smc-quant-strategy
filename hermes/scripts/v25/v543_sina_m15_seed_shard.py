#!/usr/bin/env python3
"""Bounded V543 outcome-blind shard runner; never opens any trade outcomes."""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

SOURCE = Path('/root/.hermes/scripts/v25/v543_sina_m15_ssl_displacement_absorption_seed_gate.py')
OUT = Path('/root/.hermes/smc_audit/v543_shards_20260723')
spec = importlib.util.spec_from_file_location('v543', SOURCE)
assert spec and spec.loader
v543 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v543)


def main() -> None:
    shard, total = map(int, sys.argv[1:3])
    if not (0 <= shard < total):
        raise ValueError('shard must be in [0,total)')
    paths = sorted(v543.RAW.glob('*_m15.json.gz'))
    selected = paths[shard::total]
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / f'v543_seed_shard_{shard:02d}_of_{total:02d}.csv'
    fields: list[str] | None = None
    count = malformed = 0
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = None
        for path in selected:
            rows = v543.load_rows(path)
            if len(rows) < 100:
                malformed += 1
                continue
            seeds = v543.generate(v543.symbol(path), rows)
            if seeds and writer is None:
                fields = list(seeds[0])
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
            if writer:
                writer.writerows(seeds)
                count += len(seeds)
        if writer is None:
            raise RuntimeError('shard emitted no seeds; cannot establish schema')
    print({'shard': shard, 'total': total, 'files_assigned': len(selected), 'malformed_or_short': malformed, 'outcome_blind_seed_count': count, 'csv': str(csv_path)})


if __name__ == '__main__':
    main()
