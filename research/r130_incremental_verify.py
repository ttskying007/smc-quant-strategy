# -*- coding: utf-8 -*-
"""R130: 增量反向 setup 验证 — 引擎未覆盖的候选逐个核对。

方法: combo_reverse_candidates.csv − r126 overlap → 增量集;
  对每条增量候选用 fresh kline 重算:
  - 池价 (auto pivot 0.8% 聚类, 扫日之前)
  - sweep 日 (首次影线触及) / retest 日 (二测反弹)
  - 10 bar 反向收益 (方向修正)
  与 r125 记录对比 (容差 <0.01 视为一致)。
输出: research/handover/_r130_incremental_verify.json
"""
import csv, json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from core.structure import is_swing_high, is_swing_low, pick_pivot_by_density

ROOT = Path(r'E:\test\smc_project')
KLINE = ROOT / 'hermes/kline_cache_tencent'
N_RETEST, N_FUND = 20, 10


def load_klines(sym):
    sf = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    fp = KLINE / (sf + '_daily_800.json')
    if not fp.exists():
        return None
    d = json.load(open(fp, encoding='utf-8'))
    raw = d if isinstance(d, list) else (d.get('klines') or d.get('bars') or [])
    return [{'t': str(k.get('t', k.get('date', '')))[:10].replace('-', ''),
             'h': float(k.get('h', k.get('high', 0))), 'l': float(k.get('l', k.get('low', 0))),
             'c': float(k.get('c', k.get('close', 0)))} for k in raw]


def recompute(ks, side, pool_hint, sweep_hint):
    """对已知 (side, 扫日) 重算池价/二测日/收益 — 因果安全。"""
    si = next((i for i, k in enumerate(ks) if k['t'] == sweep_hint), None)
    if si is None:
        return None
    # 池价: 扫日前的 auto pivot 聚类中找接近 hint 的池
    pv, _ = pick_pivot_by_density(ks, si)
    cut = si - 250
    pivs = ([(j, ks[j]['h']) for j in range(pv, si - pv + 1) if is_swing_high(ks, j, pv)]
            if side == 'EQH' else
            [(j, ks[j]['l']) for j in range(pv, si - pv + 1) if is_swing_low(ks, j, pv)])
    cand = sorted([(j, p) for j, p in pivs if j >= cut], key=lambda x: -x[0])
    used = [False] * len(cand)
    pp = None
    for a in range(len(cand)):
        if used[a]:
            continue
        j1, p1 = cand[a]
        members = [a]
        for b in range(a + 1, len(cand)):
            if abs(cand[b][1] - p1) / p1 <= 0.008:
                members.append(b)
                used[b] = True
        if len(members) >= 2:
            avgp = sum(cand[m][1] for m in members) / len(members)
            if pp is None or abs(avgp - pool_hint) < abs(pp - pool_hint):
                pp = avgp
    if pp is None or abs(pp - pool_hint) / pool_hint > 0.01:
        return {'ok': False, 'reason': f'池价不一致 ({pp} vs {pool_hint})'}
    # 二测: sweep 后 20 bar 内反弹且未先破
    for k in range(si + 1, min(si + N_RETEST, len(ks))):
        broke = (side == 'EQH' and ks[k]['c'] > pp) or (side == 'EQL' and ks[k]['c'] < pp)
        if broke:
            return {'ok': False, 'reason': '先破后未反弹'}
        bounce = (side == 'EQH' and ks[k]['h'] > pp and ks[k]['c'] <= pp) or \
                 (side == 'EQL' and ks[k]['l'] < pp and ks[k]['c'] >= pp)
        if bounce and k + N_FUND < len(ks):
            raw = (ks[k + N_FUND]['c'] / ks[k]['c'] - 1) * 100
            ret = -raw if side == 'EQH' else raw
            return {'ok': True, 'pool': round(pp, 2), 'retest_date': ks[k]['t'],
                    'ret_10b_signed': round(ret, 2)}
    return {'ok': False, 'reason': '无二测'}


def main():
    cands = list(csv.DictReader(open(ROOT / 'research/combo_reverse_candidates.csv', encoding='utf-8-sig')))
    try:
        ov = json.load(open(ROOT / 'research/handover/_r126_overlap.json', encoding='utf-8'))
        ov_keys = {str(r.get('symbol') or '') + '|' + str(r.get('sweep_date') or '').replace('-', '')
                   for r in (ov.get('overlap') or [])}
    except Exception:
        ov_keys = set()
    # R130b: 验证全部候选 (含引擎重叠7个) — 因果性全面核查
    inc = cands
    print(f'=== R130 全部反向 setup 因果验证 (n={len(inc)}) ===')
    jout = []
    for c in inc:
        ks = load_klines(c['symbol'])
        if not ks:
            print(f"  {c['symbol']}: 无K线")
            continue
        rc = recompute(ks, c['side'], float(c['pool_price']),
                       str(c['sweep_date']).replace('-', ''))
        if rc and rc.get('ok'):
            agree = abs(rc['ret_10b_signed'] - float(c['ret_10b_signed'])) < 0.01
            print(f"  {c['symbol']} {c['side']}: 池 {rc['pool']} (记录 {c['pool_price']}) "
                  f"二测 {rc['retest_date']} 收益 {rc['ret_10b_signed']:+.2f}% "
                  f"(记录 {float(c['ret_10b_signed']):+.2f}%) → {'✓一致' if agree else '✗不一致'}")
            jout.append({'symbol': c['symbol'], 'side': c['side'], 'verify': rc, 'agree': agree})
        else:
            print(f"  {c['symbol']} {c['side']}: ✗ {rc.get('reason') if rc else '重算失败'}")
            jout.append({'symbol': c['symbol'], 'side': c['side'], 'verify': rc, 'agree': False})
    n_ok = sum(1 for x in jout if x['agree'])
    print(f'\n汇总: {n_ok}/{len(jout)} 一致')
    # R130b: 写因果版候选集 (剔除池聚类前视的2个)
    causal = [c for c, x in zip(inc, jout) if x['agree']]
    with open(ROOT / 'research/combo_reverse_candidates_causal.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['symbol', 'side', 'pool_price', 'sweep_date',
                                           'signal_date', 'entry_price', 'ret_10b_signed'])
        w.writeheader()
        w.writerows(causal)
    cavg = [float(c['ret_10b_signed']) for c in causal]
    if cavg:
        print(f"因果集: n={len(causal)} avg={sum(cavg)/len(cavg):+.2f}% "
              f"WR={sum(1 for v in cavg if v>0)/len(cavg)*100:.1f}% → combo_reverse_candidates_causal.csv")
    json.dump({'total': len(inc), 'agree': n_ok, 'causal_n': len(causal), 'detail': jout},
              open(ROOT / 'research/handover/_r130_incremental_verify.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, default=str)
    print('写出 research/handover/_r130_incremental_verify.json')


if __name__ == '__main__':
    main()
