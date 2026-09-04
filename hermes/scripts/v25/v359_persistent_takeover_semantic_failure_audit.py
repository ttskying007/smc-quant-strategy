#!/usr/bin/env python3
"""V359 no-write semantic attribution for V358 unique persistent-takeover replays.

It does not tune, select, or publish candidates.  It tests three observable
pre-entry causes for the V358 loss distribution:
1. whether the BOS had a preceding confirmed sell-side liquidity sweep;
2. whether it followed a bullish CHOCH; and
3. whether its OB was already mitigated before the BOS anchor.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD, KDIR = ROOT / 'smc_audit', ROOT / 'kline_cache'
SRC = AUD / 'v358_unique_persistent_takeover_daily_t1_replay_latest.json'
OUT = AUD / f'v359_persistent_takeover_semantic_failure_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v359_persistent_takeover_semantic_failure_audit_latest.json'
spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def num(value: object) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def bars(symbol: str) -> list[dict]:
    try:
        raw = json.loads((KDIR / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return sorted([b for b in raw if day(b)], key=day)


def signals(ks: list[dict]) -> tuple[list[dict], list[dict]]:
    safe = [dict(x) for x in ks]
    swings = v27.confirmed_swings(safe)
    return v27.structure_signals(safe, swings), v27.sweep_signals(safe, swings)


def binned_stats(rows: list[dict]) -> dict:
    if not rows:
        return {'n': 0}
    pnl = [num(r['pnl_pct']) for r in rows]
    stops = {'SL_GAP_T1', 'STRUCTURE_SL_T1', 'SL_TP_SAME_BAR_CONSERVATIVE_SL_T1'}
    return {
        'n': len(rows),
        'wr_pct': round(100 * sum(x > 0 for x in pnl) / len(rows), 4),
        'avg_pnl_pct': round(sum(pnl) / len(rows), 4),
        'median_pnl_pct': round(sorted(pnl)[len(pnl) // 2], 4),
        'stop_pct': round(100 * sum(r['exit_reason'] in stops for r in rows) / len(rows), 4),
        'avg_mfe_pct': round(sum(num(r['mfe_pct']) for r in rows) / len(rows), 4),
        'avg_mae_pct': round(sum(num(r['mae_pct']) for r in rows) / len(rows), 4),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(SRC.read_text())
    with Path(report['artifacts']['rows']).open() as handle:
        replay = [r for r in csv.DictReader(handle) if r.get('status') == 'CLOSED']

    cache: dict[str, tuple[list[dict], list[dict], list[dict]]] = {}
    rows = []
    for row in replay:
        symbol = row['symbol']
        if symbol not in cache:
            ks = bars(symbol)
            structure, sweeps = signals(ks) if ks else ([], [])
            cache[symbol] = (ks, structure, sweeps)
        ks, structure, sweeps = cache[symbol]
        event, ob = int(row['event_idx']), int(row['ob_idx'])
        low, high = num(row['zone_low']), num(row['zone_high'])
        # All facts below are observable by the BOS close.  No bar after event is used.
        prior = ks[ob + 1:event + 1] if 0 <= ob < event <= len(ks) else []
        pre_mitigated = any(num(b.get('l')) <= high for b in prior)
        pre_invalidated = any(num(b.get('c')) < low for b in prior)
        recent_sweep = [s for s in sweeps if s.get('direction') == 'bull' and event - 15 <= int(s.get('index', -999)) < event]
        recent_choch = [s for s in structure if s.get('direction') == 'bull' and s.get('type') == 'CHOCH' and event - 30 <= int(s.get('index', -999)) < event]
        semantic_bucket = ('SWEEP+CHOCH+FRESH_OB' if recent_sweep and recent_choch and not pre_mitigated else
                           'SWEEP+FRESH_OB' if recent_sweep and not pre_mitigated else
                           'CHOCH+FRESH_OB' if recent_choch and not pre_mitigated else
                           'FRESH_OB_NO_EVENT_CONTEXT' if not pre_mitigated else
                           'PRE_MITIGATED_OB')
        rows.append({**row,
                     'pre_event_ob_mitigated': pre_mitigated,
                     'pre_event_zone_invalidated': pre_invalidated,
                     'recent_bull_sweep_15b': bool(recent_sweep),
                     'recent_bull_choch_30b': bool(recent_choch),
                     'semantic_bucket': semantic_bucket,
                     'no_write': True, 'production_write': False, 'watchlist_write': False})

    fields = sorted({key for row in rows for key in row})
    row_path = OUT / 'v359_semantic_attribution_rows.csv'
    with row_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)

    dimensions = ['semantic_bucket', 'pre_event_ob_mitigated', 'pre_event_zone_invalidated', 'recent_bull_sweep_15b', 'recent_bull_choch_30b']
    attribution = {}
    for dimension in dimensions:
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            groups[str(row[dimension])].append(row)
        attribution[dimension] = {key: binned_stats(value) for key, value in sorted(groups.items())}
    years: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        years[row['entry_date'][:4]].append(row)
    result = {
        'version': 'V359_PERSISTENT_TAKEOVER_SEMANTIC_FAILURE_AUDIT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V358 identity-collapsed, daily T+1 closed replays only',
        'facts_available_at_entry': {'pre_mitigated_ob': 'wick touches OB before BOS event', 'recent_sweep': 'bull sweep within 15 bars before BOS', 'recent_choch': 'bull CHOCH within 30 bars before BOS'},
        'n_closed': len(rows),
        'attribution': attribution,
        'yearly': {year: binned_stats(items) for year, items in sorted(years.items())},
        'invariants': {'all_rows_closed_v358': len(rows) == report['metrics']['n'], 'no_future_bars_for_tags': True, 'no_production_writes': True},
        'artifacts': {'out_dir': str(OUT), 'rows': str(row_path), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v359_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
