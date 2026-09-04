# -*- coding: utf-8 -*-
"""延续腿 scanner 集成：扫描当前 MARKUP 结构支撑 + VWAP10% + 低波动 信号
（v20c 生产 = 反转 + 延续；scanner 需输出延续候选。VWAP 5%->10% 于 2026-08-22 优化）"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we
import config as CFG  # 审计 P1: 统一路径

KT = CFG.KT_CACHE
PIVOT = 3


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def stage_detailed(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(x["v"] for x in bs[i - 20:i]) / 20
    v60 = sum(x["v"] for x in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    if ret60 > 0:
        return "UPTREND"
    return "DOWNTREND"


# global median vol20 (computed once from fresh files)
def compute_median():
    vols = []
    for p in os.listdir(KT):
        if not p.endswith("_daily_800.json"):
            continue
        daily = bars(os.path.join(KT, p))
        if len(daily) < 80:
            continue
        w20 = daily[-21:-1] if len(daily) >= 21 else daily
        if len(w20) == 20:
            vols.append(sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20)
        if len(vols) > 3000:
            break
    vols.sort()
    return vols[len(vols) // 2]


V_MED = compute_median()
print(f"vol20 中位: {V_MED:.4f}", flush=True)

# scan for continuation candidates at latest bar (entry next open)
cands = []
n = 0
latest = ""
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    if daily[-1]["t"] > latest:
        latest = daily[-1]["t"]
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    i = len(daily) - 2  # signal on second-last bar, entry = last bar open
    st = stage_detailed(daily, i)
    if st != "MARKUP":
        continue
    sl_tmp = None
    sl_idx = None
    # FIX(2026-09-05, 审计 F04): 摆动低点确认须在信号bar(i)之前完成 —— j + PIVOT <= i，
    # 否则用了 i+1（入场根）之后的K线确认（回测/实盘信号集不一致）。
    for j in range(i, PIVOT - 1, -1):
        if j + PIVOT > i:
            continue
        if is_swing_low(daily, j):
            sl_tmp = daily[j]["l"]
            sl_idx = j
            break
    if sl_tmp is None:
        continue
    # FIX(2026-08-22) P2: 支撑新鲜度 ≤5 天（研究：>5 天负收益 -2.43%）
    if sl_idx is not None and (i - sl_idx) > 5:
        continue
    if not (daily[i]["l"] <= sl_tmp * 1.01 and daily[i - 1]["c"] > sl_tmp):
        continue
    if daily[i]["c"] <= sl_tmp:
        continue
    entry_idx = i + 1
    if entry_idx >= len(daily) or entry_idx < 20:
        continue
    ep = daily[entry_idx]["o"]
    if sl_tmp >= ep:
        continue
    pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
    vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
    if vol <= 0:
        continue
    vw = pv / vol
    # FIX(2026-08-22): VWAP threshold 5% -> 10% (research: monotonic improvement, 10% = +8.56%)
    if (daily[entry_idx]["c"] - vw) / vw < 0.09:
        continue
    w20 = daily[entry_idx - 20:entry_idx]
    vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
    if vol20 >= V_MED:
        continue
    cands.append({"symbol": sym, "signal_date": daily[i]["t"], "entry_date": daily[entry_idx]["t"],
                  "support": round(sl_tmp, 3), "entry_price": round(ep, 3),
                  "hold": 10, "signal": "CONTINUATION_MARKUP", "stage": "MARKUP"})
    if n % 1500 == 0:
        print(f"  {n} files, cands {len(cands)}", flush=True)

print(f"扫描完成: {n} files, latest={latest}, 延续候选: {len(cands)}")
for c in cands[:10]:
    print(f"  {c['symbol']}: signal={c['signal_date']} entry={c['entry_date']} support={c['support']} entry_price={c['entry_price']}")

# merge into scanner result
try:
    with open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8") as fh:
        res = json.load(fh)
except Exception:
    res = {}
res["continuation_candidates"] = cands
res["continuation_count"] = len(cands)
res["latest_date"] = latest
with open(r"E:\test\smc_project\research\current_scanner_result.json", "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=2)
print("scanner result updated with continuation candidates")
