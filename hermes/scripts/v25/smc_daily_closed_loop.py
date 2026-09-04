#!/usr/bin/env python3
"""Daily SMC closed-loop automation.

Runs the active SMC engine, all audits, release gate, frontend smoke checks, and
writes a dated report. It is intentionally conservative: it regenerates and
validates the active production version; strategy evolution is handled by the
Hermes agent cron prompt that reads this report and implements the next version
when the metrics show a clear target.
"""
from __future__ import annotations
import json, pathlib, subprocess, datetime, re, urllib.request, sys

ROOT = pathlib.Path('/root/.hermes')
SCRIPTS = ROOT / 'scripts'
SMC = SCRIPTS / 'smc_unified.py'
REPORT_DIR = ROOT / 'smc_daily_closed_loop'
REPORT_DIR.mkdir(exist_ok=True)


def sh(cmd, cwd=SCRIPTS, timeout=1200):
    p = subprocess.run(cmd, cwd=str(cwd), shell=True, capture_output=True, text=True, timeout=timeout)
    return {'cmd': cmd, 'returncode': p.returncode, 'stdout': p.stdout[-4000:], 'stderr': p.stderr[-4000:]}


def active_version():
    v185_report = ROOT / 'smc_opt_v185_combined_production_candidate/v185_report.json'
    if v185_report.exists():
        try:
            report = json.loads(v185_report.read_text())
            if report.get('production_write') and report.get('frontend_write'):
                return 'v185', 'V185'
        except Exception:
            pass
    txt = SMC.read_text()
    m = re.search(r"ACTIVE_VERSION = \('([^']+)'", txt)
    if not m:
        raise RuntimeError('Cannot parse ACTIVE_VERSION')
    # If the first candidate exists, it is active by construction.
    return m.group(1).lower(), m.group(1)


def smoke():
    out = {}
    for ep in ['/api/summary', '/api/autopsy/closed-loop', '/api/picks']:
        try:
            data = urllib.request.urlopen('http://127.0.0.1:8890' + ep, timeout=15).read()
            out[ep] = {'ok': True, 'bytes': len(data), 'has_traceback': b'Traceback' in data}
        except Exception as e:
            out[ep] = {'ok': False, 'error': repr(e)}
    return out


def main():
    prefix, version = active_version()
    engine = SCRIPTS / 'v25' / f'{prefix}_engine.py'
    if version == 'V185':
        engine = SCRIPTS / 'v25' / 'v185_daily_rematerialize.py'
    if not engine.exists() and version == 'V88':
        engine = SCRIPTS / 'v25' / 'v88_apply_production_contract.py'
    if not engine.exists():
        raise RuntimeError(f'Missing engine: {engine}')
    steps = []
    # Phase 0/1/2: Run daily ops pipeline first (kline refresh + v66 selector + daily_scan + merge)
    ops_script = SCRIPTS / 'v25/smc_daily_ops.py'
    if ops_script.exists():
        ops_step = sh(f'python3 {ops_script.name}', cwd=ops_script.parent, timeout=1800)
        steps.append(ops_step)
        if ops_step['returncode'] != 0:
            daily = {
                'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
                'active_version': version,
                'engine': str(engine),
                'pipeline_state': 'FAIL_CLOSED_DAILY_OPS',
                'steps': steps,
                'report': {},
                'release_gate': {'pass': False, 'reason': 'DAILY_OPS_FAILED'},
                'closed_loop_summary': {},
                'issue_counts': {'DAILY_OPS_FAILED': 1},
                'smoke': {},
                'next_action_hint': 'Repair data/ops failure before any scanner, rematerialization, ingest, or frontend reload.'
            }
            out = REPORT_DIR / f'{datetime.datetime.now().strftime("%Y%m%d")}_{prefix}_closed_loop.json'
            out.write_text(json.dumps(daily, ensure_ascii=False, indent=2))
            print(json.dumps({'ok': False, 'version': version, 'out': str(out),
                              'pipeline_state': daily['pipeline_state']}, ensure_ascii=False))
            raise SystemExit(2)
    # Phase 2: Run active production contract/backtest engine.
    if engine.exists():
        steps.append(sh(f'python3 {engine.name}', cwd=engine.parent, timeout=1800))
    for suffix in ['quality_metrics', 'trade_provenance_audit', 'signal_sequence_audit', 'sample_bias_audit', 'closed_loop_90d_review', 't1_audit', 'release_gate']:
        script = engine.parent / f'{prefix}_{suffix}.py'
        if script.exists():
            steps.append(sh(f'python3 {script.name}', cwd=engine.parent, timeout=1800))
    if version == 'V185':
        report_path = ROOT / 'smc_opt_v185_combined_production_candidate/v185_report.json'
    else:
        report_path = ROOT / f'smc_opt_{prefix}' / f'{prefix}_report.json'
    gate_path = ROOT / 'smc_audit' / f'{prefix}_release_gate.json'
    closed_path = ROOT / 'smc_audit' / f'{prefix}_closed_loop_90d_review.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    gate = json.loads(gate_path.read_text()) if gate_path.exists() else {}
    closed = json.loads(closed_path.read_text()) if closed_path.exists() else {}
    daily = {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'active_version': version,
        'engine': str(engine),
        'steps': steps,
        'report': report,
        'release_gate': gate,
        'closed_loop_summary': closed.get('summary', {}),
        'issue_counts': closed.get('issue_counts', {}),
        'smoke': smoke(),
        'next_action_hint': 'If WR falls, analyze losses by family/zone/conf/BQ/trend; if SOLD_EARLY dominates, classify original-runner vs new setup; create next Vxx only after full audit passes.'
    }
    out = REPORT_DIR / f'{datetime.datetime.now().strftime("%Y%m%d")}_{prefix}_closed_loop.json'
    out.write_text(json.dumps(daily, ensure_ascii=False, indent=2))
    metrics = report.get('metrics', {})
    print(json.dumps({'ok': True, 'version': version, 'out': str(out), 'pass': gate.get('pass', True), 'wr': metrics.get('raw_wr', metrics.get('wr'))}, ensure_ascii=False))

if __name__ == '__main__':
    main()
