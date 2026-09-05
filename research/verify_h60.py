# -*- coding: utf-8 -*-
"""F13 近端验证：60min 真实 CHoCH 入场 vs 日线投影入场 差异
数据：kline_cache_60min（2025-10~2026-05，每只 200 根）
方法：对每只股票，找日线级"回踩 POI 后"窗口，比较：
  日线投影入场 = 次日开盘（现有语义）
  60min CHoCH 入场 = 60min 内 低点之后 阳线收过前一根高点（更优价格）
统计：入场价差（投影 - CHoCH）、等待根数、命中率
"""
import json, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = r"E:\test\smc_project\hermes\kline_cache_60min"

def load_60m(path):
    raw = json.load(open(path, encoding="utf-8"))
    bars = []
    for b in raw:
        t = str(b.get("t") or "")
        if len(t) >= 12 and b.get("o"):
            bars.append({"t": t, "o": float(b["o"]), "h": float(b["h"]),
                         "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v", 0)),
                         "d": t[:8]})
    bars.sort(key=lambda x: x["t"])
    return bars

def daily_projection_entry(hm, day):
    """日线投影：该日次根60min开盘作为入场价。"""
    idxs = [i for i, b in enumerate(hm) if b["d"] == day]
    if not idxs:
        return None
    nxt = idxs[-1] + 1
    if nxt < len(hm):
        return hm[nxt]["o"], 1
    return None

def hoc_confirm_entry(hm, day):
    """60min CHoCH：当日盘中 low 之后，阳线收过前一根高点 → 该根收盘入场（折价区）。"""
    idxs = [i for i, b in enumerate(hm) if b["d"] == day]
    if len(idxs) < 4:
        return None
    lo = min(hm[i]["l"] for i in idxs)
    lo_i = min((i for i in idxs), key=lambda i: hm[i]["l"])
    for i in range(lo_i + 1, min(idxs[-1] + 1, len(hm) - 1)):
        if hm[i]["c"] > hm[i - 1]["h"] and hm[i]["c"] > hm[i]["o"]:
            return hm[i]["c"], i - idxs[0] + 1
    return None

# 采样 300 只
files = sorted(f for f in os.listdir(D) if f.endswith("60min_200.json"))[:300]
n_ok = 0
diffs = []
waits = []
for p in files:
    try:
        hm = load_60m(os.path.join(D, p))
    except Exception:
        continue
    if len(hm) < 40:
        continue
    # 找一个"回踩日"：当日有 3 根以上且盘中 low 后收阳
    days = sorted(set(b["d"] for b in hm))
    for day in days[-6:]:  # 近 6 日
        dp = daily_projection_entry(hm, day)
        hc = hoc_confirm_entry(hm, day)
        if dp and hc:
            diffs.append(dp[0] - hc[0])       # 投影 - CHoCH（>0 = CHoCH 更优）
            waits.append(hc[1] - dp[1])        # 等待根数差异
            n_ok += 1
            break

print("样本股票:", len(files), "| 有效比对:", n_ok)
if diffs:
    mean_diff = sum(diffs) / len(diffs)
    pos = sum(1 for d in diffs if d > 0)
    base = sum(abs(d) for d in diffs) / len(diffs)
    print("入场价差(投影-CHoCH): 均值 %+.4f | CHoCH 更优占比 %.0f%%" % (mean_diff, pos / len(diffs) * 100))
    print("CHoCH 平均节省: %+.2f%% (相对投影价)" % (mean_diff * 100))
    print("等待根数差均值: %+.1f" % (sum(waits) / len(waits)))
else:
    print("无有效比对（60min 窗口不足）")
