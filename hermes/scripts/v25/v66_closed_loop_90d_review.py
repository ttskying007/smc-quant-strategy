#!/usr/bin/env python3
"""SMC closed-loop follow-up review.

This converts backtest trades into the same workflow used for live picks:
select -> monitor -> stop/target event -> keep reviewing for 90 trading days.
Outputs JSON + Markdown under /root/.hermes/smc_audit.
"""
from __future__ import annotations
import json, pathlib, collections, statistics
from datetime import datetime

ROOT = pathlib.Path('/root/.hermes')
CACHE = ROOT / 'kline_cache'
TRADES = ROOT / 'smc_opt_v66' / 'v66_trades.json'
PICKS = ROOT / 'smc_opt_v66' / 'v66_picks.json'
OUT = ROOT / 'smc_audit'
OUT.mkdir(parents=True, exist_ok=True)
FOLLOW_DAYS = 90


def f(x, d=0.0):
    try:
        return float(x if x not in (None, '') else d)
    except Exception:
        return d


def i(x, d=-1):
    try:
        return int(float(x))
    except Exception:
        return d


def dkey(v):
    return str(v or '').replace('-', '')[:8]


def load_json(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return default


def kpath(sym):
    p = CACHE / (sym.replace('.', '_') + '_daily_750.json')
    if not p.exists():
        p = CACHE / (sym.replace('.', '_') + '_daily_300.json')
    return p


def kdate(kl, idx):
    if 0 <= idx < len(kl):
        return dkey(kl[idx].get('t') or kl[idx].get('date'))
    return ''


def pct(a, b):
    return (a - b) / max(b, 1e-9) * 100


def mean(vals):
    return round(sum(vals) / max(len(vals), 1), 3) if vals else 0


def review_trade(t):
    kl = load_json(kpath(t['symbol']), []) or []
    ei = i(t.get('entry_index'))
    xi = i(t.get('exit_index'))
    entry = f(t.get('entry_price'))
    risk_pct = f(t.get('risk_pct')) or pct(entry, f(t.get('sl')))
    if not (0 <= ei < len(kl) and entry > 0):
        return {'symbol': t.get('symbol'), 'fatal': 'missing_kline_or_entry'}
    follow_end = min(len(kl) - 1, ei + FOLLOW_DAYS)
    trade_end = xi if 0 <= xi < len(kl) else follow_end
    trade_seg = kl[ei:trade_end + 1]
    follow_seg = kl[ei:follow_end + 1]
    post_exit_seg = kl[trade_end + 1:follow_end + 1]
    max_trade_hi = max([f(b.get('h')) for b in trade_seg] or [entry])
    min_trade_lo = min([f(b.get('l')) for b in trade_seg] or [entry])
    max_follow_hi = max([f(b.get('h')) for b in follow_seg] or [entry])
    min_follow_lo = min([f(b.get('l')) for b in follow_seg] or [entry])
    post_exit_hi = max([f(b.get('h')) for b in post_exit_seg] or [entry])
    pnl = f(t.get('pnl_pct'))
    hold = i(t.get('hold_bars'), max(0, trade_end - ei))
    mfe_trade = pct(max_trade_hi, entry)
    mae_trade = pct(entry, min_trade_lo)
    mfe90 = pct(max_follow_hi, entry)
    mae90 = pct(entry, min_follow_lo)
    post_exit_mfe = pct(post_exit_hi, entry)
    capture90 = pnl / max(mfe90, 1e-9) if mfe90 > 0 else 0
    realized_r = pnl / max(risk_pct, 1e-9) if risk_pct > 0 else 0
    issues = []
    if hold > FOLLOW_DAYS:
        issues.append('HOLD_OVER_90')
    if 0 < pnl < 2:
        issues.append('WIN_BELOW_2PCT_FEE_INEFFICIENT')
    if -1 < pnl < 0:
        issues.append('LOSS_BELOW_1PCT_NOISE_EXIT')
    if pnl > 0 and realized_r < 2:
        issues.append('WIN_RR_BELOW_2R')
    if risk_pct < 1:
        issues.append('RISK_BELOW_1PCT_FEE_NOISE')
    if post_exit_mfe - max(pnl, 0) >= max(3, risk_pct * 1.5):
        issues.append('SOLD_EARLY_NEXT_90D')
        er = str(t.get('exit_reason','')).upper()
        if 'TP2' in er: issues.append('SOLD_EARLY_BY_TP2_STOP')
        elif 'STRUCT' in er: issues.append('SOLD_EARLY_BY_STRUCTURE_STOP')
        elif 'TRAIL' in er: issues.append('SOLD_EARLY_BY_TRAILING')
        elif 'TIMEOUT' in er: issues.append('SOLD_EARLY_BY_TIMEOUT')
    if pnl <= 0 and mfe90 >= max(6, risk_pct * 2):
        issues.append('BAD_EXIT_LOST_BUT_90D_RECOVERED')
    if capture90 < 0.25 and mfe90 >= max(8, risk_pct * 2):
        issues.append('LOW_90D_MFE_CAPTURE')
    if hold >= FOLLOW_DAYS and pnl < mfe90 * 0.35:
        issues.append('HELD_LONG_BUT_CAPTURE_LOW')
    provenance_keys = ('source_event_idx', 'zone_idx', 'conf_index', 'entry_index', 'exit_index')
    has_signal_trace = bool(t.get('wave_ref') or t.get('struct_event') or all(i(t.get(k)) >= 0 for k in provenance_keys))
    if not has_signal_trace:
        issues.append('SIGNAL_TRACE_MISSING_FRONTEND_AUDIT')
    diagnosis = []
    if 'HOLD_OVER_90' in issues:
        diagnosis.append('持仓超过90日：日线入场后没有在合理窗口兑现，说明出场模型缺少90日硬复盘门或趋势衰竭判断。')
    if 'WIN_BELOW_2PCT_FEE_INEFFICIENT' in issues:
        diagnosis.append('盈利小于2%：扣除手续费/滑点后收益效率不足，止盈保护线过低。')
    if 'WIN_RR_BELOW_2R' in issues:
        diagnosis.append('盈利低于2R：风险收益不达标，属于保本/小利退出，不应计为合格胜利。')
    if 'SOLD_EARLY_NEXT_90D' in issues:
        diagnosis.append('90日后续高点显著高于实际卖点：runner/trailing过早或未识别趋势延续。')
    if 'LOW_90D_MFE_CAPTURE' in issues:
        diagnosis.append('MFE捕获率低：信号方向对，但出场没有吃到主要利润段。')
    return {
        'symbol': t.get('symbol'), 'zone_type': t.get('zone_type'), 'entry_mode': t.get('entry_mode_v47_1') or t.get('entry_mode') or t.get('v59_setup_family') or t.get('trade_role'),
        'conf_type': t.get('conf_type'), 'signal_date': t.get('signal_date'), 'qualified_win': t.get('qualified_win'), 'entry_date': t.get('entry_date'),
        'exit_date': t.get('exit_date'), 'follow_end_date': kdate(kl, follow_end), 'entry_price': round(entry, 4),
        'exit_price_final': t.get('exit_price_final'), 'pnl_pct': round(pnl, 3), 'risk_pct': round(risk_pct, 3),
        'realized_r': round(realized_r, 3), 'hold_bars': hold, 'exit_reason': t.get('exit_reason'),
        'mfe_trade_pct': round(mfe_trade, 3), 'mae_trade_pct': round(mae_trade, 3),
        'mfe90_pct': round(mfe90, 3), 'mae90_pct': round(mae90, 3), 'post_exit_mfe90_pct': round(post_exit_mfe, 3),
        'capture90_rate': round(capture90, 3), 'issues': issues, 'diagnosis': diagnosis,
        'monitor_source': 'BACKTEST_TRADE_AS_PICK', 'closed_loop_rule': 'entry后持续复盘90个日线bar；止盈/止损发生后仍继续看未来90日MFE/MAE判断信号和出场质量',
    }


def bucket(rows, field):
    out = {}
    for k in sorted(set(str(r.get(field)) for r in rows)):
        sub = [r for r in rows if str(r.get(field)) == k]
        out[k] = {
            'n': len(sub),
            'wr': round(sum(1 for r in sub if r['pnl_pct'] > 0) / max(len(sub), 1) * 100, 2),
            'avg_pnl': mean([r['pnl_pct'] for r in sub]),
            'avg_hold': mean([r['hold_bars'] for r in sub]),
            'avg_realized_r': mean([r['realized_r'] for r in sub]),
            'sold_early_rate': round(sum(1 for r in sub if 'SOLD_EARLY_NEXT_90D' in r['issues']) / max(len(sub), 1) * 100, 2),
            'low_capture_rate': round(sum(1 for r in sub if 'LOW_90D_MFE_CAPTURE' in r['issues']) / max(len(sub), 1) * 100, 2),
        }
    return out


def main():
    trades = load_json(TRADES, []) or []
    picks = load_json(PICKS, []) or []
    rows = [review_trade(t) for t in trades]
    rows = [r for r in rows if not r.get('fatal')]
    issue_counts = collections.Counter(x for r in rows for x in r['issues'])
    wins = [r for r in rows if r['pnl_pct'] > 0]
    losses = [r for r in rows if r['pnl_pct'] <= 0]
    summary = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'workflow': '选股/回测入场 -> 实时监控 -> 触发止盈止损 -> 未来90日持续复盘 -> 归因修复',
        'active_picks_file_count': len(picks),
        'reviewed_trades': len(rows),
        'wr': round(len(wins) / max(len(rows), 1) * 100, 2),
        'avg_pnl': mean([r['pnl_pct'] for r in rows]),
        'avg_win': mean([r['pnl_pct'] for r in wins]),
        'avg_loss': mean([r['pnl_pct'] for r in losses]),
        'profit_loss_ratio': round(mean([r['pnl_pct'] for r in wins]) / max(abs(mean([r['pnl_pct'] for r in losses])), 1e-9), 3) if losses else None,
        'avg_hold_bars': mean([r['hold_bars'] for r in rows]),
        'max_hold_bars': max([r['hold_bars'] for r in rows] or [0]),
        'hold_over_90_count': sum(1 for r in rows if r['hold_bars'] > 90),
        'small_win_below_2_count': sum(1 for r in rows if 0 < r['pnl_pct'] < 2),
        'loss_inside_1pct_noise_count': sum(1 for r in rows if -1 < r['pnl_pct'] < 0),
        'win_rr_below_2r_count': sum(1 for r in rows if r['pnl_pct'] > 0 and r['realized_r'] < 2),
        'avg_90d_capture': mean([r['capture90_rate'] for r in rows]),
    }
    report = {
        'summary': summary,
        'closed_loop_schedule': {
            'T0_after_daily_scan': '把选股写入 active picks/watchlist，字段必须含 entry/SL/TP/risk/signal provenance。',
            'intraday_or_daily_monitor': '实时页从 /api/picks 读取选股；交易时段只做价格状态，休市不抓实时行情。',
            'when_tp_sl_or_timeout': '记录 exit_legs 与 exit_reason，但不结束复盘。',
            'T_plus_1_to_T_plus_90': '每天收盘用日K刷新 MFE/MAE/capture90/post_exit_mfe90，判断卖早/卖晚/信号失败。',
            'weekly_review': '按 issue_counts、最差交易、低捕获桶回写引擎参数或信号定义。',
            'release_gate': '任何新版本必须通过：max_hold<=90、无<2%小赢、无<-1~0噪音亏、胜率和盈亏比同时达标。',
        },
        'issue_counts': dict(issue_counts),
        'by_zone': bucket(rows, 'zone_type'),
        'by_entry_mode': bucket(rows, 'entry_mode'),
        'by_exit_reason': bucket(rows, 'exit_reason'),
        'worst_trades': sorted(rows, key=lambda r: (r['pnl_pct'], r['capture90_rate']))[:20],
        'worst_sold_early': sorted([r for r in rows if 'SOLD_EARLY_NEXT_90D' in r['issues']], key=lambda r: r['post_exit_mfe90_pct'] - max(r['pnl_pct'], 0), reverse=True)[:30],
        'all_rows': rows,
    }
    (OUT / 'v66_closed_loop_90d_review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    md = ['# V66 90日闭环复盘报告\n', '## Summary\n```json\n', json.dumps(summary, ensure_ascii=False, indent=2), '\n```\n']
    md.append('## Issue Counts\n```json\n' + json.dumps(report['issue_counts'], ensure_ascii=False, indent=2) + '\n```\n')
    md.append('## 最差交易\n')
    for r in report['worst_trades'][:20]:
        md.append(f"- {r['symbol']} entry={r['entry_date']} exit={r['exit_date']} hold={r['hold_bars']} pnl={r['pnl_pct']} R={r['realized_r']} mfe90={r['mfe90_pct']} cap90={r['capture90_rate']} issues={','.join(r['issues'])}\n")
    md.append('\n## 闭环流程\n')
    for k, v in report['closed_loop_schedule'].items():
        md.append(f"- {k}: {v}\n")
    (OUT / 'v66_closed_loop_90d_review.md').write_text(''.join(md))
    print(json.dumps({'summary': summary, 'issue_counts': report['issue_counts'], 'by_zone': report['by_zone'], 'worst_trades': report['worst_trades'][:5]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
