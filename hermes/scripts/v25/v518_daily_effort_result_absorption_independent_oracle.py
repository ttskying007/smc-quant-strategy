#!/usr/bin/env python3
"""V518 independent raw-bar Oracle for V517 effort-result absorption seeds.

This implementation intentionally does not import V517. It recomputes the fixed
ontology from raw local daily bars, compares only causal seed keys, and emits no
outcome or price-path fields.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
V517 = AUD / 'v517_daily_effort_result_absorption_seed_gate_latest.json'
OUT = AUD / f'v518_daily_effort_result_absorption_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v518_daily_effort_result_absorption_independent_oracle_latest.json'
LEFT = RIGHT = 3
LOOKBACK = 20
BREACH = 0.003
RANK_FLOOR = 0.80
YEARS = ('2023', '2024', '2025', '2026')


def number(x: Any) -> float | None:
    try:
        y = float(x)
        return y if y > 0 else None
    except (TypeError, ValueError):
        return None


def day(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def read_bars(p: Path) -> list[tuple[str, float, float, float, float, float]]:
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    out = []
    for r in data if isinstance(data, list) else []:
        values = [number(r.get(k)) for k in ('o', 'h', 'l', 'c', 'v')]
        d = day(r.get('t') or r.get('date') or r.get('day'))
        if d and all(v is not None for v in values):
            out.append((d, *values))
    return sorted(out)


def low_pivot(b: list[tuple[str,float,float,float,float,float]], j: int) -> bool:
    if j - LEFT < 0 or j + RIGHT >= len(b):
        return False
    pivot = b[j][3]
    return all(pivot < b[k][3] for k in range(j - LEFT, j)) and all(pivot <= b[k][3] for k in range(j + 1, j + RIGHT + 1))


def canonical_anchor(b: list[tuple[str,float,float,float,float,float]], sweep_idx: int, pivots: list[int]) -> int | None:
    """Independent implementation of the nearest prior confirmed unmitigated SSL."""
    _, _, _, sweep_low, sweep_close, _ = b[sweep_idx]
    for j in reversed(pivots):
        if j + RIGHT >= sweep_idx:
            continue
        pivot_low = b[j][3]
        if any(b[k][3] <= pivot_low for k in range(j + RIGHT + 1, sweep_idx)):
            continue
        if sweep_low <= pivot_low * (1 - BREACH) and sweep_close > pivot_low:
            return j
    return None


def oracle_for(symbol: str, b: list[tuple[str,float,float,float,float,float]]) -> set[tuple[str,str,str,str]]:
    # key=(symbol,swing_date,sweep_date,response_date); entry date is derivative.
    found: set[tuple[str,str,str,str]] = set()
    pivots = [j for j in range(LEFT, len(b) - RIGHT) if low_pivot(b, j)]
    for i in range(max(LOOKBACK, LEFT + RIGHT + 1), len(b) - 2):
        if b[i + 2][0][:4] not in YEARS:
            continue
        _, _, sweep_h, _, _, sweep_v = b[i]
        preceding = [b[z][5] for z in range(i - LOOKBACK, i)]
        percentile = sum(x <= sweep_v for x in preceding) / LOOKBACK
        response_c = b[i + 1][4]
        if not (percentile >= RANK_FLOOR and response_c > sweep_h):
            continue
        j = canonical_anchor(b, i, pivots)
        if j is None:
            continue
        found.add((symbol, b[j][0], b[i][0], b[i + 1][0]))
    return found


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    r517 = json.loads(V517.read_text())
    if not r517.get('support_gate_pass') or r517.get('outcomes_opened'):
        raise RuntimeError('V517 support/outcome contract changed; oracle is blocked')
    with Path(r517['artifacts']['seeds']).open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    generator_keys = {(r['symbol'], r['swing_date'], r['sweep_date'], r['response_date']) for r in rows}
    oracle_keys: set[tuple[str,str,str,str]] = set()
    files = sorted(KDIR.glob('*_daily_750.json'))
    for n, path in enumerate(files, 1):
        stem = path.name.replace('_daily_750.json', '')
        try:
            code, exchange = stem.rsplit('_', 1)
        except ValueError:
            continue
        oracle_keys |= oracle_for(f'{code}.{exchange}', read_bars(path))
        if n % 1000 == 0:
            print(f'progress {n}/{len(files)} oracle={len(oracle_keys)}')
    missing = sorted(generator_keys - oracle_keys)
    extra = sorted(oracle_keys - generator_keys)
    result = {
        'version': 'V518_DAILY_EFFORT_RESULT_ABSORPTION_INDEPENDENT_ORACLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': r517['frozen_contract'],
        'generator_seed_count': len(generator_keys), 'oracle_seed_count': len(oracle_keys),
        'missing_from_oracle_count': len(missing), 'extra_from_oracle_count': len(extra),
        'missing_examples': missing[:20], 'extra_examples': extra[:20],
        'oracle_pass': not missing and not extra,
        'outcomes_opened': False,
        'decision': 'V518_ORACLE_PASS__SINGLE_FROZEN_T1_REPLAY_ALLOWED' if not missing and not extra else 'V518_ORACLE_FAIL__NO_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST), 'v517': str(V517)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v518_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)

if __name__ == '__main__':
    main()
