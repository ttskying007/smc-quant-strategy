# -*- coding: utf-8 -*-
"""全量回测复检：2024 avg 崩塌归因（旧循环+旧过滤 vs 新循环+新过滤）
分别用 (旧退出, 新退出) × (旧过滤, 新过滤) 四象限跑 2024 年样本，定位崩塌来源。"""
import io, json, os, sqlite3, sys, csv
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.events import classify_title
import core.execution as EX

# 独立复现 gen_v20f 的数据/指标函数（避免 import 触发模块级回测执行）
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
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def exit_old(bs, entry_idx, ep, sl1, tp1, tp2, tp3):
    """gen_v20f 原内联退出循环（逐 bar，stop=be?ep:sl1，无 SL_GAP 特判）"""
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


def exit_new(bs, entry_idx, ep, sl1, tp1, tp2, tp3, code):
    r = EX.simulate(bs, entry_idx, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
                    partial_tp1=0.3, stop_to_be=True, max_hold=15, code=code)
    if r.get("skipped"):
        return None  # 入场不可成交（涨停等）——与旧循环"无涨停检查"不同，跳过不入样本
    return r["net_pnl_pct"]


conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")

rows = {"old_old": [], "new_old": [], "old_new": [], "new_new": []}  # (过滤, 退出)
n_stat = {"old": 0, "new": 0, "both": 0}
seen = set()
for date, code, title in cur.fetchall():
    o = is_strong_old(title)
    n_ev, _k, n_pol = classify_title(title)[:3]
    n = bool(n_ev and n_pol > 0)
    d = str(date)[:10].replace("-", "")
    if (code, d) in seen:
        continue
    seen.add((code, d))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d not in dates:
        continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep_open = bs[entry_idx]["o"]
    disc_close = bs[i]["c"]
    if ep_open <= 0:
        continue
    highs, lows = [], []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j - 3, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + 4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j - 3, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + 4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2:
            break
    if not highs or not lows:
        continue
    highs.sort()
    limit = disc_close * 0.99
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    tp1_, tp2_, tp3_ = highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]
    _atr = 0
    if i >= 15:
        _trs = [max(bs[k]["h"] - bs[k]["l"], abs(bs[k]["h"] - bs[k - 1]["c"]), abs(bs[k]["l"] - bs[k - 1]["c"]))
                for k in range(i - 14, i)]
        _atr = sum(_trs) / 14
    sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
    _tps = sorted([x for x in (tp1_, tp2_, tp3_) if x and x > ep])
    if not _tps:
        continue
    tp1_ = _tps[0]
    tp2_ = _tps[1] if len(_tps) > 1 else tp1_ * 1.05
    tp3_ = _tps[2] if len(_tps) > 2 else tp2_ * 1.05
    y = bs[entry_idx]["t"][:4]
    if y != "2024":
        continue
    if o:
        v = exit_old(bs, entry_idx, ep, sl1, tp1_, tp2_, tp3_)
        if v is not None:
            rows["old_old"].append(v)
        v2 = exit_new(bs, entry_idx, ep, sl1, tp1_, tp2_, tp3_, code)
        if v2 is not None:
            rows["new_old"].append(v2)
    if n:
        v = exit_old(bs, entry_idx, ep, sl1, tp1_, tp2_, tp3_)
        if v is not None:
            rows["old_new"].append(v)
        v2 = exit_new(bs, entry_idx, ep, sl1, tp1_, tp2_, tp3_, code)
        if v2 is not None:
            rows["new_new"].append(v2)
    if o and n:
        n_stat["both"] += 1
    elif o:
        n_stat["old"] += 1
    elif n:
        n_stat["new"] += 1
conn.close()


def stats(pn):
    if not pn:
        return "n=0"
    n = len(pn)
    avg = sum(pn) / n
    wins = [x for x in pn if x > 0]
    losses = [x for x in pn if x <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 99
    return f"n={n} avg={avg:+.2f}% wr={len(wins)/n*100:.0f}% PF={pf:.2f}"


print("2024 年四象限（过滤 × 退出）:")
print(f"  旧过滤+旧退出(原基线):   {stats(rows['old_old'])}")
print(f"  旧过滤+新退出(simulate): {stats(rows['new_old'])}")
print(f"  新过滤+旧退出:           {stats(rows['old_new'])}")
print(f"  新过滤+新退出(现生产):   {stats(rows['new_new'])}")
print(f"\n过滤统计: 仅旧={n_stat['old']} 仅新={n_stat['new']} 都过={n_stat['both']}")