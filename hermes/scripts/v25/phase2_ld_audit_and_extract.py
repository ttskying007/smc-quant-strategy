#!/usr/bin/env python3
"""Phase2 strict L→D full audit + candidate extraction.

Produces a full per-trade replay audit and a production-candidate subset based on
full-market evidence, without touching production/frontend routing.
"""
import json, importlib.util, sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

ROOT = Path('/root/.hermes/scripts/v25')
MOD_PATH = ROOT / 'phase2_strict_ld_backtest.py'
OUT_DIR = Path('/root/.hermes/smc_opt_v25')
ALL_OUT = OUT_DIR / 'phase2_strict_ld_all_trades.json'
CAND_OUT = OUT_DIR / 'phase2_strict_ld_candidate_fvg_rr08_risk6_8_trades.json'
AUDIT_OUT = OUT_DIR / 'phase2_strict_ld_candidate_audit.json'
REPORT_OUT = OUT_DIR / 'phase2_strict_ld_candidate_report.md'

spec = importlib.util.spec_from_file_location('ld', MOD_PATH)
ld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ld)


def key_date(v):
    s = str(v or '')[:8]
    return s if len(s) == 8 and s.isdigit() else ''


def metrics(ts):
    return ld.metrics(ts)


def bucket(ts, fn):
    g = defaultdict(list)
    for t in ts:
        g[fn(t)].append(t)
    return {str(k): metrics(v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def replay_all(limit=0):
    files = sorted(ld.KLINE_DIR.glob('*_daily_750.json'))
    if limit:
        files = files[:limit]
    all_trades = []
    for i, kf in enumerate(files, 1):
        all_trades.extend(ld.replay_file(kf))
        if i % 500 == 0:
            print(f'{i}/{len(files)} trades={len(all_trades)}', flush=True)
    return files, all_trades


def semantic_issues(t):
    issues = []
    # Bar order: liquidity sweep -> displacement window creates POI -> reclaim entry -> T+1 exit.
    # Bullish FVG is confirmed by the third candle, so its zone_bar may be D.bar+1.
    if not (t.get('liq_bar') is not None and t.get('zone_bar') is not None and t.get('confirm_bar') is not None and t.get('entry_idx') is not None):
        issues.append('MISSING_BAR_INDEX')
    else:
        max_fvg_zone_bar = t['confirm_bar'] + (1 if t.get('zone_type') == 'FVG_Demand' else 0)
        if not (t['liq_bar'] <= t['zone_bar'] <= max_fvg_zone_bar and t['entry_idx'] > max(t['zone_bar'], t['confirm_bar'])):
            issues.append('SEMANTIC_BAR_ORDER_FAIL')
    if not (key_date(t.get('liq_date')) and key_date(t.get('zone_date')) and key_date(t.get('confirm_date')) and key_date(t.get('entry_date')) and key_date(t.get('exit_date'))):
        issues.append('MISSING_DATE')
    else:
        # Date order follows the same FVG confirmation rule: POI date can be the next trading day after displacement.
        if not (t['liq_date'] <= t['confirm_date'] <= t['entry_date'] <= t['exit_date'] and t['liq_date'] <= t['zone_date'] <= t['entry_date']):
            issues.append('DATE_ORDER_FAIL')
        if t['entry_date'] == t['exit_date']:
            issues.append('T_PLUS_1_FAIL_SAME_DAY_EXIT')
    for f in ['zone_type','zone_low','zone_high','entry_price','sl','tp1','risk_pct','retrace_pct','exit_reason','pnl_pct','hold_bars']:
        v = t.get(f)
        if v in (None, '') or (v in (0, '0') and f not in ('pnl_pct','retrace_pct')):
            issues.append(f'MISSING_{f.upper()}')
    if float(t.get('zone_low') or 0) <= 0 or float(t.get('zone_high') or 0) <= 0 or float(t.get('zone_high') or 0) <= float(t.get('zone_low') or 0):
        issues.append('INVALID_ZONE_RANGE')
    if not (float(t.get('sl') or 0) < float(t.get('entry_price') or 0) < float(t.get('tp1') or 0)):
        issues.append('INVALID_SL_ENTRY_TP_ORDER')
    if float(t.get('risk_pct') or 0) < 1 or float(t.get('risk_pct') or 0) > 8:
        issues.append('RISK_OUT_OF_RANGE')
    return issues


def add_review(t):
    t = dict(t)
    issues = semantic_issues(t)
    pnl = float(t.get('pnl_pct') or 0)
    t['won'] = pnl > 0
    t['semantic_order_pass'] = not any(x in issues for x in ['SEMANTIC_BAR_ORDER_FAIL','DATE_ORDER_FAIL'])
    t['t_plus_1_pass'] = 'T_PLUS_1_FAIL_SAME_DAY_EXIT' not in issues
    t['field_contract_pass'] = not any(x.startswith('MISSING_') or x.startswith('INVALID_') for x in issues)
    t['audit_pass'] = not issues
    t['audit_issues'] = issues
    t['review_verdict'] = 'TP_VALID' if t.get('exit_reason') == 'TP1_HIT' else ('SL_VALID' if t.get('exit_reason') == 'SL_HIT' else 'TIME_STOP_REVIEW')
    t['review_chain'] = f"{t.get('liq_date')} SSL → {t.get('confirm_date')} displacement → {t.get('zone_date')} {t.get('zone_type')} → {t.get('entry_date')} reclaim → {t.get('exit_date')} {t.get('exit_reason')} {pnl:+.2f}%"
    t['frontend_synced'] = False
    t['production_synced'] = False
    return t


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files, all_trades = replay_all(limit)
    reviewed_all = [add_review(t) for t in all_trades]
    candidate = [t for t in reviewed_all if t.get('zone_type') == 'FVG_Demand' and abs(float(t.get('rr_target')) - 0.8) < 1e-9 and 6 <= float(t.get('risk_pct') or 0) <= 8]

    audit = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'n_stocks': len(files),
        'all_metrics': metrics(reviewed_all),
        'candidate_name': 'Phase2_Strict_LD_FVG_RR08_Risk6_8',
        'candidate_filters': {'zone_type':'FVG_Demand','rr_target':0.8,'risk_pct':'6.0..8.0'},
        'candidate_metrics': metrics(candidate),
        'candidate_count': len(candidate),
        'candidate_audit': {
            'semantic_order_fail': sum(not t['semantic_order_pass'] for t in candidate),
            't_plus_1_fail': sum(not t['t_plus_1_pass'] for t in candidate),
            'field_contract_fail': sum(not t['field_contract_pass'] for t in candidate),
            'audit_pass': sum(t['audit_pass'] for t in candidate),
            'audit_fail': sum(not t['audit_pass'] for t in candidate),
            'issue_counts': dict(Counter(i for t in candidate for i in t['audit_issues'])),
        },
        'buckets': {
            'candidate_exit_reason': bucket(candidate, lambda t: t['exit_reason']),
            'candidate_risk_bin': bucket(candidate, lambda t: '6_7' if t['risk_pct'] < 7 else '7_8'),
            'candidate_retrace_bin': bucket(candidate, lambda t: 'a_<30' if t['retrace_pct'] < 30 else ('b_30_60' if t['retrace_pct'] < 60 else ('c_60_90' if t['retrace_pct'] < 90 else 'd_90_100'))),
            'candidate_hold_bin': bucket(candidate, lambda t: '1_3' if t['hold_bars'] <= 3 else ('4_7' if t['hold_bars'] <= 7 else ('8_15' if t['hold_bars'] <= 15 else '16_60'))),
            'all_rr_target': bucket(reviewed_all, lambda t: t['rr_target']),
            'all_zone_type': bucket(reviewed_all, lambda t: t['zone_type']),
        },
        'sample_first_20': candidate[:20],
        'sample_worst_20': sorted(candidate, key=lambda t: t['pnl_pct'])[:20],
        'sample_best_20': sorted(candidate, key=lambda t: t['pnl_pct'], reverse=True)[:20],
    }

    ALL_OUT.write_text(json.dumps(reviewed_all, ensure_ascii=False, indent=2))
    CAND_OUT.write_text(json.dumps(candidate, ensure_ascii=False, indent=2))
    AUDIT_OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2))

    md = []
    md.append('# Phase2 Strict L→D Candidate Audit\n')
    md.append(f"generated_at: {audit['generated_at']}\n")
    md.append(f"stocks: {len(files)}\n")
    md.append(f"candidate: {audit['candidate_name']}\n")
    md.append('\n## Candidate metrics\n')
    md.append('|n|WR|SL率|TP率|avgPnL|avgWin|avgLoss|RR|avgHold|\n|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    m = audit['candidate_metrics']
    md.append(f"\n|{m.get('n',0)}|{m.get('wr',0)}%|{m.get('sl_rate',0)}%|{m.get('tp_rate',0)}%|{m.get('avg_pnl',0)}%|{m.get('avg_win',0)}%|{m.get('avg_loss',0)}%|{m.get('rr',0)}|{m.get('avg_hold',0)}|\n")
    md.append('\n## Audit gates\n')
    a = audit['candidate_audit']
    md.append('|gate|fail|\n|---|---:|\n')
    md.append(f"|semantic_order|{a['semantic_order_fail']}|\n|T+1|{a['t_plus_1_fail']}|\n|field_contract|{a['field_contract_fail']}|\n|total_audit_fail|{a['audit_fail']}|\n")
    md.append('\n## 每笔交易复盘文件\n')
    md.append(f"- all trades: `{ALL_OUT}`\n- candidate trades: `{CAND_OUT}`\n- audit json: `{AUDIT_OUT}`\n")
    REPORT_OUT.write_text(''.join(md))

    print(json.dumps({k:audit[k] for k in ['generated_at','n_stocks','candidate_name','candidate_metrics','candidate_audit']}, ensure_ascii=False, indent=2))
    print('saved', ALL_OUT, CAND_OUT, AUDIT_OUT, REPORT_OUT)

if __name__ == '__main__':
    main()
