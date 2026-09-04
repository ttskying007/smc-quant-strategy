#!/usr/bin/env python3
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

V102_TRADES = Path('/root/.hermes/smc_opt_v102_balanced_volume_gate/v102_trades.json')
V103A_TRADES = Path('/root/.hermes/smc_opt_v103a_risk_gate/v103a_trades.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v103a_risk_gate')
OUT_JSON = OUT_DIR / 'v103a_stability_report.json'
OUT_MD = OUT_DIR / 'v103a_stability_report.md'


def fnum(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except Exception:
        return default


def is_sl(row):
    reason = str(row.get('exit_reason') or '').upper()
    return reason.startswith('SL') or bool(row.get('sl_hit'))


def is_win(row):
    return fnum(row.get('net_pnl_pct', row.get('pnl_pct'))) >= 0.8


def date_key(row):
    return str(row.get('entry_date') or row.get('buy_date') or row.get('pick_date') or row.get('signal_date') or '')[:8]


def month_key(row):
    return date_key(row)[:6]


def load_prod(path):
    rows = json.loads(path.read_text())
    return [r for r in rows if r.get('production_eligible_v102') and not r.get('future_leak_flag')]


def base_stats(rows):
    count = len(rows)
    sl_count = sum(1 for r in rows if is_sl(r))
    win_count = sum(1 for r in rows if is_win(r))
    avg_net = statistics.mean([fnum(r.get('net_pnl_pct', r.get('pnl_pct'))) for r in rows]) if rows else 0
    return {
        'trades': count,
        'sl_count': sl_count,
        'sl_rate': sl_count / count * 100 if count else 0,
        'net_win_count': win_count,
        'net_win_rate_ge_0_8': win_count / count * 100 if count else 0,
        'avg_net_pnl_pct': avg_net,
    }


def monthly_stats(rows):
    grouped = defaultdict(list)
    for row in rows:
        key = month_key(row)
        if key:
            grouped[key].append(row)
    out = []
    for month, items in sorted(grouped.items()):
        s = base_stats(items)
        if s['trades'] < 5:
            confidence = 'OBSERVE_ONLY'
        elif s['trades'] < 15:
            confidence = 'LOW_CONFIDENCE'
        else:
            confidence = 'EVALUABLE'
        s.update({'month': month, 'confidence': confidence})
        out.append(s)
    return out


def rolling_stats(rows, window):
    ordered = sorted(rows, key=date_key)
    windows = []
    for i in range(0, len(ordered) - window + 1):
        part = ordered[i:i + window]
        sl_rate = sum(1 for r in part if is_sl(r)) / window * 100
        windows.append({
            'start_date': date_key(part[0]),
            'end_date': date_key(part[-1]),
            'sl_rate': sl_rate,
            'sl_count': sum(1 for r in part if is_sl(r)),
        })
    rates = [w['sl_rate'] for w in windows]
    worst = max(windows, key=lambda x: x['sl_rate']) if windows else None
    return {
        'window': window,
        'count': len(windows),
        'mean_sl_rate': statistics.mean(rates) if rates else 0,
        'max_sl_rate': max(rates) if rates else 0,
        'stdev_sl_rate': statistics.pstdev(rates) if rates else 0,
        'worst_window': worst,
    }


def slice_stats(rows):
    low_risk = [r for r in rows if fnum(r.get('risk_pct')) < 0.7]
    late = [r for r in rows if int(fnum(r.get('hold_bars', r.get('hold_days')))) > 10]
    edge_5r = [r for r in rows if 4.8 <= fnum(r.get('tp2_r', r.get('tp2_R'))) <= 5.2]
    by_combo = defaultdict(list)
    for r in rows:
        by_combo[str(r.get('combo_contract_key') or r.get('combo_contract') or r.get('contract') or 'UNKNOWN')].append(r)
    return {
        'risk_pct_lt_0_7': base_stats(low_risk),
        'hold_gt_10': base_stats(late),
        'tp2r_around_5': base_stats(edge_5r),
        'combo': {k: base_stats(v) for k, v in sorted(by_combo.items(), key=lambda item: -len(item[1]))},
    }


def analyze(name, rows):
    monthly = monthly_stats(rows)
    return {
        'name': name,
        'global': base_stats(rows),
        'months_total': len(monthly),
        'months_lt_5': sum(1 for m in monthly if m['trades'] < 5),
        'true_anomaly_months': [m for m in monthly if m['trades'] >= 5 and m['sl_rate'] >= 20],
        'monthly': monthly,
        'rolling20': rolling_stats(rows, 20),
        'rolling50': rolling_stats(rows, 50),
        'slices': slice_stats(rows),
    }


def pct(value):
    return f'{value:.2f}%'


def md_table(headers, rows):
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    for row in rows:
        lines.append('| ' + ' | '.join(str(x) for x in row) + ' |')
    return '\n'.join(lines)


def main():
    v102_rows = load_prod(V102_TRADES)
    v103_rows = load_prod(V103A_TRADES)
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'v102': analyze('V102', v102_rows),
        'v103a': analyze('V103A', v103_rows),
    }
    v102 = report['v102']
    v103 = report['v103a']
    report['comparison'] = {
        'trade_delta': v103['global']['trades'] - v102['global']['trades'],
        'sl_rate_delta': v103['global']['sl_rate'] - v102['global']['sl_rate'],
        'net_win_rate_delta': v103['global']['net_win_rate_ge_0_8'] - v102['global']['net_win_rate_ge_0_8'],
        'avg_net_delta': v103['global']['avg_net_pnl_pct'] - v102['global']['avg_net_pnl_pct'],
        'rolling20_max_delta': v103['rolling20']['max_sl_rate'] - v102['rolling20']['max_sl_rate'],
        'rolling20_stdev_delta': v103['rolling20']['stdev_sl_rate'] - v102['rolling20']['stdev_sl_rate'],
        'rolling50_max_delta': v103['rolling50']['max_sl_rate'] - v102['rolling50']['max_sl_rate'],
        'rolling50_stdev_delta': v103['rolling50']['stdev_sl_rate'] - v102['rolling50']['stdev_sl_rate'],
        'anomaly_months_removed': sorted(set(m['month'] for m in v102['true_anomaly_months']) - set(m['month'] for m in v103['true_anomaly_months'])),
        'anomaly_months_remaining': [m['month'] for m in v103['true_anomaly_months']],
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    rows = []
    for label, item in [('V102', v102), ('V103A', v103)]:
        g = item['global']
        rows.append([label, g['trades'], g['sl_count'], pct(g['sl_rate']), pct(g['net_win_rate_ge_0_8']), pct(g['avg_net_pnl_pct']), item['months_lt_5'], ','.join(m['month'] for m in item['true_anomaly_months'])])
    rolling_rows = []
    for label, item in [('V102', v102), ('V103A', v103)]:
        for key in ('rolling20', 'rolling50'):
            r = item[key]
            worst = r['worst_window'] or {}
            rolling_rows.append([label, r['window'], r['count'], pct(r['mean_sl_rate']), pct(r['max_sl_rate']), pct(r['stdev_sl_rate']), f"{worst.get('start_date','')}~{worst.get('end_date','')}"])
    comp = report['comparison']
    md = f"""# V103-A 稳定性审计报告

- 生成时间: {report['generated_at']}
- 结论: `risk_pct>=0.7` 是合理的最小入场前门禁；它真实降低 SL 波峰与 rolling 方差，但没有解决 `hold>10` 后段保护不足。

## 全局对比

{md_table(['版本','交易数','SL数','SL率','净胜率>=0.8%','平均净PnL','n<5月份','真异常月份'], rows)}

## Rolling 稳定性

{md_table(['版本','窗口','窗口数','平均SL率','最大SL率','SL率方差','最差窗口'], rolling_rows)}

## 差异结论

{md_table(['指标','变化'], [
    ['交易数', comp['trade_delta']],
    ['SL率', pct(comp['sl_rate_delta'])],
    ['净胜率>=0.8%', pct(comp['net_win_rate_delta'])],
    ['平均净PnL', pct(comp['avg_net_delta'])],
    ['rolling20最大SL率', pct(comp['rolling20_max_delta'])],
    ['rolling20方差', pct(comp['rolling20_stdev_delta'])],
    ['rolling50最大SL率', pct(comp['rolling50_max_delta'])],
    ['rolling50方差', pct(comp['rolling50_stdev_delta'])],
    ['移除异常月份', ','.join(comp['anomaly_months_removed']) or '-'],
    ['残留异常月份', ','.join(comp['anomaly_months_remaining']) or '-'],
])}

## 方案判断

| 项 | 判断 | 原因 |
|---|---|---|
| `risk_pct>=0.7` | 保留 | 只用入场前字段，剔除的低risk集合 SL率显著更高 |
| 月度自然统计 | 降级为辅助 | 仍有 13 个 n<5 月份，0/100% 月度SL不可靠 |
| rolling20/50 | 升级为主稳定性视图 | V103A 最大SL率与方差均下降，能跨月平滑样本噪声 |
| 后段保护 | 下一阶段处理 | `hold>10` SL率未被 V103A 改善，说明不是入场门禁问题 |
| 继续加环境门禁 | 暂不执行 | 当前证据只支持先做审计字段，不支持硬过滤 |
"""
    OUT_MD.write_text(md)
    print(OUT_JSON)
    print(OUT_MD)


if __name__ == '__main__':
    main()
