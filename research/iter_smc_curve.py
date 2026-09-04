# -*- coding: utf-8 -*-
"""SMC 反转 alpha 时间曲线：SSL sweep 链（固定持有视角）T+5/10/15/20/30"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c, v = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c")), we.f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


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


sigs = []
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    for sd in we.build_seeds(sym, daily):
        r20 = sd.get("r20")
        if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
            continue
        entry_idx = int(sd["entry_idx"])
        if entry_idx < 61:
            continue
        st = stage_detailed(daily, entry_idx)
        if st not in ("UPTREND", "MARKUP"):
            continue
        if not any(daily[k]["h"] < daily[k - 2]["l"] for k in range(max(3, entry_idx - 12), entry_idx)):
            continue
        pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        if vol <= 0:
            continue
        vw = pv / vol
        if (daily[entry_idx]["c"] - vw) / vw < 0.05:
            continue
        if entry_idx + 30 >= len(daily):
            continue
        sigs.append({"i": entry_idx, "ep": daily[entry_idx]["o"], "daily": daily})
    if n % 1500 == 0:
        print(f"  {n} files, sigs {len(sigs)}", flush=True)
print("SMC 反转信号:", len(sigs))

print("\n=== SMC 反转 alpha 时间曲线（固定持有视角）===")
for h in (5, 10, 15, 20, 30):
    pnls = []
    for s in sigs:
        if s["i"] + h >= len(s["daily"]) or s["ep"] <= 0:
            continue
        pnls.append((s["daily"][s["i"] + h]["c"] / s["ep"] - 1) * 100)
    if pnls:
        w = sum(1 for p in pnls if p > 0)
        print(f"  T+{h}: avg={sum(pnls)/len(pnls):+.2f}% WR={100*w/len(pnls):.0f}% n={len(pnls)}")
