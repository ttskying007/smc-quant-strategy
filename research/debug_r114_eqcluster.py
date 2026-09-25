# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, r'E:\test\smc_project\research')
from core.structure import structure_events as _csev, is_swing_high as _cish, is_swing_low as _cisl, pick_pivot_by_density as _cpiv

d = json.load(open(r'E:\test\smc_project\hermes\kline_cache_tencent\000858_SZ_daily_800.json', encoding='utf-8'))
raw = d if isinstance(d, list) else (d.get('klines') or d.get('bars') or [])
klines = raw
# 与 smc_unified 一致: k 用 't' (Ymd) — klines 取自上游缓存原始格式
_cks = [{'t': str(k.get('t', k.get('date', '')))[:10].replace('-', ''), 'o': float(k.get('o', k.get('open', 0))), 'h': float(k.get('h', k.get('high', 0))), 'l': float(k.get('l', k.get('low', 0))), 'c': float(k.get('c', k.get('close', 0))), 'v': float(k.get('v') or k.get('volume') or 0)} for k in klines]
_cn = len(_cks) - 1
_pv, _pvden = _cpiv(_cks, _cn)
_cph = [(j, _cks[j]['h']) for j in range(_pv, len(_cks) - _pv) if _cish(_cks, j, _pv)]
_cpl = [(j, _cks[j]['l']) for j in range(_pv, len(_cks) - _pv) if _cisl(_cks, j, _pv)]

def _eq_cluster(pivs, side, lookback_bars=250, tol_ratio=0.008):
    cut = len(_cks) - lookback_bars
    cand = [(j, p) for j, p in pivs if j >= cut]
    cand.sort(key=lambda x: -x[0])
    used = [False] * len(cand)
    out = []
    for a in range(len(cand)):
        if used[a]: continue
        j1, p1 = cand[a]
        members = [a]
        for b in range(a + 1, len(cand)):
            j2, p2 = cand[b]
            if abs(p2 - p1) / p1 <= tol_ratio:
                members.append(b); used[b] = True
        if len(members) >= 2:
            js = [cand[m][0] for m in members]
            ps = [cand[m][1] for m in members]
            out.append({'t': _cks[min(js)]['t'],
                        't2': _cks[max(js)]['t'],
                        'price': round(sum(ps) / len(ps), 2), 'count': len(members)})
    return out[:3]

_eqh = _eq_cluster(_cph, 'eqh')
_eql = _eq_cluster(_cpl, 'eql')
print('pv', _pv, 'cph', len(_cph), 'cpl', len(_cpl))
print('eqh', _eqh)
print('eql', _eql)
