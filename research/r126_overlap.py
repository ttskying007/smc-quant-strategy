# -*- coding: utf-8 -*-
"""R126: r125 反向候选与 V517 引擎 Sweep 重叠度。

问题: 引擎 (V517 detect_smc_signals) 已在交易多少 sweep→reverse setup?
方法: 对每候选 (symbol, sweep_date), 跑 detector(mode='norm') 收集 Sweep 信号,
      检查是否有 Sweep bar 的日期 == 候选 sweep_date (±2 bar)。
输出: 重叠数 / 独有数 → handover/_r126_overlap.json
"""
import csv, json, os, sys
import importlib.util as ilu

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
ROOT = Path = __import__('pathlib').Path(r'E:\test\smc_project')
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
    cands = list(csv.DictReader(open(ROOT / 'research/combo_reverse_candidates.csv', encoding='utf-8-sig')))
    spec = ilu.spec_from_file_location('smc_detector', ROOT / 'hermes/scripts/v25/smc_detector.py')
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    overlap, unique = [], 0
    for c in cands:
        sd = str(c['sweep_date']).replace('-', '')
        bars = load_klines(c['symbol'], sd)
        if not bars or len(bars) < 30:
            unique += 1
            continue
        try:
            sigs = mod.detect_smc_signals(bars, mode='norm')
        except Exception:
            unique += 1
            continue
        n10 = len(bars) - 12
        hit = False
        for s in sigs:
            if 'Sweep' not in s.type or s.bar < n10:
                continue
            bd = bars[s.bar]['t'] if s.bar < len(bars) else ''
            d1 = bars[s.bar - 1]['t'] if s.bar >= 1 else ''
            if sd in (bd, d1, bars[min(s.bar + 1, len(bars) - 1)]['t']):
                hit = True
                break
        if hit:
            overlap.append(c)
        else:
            unique += 1

    print(f'=== R126 r125 候选 × V517 引擎 Sweep 重叠 ===')
    print(f'候选总数: {len(cands)} | 引擎已覆盖: {len(overlap)} | 引擎未覆盖(增量): {unique}')
    for c in overlap[:8]:
        print(f"  重叠: {c['symbol']} {c['side']} sweep={c['sweep_date']} ret={c['ret_10b_signed']}%")
    json.dump({'total': len(cands), 'overlap_n': len(overlap), 'unique_n': unique,
               'overlap': overlap[:20]},
              open(ROOT / 'research/handover/_r126_overlap.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, default=str)
    print('写出 research/handover/_r126_overlap.json')


if __name__ == '__main__':
    main()
