#!/usr/bin/env python3
"""V299 no-write: stricter same-source 60m lifecycle gate.

After V297/V298, raw 60m ACC->MAN->DIS had enough supply but weak months
remained poor.  This audit keeps the same source, but makes the lifecycle more
operator-like and entry-time safe:
  ACC compression/quiet volume -> MAN volume sweep -> RECLAIM without deeper
  break -> DIS volume expansion with 1/2/3 bar hold confirmation -> next daily
  T+1 execution.

This writes only audit artifacts under ~/.hermes/smc_audit.
"""
from __future__ import annotations

import csv
import importlib.util
import itertools
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V297_SCRIPT = BASE / 'scripts/v25/v297_intraday_acc_man_dis_generator.py'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v299_strict_60m_lifecycle_no_write_{TS}'
LATEST = AUDIT / 'v299_strict_60m_lifecycle_latest.json'


def load_core():
    spec = importlib.util.spec_from_file_location('v297_core_for_v299', V297_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


core = load_core()


def mean(xs: list[float]) -> float:
    vals = [x for x in xs if not math.isnan(x)]
    return sum(vals) / len(vals) if vals else math.nan


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b and b > 0 and not math.isnan(a) and not math.isnan(b) else math.nan


def bucket(x: float, cuts: list[tuple[float, str]], last: str) -> str:
    for c, name in cuts:
        if x < c:
            return name
    return last


def scan_symbol(sym: str, bars: list[dict[str, Any]], daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if len(bars) < 80 or len(daily) < 50:
        return rows
    seen: set[tuple[str, str, int, int, int]] = set()
    for i in range(25, len(bars) - 12):
        for acc_len in (8, 12, 16, 20):
            if i - acc_len < 0:
                continue
            acc = bars[i - acc_len:i]
            acc_hi = max(b['h'] for b in acc); acc_lo = min(b['l'] for b in acc)
            if acc_lo <= 0:
                continue
            acc_range = pct(acc_hi, acc_lo)
            if not (1.2 <= acc_range <= 10.0):
                continue
            prev = bars[max(0, i - acc_len - 20):i - acc_len]
            acc_vol = mean([b['v'] for b in acc])
            prev_vol = mean([b['v'] for b in prev]) if prev else acc_vol
            vol_quiet = acc_vol / prev_vol if prev_vol and prev_vol > 0 else 1.0
            if vol_quiet > 1.6:
                continue

            man_idx = None
            for j in range(i, min(len(bars), i + 3)):
                if bars[j]['l'] < acc_lo * 0.998:
                    man_idx = j
                    break
            if man_idx is None:
                continue
            man_span = bars[i:man_idx + 1]
            man_low = min(b['l'] for b in man_span)
            sweep_pct = pct(acc_lo, man_low)
            if sweep_pct < 0.2:
                continue
            man_vol = mean([b['v'] for b in man_span])
            man_vol_ratio = man_vol / acc_vol if acc_vol and acc_vol > 0 else math.nan

            reclaim_idx = None
            for j in range(man_idx, min(len(bars), man_idx + 4)):
                if bars[j]['c'] > acc_lo:
                    reclaim_idx = j
                    break
            if reclaim_idx is None:
                continue
            reclaim_vol_ratio = bars[reclaim_idx]['v'] / man_vol if man_vol and man_vol > 0 else math.nan
            reclaim_delay = reclaim_idx - man_idx + 1

            takeover_idx = None
            for j in range(reclaim_idx + 1, min(len(bars), reclaim_idx + 5)):
                if bars[j]['c'] > acc_hi and bars[j]['c'] > bars[reclaim_idx]['h']:
                    takeover_idx = j
                    break
            if takeover_idx is None:
                continue

            for hold_req in (1, 2, 3):
                confirm_idx = takeover_idx + hold_req - 1
                if confirm_idx >= len(bars):
                    continue
                hold_span = bars[takeover_idx:confirm_idx + 1]
                if len(hold_span) != hold_req:
                    continue
                if any(b['c'] <= acc_hi for b in hold_span):
                    continue
                confirm = bars[confirm_idx]
                signal_date = confirm['d']
                nd = core.next_day_open(daily, signal_date)
                if not nd:
                    continue
                entry_date, entry = nd
                sl = min(man_low, acc_lo) * 0.992
                res = core.replay(daily, entry_date, entry, sl)
                if not res:
                    continue
                key = (sym, signal_date, acc_len, takeover_idx, hold_req)
                if key in seen:
                    continue
                seen.add(key)
                dis_vol = mean([b['v'] for b in hold_span])
                dis_vol_ratio = dis_vol / acc_vol if acc_vol and acc_vol > 0 else math.nan
                impulse = pct(confirm['c'], bars[reclaim_idx]['c'])
                risk = pct(entry, sl)
                no_deep_rebreak = min(b['l'] for b in bars[reclaim_idx:confirm_idx + 1]) > man_low * 1.005
                close_extension = pct(confirm['c'], acc_hi)
                row = {
                    'symbol': sym, 'signal_date': signal_date, 'entry_date': entry_date,
                    'acc_len': acc_len, 'hold_req': hold_req,
                    'man_wait': man_idx - i + 1, 'reclaim_delay': reclaim_delay,
                    'takeover_delay': takeover_idx - reclaim_idx,
                    'acc_range_pct': round(acc_range, 4), 'vol_quiet': round(vol_quiet, 4),
                    'sweep_pct': round(sweep_pct, 4), 'man_vol_ratio': round(man_vol_ratio, 4),
                    'reclaim_vol_ratio': round(reclaim_vol_ratio, 4), 'dis_vol_ratio': round(dis_vol_ratio, 4),
                    'impulse_pct': round(impulse, 4), 'close_extension_pct': round(close_extension, 4),
                    'risk_pct': round(risk, 4), 'entry': round(entry, 4), 'sl': round(sl, 4),
                    'acc_hi': round(acc_hi, 4), 'acc_lo': round(acc_lo, 4), 'man_low': round(man_low, 4),
                    'no_deep_rebreak': bool(no_deep_rebreak), 't1_violation': res['exit_date'] <= entry_date,
                    'acc_bucket': bucket(acc_range, [(3, 'ACC_TIGHT<3'), (5, 'ACC_MID3_5'), (7, 'ACC_WIDE5_7')], 'ACC_VWIDE>=7'),
                    'sweep_bucket': bucket(sweep_pct, [(1, 'SWP_SHALLOW<1'), (2, 'SWP_MID1_2')], 'SWP_DEEP>=2'),
                    'man_vol_bucket': bucket(man_vol_ratio, [(1.0, 'MAN_VOL<1'), (1.3, 'MAN_VOL1_1.3'), (1.6, 'MAN_VOL1.3_1.6')], 'MAN_VOL>=1.6'),
                    'reclaim_vol_bucket': bucket(reclaim_vol_ratio, [(0.8, 'REC_VOL<0.8'), (1.2, 'REC_VOL0.8_1.2')], 'REC_VOL>=1.2'),
                    'dis_vol_bucket': bucket(dis_vol_ratio, [(1.0, 'DIS_VOL<1'), (1.3, 'DIS_VOL1_1.3'), (1.6, 'DIS_VOL1.3_1.6')], 'DIS_VOL>=1.6'),
                    'risk_bucket': bucket(risk, [(4, 'RISK<4'), (6, 'RISK4_6'), (8, 'RISK6_8')], 'RISK>=8'),
                }
                row.update(res)
                rows.append(row)
    return rows


def metrics(rows: list[dict[str, Any]], source_n: int = 0) -> dict[str, Any]:
    return core.metrics(rows, source_n)


def score_rules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sf(x: Any, d: float = math.nan) -> float:
        return core.sf(x, d)
    gates: dict[str, Callable[[dict[str, Any]], bool]] = {
        'acc<=3': lambda r: sf(r['acc_range_pct']) <= 3,
        'acc<=5': lambda r: sf(r['acc_range_pct']) <= 5,
        'vol_quiet<=0.8': lambda r: sf(r['vol_quiet']) <= 0.8,
        'vol_quiet<=1.0': lambda r: sf(r['vol_quiet']) <= 1.0,
        'sweep>=1': lambda r: sf(r['sweep_pct']) >= 1,
        'sweep>=2': lambda r: sf(r['sweep_pct']) >= 2,
        'man_vol>=1.3': lambda r: sf(r['man_vol_ratio']) >= 1.3,
        'man_vol>=1.6': lambda r: sf(r['man_vol_ratio']) >= 1.6,
        'reclaim_vol<=0.8': lambda r: sf(r['reclaim_vol_ratio']) <= 0.8,
        'reclaim_vol<=1.2': lambda r: sf(r['reclaim_vol_ratio']) <= 1.2,
        'dis_vol>=1.3': lambda r: sf(r['dis_vol_ratio']) >= 1.3,
        'dis_vol>=1.6': lambda r: sf(r['dis_vol_ratio']) >= 1.6,
        'hold>=2': lambda r: int(sf(r['hold_req'], 0)) >= 2,
        'hold>=3': lambda r: int(sf(r['hold_req'], 0)) >= 3,
        'no_deep_rebreak': lambda r: str(r.get('no_deep_rebreak')) == 'True' or r.get('no_deep_rebreak') is True,
        'takeover_delay<=2': lambda r: int(sf(r['takeover_delay'], 9)) <= 2,
        'risk<=8': lambda r: sf(r['risk_pct']) <= 8,
        'risk<=6': lambda r: sf(r['risk_pct']) <= 6,
        'close_ext>=0.5': lambda r: sf(r['close_extension_pct']) >= 0.5,
        'close_ext>=1.0': lambda r: sf(r['close_extension_pct']) >= 1.0,
    }
    incompatible = [
        ('acc<=3', 'acc<=5'), ('vol_quiet<=0.8', 'vol_quiet<=1.0'),
        ('sweep>=1', 'sweep>=2'), ('man_vol>=1.3', 'man_vol>=1.6'),
        ('reclaim_vol<=0.8', 'reclaim_vol<=1.2'), ('dis_vol>=1.3', 'dis_vol>=1.6'),
        ('hold>=2', 'hold>=3'), ('risk<=6', 'risk<=8'), ('close_ext>=0.5', 'close_ext>=1.0')]
    names = list(gates)
    scored: list[dict[str, Any]] = []
    # Keep this audit bounded: 20 gates already create many surfaces.  Up to
    # 3-way interactions is enough to test the stated lifecycle hypothesis
    # without turning the research script into an optimizer.
    gate_values = {name: [gates[name](r) for r in rows] for name in names}
    for k in range(0, 4):
        for combo in itertools.combinations(names, k):
            if any(a in combo and b in combo for a, b in incompatible):
                continue
            if combo:
                kept = [r for idx, r in enumerate(rows) if all(gate_values[g][idx] for g in combo)]
            else:
                kept = rows
            if len(kept) < 80:
                continue
            m = metrics(kept, len(rows))
            if m['min_month_n'] < 5 or m['min_year_n'] < 20:
                continue
            m['rule'] = 'RAW_STRICT_FEATURE_ROWS' if not combo else ' & '.join(combo)
            scored.append(m)
    scored.sort(key=lambda x: (x['min_month_wr'], x['min_year_wr'], x['wr'], x['avg'], x['n']), reverse=True)
    return scored[:100]


def bucket_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dims = ['hold_req', 'acc_bucket', 'sweep_bucket', 'man_vol_bucket', 'reclaim_vol_bucket', 'dis_vol_bucket', 'risk_bucket', 'no_deep_rebreak', 'reason']
    out = []
    for dim in dims:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            groups[str(r.get(dim, ''))].append(r)
        for val, rs in groups.items():
            if len(rs) >= 50:
                out.append({'dimension': dim, 'value': val, **metrics(rs, len(rows))})
    out.sort(key=lambda x: (-x['n'], -x.get('wr', 0)))
    return out[:160]


def weak_month_autopsy(rows: list[dict[str, Any]], rule_rows: list[dict[str, Any]]) -> dict[str, Any]:
    m = metrics(rule_rows, len(rows))
    weak = []
    for month, wr in (m.get('month_wr') or {}).items():
        if wr < 50:
            rs = [r for r in rule_rows if str(r.get('entry_date', ''))[:6] == month]
            losses = [r for r in rs if core.sf(r.get('pnl'), 0) <= 0]
            loss_buckets = defaultdict(int)
            for r in losses:
                key = '|'.join([str(r.get('acc_bucket')), str(r.get('sweep_bucket')), str(r.get('man_vol_bucket')), str(r.get('reclaim_vol_bucket')), str(r.get('dis_vol_bucket')), str(r.get('risk_bucket'))])
                loss_buckets[key] += 1
            weak.append({'month': month, 'n': len(rs), 'wr': wr, 'losses': len(losses), 'top_loss_buckets': sorted(loss_buckets.items(), key=lambda x: -x[1])[:8]})
    return {'weak_months_under_50wr': weak[:12]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    for d in core.K60_DIRS:
        for p in d.glob('*_60min_500.json'):
            files.setdefault(core.sym_from_path(p), p)
    day_cache: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    scanned = 0
    source_rows = Path(__import__('os').environ.get('V299_ROWS_CSV', ''))
    if source_rows.exists():
        with source_rows.open() as fh:
            rows = list(csv.DictReader(fh))
        scanned = len({r.get('symbol', '') for r in rows})
    else:
        for sym in sorted(files):
            b60 = core.load60(sym)
            daily = core.loadday(sym, day_cache)
            if b60 and daily:
                scanned += 1
                rows.extend(scan_symbol(sym, b60, daily))
        rows.sort(key=lambda r: (r['entry_date'], r['symbol'], r['acc_len'], r['hold_req']))
    rows_path = OUT / 'v299_rows.csv'
    if rows:
        fields = list(rows[0].keys())
        with rows_path.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader(); w.writerows(rows)
    rules = score_rules(rows)
    best_rule_rows: list[dict[str, Any]] = []
    if rules:
        best_rule = rules[0]['rule']
        if best_rule == 'RAW_STRICT_FEATURE_ROWS':
            best_rule_rows = rows
        else:
            # Re-evaluate by names using a compact local predicate map identical enough for top rule extraction.
            def sf(x: Any, d: float = math.nan) -> float: return core.sf(x, d)
            pred = {
                'acc<=3': lambda r: sf(r['acc_range_pct']) <= 3, 'acc<=5': lambda r: sf(r['acc_range_pct']) <= 5,
                'vol_quiet<=0.8': lambda r: sf(r['vol_quiet']) <= 0.8, 'vol_quiet<=1.0': lambda r: sf(r['vol_quiet']) <= 1.0,
                'sweep>=1': lambda r: sf(r['sweep_pct']) >= 1, 'sweep>=2': lambda r: sf(r['sweep_pct']) >= 2,
                'man_vol>=1.3': lambda r: sf(r['man_vol_ratio']) >= 1.3, 'man_vol>=1.6': lambda r: sf(r['man_vol_ratio']) >= 1.6,
                'reclaim_vol<=0.8': lambda r: sf(r['reclaim_vol_ratio']) <= 0.8, 'reclaim_vol<=1.2': lambda r: sf(r['reclaim_vol_ratio']) <= 1.2,
                'dis_vol>=1.3': lambda r: sf(r['dis_vol_ratio']) >= 1.3, 'dis_vol>=1.6': lambda r: sf(r['dis_vol_ratio']) >= 1.6,
                'hold>=2': lambda r: int(sf(r['hold_req'], 0)) >= 2, 'hold>=3': lambda r: int(sf(r['hold_req'], 0)) >= 3,
                'no_deep_rebreak': lambda r: str(r.get('no_deep_rebreak')).lower() == 'true',
                'takeover_delay<=2': lambda r: int(sf(r['takeover_delay'], 9)) <= 2,
                'risk<=8': lambda r: sf(r['risk_pct']) <= 8, 'risk<=6': lambda r: sf(r['risk_pct']) <= 6,
                'close_ext>=0.5': lambda r: sf(r['close_extension_pct']) >= 0.5, 'close_ext>=1.0': lambda r: sf(r['close_extension_pct']) >= 1.0,
            }
            names = [x.strip() for x in best_rule.split('&')]
            best_rule_rows = [r for r in rows if all(pred[n](r) for n in names)]
    best_path = OUT / 'v299_best_rule_rows.csv'
    if best_rule_rows:
        with best_path.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(best_rule_rows[0].keys()))
            w.writeheader(); w.writerows(best_rule_rows)
    summary = {
        'version': 'V299_STRICT_60M_LIFECYCLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'Stricter 60m operator lifecycle volume/hold gates can rescue V297/V298 weak-month instability.',
        'inputs': {'sixty_min_files': len(files), 'symbols_scanned': scanned, 'daily_symbols': len(day_cache)},
        'raw_strict_feature_rows': metrics(rows, len(rows)),
        't1_violations': sum(1 for r in rows if str(r.get('t1_violation')).lower() == 'true'),
        'top_rules': rules[:50],
        'best_rule_autopsy': weak_month_autopsy(rows, best_rule_rows) if best_rule_rows else {},
        'bucket_metrics': bucket_metrics(rows),
        'artifacts': {'rows': str(rows_path), 'best_rule_rows': str(best_path), 'summary': str(OUT / 'v299_summary.json')},
    }
    (OUT / 'v299_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'raw': summary['raw_strict_feature_rows'], 'best': rules[0] if rules else None, 't1': summary['t1_violations'], 'weak': summary['best_rule_autopsy']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
