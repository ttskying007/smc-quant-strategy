#!/usr/bin/env python3
"""V530 outcome-blind gate for a new volume-price ontology: SOS -> BUEC.

Frozen causal story, distinct from the closed spring/test and supply-breaker lines:
1. A 3-left/3-right swing high is confirmed and therefore known.
2. A later high-relative-volume Sign of Strength closes >=0.3% above that high.
3. Within five sessions, the first low-volume Backup to the Edge touches the
   broken level, holds it (no 1% close-through), and closes above it.
4. Within three further sessions a reacceptance close breaks the backup high.
5. Only the following session open is eligible. No outcome is read here.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
OUT = AUD / f'v530_sos_backup_effort_result_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v530_sos_backup_effort_result_seed_gate_latest.json'
LEFT = RIGHT = 3
VOL_LOOKBACK, HIGH_VOL_RANK = 20, 0.80
BREAK_PCT, MAX_BACKUP_CLOSE_THROUGH = 0.003, 0.01
BACKUP_VOL_MAX_OF_SOS, BACKUP_LOOKAHEAD, REACCEPT_LOOKAHEAD = 0.60, 5, 3
YEARS = ('2023', '2024', '2025', '2026')
SUPPORT_TOTAL, SUPPORT_YEAR = 300, 40
PROMOTION_GATE = {'gross_wr_pct_min': 55.0, 'avg_net_pnl_pct_min': 0.5, 'pf_min': 1.15, 'payoff_min': 0.70, 'each_year_avg_net_pnl_pct_min': 0.0, 't1_violations': 0}


def positive(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def day(value: Any) -> str:
    value = ''.join(char for char in str(value or '') if char.isdigit())
    return value[:8] if len(value) >= 8 else ''


def bars_for(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    out = []
    for row in raw if isinstance(raw, list) else []:
        date = day(row.get('t') or row.get('date') or row.get('day'))
        values = [positive(row.get(key)) for key in ('o', 'h', 'l', 'c', 'v')]
        if date and all(value is not None for value in values):
            out.append(dict(zip(('t', 'o', 'h', 'l', 'c', 'v'), (date, *values))))
    return sorted(out, key=lambda row: row['t'])


def confirmed_high(bars: list[dict[str, Any]], index: int) -> bool:
    if index < LEFT or index + RIGHT >= len(bars):
        return False
    high = bars[index]['h']
    return high > max(bars[j]['h'] for j in range(index - LEFT, index)) and high >= max(bars[j]['h'] for j in range(index + 1, index + RIGHT + 1))


def rank_prior(bars: list[dict[str, Any]], index: int) -> float:
    prior = [bars[j]['v'] for j in range(index - VOL_LOOKBACK, index)]
    return sum(value <= bars[index]['v'] for value in prior) / len(prior) if len(prior) == VOL_LOOKBACK else 0.0


def scan_symbol(symbol: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    start = max(VOL_LOOKBACK, LEFT + RIGHT + 1)
    end = len(bars) - BACKUP_LOOKAHEAD - REACCEPT_LOOKAHEAD - 1
    for sos_index in range(start, end):
        swing_index = sos_index - RIGHT - 1
        if not confirmed_high(bars, swing_index):
            continue
        level, sos = bars[swing_index]['h'], bars[sos_index]
        if not (sos['c'] >= level * (1 + BREAK_PCT) and rank_prior(bars, sos_index) >= HIGH_VOL_RANK):
            continue
        backup_index = next((j for j in range(sos_index + 1, sos_index + BACKUP_LOOKAHEAD + 1)
                             if bars[j]['l'] <= level * (1 + BREAK_PCT)
                             and bars[j]['c'] >= level * (1 - MAX_BACKUP_CLOSE_THROUGH)
                             and bars[j]['v'] <= sos['v'] * BACKUP_VOL_MAX_OF_SOS), None)
        if backup_index is None:
            continue
        backup = bars[backup_index]
        reaccept_index = next((j for j in range(backup_index + 1, backup_index + REACCEPT_LOOKAHEAD + 1)
                               if bars[j]['c'] > backup['h']), None)
        if reaccept_index is None:
            continue
        entry_index = reaccept_index + 1
        seeds.append({
            'symbol': symbol, 'ontology': 'WYCKOFF_SOS_LOW_EFFORT_BACKUP_REACCEPTANCE',
            'swing_idx': swing_index, 'swing_date': bars[swing_index]['t'], 'breakout_level': round(level, 6),
            'sos_idx': sos_index, 'sos_date': sos['t'], 'sos_high': round(sos['h'], 6), 'sos_close': round(sos['c'], 6),
            'sos_volume': round(sos['v'], 6), 'prior20_volume_rank': round(rank_prior(bars, sos_index), 6),
            'backup_idx': backup_index, 'backup_date': backup['t'], 'backup_low': round(backup['l'], 6), 'backup_high': round(backup['h'], 6),
            'backup_close': round(backup['c'], 6), 'backup_volume': round(backup['v'], 6), 'backup_to_sos_volume_ratio': round(backup['v'] / sos['v'], 6),
            'reaccept_idx': reaccept_index, 'reaccept_date': bars[reaccept_index]['t'], 'reaccept_close': round(bars[reaccept_index]['c'], 6),
            'entry_eligible_idx': entry_index, 'entry_eligible_date': bars[entry_index]['t'],
            'causal_trace': 'confirmed_swing_high -> high_effort_SOS_close_break -> low_effort_backup_holds_edge -> reaccept_close_above_backup_high -> following_open_eligible',
        })
    return seeds


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seeds: list[dict[str, Any]] = []
    files = sorted(KDIR.glob('*_daily_750.json'))
    valid = 0
    for count, path in enumerate(files, 1):
        bars = bars_for(path)
        if len(bars) < 80:
            continue
        valid += 1
        try:
            code, exchange = path.name.removesuffix('_daily_750.json').rsplit('_', 1)
        except ValueError:
            continue
        seeds.extend(scan_symbol(f'{code}.{exchange}', bars))
        if count % 1000 == 0:
            print(f'progress {count}/{len(files)} seeds={len(seeds)}', flush=True)
    seeds.sort(key=lambda row: (row['entry_eligible_date'], row['symbol'], row['sos_idx']))
    yearly = Counter(row['entry_eligible_date'][:4] for row in seeds)
    forbidden = {'pnl', 'exit', 'mfe', 'mae', 'tp', 'sl', 'entry_price'}
    checks = {
        'n>=300': len(seeds) >= SUPPORT_TOTAL,
        'each_year_n>=40': all(yearly[year] >= SUPPORT_YEAR for year in YEARS),
        'no_outcome_fields': all(not any(field in forbidden for field in row) for row in seeds),
        'strict_chronology': all(row['swing_idx'] < row['sos_idx'] < row['backup_idx'] < row['reaccept_idx'] < row['entry_eligible_idx'] for row in seeds),
    }
    csv_path = OUT / 'v530_outcome_blind_seeds.csv'
    fields = list(seeds[0]) if seeds else ['symbol', 'ontology', 'entry_eligible_date']
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(seeds)
    report = {
        'version': 'V530_SOS_BACKUP_EFFORT_RESULT_SEED_GATE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'outcomes_opened': False,
        'distinctness': 'A bullish high-effort breakout and low-effort backup/reacceptance mechanism; it does not begin from an SSL spring, a failed bearish OB, or an immediate post-sweep response.',
        'frozen_contract': 'confirmed 3-left/3-right swing high -> >=0.3% high-volume SOS close break -> first 1..5-bar low-volume backup holds edge -> 1..3-bar reacceptance close above backup high -> following open eligible',
        'constants': {'left_right': LEFT, 'volume_lookback': VOL_LOOKBACK, 'high_volume_rank_min': HIGH_VOL_RANK, 'break_pct': BREAK_PCT, 'backup_close_through_max': MAX_BACKUP_CLOSE_THROUGH, 'backup_volume_max_of_sos': BACKUP_VOL_MAX_OF_SOS, 'backup_lookahead': BACKUP_LOOKAHEAD, 'reaccept_lookahead': REACCEPT_LOOKAHEAD},
        'support_gate': {'total_min': SUPPORT_TOTAL, 'year_min': SUPPORT_YEAR, 'years': YEARS}, 'promotion_gate_if_replay': PROMOTION_GATE,
        'files_seen': len(files), 'files_valid': valid, 'seed_count': len(seeds), 'yearly_seed_count': {year: yearly[year] for year in YEARS},
        'support_checks': checks, 'support_gate_pass': all(checks.values()),
        'decision': 'V530_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(checks.values()) else 'V530_SUPPORT_FAIL__CLOSE_ONTOLOGY_WITHOUT_OUTCOMES__NO_RELAXATION',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(csv_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v530_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__ == '__main__':
    main()
