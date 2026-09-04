#!/usr/bin/env python3
"""V47 SMC output/signal/trade/frontend audit utilities.

Runs deterministic audits against the current V46_1 output bundle and the
live 8890 frontend contract. Designed to fail loudly when signal definitions,
trades, watchlist, or frontend payloads diverge.
"""
from __future__ import annotations

import collections
import json
import math
import os
import pathlib
import sys
import time
import urllib.request
from typing import Any, Dict, Iterable, List, Tuple

ROOT = pathlib.Path('/root/.hermes')
SCRIPTS = ROOT / 'scripts'
OUT = ROOT / 'smc_opt_v46_1_layered_3y'
AUDIT_DIR = ROOT / 'smc_audit'
CACHE = ROOT / 'kline_cache'

sys.path.insert(0, str(SCRIPTS / 'v25'))
try:
    import smc_core_luxalgo_v34 as lux
except Exception as exc:  # pragma: no cover
    lux = None
    LUX_IMPORT_ERROR = repr(exc)
else:
    LUX_IMPORT_ERROR = None


def load_json(path: pathlib.Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_json(name: str, payload: Any) -> pathlib.Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    p = AUDIT_DIR / name
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return p


def f(x, default=0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def i(x, default=-1) -> int:
    try:
        if x is None or x == '':
            return default
        return int(float(x))
    except Exception:
        return default


def date_key(x: Any) -> str:
    return str(x or '').replace('-', '')[:8]


def kline_path(symbol: str) -> pathlib.Path:
    return CACHE / (symbol.replace('.', '_') + '_daily_750.json')


def mtime_iso(path: pathlib.Path) -> str | None:
    if not path.exists():
        return None
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(path.stat().st_mtime))


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {'n': 0}
    wins = [r for r in rows if f(r.get('pnl_pct')) > 0]
    sl = [r for r in rows if 'SL' in str(r.get('exit_reason'))]
    early = [r for r in rows if r.get('sold_early_flag')]
    fake = [r for r in rows if r.get('fake_sl_flag')]
    return {
        'n': n,
        'wr': round(len(wins) / n * 100, 2),
        'sl_rate': round(len(sl) / n * 100, 2),
        'avg_pnl': round(sum(f(r.get('pnl_pct')) for r in rows) / n, 3),
        'avg_mfe_pct': round(sum(f(r.get('mfe_pct')) for r in rows) / n, 3),
        'avg_mae_pct': round(sum(f(r.get('mae_pct')) for r in rows) / n, 3),
        'avg_post30_mfe_pct': round(sum(f(r.get('post30_mfe_pct')) for r in rows) / n, 3),
        'sold_early_rate': round(len(early) / n * 100, 2),
        'fake_sl_rate': round(len(fake) / n * 100, 2),
        'avg_mfe_capture': round(sum(f(r.get('mfe_capture_rate')) for r in rows) / n, 3),
        'avg_entry_zone_pos': round(sum(f(r.get('entry_zone_pos')) for r in rows) / n, 3),
        'avg_sl_dist_pct': round(sum(f(r.get('sl_dist_pct')) for r in rows) / n, 3),
    }


def output_audit() -> Dict[str, Any]:
    files = {
        'report': OUT / 'v46_1_report.json',
        'trades': OUT / 'v46_1_trades.json',
        'all_annotated': OUT / 'v46_1_all_annotated_trades.json',
        'watchlist': OUT / 'v46_1_watchlist.json',
        'picks': OUT / 'v46_1_picks.json',
        'validation': OUT / 'v46_1_validation_summary.json',
        'problem_samples': OUT / 'v46_1_problem_samples.json',
    }
    payload = {'files': {}, 'counts': {}, 'coverage': {}, 'failures': []}
    for k, p in files.items():
        payload['files'][k] = {'path': str(p), 'exists': p.exists(), 'mtime': mtime_iso(p), 'size': p.stat().st_size if p.exists() else None}
        if not p.exists():
            payload['failures'].append(f'MISSING_FILE:{k}:{p}')
    trades = load_json(files['trades'], []) or []
    watch = load_json(files['watchlist'], []) or []
    report = load_json(files['report'], {}) or {}
    metrics_obj = report.get('metrics') or {}
    kept_metrics = metrics_obj.get('kept_raw') or metrics_obj
    payload['counts'] = {
        'trades': len(trades),
        'watchlist': len(watch),
        'report_n_trades': kept_metrics.get('n_trades'),
        'report_wr': kept_metrics.get('wr'),
        'report_avg_pnl': kept_metrics.get('avg_pnl'),
    }
    ob_tr = [t for t in trades if str(t.get('zone_type')).upper() == 'OB']
    fvg_tr = [t for t in trades if 'FVG' in str(t.get('zone_type')).upper()]
    payload['coverage']['ob_trade_wave_turn_label'] = sum(1 for t in ob_tr if t.get('wave_turn_label') or t.get('source_ob', {}).get('wave_turn_label'))
    payload['coverage']['ob_trades'] = len(ob_tr)
    payload['coverage']['fvg_trades'] = len(fvg_tr)
    payload['coverage']['trades_with_signal_date'] = sum(1 for t in trades if t.get('signal_date'))
    payload['coverage']['trades_with_conf_date'] = sum(1 for t in trades if t.get('conf_date') or t.get('confirm_date'))
    payload['coverage']['trades_with_entry_date'] = sum(1 for t in trades if t.get('entry_date'))
    payload['coverage']['trades_with_exit_date'] = sum(1 for t in trades if t.get('exit_date'))
    active = [r for r in watch if r.get('pick_scope') == 'ACTIVE_CANDIDATE' and r.get('is_active_pick')]
    ob_pick = [r for r in active if str(r.get('zone_type')).upper() == 'OB']
    fvg_pick = [r for r in active if 'FVG' in str(r.get('zone_type')).upper()]
    payload['coverage'].update({
        'active_candidates': len(active),
        'ob_active_picks': len(ob_pick),
        'ob_active_picks_with_wave_turn_label': sum(1 for r in ob_pick if r.get('wave_turn_label') or r.get('source_ob', {}).get('wave_turn_label')),
        'fvg_active_picks': len(fvg_pick),
        'fvg_active_picks_with_gap_bounds': sum(1 for r in fvg_pick if (r.get('gap_low') is not None or r.get('raw_zone_low') is not None) and (r.get('gap_high') is not None or r.get('raw_zone_high') is not None)),
    })
    if payload['counts']['trades'] != payload['counts']['report_n_trades']:
        payload['failures'].append('REPORT_TRADE_COUNT_MISMATCH')
    if ob_tr and payload['coverage']['ob_trade_wave_turn_label'] < len(ob_tr):
        payload['failures'].append('OB_TRADE_MISSING_WAVE_TURN_LABEL')
    return payload


def current_signal_audit(limit_symbols: int | None = None) -> Dict[str, Any]:
    if lux is None:
        return {'failures': [f'LUX_IMPORT_ERROR:{LUX_IMPORT_ERROR}']}
    files = sorted(CACHE.glob('*_daily_750.json'))
    if limit_symbols:
        files = files[:limit_symbols]
    cnt = collections.Counter()
    bad_examples = []
    signal_counts = collections.Counter()
    for fp in files:
        try:
            kl = load_json(fp, []) or []
            sig = lux.detect_all_signals_lux_v34(kl)['signals']
        except Exception as exc:
            cnt['symbol_errors'] += 1
            if len(bad_examples) < 20:
                bad_examples.append({'file': fp.name, 'error': repr(exc)})
            continue
        cnt['symbols'] += 1
        for k in ['obs', 'sweeps', 'swing_structure', 'internal_structure', 'structure', 'fvgs', 'ifvgs', 'bprs', 'ote']:
            signal_counts[k] += len(sig.get(k, []))
        for ob in sig.get('obs', []):
            cnt['ob_total'] += 1
            lab = ob.get('wave_turn_label')
            direction = ob.get('direction')
            ok = (direction == 'bull' and lab in ('HL', 'LL', 'L')) or (direction == 'bear' and lab in ('HH', 'LH', 'H'))
            dist_ok = f(ob.get('wave_turn_distance'), 99) <= 3
            if ok and dist_ok:
                cnt['ob_wave_ok'] += 1
            else:
                cnt['ob_wave_bad'] += 1
                if len(bad_examples) < 50:
                    bad_examples.append({'file': fp.name, 'ob': ob})
            cnt[f'ob_{direction}_{lab}'] += 1
    return {
        'counts': dict(cnt),
        'signal_counts': dict(signal_counts),
        'failures': [] if cnt.get('ob_wave_bad', 0) == 0 and cnt.get('symbol_errors', 0) == 0 else ['SIGNAL_AUDIT_FAILURE'],
        'bad_examples': bad_examples,
    }


def trade_autopsy() -> Dict[str, Any]:
    trades = load_json(OUT / 'v46_1_trades.json', []) or []
    rows = []
    failures = []
    for t in trades:
        fp = kline_path(t.get('symbol', ''))
        if not fp.exists():
            failures.append({'type': 'MISSING_KLINE', 'symbol': t.get('symbol')})
            continue
        kl = load_json(fp, []) or []
        ei = i(t.get('entry_index'))
        xi = i(t.get('exit_index'))
        if not (0 <= ei < len(kl) and 0 <= xi < len(kl) and xi >= ei):
            failures.append({'type': 'BAD_ENTRY_EXIT_INDEX', 'trade': t})
            continue
        entry = f(t.get('entry_price'))
        exitp = f(t.get('exit_price_final') if t.get('exit_price_final') not in (None, '') else t.get('exit_price'))
        exec_exitp = exitp
        # For stops triggered through a gap, execution is at the open even if
        # the trailing-stop level itself is outside that day's high/low.  Older
        # V41 rows sometimes label these as TRAILING_STOP, so audit the actual
        # executable price as open when the recorded final stop is outside bar.
        if 'TRAILING_STOP' in str(t.get('exit_reason','')).upper() and xi >= 0:
            xb_tmp = kl[xi]
            if not (f(xb_tmp.get('l')) - max(0.02, exitp*0.005) <= exitp <= f(xb_tmp.get('h')) + max(0.02, exitp*0.005)):
                op_tmp = f(xb_tmp.get('o'))
                if op_tmp > 0:
                    exec_exitp = op_tmp
        risk_pct = f(t.get('risk_pct')) or abs(entry - f(t.get('sl'))) / max(entry, 1e-9) * 100
        risk_pct = max(risk_pct, 1e-9)
        seg = kl[ei:xi+1]
        post = kl[xi+1:min(len(kl), xi+31)]
        mfe = (max(f(b.get('h')) for b in seg) - entry) / max(entry, 1e-9) * 100
        mae = (min(f(b.get('l')) for b in seg) - entry) / max(entry, 1e-9) * 100
        post30_mfe = ((max(f(b.get('h')) for b in post) - entry) / max(entry, 1e-9) * 100) if post else 0.0
        post30_mae = ((min(f(b.get('l')) for b in post) - entry) / max(entry, 1e-9) * 100) if post else 0.0
        pnl = f(t.get('pnl_pct'))
        sold_early = post30_mfe - max(pnl, 0) >= max(3.0, risk_pct * 1.5)
        fake_sl = ('SL' in str(t.get('exit_reason'))) and post30_mfe >= max(6.0, risk_pct * 2.0)
        rz_low, rz_high = f(t.get('raw_zone_low')), f(t.get('raw_zone_high'))
        zone_w = max(rz_high - rz_low, 1e-9)
        entry_zone_pos = (entry - rz_low) / zone_w if zone_w > 0 else None
        sl = f(t.get('sl'))
        row = {
            'symbol': t.get('symbol'), 'zone_type': t.get('zone_type'), 'sequence_kind': t.get('sequence_kind'),
            'entry_date': t.get('entry_date'), 'exit_date': t.get('exit_date'), 'entry_price': entry, 'exit_price': exitp,
            'exec_exit_price_for_bar_audit': exec_exitp,
            'exit_reason': t.get('exit_reason'), 'pnl_pct': pnl, 'risk_pct': risk_pct,
            'mfe_pct': round(mfe, 3), 'mae_pct': round(mae, 3), 'post30_mfe_pct': round(post30_mfe, 3), 'post30_mae_pct': round(post30_mae, 3),
            'mfe_capture_rate': round(pnl / max(mfe, 1e-9), 3) if mfe > 0 else 0,
            'sold_early_flag': sold_early, 'fake_sl_flag': fake_sl,
            'entry_zone_pos': round(entry_zone_pos, 3) if entry_zone_pos is not None else None,
            'sl_dist_pct': round(abs(entry - sl) / max(entry, 1e-9) * 100, 3) if sl else None,
            'wave_turn_label': t.get('wave_turn_label') or t.get('source_ob', {}).get('wave_turn_label'),
        }
        eday = kl[ei]
        xday = kl[xi]
        if not (f(eday.get('l')) - 1e-6 <= entry <= f(eday.get('h')) + 1e-6):
            failures.append({'type': 'ENTRY_PRICE_OUTSIDE_BAR', **row, 'bar_low': eday.get('l'), 'bar_high': eday.get('h')})
        if not (f(xday.get('l')) - max(0.02, exec_exitp*0.005) <= exec_exitp <= f(xday.get('h')) + max(0.02, exec_exitp*0.005)):
            failures.append({'type': 'EXIT_PRICE_OUTSIDE_BAR', **row, 'bar_low': xday.get('l'), 'bar_high': xday.get('h')})
        rows.append(row)
    by_exit = collections.defaultdict(list)
    by_zone = collections.defaultdict(list)
    by_seq = collections.defaultdict(list)
    for r in rows:
        by_exit[str(r.get('exit_reason'))].append(r)
        by_zone[str(r.get('zone_type'))].append(r)
        by_seq[str(r.get('sequence_kind'))].append(r)
    return {
        'summary': metrics(rows),
        'by_exit': {k: metrics(v) for k, v in sorted(by_exit.items(), key=lambda kv: len(kv[1]), reverse=True)},
        'by_zone': {k: metrics(v) for k, v in sorted(by_zone.items(), key=lambda kv: len(kv[1]), reverse=True)},
        'by_sequence': {k: metrics(v) for k, v in sorted(by_seq.items(), key=lambda kv: len(kv[1]), reverse=True)},
        'failures': failures[:500],
        'failure_count': len(failures),
        'worst_sold_early': sorted([r for r in rows if r['sold_early_flag']], key=lambda r: r['post30_mfe_pct'] - max(f(r['pnl_pct']), 0), reverse=True)[:50],
        'fake_sl_samples': sorted([r for r in rows if r['fake_sl_flag']], key=lambda r: r['post30_mfe_pct'], reverse=True)[:50],
        'rows': rows,
    }


def frontend_contract(base='http://127.0.0.1:8890') -> Dict[str, Any]:
    payload = {'base': base, 'endpoints': {}, 'failures': []}
    endpoints = {
        'summary': '/api/summary?ver=V46_1',
        'kline_600519': '/api/kline_full?symbol=600519.SH&tf=daily&ver=V46_1',
        'picks': '/api/picks',
        'picks_all': '/api/picks?include_reject=1',
        'rejects': '/api/picks/rejects',
        'contract': '/api/picks/contract',
    }
    for name, path in endpoints.items():
        try:
            raw = urllib.request.urlopen(base + path, timeout=30).read()
            d = json.loads(raw)
        except Exception as exc:
            payload['endpoints'][name] = {'ok': False, 'error': repr(exc)}
            payload['failures'].append(f'ENDPOINT_FAIL:{name}')
            continue
        rec = {'ok': True, 'type': type(d).__name__}
        if isinstance(d, list):
            rec['count'] = len(d)
            rec['zone_type_counts'] = dict(collections.Counter(x.get('zone_type') for x in d if isinstance(x, dict)))
            rec['layer_counts'] = dict(collections.Counter(x.get('v46_1_layer') for x in d if isinstance(x, dict)))
            rec['ob_with_wave_turn_label'] = sum(1 for x in d if isinstance(x, dict) and str(x.get('zone_type')).upper() == 'OB' and (x.get('wave_turn_label') or x.get('source_ob', {}).get('wave_turn_label')))
        elif isinstance(d, dict):
            rec['keys'] = sorted(d.keys())[:100]
            if name.startswith('kline'):
                rec['count'] = d.get('count')
                rec['signal_count'] = d.get('signal_count')
                rec['swing_count'] = d.get('swing_count')
                rec['wave_swings_count'] = len(d.get('wave_swings') or [])
                rec['wave_labels'] = dict(collections.Counter(x.get('label') for x in d.get('wave_swings') or []))
                obs = [s for s in d.get('signals_list') or [] if s.get('family') == 'ob']
                rec['ob_count'] = len(obs)
                rec['ob_missing_wave_turn_label'] = sum(1 for s in obs if not s.get('wave_turn_label'))
                if rec['wave_swings_count'] == 0:
                    payload['failures'].append('KLINE_MISSING_WAVE_SWINGS')
                if rec['ob_missing_wave_turn_label']:
                    payload['failures'].append('KLINE_OB_MISSING_WAVE_TURN')
            else:
                for k in ['total_trades','win_rate','avg_pnl','stocks','tradable_active_pick_count','rejected_active_pick_count','active_pick_count','active_pick_count_including_reject']:
                    if k in d:
                        rec[k] = d.get(k)
        payload['endpoints'][name] = rec
    return payload


def run_all() -> Dict[str, Any]:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'output_audit': output_audit(),
        'signal_audit': current_signal_audit(),
        'trade_autopsy': trade_autopsy(),
        'frontend_contract': frontend_contract(),
    }
    failures = []
    for section in ['output_audit','signal_audit','frontend_contract']:
        failures.extend(result[section].get('failures') or [])
    if result['trade_autopsy'].get('failure_count'):
        failures.append(f"TRADE_FAILURES:{result['trade_autopsy']['failure_count']}")
    result['summary'] = {
        'p0_failures': failures,
        'p0_failure_count': len(failures),
        'trade_summary': result['trade_autopsy'].get('summary'),
        'output_counts': result['output_audit'].get('counts'),
        'signal_counts': result['signal_audit'].get('signal_counts'),
    }
    save_json('v47_full_audit.json', result)
    save_json('v47_trade_autopsy.json', result['trade_autopsy'])
    save_json('v47_frontend_contract.json', result['frontend_contract'])
    return result


if __name__ == '__main__':
    res = run_all()
    print(json.dumps(res['summary'], ensure_ascii=False, indent=2))
