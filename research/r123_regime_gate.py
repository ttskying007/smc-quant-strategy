# -*- coding: utf-8 -*-
"""R123: s22/s23 regime 门控回测 — 找让狠打稳定打对的 regime 划分。

背景 (R122 发现): s23 ×0.15 按年翻转符号 (2024 PF 4.59 打错 / 2026 PF 0.13 打对)。
假设: 狠打只在特定 regime 下成立。

测试变体 (对 s22/s23 桶逐腿):
  基线     — 无门控 (现状)
  门控A    — 仅市场弱 (m20 < -2) 时狠打
  门控B    — 仅市场强 (m20 >= -2) 时狠打
  门控C    — 仅个股趋势反向时狠打 (s23 要求 tr!=up, s22 要求 tr!=down)
  门控D    — 仅市场弱 且 个股趋势不反向

对每变体按年算桶 PF + 全样本 PF; 找 PF 全年 <1 的门控 = 狠打稳定打对。
输出: research/handover/_r123_regime_gate.json
"""
import csv, json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(r'E:\test\smc_project')
IDX = json.load(open(ROOT / 'research/idx_sh000001.json', encoding='utf-8'))


def m20_of(d8):
    d = str(d8).replace('-', '')
    j = -1
    for i in range(len(IDX) - 1, -1, -1):
        if str(IDX[i]['t']) <= d:
            j = i
            break
    if j < 20:
        return None
    return (float(IDX[j]['c']) / float(IDX[j - 20]['c']) - 1) * 100


def pf_of(ps):
    if not ps:
        return None
    gp = sum(x for x in ps if x > 0)
    gl = -sum(x for x in ps if x < 0)
    return (gp / gl) if gl > 0 else 99.0


def main():
    sh3 = {r['symbol'] + '|' + r['entry_date']: r
           for r in csv.DictReader(open(ROOT / 'research/combo_v23_shadow_v3.csv', encoding='utf-8-sig'))}
    trades = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))

    legs = []  # (tag, year, pnl, m20, tr)
    for r in trades:
        key = r['symbol'] + '|' + r['entry_date']
        fls = ((sh3.get(key) or {}).get('v23_flags_v2') or '').split(';')
        tag = 's22' if 's22' in fls else ('s23' if 's23' in fls else None)
        if not tag:
            continue
        pnl = float(r['net_pnl_pct'])
        tr = r.get('trend_state') or ''
        m20 = m20_of(r['entry_date'])
        legs.append({'tag': tag, 'year': str(r['entry_date'])[:4], 'pnl': pnl,
                     'm20': m20, 'tr': tr, 'date': r['entry_date']})

    print(f's22/s23 桶总腿: {len(legs)} (s22={sum(1 for l in legs if l["tag"]=="s22")} s23={sum(1 for l in legs if l["tag"]=="s23")})')

    variants = {
        '基线(无门控)': lambda l: True,
        '门控A_市场弱': lambda l: l['m20'] is not None and l['m20'] < -2,
        '门控B_市场强': lambda l: l['m20'] is not None and l['m20'] >= -2,
        '门控C_个股反向': lambda l: (l['tag'] == 's23' and l['tr'] != 'up') or (l['tag'] == 's22' and l['tr'] != 'down'),
        '门控D_弱+反向': lambda l: (l['m20'] is not None and l['m20'] < -2)
                                   and ((l['tag'] == 's23' and l['tr'] != 'up') or (l['tag'] == 's22' and l['tr'] != 'down')),
        '门控E_市场弱或个股反向': lambda l: (l['m20'] is not None and l['m20'] < -2)
                                           or ((l['tag'] == 's23' and l['tr'] != 'up') or (l['tag'] == 's22' and l['tr'] != 'down')),
    }

    print(f"\n{'变体':<14} | {'适用n':>5} | {'全样本PF':>7} | " + ' | '.join(f'{y}PF' for y in ('2023', '2024', '2025', '2026')))
    jout = {}
    for name, gate in variants.items():
        sel = [l for l in legs if gate(l)]
        pfs = {}
        row = f"{name:<14} | {len(sel):>5} | {pf_of([l['pnl'] for l in sel]) or 0:>7.2f} | "
        for y in ('2023', '2024', '2025', '2026'):
            p = pf_of([l['pnl'] for l in sel if l['year'] == y])
            pfs[y] = round(p, 2) if p is not None else None
            row += f" | {(f'{p:.2f}' if p is not None else '-'):>5}"
        all_below1 = all(p is not None and p < 1 for p in pfs.values() if p is not None) and len(sel) >= 10
        print(row + ('   ← 全年<1 ✓' if all_below1 else ''))
        jout[name] = {'n': len(sel), 'pf_all': round(pf_of([l['pnl'] for l in sel]) or 0, 2), 'yearly': pfs}

    json.dump(jout, open(ROOT / 'research/handover/_r123_regime_gate.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n判读: "全年<1" 的门控 = 狠打在该 regime 下稳定打对; 无门控达标则维持现状。')


if __name__ == '__main__':
    main()
