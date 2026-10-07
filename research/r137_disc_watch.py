# -*- coding: utf-8 -*-
"""R137: 纪律观察名单 (前向化 R134 状态机, 记录-only 影子工具)。

背景: R134 证明"破前高→回踩POI→入场"的严格纪律在历史回测中被证伪(公告次日动量才是
alpha), 但用户想要"按纪律等"的可观察工具 — 回答"现在哪些票正在等破前高/等回踩"。

本脚本(新增, 不动任何既有产物):
  事件池: combo_v22_trades.csv 中信号日距今 ≤120 bar 的事件 (近期公告动量)
  状态机: 复用 r134_disciplined_entry 的 pivot/POI 口径, 只在"最后一根 bar"截断:
    - WAIT_BREAK : 未破前高, 等待中 (附当前最近确认摆动高 L 与其日期)
    - WAIT_RETEST: 已破前高, 等回踩 (附破位日/位 + POI 三候选描述)
    - READY      : 回踩到位, 下一 bar 即为纪律入场候选 (附 POI 类型/回踩日)
    - DROPPED    : 链已失败 (原因: 回踩穿位/超时/结构性新低无新高), 附原因
  输出: research/combo_v24_disc_watch.csv + handover/_r137_disc_watch.json
"""
import csv, json, sys, io
from pathlib import Path

ROOT = Path(r'E:\test\smc_project')
sys.path.insert(0, str(ROOT / 'research'))

from r134_disciplined_entry import (load_bars, _last_conf_sh, _ob_of_break,
                                    _fvgs_in_impulse, PIVOT, POI_TOL)

MAX_EVENT_AGE = 120   # 只观察近 120 bar 内的事件


def watch_state(bs, sig_i):
    """前向状态机: 以最后一根 bar 为'现在', 返回当前纪律阶段。"""
    n = len(bs)
    broke = False
    b_bar = sh = None
    for j in range(sig_i, n):
        _j, sh0 = _last_conf_sh(bs, j)
        if sh0 is None:
            continue
        if bs[j]['c'] > sh0:
            broke, b_bar, sh = True, j, sh0
            break
    last_close = bs[n - 1]['c']
    if not broke:
        _j2, sh2 = _last_conf_sh(bs, n - 1)
        if n - 1 - sig_i > 60:
            return {'stage': 'DROPPED', 'drop': 'no_high_break_60bar', 'last_close': last_close}
        return {'stage': 'WAIT_BREAK', 'wait_bars': n - 1 - sig_i,
                'level': sh2, 'level_date': bs[_j2]['t'] if _j2 is not None else None,
                'gap_pct': round((sh2 / last_close - 1) * 100, 1) if sh2 else None,
                'last_close': last_close}
    L = sh
    ob = _ob_of_break(bs, b_bar)
    fvgs = _fvgs_in_impulse(bs, max(sig_i, b_bar - 15), b_bar)
    for k in range(b_bar + 1, n):
        lo, cl = bs[k]['l'], bs[k]['c']
        if cl < L * (1 - POI_TOL):
            return {'stage': 'DROPPED', 'drop': 'retrace_fail_close_below_L',
                    'break_date': bs[b_bar]['t'], 'break_level': L, 'last_close': last_close}
        hit = None
        if ob and lo <= ob[1] * (1 + POI_TOL):
            hit = ('OB', ob[0], ob[1])
        if hit is None:
            for (fl, fh) in fvgs:
                if fl * (1 - POI_TOL) <= lo <= fh * (1 + POI_TOL) or (fl <= lo <= fh):
                    hit = ('FVG', fl, fh)
                    break
        if hit is None and lo <= L * (1 + POI_TOL):
            hit = ('LEVEL', L * 0.99, L * (1 + POI_TOL))
        if hit is not None:
            if n - 1 - k <= 5:
                # 回踩刚到位 → 纪律入场候选(下一bar)
                return {'stage': 'READY', 'break_date': bs[b_bar]['t'], 'break_level': L,
                        'retrace_date': bs[k]['t'], 'poi_kind': hit[0],
                        'poi_band': [round(hit[1], 2), round(hit[2], 2)],
                        'since_break': k - b_bar, 'last_close': last_close}
            # 回踩到位已久 → 纪律入场早已发生(研究观测, 不可追)
            ei_t = bs[k + 1]['t'] if k + 1 < n else ''
            return {'stage': 'ENTERED', 'break_date': bs[b_bar]['t'], 'break_level': L,
                    'retrace_date': bs[k]['t'], 'poi_kind': hit[0],
                    'entry_date': ei_t, 'since_retest': n - 1 - k, 'last_close': last_close}
    if n - 1 - b_bar > 20:
        return {'stage': 'DROPPED', 'drop': 'no_retrace_20bar',
                'break_date': bs[b_bar]['t'], 'break_level': L, 'last_close': last_close}
    pois = []
    if ob:
        pois.append('OB %.2f~%.2f' % ob)
    if fvgs:
        pois.append('FVG %.2f~%.2f' % fvgs[-1])
    pois.append('LEVEL %.2f±1%%' % L)
    return {'stage': 'WAIT_RETEST', 'break_date': bs[b_bar]['t'], 'break_level': L,
            'since_break': n - 1 - b_bar, 'poi_desc': ' | '.join(pois),
            'last_close': last_close}


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
    kcache = {}
    out, stage_ct = [], {}
    last_t = None
    for r in rows:
        sym = r['symbol']
        if sym not in kcache:
            kcache[sym] = load_bars(sym)
        bs = kcache[sym]
        if not bs:
            continue
        if last_t is None or bs[-1]['t'] > last_t:
            last_t = bs[-1]['t']
        dmap = {b['t']: ix for ix, b in enumerate(bs)}
        sd = str(r.get('entry_date', '')).replace('-', '')
        sig_i = dmap.get(sd)
        if sig_i is None:
            continue
        if len(bs) - 1 - sig_i > MAX_EVENT_AGE:
            continue
        st = watch_state(bs, sig_i)
        stage_ct[st['stage']] = stage_ct.get(st['stage'], 0) + 1
        out.append({'symbol': sym, 'event_date': sd, 'stage': st['stage'],
                    'drop': st.get('drop', ''),
                    'wait_bars': st.get('wait_bars', ''),
                    'level': st.get('level', ''), 'level_date': st.get('level_date', ''),
                    'gap_pct': st.get('gap_pct', ''),
                    'break_date': st.get('break_date', ''), 'break_level': st.get('break_level', ''),
                    'retrace_date': st.get('retrace_date', ''), 'poi_kind': st.get('poi_kind', ''),
                    'poi_desc': st.get('poi_desc', ''),
                    'since_break': st.get('since_break', ''),
                    'last_close': st.get('last_close', '')})

    fn = ROOT / 'research/combo_v24_disc_watch.csv'
    with open(fn, 'w', newline='', encoding='utf-8-sig') as f:
        if out:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
    ready = [o for o in out if o['stage'] == 'READY']
    summ = {'asof': last_t, 'event_pool': len(out), 'stage_counts': stage_ct, 'ready_n': len(ready)}
    fro = open(ROOT / 'research/handover/_r137_disc_watch.txt', 'w', encoding='utf-8')
    json.dump(summ, open(ROOT / 'research/handover/_r137_disc_watch.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    fro.write(f"asof={last_t} 事件池(近{MAX_EVENT_AGE}bar)={len(out)}\n")
    fro.write('阶段分布: ' + str(stage_ct) + '\n')
    for o in ready[:10]:
        fro.write(f"  READY {o['symbol']} 事件{o['event_date']} 破{o['break_date']}@{o['break_level']} 踩{o['poi_kind']} {o['retrace_date']} 现价{o['last_close']}\n")
    fro.write('写出 combo_v24_disc_watch.csv + _r137_disc_watch.json\n')
    fro.close()


if __name__ == '__main__':
    main()
