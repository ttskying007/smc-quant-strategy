#!/usr/bin/env python3
"""Daily SMC operational audit log.

Runs the current production selector, records why picks are/are not current,
and snapshots live/review/analysis state so the dashboard is not a blind box.
"""
from __future__ import annotations
import json, os, pathlib, subprocess, sys
from datetime import datetime, timedelta
from collections import Counter

ROOT = pathlib.Path('/root/.hermes')
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
try:
    from smc_monitor_state import automatic_buy_authorized, ingest_daily_picks
except Exception:
    automatic_buy_authorized = None
    ingest_daily_picks = None
V25 = SCRIPTS / 'v25'
V185_DIR = ROOT / 'smc_opt_v185_combined_production_candidate'
MON = ROOT / 'smc_monitor'
OPS = MON / 'ops_logs'
OPS.mkdir(parents=True, exist_ok=True)


def load(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return default


def dkey(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def file_info(path):
    p = pathlib.Path(path)
    return {'path': str(p), 'exists': p.exists(), 'size': p.stat().st_size if p.exists() else 0,
            'mtime': datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds') if p.exists() else ''}


def latest_market_date(refresh_result=None):
    """Return only the market date of the committed production epoch."""
    manifest = load(MON / 'kline_epoch_current.json', {})
    if manifest.get('status') != 'COMMITTED' or not manifest.get('epoch_id'):
        return ''
    return dkey(manifest.get('market_date'))


def refresh_is_usable(refresh_result):
    summary = (refresh_result or {}).get('summary') or {}
    manifest = load(MON / 'kline_epoch_current.json', {})
    return (
        refresh_result.get('returncode') == 0
        and summary.get('gate_pass') is True
        and summary.get('epoch_status') == 'COMMITTED'
        and bool(summary.get('epoch_id'))
        and manifest.get('status') == 'COMMITTED'
        and manifest.get('epoch_id') == summary.get('epoch_id')
        and manifest.get('market_date') == summary.get('observed_latest_date')
    )


def buy_valid_rows(rows):
    if automatic_buy_authorized is None:
        return []
    return [row for row in rows if automatic_buy_authorized(row)]


def run_selector():
    cmd = [sys.executable, str(V25 / 'v90_daily_full_market_scanner.py')]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=600)
    finished = datetime.now()
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'), 'duration_sec': round((finished - started).total_seconds(), 1), 'returncode': proc.returncode,
            'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def run_shadow_selector():
    def run_stage(cmd, timeout):
        started = datetime.now()
        try:
            proc = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=timeout)
            finished = datetime.now()
            return {
                'cmd': ' '.join(cmd),
                'started_at': started.isoformat(timespec='seconds'),
                'finished_at': finished.isoformat(timespec='seconds'),
                'duration_sec': round((finished - started).total_seconds(), 1),
                'returncode': proc.returncode,
                'timed_out': False,
                'stdout_tail': proc.stdout[-4000:],
                'stderr_tail': proc.stderr[-4000:],
            }
        except subprocess.TimeoutExpired as e:
            finished = datetime.now()
            stdout = e.stdout.decode(errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or '')
            stderr = e.stderr.decode(errors='replace') if isinstance(e.stderr, bytes) else (e.stderr or '')
            return {
                'cmd': ' '.join(cmd),
                'started_at': started.isoformat(timespec='seconds'),
                'finished_at': finished.isoformat(timespec='seconds'),
                'duration_sec': round((finished - started).total_seconds(), 1),
                'returncode': 124,
                'timed_out': True,
                'stdout_tail': stdout[-4000:],
                'stderr_tail': stderr[-4000:] + f'\nTIMEOUT after {timeout}s',
            }

    stages = []
    if os.environ.get('SMC_DAILY_OPS_SKIP_V98') == '1':
        stages.append({
            'cmd': 'SKIP v98_reachable_5r_probability_gate.py',
            'started_at': datetime.now().isoformat(timespec='seconds'),
            'finished_at': datetime.now().isoformat(timespec='seconds'),
            'duration_sec': 0,
            'returncode': 0,
            'timed_out': False,
            'skipped': True,
            'stdout_tail': '',
            'stderr_tail': '',
        })
    else:
        stages.append(run_stage([sys.executable, str(V25 / 'v98_reachable_5r_probability_gate.py')], 900))
    stages.extend([
        run_stage([sys.executable, str(V25 / 'v99_high_wr_production_gate.py')], 120),
        run_stage([sys.executable, str(V25 / 'v100_structural_net_gate.py')], 180),
        run_stage([sys.executable, str(V25 / 'v101_mtf_dna_combo_contract.py')], 600),
    ])
    started = stages[0]['started_at']
    finished = stages[-1]['finished_at']
    stdout = ''.join(s.get('stdout_tail') or '' for s in stages)
    stderr = ''.join(s.get('stderr_tail') or '' for s in stages)
    return {
        'cmd': ' && '.join(s['cmd'] for s in stages),
        'started_at': started,
        'finished_at': finished,
        'duration_sec': round(sum(float(s.get('duration_sec') or 0) for s in stages), 1),
        'returncode': next((s['returncode'] for s in stages if s.get('returncode')), 0),
        'stages': stages,
        'stdout_tail': stdout[-4000:],
        'stderr_tail': stderr[-4000:],
    }


def run_kline_refresh():
    cmd = [sys.executable, str(V25 / 'refresh_daily_750.py'), '--workers', '20']
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(SCRIPTS), text=True, capture_output=True, timeout=900)
    finished = datetime.now()
    parsed = load(MON / 'kline_refresh_latest.json', {})
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'), 'duration_sec': round((finished - started).total_seconds(), 1), 'returncode': proc.returncode,
            'summary': parsed, 'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def run_daily_scan():
    cmd = [sys.executable, str(V25 / 'daily_scan.py')]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(SCRIPTS), text=True, capture_output=True, timeout=600)
    finished = datetime.now()
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'), 'duration_sec': round((finished - started).total_seconds(), 1), 'returncode': proc.returncode,
            'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def run_v185_rematerialize():
    cmd = [sys.executable, str(V25 / 'v185_daily_rematerialize.py')]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=300)
    finished = datetime.now()
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'), 'duration_sec': round((finished - started).total_seconds(), 1), 'returncode': proc.returncode,
            'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def run_v365_shadow():
    """Run the rejected V365 lineage as an isolated no-buy negative control."""
    cmd = [sys.executable, str(V25 / 'v433_v365_negative_control_shadow.py')]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=60)
    finished = datetime.now()
    parsed = load(ROOT / 'smc_audit/v433_v365_negative_control_shadow_latest.json', {})
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'), 'duration_sec': round((finished - started).total_seconds(), 1),
            'returncode': proc.returncode, 'summary': parsed,
            'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def run_production_registry():
    cmd = [sys.executable, str(V25 / 'smc_production_registry.py')]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=60)
    finished = datetime.now()
    parsed = load(MON / 'production_registry.json', {})
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'),
            'duration_sec': round((finished - started).total_seconds(), 1),
            'returncode': proc.returncode, 'summary': parsed,
            'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def run_v231_shadow_audit():
    cmd = [sys.executable, str(V25 / 'v231_daily_current_shadow_audit.py')]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=300)
    finished = datetime.now()
    parsed = load(ROOT / 'smc_audit/v231_daily_current_shadow_audit_latest.json', {})
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'), 'duration_sec': round((finished - started).total_seconds(), 1), 'returncode': proc.returncode,
            'summary': parsed, 'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def run_v236_shadow_audit():
    cmd = [sys.executable, str(V25 / 'v236_daily_current_shadow_audit.py')]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=300)
    finished = datetime.now()
    parsed = load(ROOT / 'smc_audit/v236_daily_current_shadow_audit_latest.json', {})
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'), 'duration_sec': round((finished - started).total_seconds(), 1), 'returncode': proc.returncode,
            'summary': parsed, 'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def run_v246_shadow_audit():
    cmd = [sys.executable, str(V25 / 'v246_daily_current_shadow_audit.py')]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=str(V25), text=True, capture_output=True, timeout=300)
    finished = datetime.now()
    parsed = load(ROOT / 'smc_audit/v246_daily_current_shadow_audit_latest.json', {})
    return {'cmd': ' '.join(cmd), 'started_at': started.isoformat(timespec='seconds'),
            'finished_at': finished.isoformat(timespec='seconds'), 'duration_sec': round((finished - started).total_seconds(), 1), 'returncode': proc.returncode,
            'summary': parsed, 'stdout_tail': proc.stdout[-4000:], 'stderr_tail': proc.stderr[-4000:]}


def merge_latest_daily_scan_into_v66():
    scan_picks = load(ROOT / 'smc_opt_v25/v26_picks.json', [])
    if not scan_picks:
        return {'ok': True, 'added': 0, 'validation_only': 0, 'latest_scan_date': '', 'reason': 'NO_FULL_MARKET_SCAN_PICKS'}
    latest = max([dkey(p.get('entry_date') or p.get('pick_date')) for p in scan_picks] or [''])
    latest_rows = [dict(p) for p in scan_picks if dkey(p.get('entry_date') or p.get('pick_date')) == latest]
    for p in latest_rows:
        p['engine'] = 'V66_FULL_MARKET_SCAN'
        p['definition_version'] = 'V66_FULL_MARKET_SCAN_SAME_GATE'
        p['pick_date'] = dkey(p.get('pick_date') or p.get('entry_date')) or latest
        p['select_date'] = p['pick_date']
        p['join_date'] = dkey(p.get('join_date') or p.get('joined_at') or p.get('created_at') or p.get('pick_date')) or p['pick_date']
        p['source'] = 'full_market_kline_scan'
        p['score'] = p.get('score') or p.get('breakout_quality_score') or 0
        p['quality_tier'] = p.get('quality_tier') or p.get('entry_quality') or 'A_NORMAL'
        p['v59_setup_family'] = p.get('v59_setup_family') or ('CONTINUATION_SETUP' if p.get('zone_type') == 'OB_Bull' else 'REENTRY_SETUP')
        if 'PINBAR' in str(p.get('seq') or p.get('ctx_seq') or p.get('detail')).upper():
            p['pick_scope'] = 'REJECTED_FULL_MARKET_GATE'
            p['is_active_pick'] = False
            p['reject_reason'] = 'PINBAR_SEQUENCE_BLOCKED'
        if p.get('v25_sl_price') and not p.get('sl'):
            p['sl'] = p.get('v25_sl_price')
        tiers = p.get('v25_tp_tiers') or []
        if tiers and isinstance(tiers[0], dict) and not p.get('tp1'):
            p['tp1'] = tiers[0].get('price')
        if len(tiers) > 1 and isinstance(tiers[1], dict) and not p.get('tp2'):
            p['tp2'] = tiers[1].get('price')
        if p.get('v25_sl_pct') and not p.get('risk_pct'):
            p['risk_pct'] = p.get('v25_sl_pct')
        zl = p.get('zone_low') or p.get('dz_low') or 0
        zh = p.get('zone_high') or p.get('dz_high') or 0
        if not p.get('zone_low') and zl:
            p['zone_low'] = zl
        if not p.get('zone_high') and zh:
            p['zone_high'] = zh
        if not p.get('zone_type'):
            p['zone_type'] = p.get('signal_type') or p.get('v59_setup_family') or 'SMC_ZONE'
        if not p.get('cost_line'):
            p['cost_line'] = round((float(zl) + float(zh)) / 2, 4) if zl and zh else p.get('entry_price') or p.get('price') or 0
        if not p.get('smart_money_cost'):
            p['smart_money_cost'] = p.get('cost_line')
        if not p.get('volatility_pct'):
            p['volatility_pct'] = p.get('v25_atr_pct') or p.get('risk_pct') or p.get('v25_sl_pct') or 0
        if not p.get('v25_vol_class'):
            p['v25_vol_class'] = p.get('market_state') or p.get('regime') or (f"RISK {float(p.get('risk_pct') or 0):.1f}%" if p.get('risk_pct') else p.get('zone_type'))
        if p.get('zone_idx') is None and p.get('zone_bar') is not None:
            p['zone_idx'] = p.get('zone_bar')
        if p.get('conf_index') is None and p.get('entry_idx') is not None:
            p['conf_index'] = p.get('entry_idx')
        if not p.get('conf_date'):
            p['conf_date'] = p.get('confirm_date') or p.get('entry_date') or p.get('pick_date')
    active_rows = [p for p in latest_rows if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick')]
    best_active = {}
    for p in active_rows:
        k = (p.get('symbol'), p.get('pick_date'))
        old = best_active.get(k)
        if old is None or (float(p.get('score') or 0), -float(p.get('risk_pct') or p.get('v25_sl_pct') or 999)) > (float(old.get('score') or 0), -float(old.get('risk_pct') or old.get('v25_sl_pct') or 999)):
            best_active[k] = p
    active_rows = list(best_active.values())
    blocked_rows = [p for p in latest_rows if p not in active_rows]
    for p in blocked_rows:
        if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick'):
            p['pick_scope'] = 'REJECTED_FULL_MARKET_GATE'
            p['is_active_pick'] = False
            p['reject_reason'] = (p.get('reject_reason') + ';' if p.get('reject_reason') else '') + 'DUPLICATE_SYMBOL_DATE'
        elif p.get('pick_scope') != 'WATCH_ONLY':
            p['watch_source_scope'] = p.get('pick_scope') or 'REJECTED_FULL_MARKET_GATE'
            p['pick_scope'] = 'WATCH_ONLY'
            p['is_active_pick'] = False
            p['watch_layer'] = 'HIGH_RISK_WATCH_ONLY'
            p['watch_reason'] = p.get('reject_reason') or 'FULL_MARKET_GATE_REJECTED_OBSERVE_ONLY'
            p['reject_reason'] = p['watch_reason']
    v66_path = ROOT / 'smc_opt_v66/v66_picks.json'
    base = load(v66_path, [])
    base = [p for p in base if p.get('engine') not in ('V66_DAILY_SCAN_LATEST', 'V66_FULL_MARKET_SCAN') and p.get('source') not in ('daily_scan_after_kline_refresh', 'full_market_kline_scan')]
    for p in base:
        if p.get('pick_scope') in ('ACTIVE_ENTRY', 'ACTIVE_CANDIDATE'):
            p['pick_scope'] = 'EXPIRED_REVIEW'
            p['is_active_pick'] = False
    merged = active_rows + blocked_rows + base
    v66_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    (ROOT / 'smc_opt_v66/v66_daily_candidates.json').write_text(json.dumps(latest_rows, ensure_ascii=False, indent=2))
    return {'ok': True, 'added': len(active_rows), 'validation_only': 0, 'rejected': len(blocked_rows), 'latest_scan_date': latest, 'symbols': [p.get('symbol') for p in active_rows[:50]], 'reason': 'FULL_MARKET_KLINE_SCAN_SAME_GATE'}


def build_log(selector_result, refresh_result=None, scan_result=None, merge_result=None, shadow_selector_result=None, v185_rematerialize_result=None, v231_shadow_audit_result=None, v236_shadow_audit_result=None, v246_shadow_audit_result=None):
    today = datetime.now().strftime('%Y%m%d')
    data_date = latest_market_date(refresh_result)
    cutoff45 = (datetime.now() - timedelta(days=45)).strftime('%Y%m%d')
    v185_picks = load(V185_DIR / 'v185_active_picks.json', []) or load(V185_DIR / 'v185_picks.json', [])
    picks = v185_picks
    trades = load(V185_DIR / 'v185_trades.json', [])
    report = load(V185_DIR / 'v185_report.json', {})
    v101_report = load(ROOT / 'smc_opt_v101_mtf_dna_combo_contract/v101_report.json', {})
    rejected = []
    source_v65 = trades
    positions = load(MON / 'positions.json', [])
    reviews = load(MON / 'closed_reviews.json', [])
    ledger = load(MON / 'trade_ledger.json', [])

    by_scope = Counter(p.get('pick_scope') for p in picks)
    active_tradable = [p for p in picks if p.get('pick_scope') in ('ACTIVE_ENTRY', 'ACTIVE_CANDIDATE') or p.get('is_active_pick')]
    watch_only = [p for p in picks if p.get('pick_scope') == 'WATCH_ONLY']
    active = active_tradable + watch_only
    recent = [p for p in active if dkey(p.get('pick_date') or p.get('entry_date')) >= cutoff45]
    today_picks = [p for p in active if dkey(p.get('pick_date') or p.get('entry_date')) == today]
    data_date_picks = [p for p in active if dkey(p.get('pick_date') or p.get('entry_date')) == data_date]
    max_pick_date = max([dkey(p.get('pick_date') or p.get('entry_date')) for p in active] or [''])
    source_latest_date = max([dkey(t.get('entry_date') or t.get('pick_date')) for t in source_v65] or [''])
    kept_latest_date = max([dkey(t.get('entry_date') or t.get('pick_date')) for t in trades] or [''])
    rejected_after_active = []
    for r in rejected:
        rd = dkey(r.get('entry_date') or r.get('pick_date'))
        if rd and rd > (max_pick_date or ''):
            rejected_after_active.append({
                'entry_date': rd,
                'symbol': r.get('symbol'),
                'family': r.get('v59_setup_family'),
                'zone_type': r.get('zone_type'),
                'score': r.get('breakout_quality_score'),
                'reject_reason': r.get('reject_reason') or ';'.join(r.get('v66_gate_reasons') or []),
                'trend_ctx': (r.get('breakout_quality_detail') or {}).get('trend_ctx') or {},
            })
    rejected_after_active = sorted(rejected_after_active, key=lambda x: x.get('entry_date',''), reverse=True)[:20]

    reject_counts = Counter()
    for r in rejected:
        reject_counts[r.get('reject_reason') or ';'.join(r.get('v66_gate_reasons') or []) or 'UNKNOWN'] += 1

    stale_reason = ''
    if not refresh_is_usable(refresh_result or {}):
        stale_reason = '行情刷新未通过完整性门禁，生产链路已fail-closed；不运行选择器、不生成候选、不执行买入。'
    if (v185_rematerialize_result or {}).get('returncode') not in (None, 0) and not (v185_rematerialize_result or {}).get('skipped'):
        stale_reason = 'V185 因果/重建门禁失败，生产链路已fail-closed；当前候选为空，不运行选择器、不执行买入。'
    if not data_date_picks and not stale_reason:
        stale_reason = f"页面同步检查：回测/选股/分析/复盘已按最新行情日={data_date or '未知'}展示；生产有效选股=0。V185当前候选最新日期={max_pick_date or '无'}；V185源最新日期={source_latest_date or '无'}；V185保留交易最新日期={kept_latest_date or '无'}。结论：日期已同步，问题是最新行情日没有通过V185生产合同的入场候选。"
    if selector_result.get('returncode') != 0 and not selector_result.get('skipped'):
        stale_reason = '选择器运行失败：' + (selector_result.get('stderr_tail') or selector_result.get('stdout_tail') or '')[-500:]

    closed_today = [r for r in reviews if dkey(r.get('closed_at')) == today]
    open_pos = [p for p in positions if p.get('status') == 'OPEN']
    closed_pos = [p for p in positions if p.get('status') == 'CLOSED']
    ledger_today = [x for x in ledger if x.get('event_date') == today]

    sl_reviews = []
    clean_reviews = [r for r in reviews if r.get('sample_class') == 'PRODUCTION_CLEAN']
    diagnostic_reviews = [r for r in reviews if r.get('sample_class') != 'PRODUCTION_CLEAN']
    for r in reviews[-50:]:
        if r.get('reason') == 'SL_HIT':
            live = r.get('live') or {}
            pos = r.get('position') or {}
            entry = float(r.get('entry_price') or 0)
            planned_sl = float(r.get('planned_sl') or 0)
            exit_price = float(r.get('exit_price') or 0)
            bucket = '待K线复盘'
            if planned_sl and exit_price <= planned_sl:
                bucket = '止损设计被价格有效击穿'
            if entry and exit_price and (entry - exit_price) / entry * 100 < 1:
                bucket = '1%内噪音亏损/入场位置需复核'
            sl_reviews.append({'symbol': r.get('symbol'), 'closed_at': r.get('closed_at'), 'pnl_pct': r.get('pnl_pct'),
                               'bucket': bucket, 'diagnosis': r.get('diagnosis'), 'seq': pos.get('seq') or (pos.get('raw_pick') or {}).get('seq'),
                               'zone_type': pos.get('zone_type'), 'live_status': live.get('status')})

    return {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'date': today,
        'data_date': data_date,
        'selector': selector_result,
        'kline_refresh': refresh_result or {},
        'daily_scan': scan_result or {},
        'shadow_selector': shadow_selector_result or {},
        'v185_rematerialize': v185_rematerialize_result or {},
        'v231_shadow_audit': v231_shadow_audit_result or {},
        'v236_shadow_audit': v236_shadow_audit_result or {},
        'v246_shadow_audit': v246_shadow_audit_result or {},
        'daily_scan_merge': merge_result or {},
        'files': {k: file_info(v) for k, v in {
            'v185_active_picks': V185_DIR / 'v185_active_picks.json',
            'v185_picks': V185_DIR / 'v185_picks.json',
            'v185_trades': V185_DIR / 'v185_trades.json',
            'v185_report': V185_DIR / 'v185_report.json',
            'v185_daily_rematerialize': ROOT / 'smc_audit/v185_daily_rematerialize_latest.json',
            'v231_daily_current_shadow_audit': ROOT / 'smc_audit/v231_daily_current_shadow_audit_latest.json',
            'v236_daily_current_shadow_audit': ROOT / 'smc_audit/v236_daily_current_shadow_audit_latest.json',
            'v246_daily_current_shadow_audit': ROOT / 'smc_audit/v246_daily_current_shadow_audit_latest.json',
            'v90_active_picks': ROOT / 'smc_opt_v90_daily_full_market_scanner/v90_active_picks.json',
            'v90_report': ROOT / 'smc_opt_v90_daily_full_market_scanner/v90_daily_scan_report.json',
            'v100_active_picks': ROOT / 'smc_opt_v100_structural_net_gate/v100_active_picks.json',
            'v100_report': ROOT / 'smc_opt_v100_structural_net_gate/v100_report.json',
            'v101_active_picks': ROOT / 'smc_opt_v101_mtf_dna_combo_contract/v101_active_picks.json',
            'v101_report': ROOT / 'smc_opt_v101_mtf_dna_combo_contract/v101_report.json',
            'v101_symbol_dna': ROOT / 'smc_opt_v101_mtf_dna_combo_contract/v101_symbol_dna.json',
            'v101_bos_candidates': ROOT / 'smc_opt_v101_mtf_dna_combo_contract/v101_bos_continuation_candidates.json',
            'v99_active_picks': ROOT / 'smc_opt_v99_high_wr_gate/v99_active_picks.json',
            'v99_report': ROOT / 'smc_opt_v99_high_wr_gate/v99_report.json',
            'v98_active_picks': ROOT / 'smc_opt_v98_reachable_5r_probability_gate/v98_active_picks.json',
            'v98_report': ROOT / 'smc_opt_v98_reachable_5r_probability_gate/v98_report.json',
            'v88_picks': ROOT / 'smc_opt_v88_production_contract/v88_picks.json',
            'v88_trades': ROOT / 'smc_opt_v88_production_contract/v88_trades.json',
            'v88_report': ROOT / 'smc_opt_v88_production_contract/v88_production_report.json',
            'positions': MON / 'positions.json',
            'reviews': MON / 'closed_reviews.json',
            'ledger': MON / 'trade_ledger.json',
            'cron_log': MON / 'cron.log',
        }.items()},
        'pick_diagnostics': {
            'raw_picks': len(picks), 'active_scope_counts': dict(by_scope), 'active_count': len(active),
            'active_tradable_count': len(active_tradable), 'watch_only_count': len(watch_only),
            'recent_45d_count': len(recent), 'today_count': len(today_picks), 'data_date_count': len(data_date_picks), 'latest_pick_date': max_pick_date,
            'data_date': data_date, 'source_latest_date': source_latest_date, 'kept_latest_date': kept_latest_date,
            'rejected_after_active_latest': rejected_after_active,
            'stale_reason': stale_reason, 'active_by_zone': dict(Counter(p.get('zone_type') for p in active)),
            'active_by_family': dict(Counter(p.get('v59_setup_family') for p in active)),
            'reject_counts': dict(reject_counts or Counter(report.get('reject_counts') or {})),
            'sample_active': active[:20],
        },
        'analysis_summary': {
            'version': report.get('version', 'V185'), 'engine': report.get('engine'),
            'metrics': report.get('metrics', {}), 'production_stats': report.get('production_stats', {}),
            'family_counts': report.get('family_counts', {}), 'exit_counts': (report.get('metrics') or {}).get('exit_counts') or report.get('exit_counts', {}),
            'n_source': report.get('n_source'),
            'n_trades': report.get('n_trades') or report.get('total_trades'), 'n_rejected': report.get('n_rejected'),
        },
        'v101_contract_summary': {
            'engine': v101_report.get('engine'),
            'version': v101_report.get('version'),
            'trade_total_all_audit': v101_report.get('trade_total_all_audit'),
            'production_total': v101_report.get('production_total'),
            'active_pick_total': v101_report.get('active_pick_total'),
            'candidate_pick_total': v101_report.get('candidate_pick_total'),
            'bos_continuation_candidate_total': v101_report.get('bos_continuation_candidate_total'),
            'dna_symbol_total': v101_report.get('dna_symbol_total'),
            'production_stats': v101_report.get('production_stats', {}),
            'bos_continuation_candidate_stats': v101_report.get('bos_continuation_candidate_stats', {}),
            'combo_counts_production': v101_report.get('combo_counts_production', {}),
            'combo_counts_candidate_whitelist': v101_report.get('combo_counts_candidate_whitelist', {}),
            'mtf_permission_counts_all': v101_report.get('mtf_permission_counts_all', {}),
            'field_missing_active': v101_report.get('field_missing_active', {}),
            'production_combo_whitelist': v101_report.get('production_combo_whitelist', []),
            'candidate_combo_whitelist': v101_report.get('candidate_combo_whitelist', []),
        },
        'live_summary': {
            'open_positions': len(open_pos), 'closed_positions': len(closed_pos),
            'ledger_total': len(ledger), 'ledger_today': len(ledger_today),
            'open_by_zone': dict(Counter(p.get('zone_type') for p in open_pos)),
        },
        'review_summary': {
            'review_total': len(reviews), 'closed_today': len(closed_today),
            'production_clean_reviews': len(clean_reviews),
            'diagnostic_reviews': len(diagnostic_reviews),
            'clean_reason_counts': dict(Counter(r.get('reason') for r in clean_reviews)),
            'diagnostic_root_cause_counts': dict(Counter(r.get('root_cause') for r in diagnostic_reviews)),
            'review_reason_counts': dict(Counter(r.get('reason') for r in reviews)),
            'recent_sl_reviews': sl_reviews[-20:],
            'recent_reviews': reviews[-20:],
        },
    }


def main():
    refresh = run_kline_refresh()
    if not refresh_is_usable(refresh):
        skipped = {'cmd': 'SKIPPED_FAIL_CLOSED', 'returncode': 125, 'skipped': True,
                   'reason': 'KLINE_REFRESH_GATE_FAILED'}
        log = build_log(skipped, refresh, skipped, skipped, skipped, skipped, skipped, skipped, skipped)
        log['pipeline_state'] = 'FAIL_CLOSED_DATA_REFRESH'
        log['daily_ingest'] = {'ok': True, 'added': 0, 'reason': 'FAIL_CLOSED_DATA_REFRESH'}
        path = OPS / f"{log['date']}.json"
        path.write_text(json.dumps(log, ensure_ascii=False, indent=2))
        (MON / 'ops_latest.json').write_text(json.dumps(log, ensure_ascii=False, indent=2))
        print(json.dumps({'ok': False, 'version': 'V185', 'pipeline_state': log['pipeline_state'],
                          'log': str(path), 'refresh': refresh.get('summary', {})}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    v365_shadow = run_v365_shadow()
    registry = run_production_registry()
    if registry.get('returncode') != 0:
        skipped = {'cmd': 'SKIPPED_FAIL_CLOSED', 'returncode': 125, 'skipped': True,
                   'reason': 'PRODUCTION_REGISTRY_GATE_FAILED'}
        log = build_log(skipped, refresh, skipped, skipped, skipped, skipped, skipped, skipped, skipped)
        log['v365_shadow'] = v365_shadow
        log['production_registry'] = registry
        log['pipeline_state'] = 'FAIL_CLOSED_PRODUCTION_REGISTRY'
        log['daily_ingest'] = {'ok': True, 'added': 0, 'reason': 'FAIL_CLOSED_PRODUCTION_REGISTRY'}
        path = OPS / f"{log['date']}.json"
        path.write_text(json.dumps(log, ensure_ascii=False, indent=2))
        (MON / 'ops_latest.json').write_text(json.dumps(log, ensure_ascii=False, indent=2))
        print(json.dumps({'ok': False, 'version': None, 'pipeline_state': log['pipeline_state'],
                          'log': str(path)}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    if registry['summary'].get('state') == 'EMPTY_BOOK':
        skipped = {'cmd': 'SKIPPED_EMPTY_BOOK', 'returncode': 0, 'skipped': True,
                   'reason': 'NO_PROMOTED_PRODUCTION_STRATEGY'}
        log = build_log(skipped, refresh, skipped, skipped, skipped, skipped, skipped, skipped, skipped)
        log['v365_shadow'] = v365_shadow
        log['production_registry'] = registry['summary']
        log['pipeline_state'] = 'EMPTY_BOOK'
        log['pick_diagnostics'] = {'today_count': 0, 'recent_45d_count': 0,
                                   'latest_pick_date': '', 'stale_reason': 'NO_PROMOTED_PRODUCTION_STRATEGY'}
        log['daily_ingest'] = {'ok': True, 'added': 0, 'reason': 'EMPTY_BOOK_NO_BUY_VALID'}
        path = OPS / f"{log['date']}.json"
        path.write_text(json.dumps(log, ensure_ascii=False, indent=2))
        (MON / 'ops_latest.json').write_text(json.dumps(log, ensure_ascii=False, indent=2))
        print(json.dumps({'ok': True, 'version': None, 'pipeline_state': 'EMPTY_BOOK',
                          'buy_enabled': False, 'active_buy_valid_count': 0,
                          'data_epoch': registry['summary'].get('data_epoch'), 'log': str(path)},
                         ensure_ascii=False, indent=2))
        return
    v185_rematerialize = run_v185_rematerialize()
    selector = {'cmd': 'SKIP V90 legacy selector', 'returncode': 0, 'skipped': True,
                'reason': 'WAIT_V185_CAUSAL_CURRENT_RAW_SCANNER'}
    old_shadow = {'cmd': 'SKIP legacy parallel shadow', 'returncode': 0, 'skipped': True,
                  'reason': 'V365_IS_ONLY_DAILY_SHADOW_CONTROL'}
    v231_shadow_audit = old_shadow
    v236_shadow_audit = old_shadow
    v246_shadow_audit = old_shadow
    shadow_selector = {'cmd': 'SKIP legacy V98/V99/V100/V101 shadow selector', 'returncode': 0, 'skipped': True, 'reason': 'V185_IS_PRODUCTION_BASELINE'}
    scan = {'ok': True, 'reason': 'V90_DAILY_SCANNER_REFRESHED_SOURCE_DATA__V185_REMAINS_PRODUCTION_BASELINE'}
    merge = {'ok': True, 'reason': 'V185_ACTIVE_PICK_FILES_USED_FOR_DAILY_INGEST', 'latest_scan_date': ''}
    log = build_log(selector, refresh, scan, merge, shadow_selector, v185_rematerialize, v231_shadow_audit, v236_shadow_audit, v246_shadow_audit)
    log['v365_shadow'] = v365_shadow
    ingest_date = log.get('data_date') or (merge or {}).get('latest_scan_date') or log['date']
    active_rows = load(V185_DIR / 'v185_active_picks.json', [])
    today_picks = [p for p in buy_valid_rows(active_rows)
                   if 0 <= int(p.get('bars_since_entry') or 999) <= 3]
    if ingest_daily_picks and today_picks:
        try:
            log['daily_ingest'] = ingest_daily_picks(today_picks, source='auto_daily')
        except Exception as e:
            log['daily_ingest'] = {'ok': False, 'error': str(e), 'ingest_date': ingest_date, 'today_pick_count': len(today_picks)}
    else:
        reason = 'NO_LATEST_DATA_PICKS' if not today_picks else 'INGEST_UNAVAILABLE'
        log['daily_ingest'] = {'ok': True, 'added': 0, 'ingest_date': ingest_date, 'today_pick_count': len(today_picks), 'reason': reason}
    path = OPS / f"{log['date']}.json"
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    latest = MON / 'ops_latest.json'
    latest.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    with (MON / 'ops.log').open('a') as f:
        f.write(json.dumps({'ts': log['generated_at'], 'date': log['date'], 'today_count': log['pick_diagnostics']['today_count'],
                            'recent_45d_count': log['pick_diagnostics']['recent_45d_count'],
                            'latest_pick_date': log['pick_diagnostics']['latest_pick_date'],
                            'stale_reason': log['pick_diagnostics']['stale_reason']}, ensure_ascii=False) + '\n')
    print(json.dumps({'ok': selector.get('returncode') == 0 and v185_rematerialize.get('returncode') == 0 and v365_shadow.get('returncode') == 0, 'version': 'V185', 'shadow': 'V365_NEGATIVE_CONTROL_ONLY', 'log': str(path), 'summary': log['pick_diagnostics'], 'v365_shadow_summary': v365_shadow.get('summary', {})}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
