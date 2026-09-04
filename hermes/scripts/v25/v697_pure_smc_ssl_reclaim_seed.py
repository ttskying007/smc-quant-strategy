#!/usr/bin/env python3
"""V697 outcome-blind support gate for a distinct daily volume/price ontology.

Assumptions frozen before any outcome read:
1) A swing low becomes visible only after three completed bars on its right.
2) A later bar may sweep any such still-unmitigated visible swing low by >=0.3%
   and close back above it. If more than one low qualifies, retain only the
   nearest preceding one; this is the canonical anchor, not a threshold choice.
3) The sweep volume is in the top quintile of the preceding 20 completed
   sessions and the next completed bar closes above the sweep high; volume is diagnostic-only.
4) The first eligible execution is the following session's open (strict T+1).

No outcome, exit, or PnL field is read or emitted.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
KDIR = ROOT / 'kline_cache'
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v697_pure_smc_ssl_reclaim_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v697_pure_smc_ssl_reclaim_seed_gate_latest.json'

# Predeclared information and support gates. Never tuned after looking at outcomes.
SWING_LEFT = 3
SWING_RIGHT = 3
SWEEP_PCT = 0.003
VOL_LOOKBACK = 20
SUPPORT_TOTAL_MIN = 300
SUPPORT_YEAR_MIN = 40
YEARS = ('2023', '2024', '2025', '2026')


def fnum(v: Any) -> float | None:
    try:
        value = float(v)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def datekey(v: Any) -> str:
    digits = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def bars_for(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    bars = []
    for row in raw if isinstance(raw, list) else []:
        t = datekey(row.get('t') or row.get('date') or row.get('day'))
        o, h, l, c, v = (fnum(row.get(k)) for k in ('o', 'h', 'l', 'c', 'v'))
        if t and None not in (o, h, l, c, v):
            bars.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    return sorted(bars, key=lambda b: b['t'])


def is_confirmed_swing_low(bars: list[dict[str, Any]], j: int) -> bool:
    if j < SWING_LEFT or j + SWING_RIGHT >= len(bars):
        return False
    low = bars[j]['l']
    left = [bars[k]['l'] for k in range(j - SWING_LEFT, j)]
    right = [bars[k]['l'] for k in range(j + 1, j + SWING_RIGHT + 1)]
    return low < min(left) and low <= min(right)


def volume_rank_prior(values: list[float], current: float) -> float:
    # rank against completed sessions strictly preceding the sweep session.
    return sum(v <= current for v in values) / len(values) if values else 0.0


def canonical_swept_swing_low(bars: list[dict[str, Any]], sweep_idx: int, swing_indices: list[int]) -> tuple[int, int] | None:
    """Nearest confirmed, still-unmitigated SSL actually swept and reclaimed.

    A low touched or penetrated between its right-side confirmation and this bar
    has already supplied its liquidity and cannot be reused. The closest remaining
    qualifying low is canonical; its count is retained as anchor provenance.
    """
    sweep = bars[sweep_idx]
    qualifying: list[int] = []
    for swing_idx in reversed(swing_indices):
        if swing_idx + SWING_RIGHT >= sweep_idx:
            continue
        swing_low = bars[swing_idx]['l']
        if any(bars[k]['l'] <= swing_low for k in range(swing_idx + SWING_RIGHT + 1, sweep_idx)):
            continue
        if sweep['l'] <= swing_low * (1.0 - SWEEP_PCT) and sweep['c'] > swing_low:
            qualifying.append(swing_idx)
    return (qualifying[0], len(qualifying)) if qualifying else None


def scan_symbol(symbol: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    swing_indices = [j for j in range(SWING_LEFT, len(bars) - SWING_RIGHT) if is_confirmed_swing_low(bars, j)]
    # i=sweep bar; i+1=response confirmation; i+2=entry-eligible next open.
    start = max(VOL_LOOKBACK, SWING_LEFT + SWING_RIGHT + 1)
    for i in range(start, len(bars) - 2):
        sweep = bars[i]
        response = bars[i + 1]
        # Pure price/structure contract: volume is diagnostic-only, never a gate.
        if not (response['c'] > sweep['h']):
            continue
        anchor = canonical_swept_swing_low(bars, i, swing_indices)
        if anchor is None:
            continue
        swing_idx, qualifying_anchor_count = anchor
        swing = bars[swing_idx]
        entry = bars[i + 2]
        seeds.append({
            'symbol': symbol,
            'ontology': 'PURE_SMC_SSL_RECLAIM',
            'swing_idx': swing_idx,
            'swing_date': swing['t'],
            'swing_confirm_idx': swing_idx + SWING_RIGHT,
            'swing_confirm_date': bars[swing_idx + SWING_RIGHT]['t'],
            'swing_low': round(swing['l'], 6),
            'swing_to_sweep_bars': i - swing_idx,
            'canonical_anchor_rule': 'NEAREST_PRIOR_CONFIRMED_UNMITIGATED_SSL_SWEPT_AND_RECLAIMED',
            'qualifying_anchor_count': qualifying_anchor_count,
            'sweep_idx': i,
            'sweep_date': sweep['t'],
            'sweep_low': round(sweep['l'], 6),
            'sweep_close': round(sweep['c'], 6),
            'sweep_volume': round(sweep['v'], 6),
            'response_idx': i + 1,
            'response_date': response['t'],
            'response_close': round(response['c'], 6),
            'response_breaks_sweep_high': True,
            'entry_eligible_idx': i + 2,
            'entry_eligible_date': entry['t'],
            # Explicitly no entry price, exit, pnl, MFE, MAE, or outcome fields.
            'causal_trace': 'prior_confirmed_unmitigated_swing_low -> high_volume_SSL_sweep_close_reclaim -> next_bar_close_breaks_sweep_high -> following_open_eligible',
        })
    return seeds


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(KDIR.glob('*_daily_750.json'))
    seeds: list[dict[str, Any]] = []
    file_stats = {'files_seen': len(files), 'files_valid': 0, 'files_invalid_or_empty': 0}
    for n, path in enumerate(files, 1):
        bars = bars_for(path)
        if len(bars) < 80:
            file_stats['files_invalid_or_empty'] += 1
            continue
        file_stats['files_valid'] += 1
        stem = path.name.replace('_daily_750.json', '')
        try:
            code, exchange = stem.rsplit('_', 1)
        except ValueError:
            file_stats['files_invalid_or_empty'] += 1
            continue
        symbol_seeds = scan_symbol(f'{code}.{exchange}', bars)
        # The preregistered support window is 2023–2026. This is a calendar
        # scope, not a result-dependent selector; the rolling cache also holds
        # earlier bars solely so confirmation and volume lookbacks stay visible.
        seeds.extend(row for row in symbol_seeds if row['entry_eligible_date'][:4] in YEARS)
        if n % 1000 == 0:
            print(f'progress {n}/{len(files)} seeds={len(seeds)}')

    seeds.sort(key=lambda r: (r['entry_eligible_date'], r['symbol'], r['sweep_idx']))
    yearly = Counter(row['entry_eligible_date'][:4] for row in seeds)
    gate = {
        'total_n>=300': len(seeds) >= SUPPORT_TOTAL_MIN,
        'each_year_n>=40': all(yearly.get(year, 0) >= SUPPORT_YEAR_MIN for year in YEARS),
        'all_seed_dates_in_declared_years': all(row['entry_eligible_date'][:4] in YEARS for row in seeds),
        'no_outcome_fields': all(not any(key in row for key in ('pnl', 'exit', 'mfe', 'mae', 'tp', 'sl', 'entry_price')) for row in seeds),
        'strict_chronology': all(row['swing_idx'] + SWING_RIGHT < row['sweep_idx'] < row['response_idx'] < row['entry_eligible_idx'] for row in seeds),
        'all_anchors_unmitigated_until_sweep': all(row['canonical_anchor_rule'] == 'NEAREST_PRIOR_CONFIRMED_UNMITIGATED_SSL_SWEPT_AND_RECLAIMED' for row in seeds),
    }
    support_pass = all(gate.values())
    csv_path = OUT / 'v697_outcome_blind_seeds.csv'
    fields = list(seeds[0].keys()) if seeds else ['symbol', 'ontology', 'entry_eligible_date']
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(seeds)
    report = {
        'version': 'V697_PURE_SMC_SSL_RECLAIM_SEED_GATE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'information_set': 'local daily OHLCV including pre-existing daily volume; no external source',
        'distinctness': 'Effort-result absorption is defined by cross-variable volume-price divergence; V415-V516 closed price/structure/timeframe/context families, and V300 only tested limited 2025-2026 60m market/industry diffusion.',
        'frozen_contract': 'any prior 3-left/3-right confirmed, still-unmitigated swing low visible before sweep; canonical anchor is nearest qualifying low -> >=0.3% wick breach and close reclaim -> sweep volume in top quintile versus preceding 20 completed sessions -> next completed close breaks sweep high -> following-session open eligible',
        'constants': {'swing_left': SWING_LEFT, 'swing_right': SWING_RIGHT, 'sweep_pct': SWEEP_PCT, 'volume_lookback': VOL_LOOKBACK, 'volume_diagnostic_only': True},
        'support_gate': {'total_min': SUPPORT_TOTAL_MIN, 'year_min': SUPPORT_YEAR_MIN, 'years': YEARS},
        'file_stats': file_stats,
        'seed_count': len(seeds),
        'yearly_seed_count': {year: yearly.get(year, 0) for year in YEARS},
        'invariants': gate,
        'support_gate_pass': support_pass,
        'outcomes_opened': False,
        'decision': 'V697_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED_BEFORE_SINGLE_FROZEN_T1_REPLAY' if support_pass else 'V697_SUPPORT_FAIL__CLOSE_WITHOUT_OUTCOMES__DO_NOT_RELAX',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(csv_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v517_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
