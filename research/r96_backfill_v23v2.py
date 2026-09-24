# -*- coding: utf-8 -*-
"""R96 补账: paper_ledger.json 全量订单回填 v23_v2 权重 (R94 狠打 formula, 不覆盖, 但加字段)"""
import json, os, shutil, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = r'E:\test\smc_project'
sys.path.insert(0, os.path.join(ROOT, 'research'))

lg = json.load(open(ROOT + '/research/paper_ledger.json', encoding='utf-8'))
# 备份
shutil.copy(ROOT + '/research/paper_ledger.json', ROOT + '/research/paper_ledger.bak_r96.json')

import paper_sim
done, skip, failed = 0, 0, 0
done1, skip1 = 0, 0
for o in lg:
    if not isinstance(o, dict) or not o.get('code') or not o.get('signal_date'):
        skip += 1
        continue
    if not o.get('v23'):  # R99: 补 v1 影子 (原 R96 只补了 v2)
        try:
            r1 = paper_sim._v23_of(o, {})
            if r1:
                o['v23'] = r1
                done1 += 1
            else:
                skip1 += 1
        except Exception:
            skip1 += 1
    if o.get('v23_v2'):
        skip += 1
        continue
    try:
        r = paper_sim._v23v2_of(o)
        if r:
            o['v23_v2'] = r
            done += 1
        else:
            failed += 1
    except Exception:
        failed += 1
json.dump(lg, open(ROOT + '/research/paper_ledger.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'回填 v1(v23): {done1} / 跳过(已有) {skip1}')
print(f'回填 v23_v2: {done} / 跳过 {skip} / 失败 {failed} / 合计 {len(lg)}')

# 汇总带 v23 vs v23_v2 的两路
both = [o for o in lg if o.get('v23') and o.get('v23_v2')]
n = len(both)
low_v1 = sum(1 for o in both if o['v23']['weight'] < 0.7)
low_v2 = sum(1 for o in both if o['v23_v2']['weight'] < 0.7)
print(f'\n同时双标: {n}')
print(f'  v1 w<0.7: {low_v1} ({low_v1/max(1,n)*100:.0f}%)')
print(f'  v2 w<0.7: {low_v2} ({low_v2/max(1,n)*100:.0f}%)')
# 分歧: v1 高位但 v2 狠降 = v2想剔除的单
anti_v2 = [(o['code'], o['signal_date'], o['v23']['weight'], o['v23_v2']['weight'])
           for o in both if o['v23']['weight'] >= 0.7 and o['v23_v2']['weight'] < 0.5]
anti_v1 = [(o['code'], o['signal_date'], o['v23']['weight'], o['v23_v2']['weight'])
           for o in both if o['v23']['weight'] < 0.7 and o['v23_v2']['weight'] >= 0.7]
print(f'v1高v2狠(分歧): {len(anti_v2)}')
for r in anti_v2[:6]:
    print('   ', r)
print(f'v1狠v2高(opposite): {len(anti_v1)}')
for r in anti_v1[:6]:
    print('   ', r)
