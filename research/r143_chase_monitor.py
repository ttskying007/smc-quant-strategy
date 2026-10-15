# -*- coding: utf-8 -*-
"""R143: S2_NO_PULLBACK 追击桶深挖 + 影子旗逐月监控器。

两个职责:
  A) R138 三步链判定出的 S2_NO_PULLBACK (破位后未回撤就追, 97腿 PF0.99) 是用户
     ②步骤直接命中的唯一死桶 — R140 同款检验: 月度一致性 / 年度切分 / bootstrap,
     以及"可抢救子集"分析: 桶内赢家是否集中在某个位置特征组合 (如强收盘)?
     若追击+强收盘可活, 则 G1/G2 过滤已覆盖, 无需单独规则; 若桶内无救, 则 s28_chase
     是下一个晋级候选。
  B) 影子旗监控器: 对 combo_v23_shadow_v3.csv 的 s26/s27/s28 全部旗, 逐月输出
     带旗/无旗 PnL 对比 — 10-23 v24 评审一条命令出报告 (r106 之后的仪式补充)。

输出: research/handover/_r143_chase_monitor.json / .txt
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
    seq = list(csv.DictReader(open(ROOT / 'research/combo_v25_entry_sequence.csv', encoding='utf-8-sig')))
    loc = {r['symbol'] + '|' + r['entry_date']: r
           for r in csv.DictReader(open(ROOT / 'research/combo_v25_entry_location.csv', encoding='utf-8-sig'))}
    chase = [r for r in seq if r.get('verdict') == 'S2_NO_PULLBACK']
    base = [r for r in seq if r.get('verdict')]

    out = {'chase_bucket': {}, 'rescue': {}, 'monitor': {}}

    # --- A) 追击桶检验 ---
    cp = [float(r['net_pnl_pct']) for r in chase]
    bp = [float(r['net_pnl_pct']) for r in base]
    out['chase_bucket'] = {'chase': stats(cp), 'baseline_seq': stats(bp)}

    mo = collections.defaultdict(lambda: ([], []))
    for r in base:
        p = float(r['net_pnl_pct'])
        k, d = mo[str(r['entry_date'])[:6]]
        (d if r.get('verdict') == 'S2_NO_PULLBACK' else k).append(p)
    win = sum(1 for k, d in mo.values() if k and d and (sum(d) / len(d)) < (sum(k) / len(k)))
    valid = sum(1 for k, d in mo.values() if k and d)
    out['chase_bucket']['monthly_consistency'] = f'{win}/{valid}'

    isd = [r.get('verdict') == 'S2_NO_PULLBACK' for r in base]
    db = []
    for _ in range(2000):
        smp = [random.randrange(len(base)) for _ in base]
        ka = [float(base[i]['net_pnl_pct']) for i in smp if not isd[i]]
        da = [float(base[i]['net_pnl_pct']) for i in smp if isd[i]]
        if ka and da:
            db.append(sum(ka) / len(ka) - sum(da) / len(da))
    out['chase_bucket']['bootstrap_P_kept_gt_chase'] = round(sum(1 for x in db if x > 0) / max(1, len(db)), 3)

    # 可抢救子集: 追击桶 × 位置特征 (day_pos / near_high)
    res = {}
    for name, pred in (
        ('chase_x_weakday', lambda l: l and float(l.get('day_pos') or 0) < 40),
        ('chase_x_strongday', lambda l: l and float(l.get('day_pos') or 0) >= 70),
        ('chase_x_underhigh', lambda l: l is not None and l.get('near_high') not in (None, '')
         and -2 <= float(l.get('near_high')) <= 2),
        ('chase_x_clearsky', lambda l: l is not None and l.get('near_high') not in (None, '')
         and float(l.get('near_high')) > 5),
    ):
        sel = [float(r['net_pnl_pct']) for r in chase if pred(loc.get(r['symbol'] + '|' + r['entry_date']))]
        res[name] = stats(sel)
    out['rescue'] = res

    # --- B) 影子旗监控器 (s26/s27/s28) ---
    sh = list(csv.DictReader(open(ROOT / 'research/combo_v23_shadow_v3.csv', encoding='utf-8-sig')))
    flags_all = ['s26_newlow', 's26_nohb', 's26_nopoi', 's26_noretrace',
                 's27_weakday', 's27_underhigh', 's27_botdec',
                 's28_chase', 's28_notpoi', 's28_pbbroke', 's28_all_ok']
    mon = {}
    for fl in flags_all:
        withf, nof = [], []
        for r in sh:
            p = float(r.get('net_pnl_pct') or 0)
            if fl in (r.get('v23_flags_v2') or ''):
                withf.append(p)
            else:
                nof.append(p)
        if withf:
            mon[fl] = {'with_flag': stats(withf), 'without': stats(nof)}
    out['monitor'] = mon

    json.dump(out, open(ROOT / 'research/handover/_r143_chase_monitor.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    lg = open(ROOT / 'research/handover/_r143_chase_monitor.txt', 'w', encoding='utf-8')
    cb = out['chase_bucket']
    lg.write('=== R143 追击桶(S2_NO_PULLBACK)检验 ===\n')
    lg.write(f"chase {cb['chase']} | 序列基线 {cb['baseline_seq']}\n")
    lg.write(f"月度一致性(无旗更差): {cb['monthly_consistency']} | bootstrap P={cb['bootstrap_P_kept_gt_chase']}\n")
    lg.write('[可抢救子集]\n')
    for k, v in res.items():
        lg.write(f'  {k}: {v}\n')
    lg.write('\n=== 影子旗逐月监控器 (s26/s27/s28, v23_shadow_v3 全量) ===\n')
    for fl, v in mon.items():
        lg.write(f"  {fl:14s} 带旗 {v['with_flag']} | 无旗 {v['without']}\n")
    lg.write('监控器用法: 每次评审跑 r143_chase_monitor.py 即可 (r106 仪式补充)\n')
    lg.close()


if __name__ == '__main__':
    main()
