# -*- coding: utf-8 -*-
"""refresh_60min_incremental.py —— 60min 增量刷新 v2(§50/§53):
只刷"末bar < 目标日"的文件(跳过已新鲜的), 失败重试×2, 限速可调。
v3(2026-09-13 §53): 支持 _60min_500.json 与 _60min_200.json 双文件族
(F7 读 _500 族, 日频链历史用 _200 族 —— 两族都要新鲜)。用法:
    python refresh_60min_incremental.py            # 默认刷两族
    python refresh_60min_incremental.py 500        # 只刷 _500 族
"""
import json, os, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CACHE = r"E:\test\smc_project\hermes\kline_cache_60min"
UA = {"User-Agent": "Mozilla/5.0"}
TARGET = "20260911"          # 期望末bar 日期(8位)
RETRY = 2
SLEEP = 0.22
FAMILIES = ("500",) if (len(sys.argv) > 1 and sys.argv[1] == "500") else ("500", "200")


def get_60min(tc, count=500):
    url = "http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=%s,m60,,%d" % (tc, count)
    for attempt in range(RETRY + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            ks = data.get("data", {}).get(tc, {}).get("m60", [])
            if not ks:
                return None
            bars = []
            for k in ks:
                t_raw = str(k[0])
                t_num = t_raw.replace("-", "").replace(":", "").replace(" ", "")[:12]
                bars.append({"t": int(t_num), "date": t_raw,
                             "o": float(k[1]), "c": float(k[2]),
                             "h": float(k[3]), "l": float(k[4]), "v": float(k[5])})
            return bars
        except Exception:
            if attempt < RETRY:
                time.sleep(1.5 * (attempt + 1))
            continue
    return None


# 找需要刷新的: 末bar < TARGET (双文件族)
stale = []
for fam in FAMILIES:
    for f in sorted(os.listdir(CACHE)):
        if not f.endswith(f"_60min_{fam}.json"):
            continue
        try:
            j = json.load(open(os.path.join(CACHE, f), encoding="utf-8"))
            last = str(j[-1].get("t") or "")[:8]
            if last < TARGET:
                stale.append((f, last))
        except Exception:
            stale.append((f, "?"))
print(f"需刷新: {len(stale)} (族={FAMILIES}, 目标末bar {TARGET})", flush=True)
ok = fail = 0
for i, (f, old) in enumerate(stale):
    sym = f.split("_60min_")[0]
    code, market = (sym.split("_", 1) + ["SZ"])[:2]
    tc = ("sh" if market == "SH" else "sz") + code
    bars = get_60min(tc)
    if bars and str(bars[-1]["t"])[:8] >= TARGET:
        with open(os.path.join(CACHE, f), "w", encoding="utf-8") as fh:
            json.dump(bars, fh, ensure_ascii=False)
        ok += 1
    else:
        fail += 1
        if fail <= 5:
            print(f"  FAIL {f}: old={old} new={str(bars[-1]['t'])[:8] if bars else None}", flush=True)
    if (i + 1) % 500 == 0:
        print(f"  {i+1}/{len(stale)} ok={ok} fail={fail}", flush=True)
    time.sleep(SLEEP)
print(f"\n完成: ok={ok} fail={fail}", flush=True)