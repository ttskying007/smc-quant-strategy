# -*- coding: utf-8 -*-
"""core/chain.py — SMC 因果信号链抽取器(单源)

R60(用户需求): 回测/选股/前端统一消费一条"信号链":
  当前趋势 → BOS/CHoCH(时间+价格) → BSL/SSL 前高前低池(时间+价格+类型)
  → OB(订单块) → FVG/IFVG(缺口/逆缺口) → 突破时间+价格 → 回踩(价格+信号类型)
  → 当前回踩状态(价格+信号类型)

全部因果: 任何元素只使用 <= 信号日截断的数据, 摆动点需确认(j+PIVOT<=i)。
消费者: gen_v22(回测列) / paper_sim(挂单留档) / smc_unified.py /kline(前端绘制)。
"""
from core.structure import structure_events, pick_pivot_by_density

PIVOT = 3


def _fvg_boxes(bs, i, lookback=30):
    """因果 FVG 检测: 三柱缺口。
    bullish FVG at bar k: bs[k].l > bs[k-2].h  → box=(bs[k-2].h, bs[k].l)
    bearish FVG at bar k: bs[k].h < bs[k-2].l  → box=(bs[k-2].l, bs[k].h)
    返回 (bull_list, bear_list), 元素 {"t": 形成日, "low":盒下沿, "high":盒上沿, "ifvg":bool}
    IFVG(逆缺口): 缺口箱被对侧收盘完全穿越后角色反转(bullish→阻力, bearish→支撑)。"""
    bull, bear = [], []
    for k in range(max(2, i - lookback), i + 1):
        if bs[k]["l"] > bs[k - 2]["h"]:
            bull.append({"t": bs[k]["t"], "low": bs[k - 2]["h"], "high": bs[k]["l"], "side": "bull"})
        if bs[k]["h"] < bs[k - 2]["l"]:
            bear.append({"t": bs[k]["t"], "low": bs[k]["h"], "high": bs[k - 2]["l"], "side": "bear"})
    # IFVG 判定: 形成日之后, 有 bar 收盘完全越过箱体
    for box in bull:
        k0 = None
        for j in range(i - lookback, i + 1):
            if j >= 0 and bs[j]["t"] == box["t"]:
                k0 = j; break
        if k0 is None: continue
        for j in range(k0 + 1, i + 1):
            if bs[j]["c"] < box["low"]:
                box["ifvg"] = True; break
        box.setdefault("ifvg", False)
    for box in bear:
        k0 = None
        for j in range(i - lookback, i + 1):
            if j >= 0 and bs[j]["t"] == box["t"]:
                k0 = j; break
        if k0 is None: continue
        for j in range(k0 + 1, i + 1):
            if bs[j]["c"] > box["high"]:
                box["ifvg"] = True; break
        box.setdefault("ifvg", False)
    return bull, bear


def _order_blocks(bs, i, events, lookback=40):
    """OB: 结构突破柱之前的最后一根反向K线。
    对每个 <=i 的 BOS/CHoCH 事件(突破柱k0=事件bar), 在 [k0-3, k0) 找最后一根
    方向相反的K线(BOS↑↑找阴线, BOS↓找阳线) → OB box=(low, high)。
    只保留最近 N 个。"""
    obs = []
    recent = [e for e in events if e["bar"] <= i][-6:]
    for e in recent:
        k0 = e["bar"]
        up = e["kind"] in ("BOS↑", "CHoCH↑")
        for j in range(k0 - 1, max(k0 - 4, i - lookback), -1):
            if j < 1: break
            if up and bs[j]["c"] < bs[j]["o"]:
                obs.append({"t": bs[j]["t"], "low": bs[j]["l"], "high": bs[j]["h"],
                            "side": "demand(OB+)", "broke_at": e["date"], "broke_kind": e["kind"]})
                break
            if (not up) and bs[j]["c"] > bs[j]["o"]:
                obs.append({"t": bs[j]["t"], "low": bs[j]["l"], "high": bs[j]["h"],
                            "side": "supply(OB-)", "broke_at": e["date"], "broke_kind": e["kind"]})
                break
    return obs


def _swing_levels(bs, i, pivot=PIVOT, lookback=90):
    """已确认摆动高/低(时间+价格+角色标签)。
    高=BSL(买方流动性, 在上) 低=SSL(卖方流动性, 在下); 标注是否已被sweep。"""
    highs, lows = [], []
    for j in range(max(pivot, i - lookback), i - pivot + 1):
        win = bs[j - pivot:j + pivot + 1]
        if all(bs[j]["h"] >= b["h"] for b in win):
            # sweep: 之后有bar上摸过该高点但收盘收回
            swept = any(bs[k]["h"] >= bs[j]["h"] and bs[k]["c"] < bs[j]["h"]
                        for k in range(j + pivot, i + 1))
            highs.append({"t": bs[j]["t"], "price": bs[j]["h"], "type": "BSL", "swept": swept})
        if all(bs[j]["l"] <= b["l"] for b in win):
            swept = any(bs[k]["l"] <= bs[j]["l"] and bs[k]["c"] > bs[j]["l"]
                        for k in range(j + pivot, i + 1))
            lows.append({"t": bs[j]["t"], "price": bs[j]["l"], "type": "SSL", "swept": swept})
    return highs[-6:], lows[-6:]


def _hh_ll_sequence(bs, i, pivot=PIVOT, lookback=90):
    """R101 (goal round 13): 显式 HH/HL/LH/LL 序列 —— 目标里点名的、此前缺口的指标.

    取 [i-lookback, i] 内已确认的摆动高/低 (与 _swing_levels 同参数),
    按时间序交错合并, 相邻同类比较打标签:
      高点序列: 新高 → HH, 低于前高 → LH
      低点序列: 新低 → LL, 高于前低 → HL
    返回 dict:
      seq: [{'t','side'('H'/'L'),'price','label'('HH'/'LH'/'HL'/'LL')}] 最近 8 个
      structure_state: 最近两条高低的状态合成:
        H结构 'HH'/'LH', L结构 'HL'/'LL' →
          'HH+HL' (牛势), 'LH+LL' (熊势), 'HH+LL' (扩张),
          'LH+HL' (收敛), 'LH+LH' (不明), '不略'
    全部只用甚至为 i 已确认信息 （防未来)"""
    raw = []
    for j in range(max(pivot, i - lookback), i - pivot + 1):
        win = bs[j - pivot:j + pivot + 1]
        if all(bs[j]["h"] >= b["h"] for b in win):
            raw.append((j, 'H', bs[j]["h"]))
        if all(bs[j]["l"] <= b["l"] for b in win):
            raw.append((j, 'L', bs[j]["l"]))
    raw.sort(key=lambda x: x[0])
    seq = []
    prev = {'H': None, 'L': None}
    for j, side, price in raw:
        label = None
        if prev[side] is not None:
            if side == 'H':
                label = 'HH' if price > prev['H'] else 'LH'
            else:
                label = 'LL' if price < prev['L'] else 'HL'
        seq.append({'t': bs[j]['t'], 'side': side, 'price': round(price, 3), 'label': label})
        prev[side] = price
    # 结构合成: 最近扫 H 标签 与 L 标签
    last_H = next((s for s in reversed(seq) if s['side'] == 'H' and s['label']), None)
    last_L = next((s for s in reversed(seq) if s['side'] == 'L' and s['label']), None)
    if last_H and last_L:
        hlab, llab = last_H['label'], last_L['label']
        if hlab == 'HH' and llab == 'HL':
            sst = 'bull(HH+HL)'
        elif hlab == 'LH' and llab == 'LL':
            sst = 'bear(LH+LL)'
        elif hlab == 'HH' and llab == 'LL':
            sst = 'expansion(HH+LL)'
        elif hlab == 'LH' and llab == 'HL':
            sst = 'compress(LH+HL)'
        else:
            sst = f'mixed({hlab}+{llab})'
    else:
        sst = 'none'
    return {'seq': seq[-8:], 'structure_state': sst,
            'last_high_label': last_H['label'] if last_H else None,
            'last_low_label': last_L['label'] if last_L else None}


def _retrace_state(bs, i, events):
    """最近结构事件的回踩分析:
    对最近一个 BOS/CHoCH(突破水平L), 逐bar检查 i 内:
      回踩: 最低(高点突破)<=L*1.005 且当前收盘仍>L  → "retrace_ok"(回踩到位)
      失败: 收盘<L*(1-buffer) 且其后未恢复      → "retrace_fail"(回踩失败延续)
      未回踩: 最低点仍>L*1.005                    → "no_retrace"
    返回 dict(突破时间/价格/回踩价格/回踩状态/回踩信号类型)"""
    evs = [e for e in events if e["bar"] <= i]
    if not evs:
        return {"breakout_date": "", "breakout_price": "", "breakout_kind": "",
                "retrace_price": "", "retrace_state": "no_event", "retrace_signal": "",
                "current_price": round(bs[i]["c"], 3)}
    e = evs[-1]
    L = e["level"]
    up = e["kind"] in ("BOS↑", "CHoCH↑")
    seg = bs[e["bar"] + 1: i + 1]
    state = "no_retrace"
    rt_price = ""
    if seg:
        if up:
            low_after = min(b["l"] for b in seg)
            rt_price = round(low_after, 3)
            if low_after <= L * 1.005:
                state = "retrace_ok" if bs[i]["c"] > L else "retrace_fail"
        else:
            high_after = max(b["h"] for b in seg)
            rt_price = round(high_after, 3)
            if high_after >= L * 0.995:
                state = "retrace_ok" if bs[i]["c"] < L else "retrace_fail"
    if up:
        sig_map = {"retrace_ok": "回踩到位(接多窗口)", "retrace_fail": "回踩跌破(突破失败)",
                   "no_retrace": "尚未回踩", "no_event": "无结构事件"}
    else:
        sig_map = {"retrace_ok": "反抽受限(延续下跌)", "retrace_fail": "反抽收复(破位失败)",
                   "no_retrace": "尚未反抽", "no_event": "无结构事件"}
    return {"breakout_date": e["date"], "breakout_price": round(L, 3),
            "breakout_kind": e["kind"], "retrace_price": rt_price,
            "retrace_state": state, "retrace_signal": sig_map[state],
            "current_price": round(bs[i]["c"], 3)}


def build_chain(bs, i, ret_bars=90, mode='fixed'):
    """主入口: 信号日 bar 索引 i(含)的完整因果链。
    返回 dict:
      trend_state, events_tail(最近4个BOS/CHoCH, 含时间/价格/类型),
      bsl_levels[N]{t,price,type,swept}, ssl_levels[N], ob[N], fvg_bull[N], fvg_bear[N],
      breakout: {date,price,kind}, retrace: {price,state,signal},
      current: {price, zone_px_band}
    mode='auto' (R90): 跨股 swing 密度收归 pivot + ATR 穿透缘; 默认 fixed = 原行为.
    """
    _pivot = PIVOT
    if mode == 'auto':
        _pivot, _ = pick_pivot_by_density(bs, i)
    events = structure_events(bs, i, pivot=_pivot, mode='auto' if mode == 'auto' else 'fixed')
    trend = events[-1]["trend"] if events else "none"
    bull, bear = _fvg_boxes(bs, i)
    obs = _order_blocks(bs, i, events)
    highs, lows = _swing_levels(bs, i, pivot=_pivot)
    rt = _retrace_state(bs, i, events)
    hhll = _hh_ll_sequence(bs, i, pivot=_pivot)   # R101: HH/HL/LH/LL 显式结构
    return {
        "trend_state": trend,
        "structure_state": hhll['structure_state'],
        "swing_seq": hhll['seq'],
        "events_tail": [ {"date": e["date"], "kind": e["kind"], "level": round(e["level"], 3)}
                         for e in [x for x in events if x["bar"] <= i][-4:] ],
        "bsl_levels": [{**h, "price": round(h["price"], 3)} for h in highs],
        "ssl_levels": [{**l, "price": round(l["price"], 3)} for l in lows],
        "ob": obs[-4:],
        "fvg_bull": [{**b, "low": round(b["low"], 3), "high": round(b["high"], 3)} for b in bull[-4:]],
        "fvg_bear": [{**b, "low": round(b["low"], 3), "high": round(b["high"], 3)} for b in bear[-4:]],
        "breakout": {"date": rt["breakout_date"], "price": rt["breakout_price"], "kind": rt["breakout_kind"]},
        "retrace": {"price": rt["retrace_price"], "state": rt["retrace_state"], "signal": rt["retrace_signal"]},
        "current_price": rt["current_price"],
    }
