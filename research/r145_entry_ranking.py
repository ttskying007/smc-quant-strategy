# -*- coding: utf-8 -*-
"""R145: 入场质量评分排序 (选股向) — 把 R139 因果位置因子变成连续分数做事件日排序。

动机: R140 的二值过滤器有硬边界 (G3 在 2026 反转); 排序取头部只用相对顺序,
对时代漂移更稳。且公告日常多股同触发 — 排序选头部正是选股场景。

评分 (全因果, 入场日已知):
  score = day_pos                     收盘位 0-100 (R139: >70 PF10.75)
        + clip(near_high, 0, 20)      顶距净空 (R139: >5% PF4.76; 越远越好, 截断防极端)
        + 15 if gap_pct > 3           跳空强承接 (R139: PF7.94)
        - 15 if gap_pct < -3
  (loc20 底部不再单独罚 — G3 已证时代不稳, 仅靠 day_pos 间接覆盖)

检验: 按事件日分组, 组内按 score 排序取 Top-K (K=1/2/3), 对比组内基线与全池;
      分时代 (2023-25 vs 2026) 验证排序稳定性。
输出: research/handover/_r145_ranking.json / .txt
"""
import csv, json
import collections
from pathlib import Path

ROOT = Path(r'E:\test\smc_project')


def stats(ps):
    if not ps:
        return {'n': 0}
    gp = sum(x for x in ps if x > 0)
    gl = -sum(x for x in ps if x < 0)
    return {'n': len(ps), 'avg': round(sum(ps) / len(ps), 2),
            'wr': round(sum(1 for x in ps if x > 0) / len(ps) * 100, 1),
            'pf': round(gp / gl, 2) if gl > 0 else 99}


def score_of(r):
    try:
        dp = float(r.get('day_pos') or 0)
    except Exception:
        return None
    nhv = r.get('near_high')
    try:
        nh = float(nhv) if nhv not in (None, '') else 0.0
    except Exception:
        nh = 0.0
    try:
        gap = float(r.get('gap_pct') or 0)
    except Exception:
        gap = 0.0
    s = dp + max(0.0, min(nh, 20.0))
    if gap > 3:
        s += 15
    elif gap < -3:
        s -= 15
    return s


def main():
    rows = [r for r in csv.DictReader(open(ROOT / 'research/combo_v25_entry_location.csv', encoding='utf-8-sig'))
            if r.get('day_pos')]
    for r in rows:
        r['_score'] = score_of(r)
        r['_pnl'] = float(r['net_pnl_pct'] or 0)
    rows = [r for r in rows if r['_score'] is not None]

    allp = [r['_pnl'] for r in rows]
    res = {'legs': len(rows), 'all': stats(allp)}

    # 事件日分组
    cohorts = collections.defaultdict(list)
    for r in rows:
        cohorts[str(r['entry_date'])].append(r)
    multi = {d: v for d, v in cohorts.items() if len(v) >= 2}
    res['cohorts_ge2'] = len(multi)

    for K in (1, 2, 3):
        top = []
        for d, v in multi.items():
            v2 = sorted(v, key=lambda r: -r['_score'])
            top += [r['_pnl'] for r in v2[:K]]
        res[f'top{K}_per_cohort'] = stats(top)

    # 组内第一名 vs 组内其余 (多股同日才有区分度)
    firsts, rests = [], []
    for d, v in multi.items():
        v2 = sorted(v, key=lambda r: -r['_score'])
        firsts.append(v2[0]['_pnl'])
        rests += [r['_pnl'] for r in v2[1:]]
    res['cohort_first'] = stats(firsts)
    res['cohort_rest'] = stats(rests)

    # 分时代稳定性
    for era, lo, hi in (('2023-2025', '202301', '202512'), ('2026_样本外', '202601', '202699')):
        e_rows = [r for r in rows if lo <= str(r['entry_date'])[:6] <= hi]
        e_multi = {d: v for d, v in collections.defaultdict(list, {
            d: [r for r in e_rows if str(r['entry_date']) == d] for d in {str(r['entry_date']) for r in e_rows}
        }).items() if len(v) >= 2}
        firsts, rests, top2 = [], [], []
        for d, v in e_multi.items():
            v2 = sorted(v, key=lambda r: -r['_score'])
            firsts.append(v2[0]['_pnl'])
            rests += [r['_pnl'] for r in v2[1:]]
            top2 += [r['_pnl'] for r in v2[:2]]
        res[era] = {'all': stats([r['_pnl'] for r in e_rows]),
                    'cohort_first': stats(firsts), 'cohort_rest': stats(rests), 'top2': stats(top2)}

    json.dump(res, open(ROOT / 'research/handover/_r145_ranking.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    lg = open(ROOT / 'research/handover/_r145_ranking.txt', 'w', encoding='utf-8')
    lg.write(f"=== R145 位置评分排序 (选股向) — {len(rows)} 腿, 事件日组≥2股: {res['cohorts_ge2']} 组 ===\n")
    lg.write(f"全池: {res['all']}\n")
    for k in ('top1_per_cohort', 'top2_per_cohort', 'top3_per_cohort', 'cohort_first', 'cohort_rest'):
        lg.write(f"  {k:18s} {res.get(k)}\n")
    for era in ('2023-2025', '2026_样本外'):
        e = res[era]
        lg.write(f"[{era}] all {e['all']} | first {e['cohort_first']} | rest {e['cohort_rest']} | top2 {e['top2']}\n")
    lg.write('评分口径: day_pos + clip(near_high,0,20) + gap强承接±15 (全因果)\n')
    lg.close()


if __name__ == '__main__':
    main()
