# -*- coding: utf-8 -*-
"""延续腿样本扩充：VWAP 阈值（8%/9%/10%）× 新鲜度（≤5/≤10 天）敏感性
找样本-质量平衡（补 2025 贡献）"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}

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


def stage_of(bs, i):
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
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


# collect all signals with vw ratio + support age
sigs_all = []
vols = []
for p in sorted(os.listdir(KT)):
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
V_MED = vols[len(vols) // 2]

for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    for i in range(80, len(daily) - 11):
        st = stage_of(daily, i)
        if st != "MARKUP":
            continue
        sl_idx = None
        for j in range(i, PIVOT - 1, -1):
            if is_swing_low(daily, j):
                sl_idx = j
                break
        if sl_idx is None:
            continue
        if not (daily[i]["l"] <= daily[sl_idx]["l"] * 1.01 and daily[i - 1]["c"] > daily[sl_idx]["l"]):
            continue
        if daily[i]["c"] <= daily[sl_idx]["l"]:
            continue
        entry_idx = i + 1
        if entry_idx + 11 >= len(daily) or entry_idx < 130:
            continue
        if daily[entry_idx]["t"] < "20230901":
            continue
        ep = daily[entry_idx]["o"]
        if daily[sl_idx]["l"] >= ep:
            continue
        pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        if vol <= 0:
            continue
        vw = pv / vol
        vw_ratio = (daily[entry_idx]["c"] - vw) / vw
        support_age = i - sl_idx
        w20 = daily[entry_idx - 20:entry_idx]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
        if vol20 >= V_MED:
            continue
        sigs_all.append({"entry_date": daily[entry_idx]["t"],
                         "net_pnl_pct": round((daily[entry_idx + 10]["c"] / ep - 1) * 100 - 0.20, 4),
                         "vw_ratio": vw_ratio, "support_age": support_age})
print("全部延续候选:", len(sigs_all))


def report(label, sigs):
    if not sigs:
        print(f"{label}: 0 笔")
        return
    pnls = [s["net_pnl_pct"] for s in sigs]
    wins = [x for x in pnls if x > 0]
    pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
    y25 = [s["net_pnl_pct"] for s in sigs if str(s["entry_date"])[:4] == "2025"]
    y25s = f" | 2025:{sum(y25)/len(y25):+.2f}%({len(y25)})" if y25 else ""
    print(f"{label}: n={len(sigs)} avg={sum(pnls)/len(pnls):+.2f}% PF={pf:.2f}{y25s}")


print("\n=== VWAP 阈值 × 新鲜度敏感性 ===")
for vw_thr in (0.08, 0.09, 0.10):
    for age in (5, 10):
        rs = [s for s in sigs_all if s["vw_ratio"] >= vw_thr and s["support_age"] <= age]
        report(f"VWAP>{100*vw_thr:.0f}% 新鲜度≤{age}", rs)
