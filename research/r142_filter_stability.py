# -*- coding: utf-8 -*-
"""R142: G1/G123 稳定性 + 显著性检验 — 晋级前最后一块证据。

R139/R140 给出了位置过滤器的分层证据 (G1 弱收盘 PF 1.58 vs 留存 6.83), 但晋级决策
还差两个问题: ①这个模式是否跨月稳定 (还是被某几个月撑起来的)? ②bootstrap 下
"留存优于基线"的概率多大? 本轮补齐:

  1) 月度稳定性: 逐月比较 留存avg vs 被剔avg, 统计"被剔更差"的月占比。
  2) 年度切分: 2023-2025 (证据构造期) vs 2026 (样本外) 分别算 kept/dropped。
  3) Bootstrap 2000 次: 有放回抽样, 每次在样本内重算 kept/baseline 均值差与 PF 差,
     报 P(diff>0) — R132 同款口径。

输出: research/handover/_r142_stability.json / _r142_stability.txt
"""
import csv, json, random
import collections
from pathlib import Path

ROOT = Path(r'E:\test\smc_project')
random.seed(42)


def stats(ps):
    if not ps:
        return {'n': 0}
    gp = sum(x for x in ps if x > 0)
    gl = -sum(x for x in ps if x < 0)
    return {'n': len(ps), 'avg': round(sum(ps) / len(ps), 2),
            'wr': round(sum(1 for x in ps if x > 0) / len(ps) * 100, 1),
            'pf': round(gp / gl, 2) if gl > 0 else 99}


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v25_entry_location.csv', encoding='utf-8-sig')))

    def feats(r):
        try:
            dp = float(r.get('day_pos') or 0)
            l20 = float(r.get('loc20') or 0)
        except Exception:
            return None
        nhv = r.get('near_high')
        nh = float(nhv) if nhv not in (None, '') else None
        return dp, l20, nh

    flt = {
        'G1_weakday': lambda f: f[0] < 40,
        'G2_underhigh': lambda f: f[2] is not None and -2 <= f[2] <= 2,
        'G3_botdec': lambda f: f[1] <= 10,
        'G123': lambda f: (f[0] < 40) or (f[2] is not None and -2 <= f[2] <= 2) or (f[1] <= 10),
    }

    out = {}
    for name, pred in flt.items():
        kept = [float(r['net_pnl_pct']) for r in rows if r.get('day_pos') and not pred(feats(r))]
        drop = [float(r['net_pnl_pct']) for r in rows if r.get('day_pos') and pred(feats(r))]
        # 1) 月度稳定性
        mo = collections.defaultdict(lambda: ([], []))
        for r in rows:
            if not r.get('day_pos'):
                continue
            f = feats(r)
            p = float(r['net_pnl_pct'])
            k, d = mo[str(r['entry_date'])[:6]]
            (d if pred(f) else k).append(p)
        win = sum(1 for k, d in mo.values() if k and d and (sum(d) / len(d)) < (sum(k) / len(k)))
        valid = sum(1 for k, d in mo.values() if k and d)
        # 2) 年度切分
        era = {}
        for era_name, lo, hi in (('2023-2025', '202301', '202512'), ('2026_样本外', '202601', '202699')):
            rk = [float(r['net_pnl_pct']) for r in rows if r.get('day_pos') and not pred(feats(r))
                  and lo <= str(r['entry_date'])[:6] <= hi]
            rd = [float(r['net_pnl_pct']) for r in rows if r.get('day_pos') and pred(feats(r))
                  and lo <= str(r['entry_date'])[:6] <= hi]
            era[era_name] = {'kept': stats(rk), 'dropped': stats(rd)}
        # 3) bootstrap 2000
        idx_all = [i for i, r in enumerate(rows) if r.get('day_pos')]
        isdrop = [pred(feats(r)) for r in rows]
        pnl = [float(r['net_pnl_pct']) for r in rows]
        db, dpf = [], []
        for _ in range(2000):
            smp = [idx_all[random.randrange(len(idx_all))] for _ in idx_all]
            ka = [pnl[i] for i in smp if not isdrop[i]]
            ba = [pnl[i] for i in smp]
            if not ka or not ba:
                continue
            db.append(sum(ka) / len(ka) - sum(ba) / len(ba))
            gk = sum(x for x in ka if x > 0); lk = -sum(x for x in ka if x < 0)
            gb = sum(x for x in ba if x > 0); lb = -sum(x for x in ba if x < 0)
            pfk = gk / lk if lk > 0 else 99
            pfb = gb / lb if lb > 0 else 99
            if pfk < 90 and pfb < 90:
                dpf.append(pfk - pfb)
        out[name] = {'kept': stats(kept), 'dropped': stats(drop),
                     'monthly_consistency': f'{win}/{valid}',
                     'by_era': era,
                     'bootstrap_P_avg_gt_base': round(sum(1 for x in db if x > 0) / max(1, len(db)), 3),
                     'bootstrap_P_pf_gt_base': round(sum(1 for x in dpf if x > 0) / max(1, len(dpf)), 3)}

    json.dump(out, open(ROOT / 'research/handover/_r142_stability.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    lg = open(ROOT / 'research/handover/_r142_stability.txt', 'w', encoding='utf-8')
    lg.write('=== R142 稳定性+显著性 (1510腿, bootstrap 2000x, seed42) ===\n')
    for name, v in out.items():
        lg.write(f"\n[{name}] kept {v['kept']} | dropped {v['dropped']}\n")
        lg.write(f"  月度一致性(被剔更差): {v['monthly_consistency']}\n")
        for en, ev in v['by_era'].items():
            lg.write(f"  {en}: kept {ev['kept']} | dropped {ev['dropped']}\n")
        lg.write(f"  bootstrap P(avg_kept>avg_base)={v['bootstrap_P_avg_gt_base']}  P(pf_kept>pf_base)={v['bootstrap_P_pf_gt_base']}\n")
    lg.close()


if __name__ == '__main__':
    main()
