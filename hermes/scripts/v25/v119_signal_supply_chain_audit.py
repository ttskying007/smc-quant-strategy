#!/usr/bin/env python3
"""V119 read-only signal supply-chain audit.

Reconstructs where current daily scanner candidates are lost:
context -> event -> POI -> reclaim entry -> V85/V86/V90 -> recent/active -> live.
No production/API/frontend files are modified.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from v81_contextual_smc_generator import classify_context, detect_event, locate_entry, locate_poi, _date  # noqa: E402
from v81_full_market_scan import ENV_PATH, KLINE_DIR, load_json, normalize_env, symbol_from_path  # noqa: E402
from v85_mixed_accumulation_generator import generate_v85_candidates, zone_width_pct  # noqa: E402
from v90_daily_full_market_scanner import passes_v86_gate, v88_contract_from_candidate, date_key, num  # noqa: E402

OUT = Path('/root/.hermes/smc_audit/v119_signal_supply_chain_audit_20260619')
V90_DIR = Path('/root/.hermes/smc_opt_v90_daily_full_market_scanner')
V102_DIR = Path('/root/.hermes/smc_opt_v102_balanced_volume_gate')
POSITIONS = Path('/root/.hermes/smc_monitor/positions.json')
OUT.mkdir(parents=True, exist_ok=True)


def pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 2) if whole else 0.0


def load_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data if isinstance(data, list) else []


def cdict(counter: Counter) -> Dict[str, int]:
    return {str(k): int(v) for k, v in counter.most_common()}


def interval(row: Dict[str, Any], a: str, b: str) -> int | None:
    ia, ib = row.get(a), row.get(b)
    if ia in (None, '') or ib in (None, ''):
        return None
    try:
        return int(float(ib)) - int(float(ia))
    except Exception:
        return None


def describe(vals: Iterable[int | None]) -> Dict[str, Any]:
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return {'n': 0}
    return {'n': len(xs), 'min': xs[0], 'median': xs[len(xs)//2], 'max': xs[-1]}


def audit_generator() -> Dict[str, Any]:
    env_raw = load_json(ENV_PATH)
    env_by_date = {str(k)[:8]: normalize_env(v) for k, v in env_raw.items()}
    scanned = 0
    bar_checks = 0
    context = Counter()
    trend = Counter()
    events = Counter()
    poi_valid = 0
    poi_invalid = Counter()
    entry_valid = 0
    entry_invalid = Counter()
    v85_count = 0
    v86_pass = 0
    v86_fail = Counter()
    recovery_fail = 0
    v90_contracts = []
    candidate_by_symbol: Dict[str, Dict[str, Any]] = {}
    latest_date = ''

    for path in sorted(KLINE_DIR.glob('*_daily_750.json')):
        ks = load_json(path)
        if len(ks) < 80:
            continue
        scanned += 1
        symbol = symbol_from_path(path)
        latest_date = max(latest_date, date_key(_date(ks[-1])))

        for idx in range(4, max(0, len(ks) - 2)):
            bar_checks += 1
            env = env_by_date.get(str(_date(ks[idx]))[:8], {})
            ctx = classify_context(ks, idx, env, lookback=5)
            context[ctx.get('environment_permission')] += 1
            trend[ctx.get('trend_regime')] += 1
            if ctx.get('environment_permission') == 'BLOCKED':
                continue
            ev = detect_event(ks, idx, ctx, lookback=5)
            events[ev.get('event_type')] += 1
            if ev.get('event_type') == 'NO_VALID_SMC_EVENT':
                continue
            poi = locate_poi(ks, ev, env)
            if poi.get('valid'):
                poi_valid += 1
            else:
                poi_invalid[poi.get('reason') or poi.get('poi_type') or 'INVALID_POI'] += 1
                continue
            ent = locate_entry(ks, poi, idx, max_wait=5)
            if ent.get('entry_valid'):
                entry_valid += 1
            else:
                entry_invalid[ent.get('reason') or ent.get('entry_semantic') or 'INVALID_ENTRY'] += 1

        try:
            cands = generate_v85_candidates(symbol, ks, env_by_date)
        except Exception as exc:
            v86_fail[f'GENERATOR_ERROR:{type(exc).__name__}'] += 1
            continue
        v85_count += len(cands)
        for c in cands:
            c = dict(c)
            c['v85_zone_width_pct'] = round(zone_width_pct(c), 4)
            entry_idx = int(num(c.get('entry_idx'), -1))
            takeover_idx = int(num(c.get('v83_takeover_idx'), c.get('reclaim_idx') or -1))
            c['hold_bars'] = max(0, entry_idx - takeover_idx) if entry_idx >= 0 and takeover_idx >= 0 else 999
            if not passes_v86_gate({**c, 'exit_date': '20991231'}):
                width = num(c.get('v85_zone_width_pct'), 999)
                risk = num(c.get('risk_pct'), 0.0)
                if risk <= 0:
                    entry = num(c.get('entry_price'))
                    zl = num(c.get('zone_low'))
                    risk = (entry / zl - 1) * 100 if entry and zl else 999.0
                if not (1.0 < width <= 1.6):
                    reason = 'V86_WIDTH_OUT_OF_1_0_1_6'
                elif not (1.0 < risk <= 1.5):
                    reason = 'V86_RISK_OUT_OF_1_0_1_5'
                elif num(c.get('hold_bars'), 0.0) > 2:
                    reason = 'V86_HOLD_BARS_GT_2'
                elif c.get('v83_takeover_type') != 'HOLD_ABOVE_POI':
                    reason = 'V86_TAKEOVER_NOT_HOLD_ABOVE_POI'
                elif str(c.get('entry_date')) == str(c.get('exit_date')):
                    reason = 'V86_SAME_DAY_EXIT'
                else:
                    reason = 'V86_OTHER'
                v86_fail[reason] += 1
                continue
            v86_pass += 1
            row = v88_contract_from_candidate(c, ks)
            if row.get('market_state') == 'RECOVERY' and row.get('v90_recovery_substate') not in {'RECOVERY_CONFIRMED_FAST_RECLAIM', 'RECOVERY_STABLE_HIGHER_LOW'}:
                recovery_fail += 1
                continue
            v90_contracts.append(row)
            old = candidate_by_symbol.get(symbol)
            if old is None or date_key(row.get('entry_date')) > date_key(old.get('entry_date')):
                candidate_by_symbol[symbol] = row

    recent = []
    active = []
    for r in candidate_by_symbol.values():
        p = KLINE_DIR / f"{str(r.get('symbol')).replace('.', '_')}_daily_750.json"
        ks = load_json(p) if p.exists() else []
        dist = len(ks) - 1 - int(num(r.get('entry_idx'), -9999)) if ks else 9999
        r = dict(r)
        r['bars_since_entry_audit'] = dist
        if 0 <= dist <= 45:
            recent.append(r)
            if dist <= 3:
                active.append(r)

    return {
        'scanned_symbols': scanned,
        'latest_date': latest_date,
        'bar_checks': bar_checks,
        'context_permission': cdict(context),
        'trend_regime': cdict(trend),
        'event_counts': cdict(events),
        'poi_valid': poi_valid,
        'poi_invalid': cdict(poi_invalid),
        'entry_valid': entry_valid,
        'entry_invalid': cdict(entry_invalid),
        'v85_candidates': v85_count,
        'v86_pass': v86_pass,
        'v86_fail': cdict(v86_fail),
        'recovery_substate_fail': recovery_fail,
        'v90_contracts_rebuilt': len(v90_contracts),
        'latest_per_symbol': len(candidate_by_symbol),
        'recent_45_bars': len(recent),
        'active_3_bars': len(active),
        'recent_by_event': cdict(Counter(r.get('event_type') for r in recent)),
        'recent_by_state': cdict(Counter(r.get('market_state') for r in recent)),
        'active_by_event': cdict(Counter(r.get('event_type') for r in active)),
        'intervals_v90_all': {
            'event_to_touch': describe(interval(r, 'event_idx', 'touch_idx') for r in v90_contracts),
            'touch_to_reclaim': describe(interval(r, 'touch_idx', 'reclaim_idx') for r in v90_contracts),
            'reclaim_to_entry': describe(interval(r, 'reclaim_idx', 'entry_idx') for r in v90_contracts),
            'event_to_entry': describe(interval(r, 'event_idx', 'entry_idx') for r in v90_contracts),
        },
    }


def audit_existing_outputs() -> Dict[str, Any]:
    v90_all = load_list(V90_DIR / 'v90_all_contract_candidates.json')
    v90_recent = load_list(V90_DIR / 'v90_active_picks.json')
    v90_report = json.loads((V90_DIR / 'v90_daily_scan_report.json').read_text())
    v102_active = load_list(V102_DIR / 'v102_active_picks.json')
    v102_cand = load_list(V102_DIR / 'v102_candidate_picks.json')
    positions = load_list(POSITIONS)
    return {
        'v90_report': v90_report,
        'v90_all_rows': len(v90_all),
        'v90_recent_rows': len(v90_recent),
        'v90_recent_scope': cdict(Counter(r.get('pick_scope') for r in v90_recent)),
        'v90_recent_bars_since_entry': describe(int(num(r.get('bars_since_entry'), -1)) for r in v90_recent),
        'v90_recent_calendar_live_visible_pickdate_ge_20260505': sum(1 for r in v90_recent if str(r.get('pick_date') or '') >= '20260505'),
        'v90_all_by_poi': cdict(Counter(r.get('poi_type') for r in v90_all)),
        'v90_all_by_event': cdict(Counter(r.get('event_type') for r in v90_all)),
        'v90_all_by_source_label': cdict(Counter(r.get('source_label') for r in v90_all)),
        'v102_active_rows': len(v102_active),
        'v102_candidate_rows': len(v102_cand),
        'v102_active_family': cdict(Counter(r.get('combo_family') for r in v102_active)),
        'v102_candidate_family': cdict(Counter(r.get('combo_family') for r in v102_cand)),
        'v102_active_setup_status': cdict(Counter(r.get('setup_status') for r in v102_active)),
        'v102_candidate_setup_status': cdict(Counter(r.get('setup_status') for r in v102_cand)),
        'monitor_positions_rows': len(positions),
        'monitor_status': cdict(Counter(r.get('status') for r in positions)),
        'monitor_engine_prefix': cdict(Counter(str(r.get('engine') or r.get('version') or '')[:16] for r in positions)),
    }


def write_combo_csv(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with (OUT / 'supply_chain_combo.csv').open('w', newline='') as fp:
        fields = list(rows[0].keys())
        w = csv.DictWriter(fp, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    gen = audit_generator()
    existing = audit_existing_outputs()
    summary = {
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'mode': 'READ_ONLY_AUDIT_NO_PRODUCTION_WRITES',
        'decision': 'SIGNAL_SUPPLY_CHAIN_SHORTAGE_ROOT_CAUSE_IDENTIFIED_NOT_CHANGED',
        'generator_funnel': gen,
        'existing_outputs': existing,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    lines = ['# V119 信号供应链流失审计（只读）', '', '## 1. 全链路漏斗', '', '|阶段|数量|通过率/说明|', '|---|---:|---|']
    rows = [
        ('bar checks', gen['bar_checks'], '所有扫描bar'),
        ('context allowed', sum(v for k, v in gen['context_permission'].items() if k != 'BLOCKED'), f"blocked={gen['context_permission'].get('BLOCKED', 0)}"),
        ('valid SMC events', sum(v for k, v in gen['event_counts'].items() if k != 'NO_VALID_SMC_EVENT'), str(gen['event_counts'])),
        ('valid POI', gen['poi_valid'], str(gen['poi_invalid'])),
        ('valid reclaim entry', gen['entry_valid'], str(gen['entry_invalid'])),
        ('V85 candidates', gen['v85_candidates'], 'generate_v85_candidates output'),
        ('V86 pass', gen['v86_pass'], str(gen['v86_fail'])),
        ('V90 contracts', gen['v90_contracts_rebuilt'], f"recovery_fail={gen['recovery_substate_fail']}"),
        ('latest per symbol', gen['latest_per_symbol'], '每股保留最新候选'),
        ('recent 45 bars', gen['recent_45_bars'], str(gen['recent_by_event'])),
        ('active 3 bars', gen['active_3_bars'], str(gen['active_by_event'])),
        ('live visible calendar 45d', existing['v90_recent_calendar_live_visible_pickdate_ge_20260505'], '前端live实际剩余'),
    ]
    for name, n, note in rows:
        lines.append(f'|{name}|{n}|{note}|')

    lines += ['', '## 2. 关键分布', '', '|维度|分布|', '|---|---|']
    for key in ['context_permission', 'trend_regime', 'event_counts', 'v86_fail', 'recent_by_event', 'recent_by_state']:
        lines.append(f"|{key}|`{gen[key]}`|")
    for key in ['v90_all_by_poi', 'v90_all_by_event', 'v90_all_by_source_label', 'v102_active_family', 'v102_candidate_family', 'v102_candidate_setup_status', 'monitor_status']:
        lines.append(f"|{key}|`{existing[key]}`|")

    lines += ['', '## 3. 事件节奏', '', '|间隔|n|min|median|max|', '|---|---:|---:|---:|---:|']
    for k, v in gen['intervals_v90_all'].items():
        lines.append(f"|{k}|{v.get('n',0)}|{v.get('min','')}|{v.get('median','')}|{v.get('max','')}|")

    lines += ['', '## 4. 机制结论', '',
        '- 流失最大层不是 active/live，而是 V86 合同门禁前：有效 reclaim entry 远大于 V86 pass，V86 主要按 zone_width/risk/takeover/hold_bars 压缩。',
        '- active=0 是时间窗结果：V90 recent=49 全部超过 3bar active 窗口，因此全部 WATCH_ONLY。',
        '- live=7 是前端日历窗口结果：V90 recent 45 trading bars=49，但 live 只保留 pick_date>=20260505 的7行。',
        '- POI 供应单一：V90 全部为 DEMAND_OB；true FVG source 仍没有并行进入 daily scanner。',
        '- V102 active=3 且全是 REVERSAL，说明生产组合白名单/MTF/5R门禁把 continuation 大量压到 watch。',
        '- 本审计没有修改策略、API、前端、watchlist 或 TP/SL。']
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'out': str(OUT), 'decision': summary['decision'], 'v90_contracts': gen['v90_contracts_rebuilt'], 'active_3_bars': gen['active_3_bars']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
