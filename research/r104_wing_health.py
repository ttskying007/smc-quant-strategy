# -*- coding: utf-8 -*-
r"""R104 — 自适应 pivot 的健康性检查 (跨股分布, 防退化)

R90 的 pick_pivot_by_density 在 [2,8] 找翼. 需要确认:
  1. 不同股票是否真取到不同 wing (还是都打 2 或 8 = 塌缩)
  2. 密度目标是否被有效收归 (swings/100bar 6~14 附近)
  3. 每股 wing 稳定性: 不同时期有没有乱抖
"""
import csv, json, sys, io
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, r'E:\test\smc_project\research')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')

from core.structure import pick_pivot_by_density

KC = ROOT / 'hermes' / 'kline_cache_tencent'

def bars_of(code6):
    p = KC / (code6 + ('_SH' if code6.startswith('6') else '_SZ') + '_daily_800.json')
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding='utf-8'))
    bs = []
    for r in raw:
        t = ''.join(x for x in str(r.get('t') or '') if x.isdigit())[:8]
        if t:
            try:
                bs.append({'t': t, 'o': float(r['o']), 'h': float(r['h']), 'l': float(r['l']),
                           'c': float(r['c']), 'v': float(r.get('v') or 0)})
            except Exception:
                continue
    bs.sort(key=lambda b: b['t'])
    return bs


def main():
    legs = list(csv.DictReader(open(ROOT / 'research' / 'combo_v22_trades.csv', encoding='utf-8-sig')))
    syms = sorted(set(r['symbol'] for r in legs))
    print(f'涉及股票数: {len(syms)}')
    wings_per_sym = {}
    cache = {}
    for s in syms:
        code6 = s[:6]
        if code6 not in cache:
            cache[code6] = bars_of(code6)
        bs = cache[code6]
        if not bs:
            continue
        p, d = pick_pivot_by_density(bs, len(bs) - 1)
        wings_per_sym[s] = (p, round(d, 1))
    # 分布
    from collections import Counter
    dist = Counter(w for w, _ in wings_per_sym.values())
    print(f'\n=== pivot 分股分布 ===')
    for w in sorted(dist):
        print(f"  pivot={w}: {dist[w]} 股")
    # 密度分布
    dens = [d for _, d in wings_per_sym.values()]
    print(f'\n=== swings/100bar 密度 (自适应后) ===')
    print(f'  min={min(dens)} p25={sorted(dens)[len(dens)//4]} median={sorted(dens)[len(dens)//2]} p75={sorted(dens)[3*len(dens)//4]} max={max(dens)}')
    target_in = [d for d in dens if 8 <= d <= 14]
    print(f'  在目标带 [8,14] 内: {len(target_in)}/{len(dens)} = {len(target_in)/len(dens)*100:.1f}%')
    # 外部点
    out_low = {s: v for s, v in wings_per_sym.items() if v[1] < 8}
    out_high = {s: v for s, v in wings_per_sym.items() if v[1] > 14}
    print(f'\n  低于8: {len(out_low)} 股')
    for s, v in sorted(out_low.items(), key=lambda kv: kv[1][1])[:5]:
        print(f'    {s} -> wing={v[0]} density={v[1]}')
    print(f'  高于14: {len(out_high)} 股')
    for s, v in sorted(out_high.items(), key=lambda kv: -kv[1][1])[:5]:
        print(f'    {s} -> wing={v[0]} density={v[1]}')
    # pnl 按 wing 分
    sym_map = defaultdict(list)
    for r in legs:
        s = r['symbol']
        if s in wings_per_sym:
            sym_map[wings_per_sym[s][0]].append(float(r['net_pnl_pct'] or 0))
    print('\n=== 按 pivot 分桶 (等权) ===')
    for w in sorted(sym_map):
        arr = sym_map[w]
        avg = sum(arr) / len(arr)
        pos = sum(v for v in arr if v > 0)
        neg = -sum(v for v in arr if v < 0)
        print(f"  pivot={w}: n={len(arr)} avg={avg:+.2f} PF={pos/neg if neg else 999:.2f}")


if __name__ == '__main__':
    main()
