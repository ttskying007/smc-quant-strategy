#!/usr/bin/env python3
"""V671 outcome-blind seed generator.

Event-first ontology: an institutional-survey disclosure (NOTICE_DATE) may create
persistent informed attention; a later first demand-absorption state within a
fixed 20-session post-disclosure window tests whether that attention survives
strict T+1. This script is OUTCOME-BLIND: it emits only event identity and
causal-state locations (swing/sweep/response/entry-eligible dates, volume rank).
It never reads or emits entry prices, exits, pnl, mfe, mae, stop, target, win.

Gated on V670 source_research_gate_pass == true.
"""
from __future__ import annotations
import json
import pathlib
import datetime as dt

ROOT = pathlib.Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
KD = ROOT / 'kline_cache'
V670_LATEST = AUDIT / 'v670_institutional_survey_source_recovery_latest.json'
V671_EVENTS = AUDIT / 'v670_institutional_survey_source_recovery_no_outcome_20260804_141356' / 'v670_events.jsonl'

POST_WINDOW = 20       # fixed post-disclosure window (completed sessions after notice)
LEFT = RIGHT = 3       # swing confirmation arms
BREACH = 0.003         # 0.3% liquidity sweep below swing low
RANK = 0.80            # sweep volume rank vs preceding 20 sessions
LOOKBACK = 20
OUT_DIR = AUDIT / 'v671_institutional_survey_post_disclosure_absorption_seeds_no_outcome_20260804_141356'


def d(x) -> str:
    s = ''.join(c for c in str(x or '') if c.isdigit())
    return s[:8] if len(s) >= 8 else ''


def n(x):
    try:
        z = float(x)
        return z if z > 0 else None
    except (TypeError, ValueError):
        return None


def bars(symbol: str):
    code, ex = symbol.rsplit('.', 1)
    p = KD / f'{code}_{ex}_daily_750.json'
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text())
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        date = d(r.get('t') or r.get('date') or r.get('day'))
        q = [n(r.get(k)) for k in ('o', 'h', 'l', 'c', 'v')]
        if date and all(v is not None for v in q):
            out.append({'d': date, 'o': q[0], 'h': q[1], 'l': q[2], 'c': q[3], 'v': q[4]})
    return sorted(out, key=lambda x: x['d'])


def pivot_low(b, j):
    if j < LEFT or j + RIGHT >= len(b):
        return False
    return b[j]['l'] < min(b[x]['l'] for x in range(j - LEFT, j)) and \
           b[j]['l'] <= min(b[x]['l'] for x in range(j + 1, j + RIGHT + 1))


def unmitigated_anchors(b, sweep):
    anchors = []
    for j in range(sweep - RIGHT - 1, LEFT - 1, -1):
        if not pivot_low(b, j):
            continue
        ssl = b[j]['l']
        if not any(b[k]['l'] <= ssl for k in range(j + RIGHT + 1, sweep)):
            anchors.append(j)
    return anchors


def canonical_anchor(b, sweep):
    for j in unmitigated_anchors(b, sweep):
        ssl = b[j]['l']
        if b[sweep]['l'] <= ssl * (1 - BREACH) and b[sweep]['c'] > ssl:
            return j
    return None


def canonical_anchors_by_sweep(b):
    """Exact one-pass equivalent of canonical_anchor(b, sweep) for every sweep."""
    active = []  # newest confirmed, still-unmitigated pivot lows first
    anchors = {}
    for sweep in range(len(b)):
        j = sweep - RIGHT - 1
        if j >= LEFT and pivot_low(b, j):
            active.insert(0, j)
        anchors[sweep] = next((j for j in active
                               if b[sweep]['l'] <= b[j]['l'] * (1 - BREACH)
                               and b[sweep]['c'] > b[j]['l']), None)
        # A touch on this bar is eligible for this sweep but consumes the anchor
        # for every following sweep, exactly matching [pivot+RIGHT+1, sweep).
        active = [j for j in active if b[sweep]['l'] > b[j]['l']]
    return anchors


def pivot_high(b, j):
    if j < LEFT or j + RIGHT >= len(b):
        return False
    return b[j]['h'] > max(b[x]['h'] for x in range(j - LEFT, j)) and \
           b[j]['h'] >= max(b[x]['h'] for x in range(j + 1, j + RIGHT + 1))


def session_index_by_date(b, date: str):
    for i, x in enumerate(b):
        if x['d'] == date:
            return i
    return None


def main() -> None:
    v670 = json.loads(V670_LATEST.read_text())
    if not v670.get('source_research_gate_pass'):
        print(json.dumps({'version': 'V671_SEED_GENERATOR', 'decision': 'BLOCKED_V670_SOURCE_GATE_NOT_PASS',
                          'gate': v670.get('source_research_gate_pass')}, ensure_ascii=False))
        raise SystemExit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = [json.loads(line) for line in V671_EVENTS.open() if line.strip()]
    print(f'events loaded: {len(events)}')

    # canonicalize: symbol + NOTICE_DATE unique
    canonical = {}
    for e in events:
        key = (e.get('secucode'), e.get('notice_date'))
        canonical.setdefault(key, e)
    print(f'canonical (symbol, notice_date) events: {len(canonical)}')

    seeds = []
    strict_chronology_violations = 0
    outcome_fields = []
    stats = {'no_bars': 0, 'no_anchor': 0, 'no_effort': 0, 'no_response': 0, 'ok': 0}

    bar_cache = {}
    for (symbol, notice), ev in sorted(canonical.items()):
        if symbol not in bar_cache:
            b0 = bars(symbol)
            bar_cache[symbol] = (b0, canonical_anchors_by_sweep(b0) if b0 else {})
        b, anchor_by_sweep = bar_cache[symbol]
        if not b:
            stats['no_bars'] += 1
            continue
        notice_key = d(notice)
        notice_i = session_index_by_date(b, notice_key)
        if notice_i is None:
            stats['no_bars'] += 1  # notice date not in bars (suspended / before cache start)
            continue
        # post-disclosure window: strictly after notice_date, up to POST_WINDOW sessions
        window_end = min(len(b) - 1, notice_i + POST_WINDOW)
        if window_end <= notice_i + RIGHT + 2:
            continue
        found = None
        for sweep in range(notice_i + 1, window_end + 1):
            swing = anchor_by_sweep[sweep]
            if swing is None:
                continue
            prior = [b[k]['v'] for k in range(sweep - LOOKBACK, sweep)]
            if len(prior) < LOOKBACK:
                continue
            vol_rank = sum(v <= b[sweep]['v'] for v in prior) / LOOKBACK
            if not (b[sweep]['l'] <= b[swing]['l'] * (1 - BREACH) and b[sweep]['c'] > b[swing]['l'] and vol_rank >= RANK):
                stats['no_effort'] += 1
                continue
            r = sweep + 1
            if r >= len(b):
                continue
            if not (b[r]['c'] > b[sweep]['h']):
                stats['no_response'] += 1
                continue
            entry = r + 1
            if entry >= len(b):
                continue
            found = {'symbol': symbol, 'ontology': 'INSTITUTIONAL_SURVEY_POST_DISCLOSURE_ABSORPTION',
                     'seed_contract': 'V671_EVENT_FIRST_20_SESSION_WINDOW_FIRST_CHAIN',
                     'notice_date': notice, 'sweep_date': b[sweep]['d'],
                     'swing_date': b[swing]['d'], 'swing_confirm_date': b[swing + RIGHT]['d'],
                     'response_date': b[r]['d'], 'entry_eligible_date': b[entry]['d'],
                     'swing_to_sweep_bars': sweep - swing,
                     'sweep_volume_rank': round(vol_rank, 6),
                     'canonical_anchor_rule': 'NEAREST_PRIOR_CONFIRMED_UNMITIGATED_SSL_SWEPT_AND_RECLAIMED',
                     'participant_count': ev.get('participant_count'),
                     'org_type_count': ev.get('org_type_count'),
                     'identity_mode': ev.get('identity_mode')}
            break  # first chain only per event
        if found is None:
            continue
        if found['sweep_date'] <= notice_key:
            strict_chronology_violations += 1
        seeds.append(found)
        stats['ok'] += 1

    # forbidden-field audit
    forbidden = {'entry_price', 'exit', 'pnl', 'return', 'mfe', 'mae', 'stop', 'target', 'win'}
    for s in seeds:
        hit = sorted(k for k in s if k.lower() in forbidden)
        if hit:
            outcome_fields.append(hit)

    by_year = {}
    symbols = set()
    for s in seeds:
        y = s['sweep_date'][:4]
        by_year[y] = by_year.get(y, 0) + 1
        symbols.add(s['symbol'])

    report = {
        'version': 'V671_INSTITUTIONAL_SURVEY_POST_DISCLOSURE_ABSORPTION_SEED_GENERATOR_NO_OUTCOME',
        'generated_at': dt.datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'outcome_read': False,
        'gate': 'V670 source_research_gate_pass == true',
        'event_universe': {'canonical_events': len(canonical)},
        'seed_stats': stats,
        'seeds': len(seeds),
        'seeds_by_sweep_year': dict(sorted(by_year.items())),
        'unique_symbols': len(symbols),
        'strict_chronology_violations': strict_chronology_violations,
        'forbidden_field_hits': outcome_fields,
        'contract': 'event-first; sweep strictly after NOTICE_DATE; first chain per event; '
                    '20-session post-disclosure window; outcome-blind',
        'artifacts': {'seeds': str(OUT_DIR / 'v671_seeds.jsonl'), 'report': str(OUT_DIR / 'v671_seed_report.json')},
    }
    with (OUT_DIR / 'v671_seeds.jsonl').open('w') as f:
        for s in seeds:
            f.write(json.dumps(s, ensure_ascii=False, sort_keys=True) + '\n')
    (OUT_DIR / 'v671_seed_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
