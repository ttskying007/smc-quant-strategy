# -*- coding: utf-8 -*-
"""R139: 入场位置深度研究 (归纳法, 不预设规则) — 赢/输入场的结构画像。

用户持续反馈入场位置不对。R133/R134/R138 都是"拿规则清单对答案"(演绎), 本轮反向:
对每腿入场量化全部因果可得的位置特征, 再看 PnL/MFE/MAE 到底由什么驱动 —
让数据自己指出"什么样的位置是坏入场", 而不是先验假设。

特征(全部只用入场bar及之前数据):
  loc20        入场价在近20bar高低区间分位 (0=区间底, 100=区间顶)
  newlow20     入场价 ≤ 近20bar最低价 (创新低)
  near_high    距最近确认摆动高(pivot3, ≤90bar) 距离% (越近=越顶着阻力买)
  near_low     距最近确认摆动低 距离%
  day_pos      事件日收盘在当日振幅中的位置 (c-l)/(h-l)
  gap_pct      事件日开盘相对前收跳空%
  vol_ratio    事件日量 / 前20日均量
  ret5/ret20   事件前5/20日收益%
  atr_pct      事件日ATR14/收盘

结果: research/combo_v25_entry_location.csv + handover/_r139_entry_location.json
分析: 分位桶PnL / 趋势×位置交叉 / 赢家top20% vs 输家bottom20%画像对比。
"""
import csv, json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')
sys.path.insert(0, str(ROOT / 'research'))

KT = ROOT / 'hermes/kline_cache_tencent'


def load_bars(sym):
    sf = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    for name in ('_daily_800.json', '_daily_750.json', '_daily_300.json'):
        fp = KT / (sf + name)
        if fp.exists():
            break
    else:
        return None
    d = json.load(open(fp, encoding='utf-8'))
    raw = d if isinstance(d, list) else (d.get('klines') or d.get('bars') or [])
    if not raw:
        return None
    if 'h' not in raw[0] and 'high' not in raw[0]:
        return None
    out = []
    for b in raw:
        t = str(b.get('t', b.get('date', '')))[:10].replace('-', '')
        out.append({'t': t, 'o': float(b.get('o', b.get('open', 0))), 'h': float(b.get('h', b.get('high', 0))),
                    'l': float(b.get('l', b.get('low', 0))), 'c': float(b.get('c', b.get('close', 0))),
                    'v': float(b.get('v', b.get('volume', 0)))})
    return out


def _swing_levels(bs, i, pivot=3):
    """i 之前(确认口径 j+pivot<=i) 最近摆动高/低."""
    sh = sl = None
    for j in range(i - pivot, max(pivot, i - 90), -1):
        if j - pivot < 0 or j + pivot >= i + 1:
            continue
        h = bs[j]['h']
        if sh is None and all(h >= bs[k]['h'] for k in range(j - pivot, j + pivot + 1)):
            sh = h
        lo = bs[j]['l']
        if sl is None and all(lo <= bs[k]['l'] for k in range(j - pivot, j + pivot + 1)):
            sl = lo
        if sh is not None and sl is not None:
            break
    return sh, sl


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
    ch2 = {r['symbol'] + '|' + r['entry_date']: r
           for r in csv.DictReader(open(ROOT / 'research/combo_v22_chain_v2_hhll.csv', encoding='utf-8-sig'))}
    smc = {r['symbol'] + '|' + r['entry_date']: r
           for r in csv.DictReader(open(ROOT / 'research/combo_v22_smc_full_v2.csv', encoding='utf-8-sig'))}

    out, kcache = [], {}
    for r in rows:
        sym = r['symbol']
        bs = kcache.get(sym)
        if bs is None:
            bs = load_bars(sym)
            kcache[sym] = bs or []
        if not bs:
            continue
        dmap = {b['t']: ix for ix, b in enumerate(bs)}
        sd = str(r.get('entry_date', '')).replace('-', '')
        ei = dmap.get(sd)
        if ei is None or ei < 25 or ei >= len(bs):
            continue
        b = bs[ei]
        prior = bs[max(0, ei - 20):ei]
        hi20 = max(x['h'] for x in prior)
        lo20 = min(x['l'] for x in prior)
        buy = float(r.get('buy_price') or 0)
        if buy <= 0:
            buy = b['c']
        rng = hi20 - lo20
        loc20 = round((buy - lo20) / rng * 100, 1) if rng > 0 else 50.0
        newlow20 = buy <= lo20
        sh, sl = _swing_levels(bs, ei)
        near_high = round((sh / buy - 1) * 100, 1) if sh else None   # >0: 前高在上方x%
        near_low = round((sl / buy - 1) * 100, 1) if sl else None
        prev_c = bs[ei - 1]['c']
        gap = round((b['o'] / prev_c - 1) * 100, 1)
        day_rng = b['h'] - b['l']
        day_pos = round((b['c'] - b['l']) / day_rng * 100, 1) if day_rng > 0 else 50.0
        v20 = sum(x['v'] for x in prior) / len(prior) if prior else 0
        vol_ratio = round(b['v'] / v20, 2) if v20 > 0 else None
        c5 = bs[max(0, ei - 5)]['c']
        c20 = bs[max(0, ei - 20)]['c']
        ret5 = round((b['c'] / c5 - 1) * 100, 1)
        ret20 = round((b['c'] / c20 - 1) * 100, 1)
        trs = [max(bs[k]['h'] - bs[k]['l'], abs(bs[k]['h'] - bs[k - 1]['c']), abs(bs[k]['l'] - bs[k - 1]['c']))
               for k in range(max(1, ei - 14), ei)]
        atr = sum(trs) / 14 if trs else 0
        atr_pct = round(atr / b['c'] * 100, 2)
        key = sym + '|' + sd
        ch = ch2.get(key) or {}
        sm = smc.get(key) or {}
        out.append({
            'symbol': sym, 'entry_date': sd, 'buy_price': buy,
            'net_pnl_pct': float(r.get('net_pnl_pct') or 0),
            'mfe_pct': float(sm.get('mfe_pct') or 0) if sm else None,
            'mae_pct': float(sm.get('mae_pct') or 0) if sm else None,
            'trend_state': ch.get('trend_v2') or sm.get('trend_state') or '',
            'loc20': loc20, 'newlow20': newlow20,
            'near_high': near_high, 'near_low': near_low,
            'day_pos': day_pos, 'gap_pct': gap, 'vol_ratio': vol_ratio,
            'ret5': ret5, 'ret20': ret20, 'atr_pct': atr_pct,
        })

    fn = ROOT / 'research/combo_v25_entry_location.csv'
    with open(fn, 'w', newline='', encoding='utf-8-sig') as f:
        if out:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)

    def stats(pnls):
        pnls = [x for x in pnls if x is not None]
        if not pnls:
            return {'n': 0}
        gp = sum(x for x in pnls if x > 0)
        gl = -sum(x for x in pnls if x < 0)
        return {'n': len(pnls), 'avg': round(sum(pnls) / len(pnls), 2),
                'wr': round(sum(1 for x in pnls if x > 0) / len(pnls) * 100, 1),
                'pf': round(gp / gl, 2) if gl > 0 else 99}

    # 1) 区间分位桶
    buckets = {}
    for o in out:
        q = '00-10' if o['loc20'] <= 10 else ('10-30' if o['loc20'] <= 30 else ('30-60' if o['loc20'] <= 60
             else ('60-85' if o['loc20'] <= 85 else '85-100(顶)')))
        buckets.setdefault(q, []).append(o['net_pnl_pct'])
    by_loc = {k: stats(v) for k, v in sorted(buckets.items())}

    # 2) 趋势 × 位置交叉 (低半区 vs 高半区)
    cross = {}
    for o in out:
        tr = o['trend_state'] or '?'
        half = 'low_half' if o['loc20'] <= 50 else 'high_half'
        cross.setdefault(tr + '|' + half, []).append(o['net_pnl_pct'])
    by_cross = {k: stats(v) for k, v in sorted(cross.items())}

    # 3) 顶阻力: 前高就在头顶(±2%) 的入场
    res = [o for o in out if o['near_high'] is not None and -2 <= o['near_high'] <= 2]
    free = [o for o in out if o['near_high'] is not None and o['near_high'] > 5]
    by_near_high = {'resistance_2pct': stats([o['net_pnl_pct'] for o in res]),
                    'clear_sky_5pct': stats([o['net_pnl_pct'] for o in free])}

    # 4) 赢家 top20% vs 输家 bottom20% 画像 (中位数对比)
    srt = sorted(out, key=lambda o: o['net_pnl_pct'])
    n = len(srt)
    losers = srt[:max(1, n // 5)]
    winners = srt[-max(1, n // 5):]
    def med(xs, k):
        v = sorted(x[k] for x in xs if x.get(k) is not None)
        return round(v[len(v) // 2], 1) if v else None
    profile = {
        'losers_bottom20pct': {k: med(losers, k) for k in ('loc20', 'near_high', 'near_low', 'day_pos', 'gap_pct', 'ret20', 'vol_ratio')},
        'winners_top20pct': {k: med(winners, k) for k in ('loc20', 'near_high', 'near_low', 'day_pos', 'gap_pct', 'ret20', 'vol_ratio')},
    }

    # 5) 事件日强弱: day_pos 与 gap
    dp_b, gp_b = {}, {}
    for o in out:
        q = 'weak<40' if o['day_pos'] < 40 else ('mid' if o['day_pos'] <= 70 else 'strong>70')
        dp_b.setdefault(q, []).append(o['net_pnl_pct'])
        q2 = 'gap<-3' if o['gap_pct'] < -3 else ('gap-3~3' if o['gap_pct'] <= 3 else 'gap>3')
        gp_b.setdefault(q2, []).append(o['net_pnl_pct'])
    by_daypos = {k: stats(v) for k, v in sorted(dp_b.items())}
    by_gap = {k: stats(v) for k, v in sorted(gp_b.items())}

    summ = {'legs': len(out), 'by_loc20': by_loc, 'by_trend_x_loc': by_cross,
            'by_near_high': by_near_high, 'by_day_pos': by_daypos, 'by_gap': by_gap,
            'profile_top20_vs_bottom20': profile}
    json.dump(summ, open(ROOT / 'research/handover/_r139_entry_location.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    lg = open(ROOT / 'research/handover/_r139_entry_location.txt', 'w', encoding='utf-8')
    lg.write(f"=== R139 入场位置归纳研究 — {len(out)} 腿 ===\n")
    lg.write('[区间分位 → PnL]\n')
    for k, v in by_loc.items():
        lg.write(f"  loc20 {k:12s} n={v.get('n',0):5d} avg={v.get('avg','-')}% PF={v.get('pf','-')}\n")
    lg.write('[趋势 × 区间半区]\n')
    for k, v in by_cross.items():
        lg.write(f"  {k:20s} n={v.get('n',0):5d} avg={v.get('avg','-')}% PF={v.get('pf','-')}\n")
    lg.write('[顶阻力]\n')
    for k, v in by_near_high.items():
        lg.write(f"  {k:20s} n={v.get('n',0):5d} avg={v.get('avg','-')}% PF={v.get('pf','-')}\n")
    lg.write('[事件日强弱 day_pos]\n')
    for k, v in by_daypos.items():
        lg.write(f"  {k:12s} n={v.get('n',0):5d} avg={v.get('avg','-')}% PF={v.get('pf','-')}\n")
    lg.write('[跳空 gap]\n')
    for k, v in by_gap.items():
        lg.write(f"  {k:12s} n={v.get('n',0):5d} avg={v.get('avg','-')}% PF={v.get('pf','-')}\n")
    lg.write('[top20%赢家 vs bottom20%输家 中位画像]\n')
    lg.write('  输家: ' + str(profile['losers_bottom20pct']) + '\n')
    lg.write('  赢家: ' + str(profile['winners_top20pct']) + '\n')
    lg.write('写出 combo_v25_entry_location.csv + _r139_entry_location.json\n')
    lg.close()


if __name__ == '__main__':
    main()
