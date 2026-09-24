# -*- coding: utf-8 -*-
r"""R99 — 2026-10-23 复盘判定器 (自动执行 v24 生产切换闸门)

门口的规矩 (用户在 R87 立下的):
  v24 影子若区间法: v1 weight>=0.7 组 vs <0.7 组的 avg 差 ≥2pp 且 PF 比 ≥1.5 → 可升级生产.

新版对照: R95 起 ledger 订单都同时打 v23 v1 和 v23_v2 两路影子 —— 本次复盘必须三条线:

  A. v24 v1 是否达标 (维持原判)
  B. v1 的 高指 vs 低指位置对实际 PnL 是否"方向正确"
  C. v23_v2 相对 v23_v1 的 边际改进量 (实际前瞻数据)

输出: research/handover/_复盘_R99_判定.txt (也将进 /audit 门户卡)
"""
import json, sys, io
from pathlib import Path
from collections import defaultdict

ROOT = Path(r'E:\test\smc_project')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

led = json.load(open(ROOT / 'research/paper_ledger.json', encoding='utf-8'))

# 只纳入可判定单: 已闭合 (pnl_pct 非 None) 且 v23_v2 已标
orders = [o for o in led if isinstance(o, dict) and o.get('code')
          and o.get('pnl_pct') is not None]


def st(rs):
    rs = [r for r in rs if r.get('_pnl') is not None]
    if not rs:
        return (0, 0, 0, 0)
    n = len(rs)
    p = [r['_pnl'] for r in rs]
    avg = sum(p) / n
    wr = sum(1 for v in p if v > 0) / n * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    pf = pos / neg if neg else 999
    return n, round(avg, 2), round(wr, 1), round(pf, 2)


for o in orders:
    try:
        o['_pnl'] = float(o['pnl_pct'])
    except Exception:
        o['_pnl'] = None
orders = [o for o in orders if o.get('_pnl') is not None]
print(f'订单(结算且有pnl): {len(orders)}')

# A: v23 v1 高/低分裂
lo = [o for o in orders if (o.get('v23') or {}).get('weight') is not None and o['v23']['weight'] < 0.7]
hi = [o for o in orders if (o.get('v23') or {}).get('weight') is not None and o['v23']['weight'] >= 0.7]
print('\n=== A. v24 v1 影子 高/低段 (生产切换原判) ===')
s_lo, s_hi = st(lo), st(hi)
print(f'  w<0.7: n={s_lo[0]} avg={s_lo[1]} WR={s_lo[2]} PF={s_lo[3]}')
print(f'  w≥0.7: n={s_hi[0]} avg={s_hi[1]} WR={s_hi[2]} PF={s_hi[3]}')
diff = None
ratio = None
if s_lo[0] >= 10 and s_hi[0] >= 10:
    diff = s_hi[1] - s_lo[1]
    ratio = (s_hi[3] / s_lo[3]) if s_lo[3] > 0 else None
    print(f'  差 {diff:+.2f}pp  PF 比 {ratio:.2f}  → 判: {"✅ 达标" if (diff >= 2 and ratio and ratio >= 1.5) else "❌ 未达标"}')
else:
    print(f'  样本量少 (n_lo={s_lo[0]} n_hi={s_hi[0]}), 不可判 — 需等 2026-10-23 再算')

# B: v23_v2 高/低段 (双标交集)
both = [o for o in orders if (o.get('v23') or {}).get('weight') is not None and (o.get('v23_v2') or {}).get('weight') is not None]
print('\n=== B. v2 狠打分逻辑 高低段 (已双标, n={}) ==='.format(len(both)))
lo2 = [o for o in both if o['v23_v2']['weight'] < 0.7]
hi2 = [o for o in both if o['v23_v2']['weight'] >= 0.7]
s_lo2, s_hi2 = st(lo2), st(hi2)
print(f'  v2 w<0.7: n={s_lo2[0]} avg={s_lo2[1]} WR={s_lo2[2]} PF={s_lo2[3]}')
print(f'  v2 w≥0.7: n={s_hi2[0]} avg={s_hi2[1]} WR={s_hi2[2]} PF={s_hi2[3]}')
if s_lo2[0] >= 10 and s_hi2[0] >= 10:
    d2 = s_hi2[1] - s_lo2[1]
    print(f'  差 {d2:+.2f}pp')
else:
    print('  样本量不足 — 复盘日再算')

# C: 与 v1 作对的分歧单 (v1高 v2狠)
div = [o for o in both if o['v23']['weight'] >= 0.7 and o['v23_v2']['weight'] < 0.5]
agree = [o for o in both if not (o['v23']['weight'] >= 0.7 and o['v23_v2']['weight'] < 0.5)]
print('\n=== C. 双链分歧单实战证 ===')
s_d, s_a = st(div), st(agree)
print(f'  分歧 (v1高v2狠): n={s_d[0]} avg={s_d[1]} PF={s_d[3]}')
print(f'  一致与中性:  n={s_a[0]} avg={s_a[1]} PF={s_a[3]}')
if s_d[0] >= 10 and s_a[0] >= 10 and s_a[1] - s_d[1] > 0.5:
    print('  ➡️ 笔记 v2 打狗的对: 分歧单确实比一致单贴')
elif s_d[0] < 10:
    print('  样本量不足')

# 终场定论小结
md = []
md.append('# 2026-10-23 复盘主看表 (由 R99 判定器生成)')
md.append('')
md.append(f'| 测 | n | avg | WR | PF |')
md.append('|---|---|---|---|---|')
md.append(f'| v1 低权单 | {s_lo[0]} | {s_lo[1]} | {s_lo[2]} | {s_lo[3]} |')
md.append(f'| v1 高权单 | {s_hi[0]} | {s_hi[1]} | {s_hi[2]} | {s_hi[3]} |')
md.append(f'| v2 低权单 | {s_lo2[0]} | {s_lo2[1]} | {s_lo2[2]} | {s_lo2[3]} |')
md.append(f'| v2 高权单 | {s_hi2[0]} | {s_hi2[1]} | {s_hi2[2]} | {s_hi2[3]} |')
md.append(f'| 双链分歧单 (v1高v2狠) | {s_d[0]} | {s_d[1]} | {s_d[2]} | {s_d[3]} |')
md.append(f'| 一致单 | {s_a[0]} | {s_a[1]} | {s_a[2]} | {s_a[3]} |')
md.append('')
if diff is not None and ratio is not None:
    ok = (diff >= 2 and ratio >= 1.5)
    md.append(f'**v1 影子原判**: 差 {diff:+.2f}pp / PF 比 {ratio:.2f} → {"✅ 需召升生产" if ok else "❌ 不召升"}')
else:
    md.append(f'**v1 影子原判**: 样本不足 (n_lo={s_lo[0]}, n_hi={s_hi[0]}) → 等 10-23 之后等')
p = ROOT / 'research/handover/_复盘_R99_judgment.md'
p.write_text('\n'.join(md), encoding='utf-8')
print(f'\n已写 {p.name}')
