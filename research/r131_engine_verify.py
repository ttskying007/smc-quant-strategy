# -*- coding: utf-8 -*-
"""R131: 引擎级 Sweep_Reclaim_Reject 验证 — detector 新类型 vs 因果候选集。

方法: 对因果候选集 (combo_reverse_candidates_causal.csv, n=18) 的 symbol,
      跑 detect_smc_signals(mode='norm'), 收集 Sweep_Reclaim_Reject 信号,
      对比 (symbol, 信号bar日期) 与候选 (symbol, retest_date)。
判读: 覆盖数 / 漏检数 / 新增数; 覆盖率高 → 引擎接入成功。
输出: research/handover/_r131_engine_verify.json
"""
import csv, json, os, sys
import importlib.util as ilu
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
ROOT = Path(r'E:\test\smc_project')
KT = ROOT / 'hermes/kline_cache_tencent'


def load_klines(sym, upto=None):
    sf = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    fp = KT / (sf + '_daily_800.json')
    if not fp.exists():
        return None
    d = json.load(open(fp, encoding='utf-8'))
    raw = d if isinstance(d, list) else (d.get('klines') or d.get('bars') or [])
    bars = [{'t': str(k.get('t', k.get('date', '')))[:10].replace('-', ''),
             'o': float(k.get('o', k.get('open', 0))),
             'h': float(k.get('h', k.get('high', 0))), 'l': float(k.get('l', k.get('low', 0))),
             'c': float(k.get('c', k.get('close', 0))), 'v': float(k.get('v', 0))} for k in raw]
    if upto:
        bars = [b for b in bars if b['t'] <= upto]
    return bars


def main():
    cands = list(csv.DictReader(open(ROOT / 'research/combo_reverse_candidates_causal.csv', encoding='utf-8-sig')))
    spec = ilu.spec_from_file_location('smc_detector', ROOT / 'hermes/scripts/v25/smc_detector.py')
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    covered, missed = [], 0
    all_engine_rr = []
    for c in cands:
        rd = str(c['signal_date']).replace('-', '')  # retest/信号日
        bars = load_klines(c['symbol'])
        if not bars or len(bars) < 30:
            missed += 1
            continue
        try:
            sigs = mod.detect_smc_signals(bars, mode='norm')
        except Exception as e:
            print(f"  {c['symbol']}: detector 异常 {e}")
            missed += 1
            continue
        rr = [s for s in sigs if s.type == 'Reclaim_Reject']
        all_engine_rr.extend((c['symbol'], bars[s.bar]['t'], s.dir, s.meta.get('pool_price')) for s in rr)
        hit = any(bars[s.bar]['t'] == rd for s in rr if s.bar < len(bars))
        if hit:
            covered.append(c)
        else:
            missed += 1
            eng_dates = [bars[s.bar]['t'] for s in rr if s.bar < len(bars)]
            print(f"  漏检: {c['symbol']} {c['side']} 候选信号日 {rd} | 引擎RR日期 {eng_dates[:3]}")

    print(f'=== R131 引擎级 Sweep_Reclaim_Reject 验证 ===')
    print(f'因果候选: {len(cands)} | 引擎覆盖: {len(covered)} | 漏检: {missed}')
    print(f'引擎 RR 信号总数 (18股): {len(all_engine_rr)}')
    # 候选外的引擎新增 RR 信号 (引擎比 r125 多发现的)
    cand_keys = {c['symbol'] + '|' + str(c['signal_date']).replace('-', '') for c in cands}
    extra = [(sy, d, dr) for (sy, d, dr, p) in all_engine_rr
             if (sy + '|' + d) not in cand_keys]
    print(f'候选外新增: {len(extra)}')
    for x in extra[:6]:
        print(f'  新增: {x[0]} {x[2]} @ {x[1]}')
    # R131b: 引擎新增 RR 的远期收益 (方向修正: bear→空取负, bull→多取正)
    fwd = []
    for (sy, d, dr) in extra:
        ks = load_klines(sy)
        if not ks:
            continue
        ri = next((i for i, k in enumerate(ks) if k['t'] == d), None)
        if ri is None or ri + 10 >= len(ks):
            continue
        raw = (ks[ri + 10]['c'] / ks[ri]['c'] - 1) * 100
        fwd.append({'sym': sy, 'dir': dr, 'date': d,
                    'ret_10b_signed': round(-raw if dr == 'bear' else raw, 2)})
    if fwd:
        rets = [x['ret_10b_signed'] for x in fwd]
        gp = sum(x for x in rets if x > 0)
        gl = -sum(x for x in rets if x < 0)
        print(f"新增 RR 远期收益: n={len(fwd)} avg={sum(rets)/len(rets):+.2f}% "
              f"WR={sum(1 for v in rets if v>0)/len(fwd)*100:.1f}% "
              f"PF={(gp/gl) if gl>0 else 99:.2f}")
    json.dump({'causal_n': len(cands), 'covered_n': len(covered), 'missed_n': missed,
               'engine_rr_total': len(all_engine_rr), 'extra_n': len(extra),
               'extra': extra[:20], 'covered': covered},
              open(ROOT / 'research/handover/_r131_engine_verify.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, default=str)
    print('写出 research/handover/_r131_engine_verify.json')


if __name__ == '__main__':
    main()
