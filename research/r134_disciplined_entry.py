# -*- coding: utf-8 -*-
"""R134: 纪律版入场引擎 (v23-discipline, 研究轨道) — 破前高→回踩POI→入场。

背景: R133 诊断 — v22 腿 64% 未破前高进场 / 85% 未回踩 POI / 4% 20bar新低进场;
全合规仅 5%。根因: v20f2→v22 入场 = 公告次日 close×0.99 限价单, 与结构确认脱钩。

本引擎(新增, 不动任何既有脚本/产物):
  观察触发: 复用 v22 legs 的事件 (symbol+entry_date=信号日), 保证与冻结基线同池可比
  入场纪律(自信号日起 60 bar 窗口内, 逐 bar 因果):
    1. 破前高: 收盘 > 最近已确认摆动高 (pivot=3, 确认口径 j+3<=当前bar)
               → 记录突破 bar b 与突破水平 L
    2. 回踩 POI (突破后 ≤20 bar 内): 逐 bar 检查回踩进 POI——
         POI = 突破事件的 OB demand 箱 | 突破段产生的 bull FVG | 突破水平 L ±1%
         进场 bar k: bs[k].l 进入 POI 带 且 bs[k].c 仍在 L 上方(未回踩穿)
    3. 入场: 若下个 bar 未高开超过 L+3% 则以 POI 带中位限价, 否则放弃
    4. 超时(信号日+60 bar 未完成) → 放弃该事件
    5. 期间出现新 BOS↓(收盘跌破最后已确认摆动低) → 放弃 (结构继续走坏)
  出场: 完全冻结 (R71) — core.execution.simulate, 入场bar处重算 TP(摆动高)/SL(摆动低-0.5ATR)

对比输出: research/combo_v23_disciplined_entry.csv + handover/_r134_disciplined_entry.json
"""
import csv, json, sys, io, os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')
sys.path.insert(0, str(ROOT / 'research'))
KT = ROOT / 'hermes/kline_cache_tencent'

WAIT_BARS = 60      # 破前高等候窗
RETEST_BARS = 20    # 回踩 POI 等候窗
PIVOT = 3
POI_TOL = 0.01      # 突破水平带 ±1%


def load_bars(sym):
    sf = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    fp = KT / (sf + '_daily_800.json')
    if not fp.exists():
        return None
    d = json.load(open(fp, encoding='utf-8'))
    raw = d if isinstance(d, list) else (d.get('klines') or d.get('bars') or [])
    if not raw or 'h' not in raw[0]:
        if raw:
            raw = [{'t': str(b.get('t', b.get('date', '')))[:10].replace('-', ''),
                    'o': float(b.get('open', 0)), 'h': float(b.get('high', 0)),
                    'l': float(b.get('low', 0)), 'c': float(b.get('close', 0)),
                    'v': float(b.get('v', b.get('volume', 0)))} for b in raw]
        else:
            return None
    return [{'t': str(b.get('t', ''))[:10].replace('-', ''), 'o': float(b['o']),
             'h': float(b['h']), 'l': float(b['l']), 'c': float(b['c']),
             'v': float(b.get('v', 0))} for b in raw]


def _conf_swing_high(bs, j, pivot=PIVOT):
    """j 处已确认摆动高价(确认口径 j+pivot<=当前bar 由调用者保证), 无则 None"""
    if j < pivot or j + pivot >= len(bs):
        return None
    h = bs[j]['h']
    if all(h >= bs[k]['h'] for k in range(j - pivot, j + pivot + 1)):
        return h
    return None


def _last_conf_sh(bs, i):
    for j in range(i - PIVOT, max(PIVOT, i - 90), -1):
        h = _conf_swing_high(bs, j)
        if h is not None:
            return j, h
    return None, None


def _last_conf_sl(bs, i):
    for j in range(i - PIVOT, max(PIVOT, i - 90), -1):
        if j < PIVOT or j + PIVOT >= len(bs):
            continue
        lo = bs[j]['l']
        if all(lo <= bs[k]['l'] for k in range(j - PIVOT, j + PIVOT + 1)):
            return j, lo
    return None, None


def _ob_of_break(bs, b):
    """突破 bar b 之前 3 根内最后阴线 (OB demand)"""
    for j in range(b - 1, max(b - 4, 0), -1):
        if bs[j]['c'] < bs[j]['o']:
            return bs[j]['l'], bs[j]['h']
    return None


def _fvgs_in_impulse(bs, frm, to):
    """突破段 [frm, to] 内 bull FVG 箱"""
    out = []
    for k in range(max(2, frm), min(to + 1, len(bs))):
        if bs[k]['l'] > bs[k - 2]['h']:
            out.append((bs[k - 2]['h'], bs[k]['l']))
    return out


def _tps_sl_at(bs, i, ep):
    """与 v22 相同口径: TP=90bars内2个摆动高 / SL=最近摆动低-0.5ATR"""
    highs, lows = [], []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        h = bs[j]['h']
        l = bs[j]['l']
        if len(highs) < 2 and h > max(bs[k]['h'] for k in range(j - 3, j)) and h >= max(bs[k]['h'] for k in range(j + 1, j + 4)):
            highs.append(h)
        if len(lows) < 2 and l < min(bs[k]['l'] for k in range(j - 3, j)) and l <= min(bs[k]['l'] for k in range(j + 1, j + 4)):
            lows.append(l)
        if len(highs) >= 2 and len(lows) >= 2:
            break
    if not highs or not lows:
        return None
    highs.sort()
    trs = [max(bs[k]['h'] - bs[k]['l'], abs(bs[k]['h'] - bs[k - 1]['c']), abs(bs[k]['l'] - bs[k - 1]['c']))
           for k in range(max(1, i - 14), i)]
    atr = sum(trs) / 14 if trs else 0
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]
    sl = (lows[0] - 0.5 * atr) if atr > 0 else lows[0] * 0.99
    _tps = sorted(x for x in (tp1, tp2, tp3) if x and x > ep)
    if not _tps:
        return None
    tp1 = _tps[0]
    tp2 = _tps[1] if len(_tps) > 1 else tp1 * 1.05
    tp3 = _tps[2] if len(_tps) > 2 else tp2 * 1.05
    return tp1, tp2, tp3, sl


def disciplined_entry(bs, sig_i):
    """从信号日 sig_i 起执行入场纪律; 返回 dict 或 None(放弃)"""
    n = len(bs)
    broke = False
    b_bar = sh = None
    for j in range(sig_i, min(sig_i + WAIT_BARS, n)):
        # 结构走坏: 收盘跌破最近已确认摆动低 → 放弃
        _j, sl = _last_conf_sl(bs, j)
        if sl is not None and bs[j]['c'] < sl:
            if broke:
                # 破位后跌破 → 链失败
                if j > b_bar:
                    return None
            elif j > sig_i + 2:
                # 观察期就继续跌破新低 → 可以等 (创新低并不放弃, 因为我们在等反转)
                pass
        jj, sh = _last_conf_sh(bs, j)
        if sh is None:
            continue
        if bs[j]['c'] > sh:
            broke = True
            b_bar = j
            L = sh
            break
    if not broke:
        return {'dropped': 'no_high_break_in_window'}
    L = sh
    # POI: OB(突破前最后阴线) + 突破段 bull FVG + 突破水平带
    ob = _ob_of_break(bs, b_bar)
    fvgs = _fvgs_in_impulse(bs, max(sig_i, b_bar - 15), b_bar)
    for k in range(b_bar + 1, min(b_bar + RETEST_BARS + 1, n)):
        lo, cl, hi = bs[k]['l'], bs[k]['c'], bs[k]['h']
        # 回踩穿 (收盘跌破突破水平) → 链失败
        if cl < L * (1 - POI_TOL):
            return {'dropped': 'retrace_fail_close_below_L'}
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
        if hit is None:
            continue
        # 入场: 下 bar 开盘若高开 >L*1.03 放弃; 否则限价 = POI 带上沿(保守)
        ei = k + 1
        if ei >= n - 17:
            return {'dropped': 'no_data_after_entry'}
        ep_open = bs[ei]['o']
        ep_lim = hit[2]
        if ep_open > L * 1.03:
            return {'dropped': 'gap_up_too_far'}
        ep = ep_lim if bs[ei]['l'] <= ep_lim else ep_open
        tps = _tps_sl_at(bs, ei, ep)
        if not tps:
            return {'dropped': 'no_tp_sl'}
        return {'entry_idx': ei, 'ep': ep, 'tp': tps[:3], 'sl': tps[3],
                'break_date': bs[b_bar]['t'], 'break_level': L,
                'retrace_date': bs[k]['t'], 'poi_kind': hit[0],
                'wait_bars': b_bar - sig_i, 'retrace_bars': k - b_bar}
    return {'dropped': 'no_retrace_in_window'}


def main():
    from core.execution import simulate as _sim
    import config as CFG
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
    print(f'对照事件池: v22 腿 {len(rows)}')

    kcache = {}
    out, drops = [], {}
    for r in rows:
        sym = r['symbol']
        if sym not in kcache:
            kcache[sym] = load_bars(sym)
        bs = kcache[sym]
        if not bs:
            drops['no_klines'] = drops.get('no_klines', 0) + 1
            continue
        dmap = {b['t']: ix for ix, b in enumerate(bs)}
        sd = str(r.get('entry_date', '')).replace('-', '')
        sig_i = dmap.get(sd)
        if sig_i is None:
            drops['signal_date_missing'] = drops.get('signal_date_missing', 0) + 1
            continue
        res = disciplined_entry(bs, sig_i)
        if res is None or 'dropped' in res:
            k = (res or {}).get('dropped', 'none')
            drops[k] = drops.get(k, 0) + 1
            continue
        ei = res['entry_idx']
        _r = _sim(bs, ei, res['ep'], res['sl'], tp1=res['tp'][0], tp2=res['tp'][1],
                  tp3=res['tp'][2], partial_tp1=0.3, stop_to_be=True,
                  max_hold=CFG.MAX_HOLD, code=sym[:6])
        if _r.get('skipped'):
            drops['sim_skipped'] = drops.get('sim_skipped', 0) + 1
            continue
        out.append({'symbol': sym, 'event_date': r['entry_date'],
                    'entry_date': bs[ei]['t'], 'buy_price': round(res['ep'], 3),
                    'sell_price': round(_r.get('sell_price', 0), 3),
                    'net_pnl_pct': _r.get('net_pnl_pct', 0),
                    'hold_bars': _r.get('hold_bars', 0), 'reason': _r.get('reason'),
                    'break_date': res['break_date'], 'break_level': res['break_level'],
                    'retrace_date': res['retrace_date'], 'poi_kind': res['poi_kind'],
                    'wait_bars': res['wait_bars'], 'retrace_bars': res['retrace_bars'],
                    'old_net': round(float(r.get('net_pnl_pct') or 0), 3)})

    with open(ROOT / 'research/combo_v23_disciplined_entry.csv', 'w', newline='', encoding='utf-8-sig') as f:
        if out:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)

    old_pnls = [float(r.get('net_pnl_pct') or 0) for r in rows]
    new_pnls = [o['net_pnl_pct'] for o in out]

    def _stats(pnls):
        if not pnls:
            return {}
        gp = sum(x for x in pnls if x > 0)
        gl = -sum(x for x in pnls if x < 0)
        return {'n': len(pnls), 'avg': round(sum(pnls) / len(pnls), 2),
                'wr': round(sum(1 for x in pnls if x > 0) / len(pnls) * 100, 1),
                'pf': round(gp / gl, 2) if gl > 0 else 99}

    summ = {'old': _stats(old_pnls), 'new': _stats(new_pnls), 'drops': drops,
            'entered_n': len(out), 'event_pool': len(rows)}
    print('=== R134 纪律引擎 vs 冻结基线 (同事件池 1844) ===')
    print(f"旧引擎(公告次日闭眼): n={summ['old']['n']} avg={summ['old']['avg']}% WR={summ['old']['wr']}% PF={summ['old']['pf']}")
    if new_pnls:
        print(f"纪律引擎(破前高→回踩POI): n={summ['new']['n']} avg={summ['new']['avg']}% WR={summ['new']['wr']}% PF={summ['new']['pf']}")
        print(f"放弃原因: {drops}")
        wb = [o['wait_bars'] for o in out]
        rb = [o['retrace_bars'] for o in out]
        print(f"平均等候: 破前高 {sum(wb)/len(wb):.1f} bar / 回踩 {sum(rb)/len(rb):.1f} bar")
    json.dump(summ, open(ROOT / 'research/handover/_r134_disciplined_entry.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('写出 combo_v23_disciplined_entry.csv + handover/_r134_disciplined_entry.json')


if __name__ == '__main__':
    main()
