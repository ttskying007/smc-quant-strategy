#!/usr/bin/env python3
"""V109 RANGE_TRANSITION confirmation semantic rebuild.

Research-only. Reuses V104 strict reclaim rows and V107C 750-bar regime
classification, then audits BULL_EXPANSION/RANGE_TRANSITION confirmation timing.
It does not change production/API/frontend files.
"""
from __future__ import annotations

import bisect
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
KLINE = ROOT / 'kline_cache'
OUT_JSON = ROOT / 'smc_audit' / 'v109_range_transition_semantic_rebuild_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v109_range_transition_semantic_rebuild_20260619.md'
NET_SUCCESS = 0.8


def f(x, default=0.0):
    try:
        if x is None or x == '':
            return default
        y = float(x)
        return y if math.isfinite(y) else default
    except Exception:
        return default


def pct(n, d):
    return round(n * 100.0 / d, 2) if d else 0.0


def d(b):
    return str(b.get('t') or b.get('date') or b.get('day') or '')[:8]


def sym_path(symbol):
    code, ex = str(symbol).split('.')
    return KLINE / f'{code}_{ex}_daily_750.json'


def load_kline(symbol):
    path = sym_path(symbol)
    try:
        rows = json.loads(path.read_text())
    except Exception:
        return []
    out = []
    for b in rows:
        bb = dict(b)
        for k in ('o', 'h', 'l', 'c'):
            bb[k] = f(bb.get(k))
        if d(bb):
            out.append(bb)
    return out


def load_close_pairs(path):
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return [], []
    pairs = []
    for r in raw:
        dd = str(r.get('t') or r.get('date') or '')[:8]
        c = f(r.get('c'), None)
        if len(dd) == 8 and c and c > 0:
            pairs.append((dd, c))
    pairs.sort(key=lambda x: x[0])
    return [x[0] for x in pairs], [x[1] for x in pairs]


def winsor(v, lo=-30.0, hi=30.0):
    return max(lo, min(hi, f(v)))


def market_stats_750(entry_dates):
    dates = sorted(entry_dates)
    acc = {dd: {'total': 0, 'up20': 0, 'up60': 0, 'pos20': 0, 'r20': [], 'r60': []} for dd in dates}
    for path in sorted(KLINE.glob('*_daily_750.json')):
        kdates, closes = load_close_pairs(path)
        if len(kdates) < 80:
            continue
        for dd in dates:
            idx = bisect.bisect_right(kdates, dd) - 1
            if idx < 60:
                continue
            c = closes[idx]
            if c <= 0 or closes[idx - 20] <= 0 or closes[idx - 60] <= 0:
                continue
            ma20 = mean(closes[idx - 19:idx + 1])
            ma60 = mean(closes[idx - 59:idx + 1])
            r20 = winsor((c / closes[idx - 20] - 1) * 100)
            r60 = winsor((c / closes[idx - 60] - 1) * 100)
            a = acc[dd]
            a['total'] += 1
            a['up20'] += int(c > ma20)
            a['up60'] += int(c > ma60)
            a['pos20'] += int(r20 > 0)
            a['r20'].append(r20)
            a['r60'].append(r60)
    out = {}
    for dd, a in acc.items():
        total = a['total']
        out[dd] = {
            'total': total,
            'up20_pct': pct(a['up20'], total),
            'up60_pct': pct(a['up60'], total),
            'ret20_pos_pct': pct(a['pos20'], total),
            'avg_ret20_w': round(mean(a['r20']), 4) if a['r20'] else 0.0,
            'median_ret20': round(median(a['r20']), 4) if a['r20'] else 0.0,
            'median_ret60': round(median(a['r60']), 4) if a['r60'] else 0.0,
        }
    return out


def classify_regime(m):
    up20 = f(m.get('up20_pct'))
    up60 = f(m.get('up60_pct'))
    pos20 = f(m.get('ret20_pos_pct'))
    med20 = f(m.get('median_ret20'))
    med60 = f(m.get('median_ret60'))
    avg20 = f(m.get('avg_ret20_w'))
    if up20 >= 55 and up60 >= 50 and pos20 >= 55 and med20 >= 2 and avg20 >= 1:
        return 'BULL_EXPANSION'
    if up20 >= 45 and up60 >= 38 and pos20 >= 52 and med20 >= 0:
        return 'BULL_RECOVERY'
    if up20 >= 35 and up60 >= 30 and med20 >= -2:
        return 'REPAIRABLE_RANGE'
    if up20 < 30 or up60 < 25 or pos20 < 35 or med20 < -4 or med60 < -6:
        return 'NO_TRADE_BEAR_STRESS'
    return 'MIXED_CHOP'


def atr(ks, idx, n=14):
    vals = []
    for i in range(max(1, idx - n + 1), idx + 1):
        h, l, pc = f(ks[i].get('h')), f(ks[i].get('l')), f(ks[i - 1].get('c'))
        vals.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(vals) / len(vals) if vals else 0.0


def is_sw_high(ks, i, left=3, right=3):
    if i - left < 0 or i + right >= len(ks):
        return False
    hi = f(ks[i].get('h'))
    return all(f(ks[j].get('h')) < hi for j in range(i - left, i)) and all(f(ks[j].get('h')) <= hi for j in range(i + 1, i + right + 1))


def confirmed_highs(ks):
    return [{'bar': i, 'price': f(ks[i].get('h'))} for i in range(3, len(ks) - 3) if is_sw_high(ks, i)]


def second_structure_confirm(ks, event_idx, entry_idx, max_wait=21):
    highs = confirmed_highs(ks)
    stop = min(len(ks) - 2, event_idx + max_wait)
    for j in range(event_idx + 1, stop + 1):
        candidates = [h for h in highs if event_idx < h['bar'] <= j - 3 and j - h['bar'] <= 40]
        if not candidates:
            continue
        sh = candidates[-1]
        op, cl, a = f(ks[j].get('o')), f(ks[j].get('c')), atr(ks, j)
        if cl > sh['price'] and cl > op and (cl - op) >= a * 0.25:
            return {
                'idx': j,
                'date': d(ks[j]),
                'broken_high_bar': sh['bar'],
                'broken_high': round(sh['price'], 4),
                'before_entry': j < entry_idx,
                'bars_after_event': j - event_idx,
            }
    return None


def summary(rows):
    n = len(rows)
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    return {
        'n': n,
        'wr': pct(sum(v >= NET_SUCCESS for v in vals), n),
        'sl': pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), n),
        'avg': round(mean(vals), 4) if vals else 0.0,
        'median': round(median(vals), 4) if vals else 0.0,
        'cum': round(sum(vals), 4),
    }


def group(rows, key, min_n=1):
    dd = defaultdict(list)
    for r in rows:
        dd[str(key(r))].append(r)
    out = []
    for k, rs in dd.items():
        if len(rs) >= min_n:
            s = summary(rs)
            s['key'] = k
            out.append(s)
    out.sort(key=lambda x: x['key'])
    return out


def month_detail(rows):
    out = []
    for s in group(rows, lambda r: r['month']):
        rs = [r for r in rows if r['month'] == s['key']]
        s['tp1'] = sum(r.get('exit_reason') == 'TP1_HIT' for r in rs)
        s['time_stop'] = sum(r.get('exit_reason') == 'TIME_STOP' for r in rs)
        s['symbols'] = ','.join(r['symbol'] for r in sorted(rs, key=lambda x: (x['entry_date'], x['symbol']))[:20])
        out.append(s)
    return out


def concise_trade(r):
    keys = ['symbol', 'entry_date', 'month', 'family', 'event_to_entry', 'second_confirm_before_entry', 'second_confirm_date', 'v109_action', 'v109_reason', 'exit_reason', 'net_pnl_pct', 'risk_pct', 'retrace_pct', 'chase_pct']
    return {k: r.get(k) for k in keys}


def unique_symbol_date_rows(rows):
    chosen = {}
    for r in sorted(rows, key=lambda x: (x.get('symbol', ''), x.get('entry_date', ''), f(x.get('risk_pct')), int(x.get('event_to_entry', 999)), str(x.get('family')))):
        key = (r.get('symbol'), r.get('entry_date'))
        if key not in chosen:
            chosen[key] = r
    return list(chosen.values())


def duplicate_audit(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r.get('symbol'), r.get('entry_date'))].append(r)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    samples = []
    for (symbol, entry_date), rs in sorted(dup_groups.items())[:50]:
        samples.append({
            'symbol': symbol,
            'entry_date': entry_date,
            'count': len(rs),
            'families': ','.join(str(r.get('family')) for r in rs),
            'actions': ','.join(str(r.get('v109_action', '')) for r in rs),
            'net_values': ','.join(str(r.get('net_pnl_pct')) for r in rs),
        })
    return {'duplicate_groups': len(dup_groups), 'duplicate_rows': sum(len(v) for v in dup_groups.values()), 'sample': samples}


def enrich_rows(rows):
    stats = market_stats_750({str(r.get('entry_date')) for r in rows})
    kcache = {}
    for r in rows:
        r['month'] = str(r.get('entry_date'))[:6]
        r['event_to_entry'] = int(r.get('entry_idx', 0)) - int(r.get('source_event_idx', r.get('event_idx', 0)))
        m = stats.get(str(r.get('entry_date')), {})
        r['market_v109'] = m
        r['tradeable_regime'] = classify_regime(m)
        sym = r.get('symbol')
        if sym not in kcache:
            kcache[sym] = load_kline(sym)
        ks = kcache[sym]
        second = second_structure_confirm(ks, int(r.get('source_event_idx', r.get('event_idx', 0))), int(r.get('entry_idx', 0))) if ks else None
        r['second_confirm_idx'] = second['idx'] if second else None
        r['second_confirm_date'] = second['date'] if second else ''
        r['second_confirm_before_entry'] = bool(second and second['before_entry'])
        r['second_confirm_bars_after_event'] = second['bars_after_event'] if second else None
        r['second_confirm_broken_high'] = second['broken_high'] if second else None
    return rows


def apply_v109_range_rule(r):
    ete = int(r['event_to_entry'])
    second_before = bool(r.get('second_confirm_before_entry'))
    if r.get('tradeable_regime') != 'BULL_EXPANSION':
        return 'REJECT', 'NOT_BULL_EXPANSION'
    if r.get('trend_state') != 'RANGE_TRANSITION':
        return 'REJECT', 'NOT_RANGE_TRANSITION'
    if 8 <= ete <= 21:
        return 'ACCEPT_RESEARCH_ONLY', 'WAIT_8_21_CONFIRMED'
    if second_before:
        return 'ACCEPT_RESEARCH_ONLY', 'SECOND_STRUCTURE_BEFORE_ENTRY'
    if ete < 8:
        return 'REJECT', 'FAST_0_7_NO_SECOND_STRUCTURE'
    return 'REJECT', 'LATE_GT_21_NO_SECOND_STRUCTURE'


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    rows = [dict(r) for r in json.loads(TRADES.read_text())]
    rows = enrich_rows(rows)
    for r in rows:
        action, reason = apply_v109_range_rule(r)
        r['v109_action'] = action
        r['v109_reason'] = reason

    bull = [r for r in rows if r['tradeable_regime'] == 'BULL_EXPANSION']
    bull_range = [r for r in bull if r.get('trend_state') == 'RANGE_TRANSITION']
    bull_trend = [r for r in bull if r.get('trend_state') == 'TREND_UP']
    accepted = [r for r in bull_range if r['v109_action'] == 'ACCEPT_RESEARCH_ONLY']
    rejected = [r for r in bull_range if r['v109_action'] == 'REJECT']
    fast_rejected = [r for r in rejected if r['v109_reason'] == 'FAST_0_7_NO_SECOND_STRUCTURE']
    bull_range_unique = unique_symbol_date_rows(bull_range)
    accepted_unique = unique_symbol_date_rows(accepted)
    rejected_unique = unique_symbol_date_rows(rejected)

    by_reason = group(bull_range, lambda r: r['v109_reason'])
    by_event_to_entry = group(bull_range, lambda r: r['event_to_entry'])
    by_second = group(bull_range, lambda r: 'SECOND_BEFORE_ENTRY' if r.get('second_confirm_before_entry') else 'NO_SECOND_BEFORE_ENTRY')

    result = {
        'version': 'V109_RANGE_TRANSITION_CONFIRMATION_SEMANTIC_REBUILD',
        'research_only': True,
        'production_files_touched': False,
        'inputs': {'trades': str(TRADES), 'kline': str(KLINE)},
        'rule': 'For BULL_EXPANSION + RANGE_TRANSITION only: accept research rows only when event_to_entry is 8..21, or a second post-event swing-high break is confirmed before entry. Reject 0..7 premature confirmations without second structure. No TP/SL changes.',
        'baseline': {
            'all_v104': summary(rows),
            'bull_expansion': summary(bull),
            'bull_trend_up': summary(bull_trend),
            'bull_range_transition': summary(bull_range),
        },
        'v109_range_rule': {
            'accepted_research_only': summary(accepted),
            'accepted_unique_symbol_date': summary(accepted_unique),
            'rejected': summary(rejected),
            'rejected_unique_symbol_date': summary(rejected_unique),
            'fast_rejected_0_7_no_second': summary(fast_rejected),
            'duplicate_audit_all_range': duplicate_audit(bull_range),
            'duplicate_audit_accepted': duplicate_audit(accepted),
            'unique_symbol_date_all_range': summary(bull_range_unique),
            'by_reason': by_reason,
            'by_event_to_entry': by_event_to_entry,
            'by_second_structure': by_second,
            'monthly_accepted': month_detail(accepted),
            'monthly_all_range': month_detail(bull_range),
            'monthly_rejected': month_detail(rejected),
        },
        'per_trade_range_transition': [concise_trade(r) for r in sorted(bull_range, key=lambda x: (x['entry_date'], x['symbol']))],
        'loss_rows_after_v109_accept': [concise_trade(r) for r in sorted(accepted, key=lambda x: f(x.get('net_pnl_pct'))) if f(r.get('net_pnl_pct')) < NET_SUCCESS],
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'non_promotion_reasons': [
            'V109 only rebuilds RANGE_TRANSITION confirmation semantics and does not run a fresh production candidate generator.',
            'Accepted subset is a semantic research slice, not a full-market multi-year production scanner output.',
            'No TP/SL changes were made; MIXED_CHOP is excluded and not used for promotion.',
            'Production remains V90 WATCH_ONLY / tradable active=0 until a fresh full-market multi-year gate passes.',
        ],
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = ['# V109 RANGE_TRANSITION Confirmation Semantic Rebuild', '', 'Decision: **RESEARCH_ONLY_NOT_PROMOTED**', '', 'Scope: BULL_EXPANSION + RANGE_TRANSITION only. No TP/SL tuning. No production/API/frontend changes.', '', '## Core tables', '| Slice | n | WR | SL | Avg | Median | Cum |', '|---|---:|---:|---:|---:|---:|---:|']
    for name, s in [('All V104', result['baseline']['all_v104']), ('BULL_EXPANSION', result['baseline']['bull_expansion']), ('BULL TREND_UP', result['baseline']['bull_trend_up']), ('BULL RANGE_TRANSITION', result['baseline']['bull_range_transition']), ('BULL RANGE unique symbol-date', result['v109_range_rule']['unique_symbol_date_all_range']), ('V109 Accepted research-only', result['v109_range_rule']['accepted_research_only']), ('V109 Accepted unique symbol-date', result['v109_range_rule']['accepted_unique_symbol_date']), ('V109 Rejected', result['v109_range_rule']['rejected']), ('V109 Rejected unique symbol-date', result['v109_range_rule']['rejected_unique_symbol_date']), ('Fast rejected 0-7 no second', result['v109_range_rule']['fast_rejected_0_7_no_second'])]:
        lines.append(f"| {name} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['median']}% | {s['cum']}% |")
    da = result['v109_range_rule']['duplicate_audit_all_range']; daa = result['v109_range_rule']['duplicate_audit_accepted']
    lines += ['', '## Duplicate audit', '| Slice | duplicate_groups | duplicate_rows |', '|---|---:|---:|', f"| BULL RANGE_TRANSITION | {da['duplicate_groups']} | {da['duplicate_rows']} |", f"| V109 accepted | {daa['duplicate_groups']} | {daa['duplicate_rows']} |"]
    lines += ['', '## V109 reason buckets', '| Reason | n | WR | SL | Avg |', '|---|---:|---:|---:|---:|']
    for s in by_reason:
        lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% |")
    lines += ['', '## RANGE_TRANSITION event_to_entry detail', '| event_to_entry | n | WR | SL | Avg |', '|---:|---:|---:|---:|---:|']
    for s in by_event_to_entry:
        lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% |")
    for title, arr in [('Monthly accepted research-only', result['v109_range_rule']['monthly_accepted']), ('Monthly all RANGE_TRANSITION', result['v109_range_rule']['monthly_all_range']), ('Monthly rejected', result['v109_range_rule']['monthly_rejected'])]:
        lines += ['', f'## {title}', '| Month | n | WR | SL | Avg | Median | Cum | TP1 | TIME | Symbols |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
        for s in arr:
            lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['median']}% | {s['cum']}% | {s['tp1']} | {s['time_stop']} | {s['symbols']} |")
    lines += ['', '## Per-trade RANGE_TRANSITION audit', '| Symbol | Entry | E2E | SecondBefore | SecondDate | Action | Reason | Exit | Net | Risk | Retrace | Chase |', '|---|---|---:|---|---|---|---|---|---:|---:|---:|---:|']
    for r in result['per_trade_range_transition']:
        lines.append(f"| {r['symbol']} | {r['entry_date']} | {r['event_to_entry']} | {r['second_confirm_before_entry']} | {r['second_confirm_date']} | {r['v109_action']} | {r['v109_reason']} | {r['exit_reason']} | {r['net_pnl_pct']} | {r['risk_pct']} | {r['retrace_pct']} | {r['chase_pct']} |")
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision'], 'baseline': result['baseline'], 'v109_range_rule': {k: v for k, v in result['v109_range_rule'].items() if k.startswith('accepted') or k in ('rejected', 'fast_rejected_0_7_no_second', 'by_reason', 'by_event_to_entry')}}, ensure_ascii=False, indent=2)[:20000])


if __name__ == '__main__':
    main()
