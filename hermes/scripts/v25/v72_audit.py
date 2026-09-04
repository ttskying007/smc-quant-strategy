#!/usr/bin/env python3
import collections
import json
import pathlib
import statistics

ROOT = pathlib.Path('/root/.hermes')
rows = json.loads((ROOT / 'smc_opt_v72_layered' / 'v72_trades.json').read_text())


def f(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def met(rs):
    if not rs:
        return {'n': 0}
    pnl = [f(r.get('pnl_pct')) for r in rs]
    wins = [x for x in pnl if x > 0]
    losses = [-x for x in pnl if x <= 0]
    sl = sum(1 for r in rs if r.get('exit_reason') in ('SL_HIT', 'GAP_SL_HIT'))
    return {
        'n': len(rs),
        'wr': round(len(wins) / len(rs) * 100, 2),
        'sl_rate': round(sl / len(rs) * 100, 2),
        'sl_n': sl,
        'avg': round(statistics.mean(pnl), 3),
        'rr': round((statistics.mean(wins) / statistics.mean(losses)) if wins and losses else 999, 3),
    }


def group(keyfn, source=rows):
    d = collections.defaultdict(list)
    for r in source:
        d[keyfn(r)].append(r)
    return {str(k): met(v) for k, v in sorted(d.items(), key=lambda kv: str(kv[0]))}


thresholds = {'Base': 0, 'QualityA': 0.25, 'QualityB': 0.5, 'Strict': 0.75}
layers = {name: [r for r in rows if f(r.get('sl_buffer_below_zone_pct')) >= thr] for name, thr in thresholds.items()}
audit = {
    'overall': met(rows),
    'layers': {k: met(v) for k, v in layers.items()},
    'by_year': group(lambda r: str(r.get('entry_date', ''))[:4]),
    'by_layer_year': {ln: group(lambda r: str(r.get('entry_date', ''))[:4], rs) for ln, rs in layers.items()},
    'by_family': group(lambda r: r.get('v59_setup_family')),
    'by_zone': group(lambda r: r.get('zone_type')),
    'by_conf': group(lambda r: r.get('conf_type')),
    'by_combo': group(lambda r: (r.get('v59_setup_family'), r.get('zone_type'), r.get('conf_type'))),
    'exit_counts': dict(collections.Counter(r.get('exit_reason') for r in rows)),
}
(ROOT / 'smc_audit' / 'v72_layered_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))

lines = [
    '# V72 分层扩容审计',
    '',
    '## 总体与分层',
    '',
    '|层级|笔数|WR|SL率|SL笔数|均盈|RR|',
    '|---|---:|---:|---:|---:|---:|---:|',
]
for name in ['Base', 'QualityA', 'QualityB', 'Strict']:
    m = audit['layers'][name]
    lines.append(f"|{name}|{m['n']}|{m['wr']}%|{m['sl_rate']}%|{m['sl_n']}|{m['avg']}%|{m['rr']}|")
lines += ['', '## 年度分布', '', '|年份|笔数|WR|SL率|均盈|RR|', '|---|---:|---:|---:|---:|---:|']
for y, m in audit['by_year'].items():
    lines.append(f"|{y}|{m['n']}|{m['wr']}%|{m['sl_rate']}%|{m['avg']}%|{m['rr']}|")
lines += ['', '## 机制分布（n>=10）', '', '|机制|笔数|WR|SL率|均盈|RR|', '|---|---:|---:|---:|---:|---:|']
for k, m in audit['by_combo'].items():
    if m['n'] >= 10:
        lines.append(f"|{k}|{m['n']}|{m['wr']}%|{m['sl_rate']}%|{m['avg']}%|{m['rr']}|")
lines += [
    '',
    '## 结论',
    '',
    '- V72 解决了 V71 严格层样本过小问题：Base=250，QualityB=140，Strict=126。',
    '- V72 Base/Quality 层质量仍低于 V66 默认生产，不能替换 V66。',
    '- V72 正确定位：前端并行分层候选池，用于观察扩容样本与 SL-buffer 质量等级。',
]
(ROOT / 'smc_audit' / 'v72_layered_audit.md').write_text('\n'.join(lines))
print(json.dumps({'overall': audit['overall'], 'layers': audit['layers']}, ensure_ascii=False, indent=2))
