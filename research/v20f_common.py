# -*- coding: utf-8 -*-
"""v20f 事件腿共享工具（供 quad/skip 等归因脚本复用，不含模块级执行）"""
import json, os

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}


def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        raw = json.load(open(p, encoding="utf-8")) if p else []
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                           "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def adx14(bs, i):
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up, dn = h - bs[k - 1]["h"], bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr_sum += max(h - l, abs(h - pc), abs(l - pc))
    if tr_sum <= 0:
        return None
    pdi, mdi = 100 * plus_dm / tr_sum, 100 * minus_dm / tr_sum
    return 100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else None


def stage_of(bs, i):
    if i < 91:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


def is_strong_old(title):
    """旧 gen_v20f.is_strong（研究基线过滤，历史对照用）"""
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def exit_old(bs, entry_idx, ep, sl1, tp1, tp2, tp3):
    """gen_v20f 原内联退出循环（历史对照，无涨停/SL_GAP特判）"""
    remaining, net, be = 1.0, 0.0, False
    for k in range(entry_idx + 1, min(len(bs), entry_idx + 16)):
        bb = bs[k]
        stop = ep if be else sl1
        if bb["l"] <= stop:
            net += remaining * (stop / ep - 1) * 100
            remaining = 0
            break
        if not be and bb["h"] >= tp1:
            net += 0.3 * (tp1 / ep - 1) * 100
            remaining, be = 0.7, True
        elif be and bb["h"] >= tp2:
            net += remaining * (tp2 / ep - 1) * 100
            remaining = 0
            break
        elif be and bb["h"] >= tp3:
            net += remaining * (tp3 / ep - 1) * 100
            remaining = 0
            break
    if remaining > 0:
        last = bs[min(len(bs), entry_idx + 15) - 1]["c"]
        net += remaining * (last / ep - 1) * 100
    return net - 0.20