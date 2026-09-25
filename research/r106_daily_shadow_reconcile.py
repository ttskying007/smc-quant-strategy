# -*- coding: utf-8 -*-
r"""R106 — 复盘日一键脚本 (2026-10-23 使用)

依序执行 (每条单独审计):
  1. paper_ledger 回填 v23_v2 (终版狠打公式, 含 s22/s23)
  2. r99_review_judgment 重算判定
  3. 输出详细复盘报表到 _复盘_R106_judgment.md

用法: python -X utf8 research/r106_daily_shadow_reconcile.py
"""
import subprocess, sys, io, os, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')

PY = sys.executable
print('步骤1: 重新回填 paper_ledger v23_v2 (含 s22/s23)...')
r = subprocess.run([PY, '-X', 'utf8', str(ROOT / 'research' / 'r96_backfill_v23v2.py')],
                   capture_output=True, text=True, cwd=str(ROOT))
print(r.stdout.splitlines()[-2:])
if r.returncode != 0:
    print('回填失败:', r.stderr.splitlines()[-5:])
    sys.exit(1)

print('\n步骤2: 重跑判定器...')
r = subprocess.run([PY, '-X', 'utf8', str(ROOT / 'research' / 'r99_review_judgment.py')],
                   capture_output=True, text=True, cwd=str(ROOT))
tail = '\n'.join(r.stdout.splitlines()[-20:])
print(tail)
if r.returncode != 0:
    print('判定失败:', r.stderr.splitlines()[-5:])
    sys.exit(1)

print('\n步骤3: 汇总 (复盘报表新写入)')
lg = json.load(open(ROOT / 'research/paper_ledger.json', encoding='utf-8'))
orders = [o for o in lg if isinstance(o, dict) and o.get('code') and o.get('pnl_pct') is not None]
v1_lo = [o for o in orders if (o.get('v23') or {}).get('weight') is not None and o['v23']['weight'] < 0.7]
v1_hi = [o for o in orders if (o.get('v23') or {}).get('weight') is not None and o['v23']['weight'] >= 0.7]
v2_lo = [o for o in orders if (o.get('v23_v2') or {}).get('weight') is not None and o['v23_v2']['weight'] < 0.7]
v2_hi = [o for o in orders if (o.get('v23_v2') or {}).get('weight') is not None and o['v23_v2']['weight'] >= 0.7]
both_div = [o for o in orders if (o.get('v23') or {}).get('weight') is not None and o['v23']['weight'] >= 0.7
            and (o.get('v23_v2') or {}).get('weight') is not None and o['v23_v2']['weight'] < 0.5]

def st(rs):
    if not rs:
        return (0, 0, 0, 0)
    p = [o['pnl_pct'] for o in rs]
    n = len(p)
    avg = sum(p) / n
    wr = sum(1 for v in p if v > 0) / n * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return n, round(avg, 3), round(wr, 1), round(pos / neg, 2) if neg else 999

md = [
    '# R106 复盘判定 (动中调)', f'运行时间： 此前 (2026-10-23 使用时重跑这个脚本)',
    '',
    f'账本 （已结算 pnl): {len(orders)} 单',
    '',
    '| 段 | n | avg | WR% | PF |',
    '|---|---|---|---|---|',
    f'| v1 低权 (w<0.7) | * | {st(v1_lo)[0]} | {st(v1_lo)[1]} | {st(v1_lo)[2]} | {st(v1_lo)[3]} |',
    f'| v1 高权 (w≥0.7) | * | {st(v1_hi)[0]} | {st(v1_hi)[1]} | {st(v1_hi)[2]} | {st(v1_hi)[3]} |',
    f'| v2 低权 (w<0.7) | * | {st(v2_lo)[0]} | {st(v2_lo)[1]} | {st(v2_lo)[2]} | {st(v2_lo)[3]} |',
    f'| v2 高权 (w≥0.7) | * | {st(v2_hi)[0]} | {st(v2_hi)[1]} | {st(v2_hi)[2]} | {st(v2_hi)[3]} |',
    f'| 双链分歧单 (v1高 v2狠) | * | {st(both_div)[0]} | {st(both_div)[1]} | {st(both_div)[2]} | {st(both_div)[3]} |',
    '',
    '## 计算口径',
    '- 原 v24 升级票: v1 高低差 ≥2pp 且 PF 比 ≥1.5',
    '- 新 v2 升级票 (自适应链): 分歧单 PF < 一致单 PF (证明 v2 狠打有效)',
]

# R127: s24/s25 影子计数报告 (additive) — combo_v23_shadow_v3 flags
try:
    import csv as _csv106
    _sh3 = list(_csv106.DictReader(open(ROOT / 'research/combo_v23_shadow_v3.csv', encoding='utf-8-sig')))
    _s24_n = sum(1 for r in _sh3 if 's24_eql_risk' in (r.get('v23_flags_v2') or ''))
    _s25_n = sum(1 for r in _sh3 if 's25_reverse' in (r.get('v23_flags_v2') or ''))
    _s22_n = sum(1 for r in _sh3 if 's22' in ((r.get('v23_flags_v2') or '').split(';')))
    _s23_n = sum(1 for r in _sh3 if 's23' in ((r.get('v23_flags_v2') or '').split(';')))
    md += ['', '## 影子因子计数 (R127)',
           f'- s24_eql_risk (磁区毒性): {_s24_n} 腿 (w×0.15)',
           f'- s25_reverse (二测拒绝反向): {_s25_n} 腿 (记录-only)',
           f'- s22/s23 (相对弱势压制): {_s22_n}/{_s23_n} 腿 (w×0.15)',
           '- 反向候选 (sweep→reverse 2.0): 20 信号全胜 (research/combo_reverse_candidates.csv)']
except Exception as _e106:
    print('s24/s25 计数失败:', _e106)
out = ROOT / 'research/handover/_复盘_R106_judgment.md'
out.write_text('\n'.join(md), encoding='utf-8')
print(f'已写 {out.name}')

# 结算: v1 判
if len(v1_lo) and len(v1_hi) and st(v1_lo)[0] + st(v1_hi)[0] >= 20:
    diff = st(v1_hi)[1] - st(v1_lo)[1]
    ratio = st(v1_hi)[3] / st(v1_lo)[3] if st(v1_lo)[3] else None
    print(f'\nv1 高低段判定: diff={diff:+.2f}pp / PF 比={ratio}')
    print('判定： 同 2026-10-23 仪式参阅')
print('完成')
