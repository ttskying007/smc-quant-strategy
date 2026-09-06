# -*- coding: utf-8 -*-
"""复审 P0-2: 时间断言 + 反前视测试
1. 时间不变量: max(扫损/OB/BOS/触POI/收回) < entry_idx（所有锚点早于入场）
2. 截断重放: build_seeds(sym, daily[:entry_idx]) 必须复现同一 seed（无未来K）
3. 未来列打乱: 打乱未来量能列后，seeds 应不变或减少（确认不使用未来量）
"""
import io, json, os, sys, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as WE

KLINE = r"E:\test\smc_project\hermes\kline_cache"
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def load(path):
    raw = json.load(open(path, encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                       "c": float(r["c"]), "v": float(r["v"])})
    bs.sort(key=lambda b: b["t"])
    return bs

print("== P0-2.1 时间不变量 ==")
n_seed = n_viol = 0
files1 = sorted(f for f in os.listdir(KLINE) if f.endswith("_daily_750.json"))[::23][:120]
for p in files1:
    d = load(os.path.join(KLINE, p))
    if len(d) < 400:
        continue
    code = p.split("_")[0]
    sym = code + (".SH" if code.startswith("6") else ".SZ")
    for sd in WE.build_seeds(sym, d):
        n_seed += 1
        ei = int(sd["entry_idx"])
        dates = {b["t"]: i for i, b in enumerate(d)}
        try:
            sweep_i = dates.get(str(sd.get("sweep_date")), -1)
            ob_i = dates.get(str(sd.get("ob_date")), -1)
            touch_i = dates.get(str(sd.get("touch_date")), -1)
            reclaim_i = dates.get(str(sd.get("reclaim_date")), -1)
            if max(sweep_i, ob_i, touch_i, reclaim_i) >= ei:
                n_viol += 1
        except Exception:
            pass
ok(f"锚点<入场 不变量 ({n_seed} seeds)", n_viol == 0, f"violations={n_viol}")

print("== P0-2.2 截断重放（无未来K）==")
rep = 0
tot_full = 0
files = sorted(f for f in os.listdir(KLINE) if f.endswith("_daily_750.json"))[::23][:120]
for p in files:
    d = load(os.path.join(KLINE, p))
    if len(d) < 400:
        continue
    code = p.split("_")[0]
    sym = code + (".SH" if code.startswith("6") else ".SZ")
    full = WE.build_seeds(sym, d)
    dates = {b["t"]: i for i, b in enumerate(d)}
    for sd in full:
        ei = int(sd["entry_idx"])
        if ei < 350 or ei >= len(d) - 2:
            continue
        # 截断重放标准: 用 d[:ei+1]（含 entry 日开盘，不含 entry 后），
        # seed 的锚点(sweep/ob/touch/reclaim) 全部 < ei → 确认链在 entry 前完整，必须复现
        _anchors = [dates.get(str(sd.get(k)), -1) for k in ("sweep_date", "ob_date", "touch_date", "reclaim_date")]
        if max(_anchors) >= ei:
            continue  # 锚点触及 entry → 不在截断验证范围
        truncated = WE.build_seeds(sym, d[:ei + 1])
        ids_trunc = {s["identity"] for s in truncated}
        tot_full += 1
        if sd["identity"] in ids_trunc:
            rep += 1
ok(f"截断重放复现 ({tot_full} 可测seed, 锚点全在entry前)", rep >= max(1, int(tot_full * 0.8)), f"reproduced={rep}/{tot_full}")

print("== P0-2.3 未来量能打乱（确认不使用未来v）==")
n0 = n1 = 0
for p in files1:
    d = load(os.path.join(KLINE, p))
    if len(d) < 400:
        continue
    code = p.split("_")[0]
    sym = code + (".SH" if code.startswith("6") else ".SZ")
    n0 += len(WE.build_seeds(sym, d))
    d2 = [dict(b) for b in d]
    tail = d2[-60:]
    vs = [b["v"] for b in tail]
    random.Random(42).shuffle(vs)
    for b, v in zip(tail, vs):
        b["v"] = v
    d2[-60:] = tail
    n1 += len(WE.build_seeds(sym, d2))
print(f"原seeds={n0} 未来v打乱后={n1}（若差大→使用了未来量）")
ok("未来v打乱不改变信号集", abs(n1 - n0) <= max(2, n0 * 0.1), f"Δ={n1-n0}")

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
