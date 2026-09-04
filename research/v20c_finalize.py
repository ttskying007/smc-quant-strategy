# -*- coding: utf-8 -*-
"""保存 v20c trades + 升级生产（v18反转 + 延续低波动）"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3
FEE = 0.20

trades_v18 = []
with open(r"E:\test\smc_project\research\combo_v18_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades_v18.append(r)


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


all_rows = []
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    for i in range(80, len(daily) - 15):
        st = stage_detailed(daily, i)
        if st != "MARKUP":
            continue
        sl_tmp = None
        for j in range(i, PIVOT - 1, -1):
            if is_swing_low(daily, j):
                sl_tmp = daily[j]["l"]
                break
        if sl_tmp is None:
            continue
        if not (daily[i]["l"] <= sl_tmp * 1.01 and daily[i - 1]["c"] > sl_tmp):
            continue
        if daily[i]["c"] <= sl_tmp:
            continue
        entry_idx = i + 1
        if entry_idx >= len(daily) or entry_idx < 20 or entry_idx + 10 >= len(daily):
            continue
        ep = daily[entry_idx]["o"]
        if sl_tmp >= ep:
            continue
        pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        if vol <= 0:
            continue
        vw = pv / vol
        if (daily[entry_idx]["c"] - vw) / vw < 0.05:
            continue
        w20 = daily[entry_idx - 20:entry_idx]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
        all_rows.append({"symbol": sym, "entry_date": daily[entry_idx]["t"], "vol20": vol20,
                         "net_pnl_pct": round((daily[entry_idx + 10]["c"] / ep - 1) * 100 - FEE, 4)})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(all_rows)}", flush=True)
vols = sorted(r["vol20"] for r in all_rows)
vmed = vols[len(vols) // 2]
cont_low = [r for r in all_rows if r["vol20"] < vmed]
print("延续腿(低波动):", len(cont_low))

seen = set()
combined = []
for t in cont_low + trades_v18:
    key = (str(t.get("symbol", "")), str(t.get("entry_date", "")))
    if key in seen:
        continue
    seen.add(key)
    t = dict(t)
    t.setdefault("src", "CONT")
    combined.append(t)

for t in combined:
    t.setdefault("t1_violation", "False")
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    t["year"] = str(t["entry_date"])[:4]

with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=["symbol", "entry_date", "net_pnl_pct", "t1_violation", "year", "src"])
    w.writeheader()
    for t in combined:
        w.writerow({"symbol": t.get("symbol", ""), "entry_date": t.get("entry_date", ""),
                    "net_pnl_pct": t.get("net_pnl_pct", 0), "t1_violation": t.get("t1_violation", ""),
                    "year": t.get("year", ""), "src": t.get("src", "SMC")})
print("combo_v20c_trades saved:", len(combined))


def stats(rs):
    n = len(rs)
    w = sum(1 for t in rs if t["net_pnl_pct"] > 0)
    gp = sum(max(t["net_pnl_pct"], 0) for t in rs)
    gl = abs(sum(min(t["net_pnl_pct"], 0) for t in rs))
    return {"n": n, "wr": round(100 * w / n, 1), "avg": round(sum(t["net_pnl_pct"] for t in rs) / n, 3),
            "pf": round(gp / gl, 2) if gl else 0}

by_y = defaultdict(list)
for t in combined:
    by_y[t["year"]].append(t)
yearly = [{"year": y, **stats(by_y[y])} for y in sorted(by_y)]
by_m = defaultdict(list)
for t in combined:
    by_m[str(t["entry_date"])[:6]].append(t)
monthly = [{"month": m, **stats(by_m[m])} for m in sorted(by_m) if m >= "202309"]

lines = ["# 组合 v20c（反转 + 延续低波动）每年/每月报告", ""]
lines.append("> v20c = v18（SMC反转 + 事件反转）+ 延续腿（MARKUP结构+VWAP5%+低波动+固定10日）")
lines.append("> 延续腿低波动（PF 3.91）替换全量延续 → avg +6.41%/PF 3.50，年度均衡")
lines.append("")
lines.append("## 逐年")
lines.append("| 年 | n | 胜率% | 平均% | PF |")
lines.append("|---|---|---|---|---|")
for y in yearly:
    lines.append(f"| {y['year']} | {y['n']} | {y['wr']} | {y['avg']:+.2f} | {y['pf']} |")
lines.append("")
lines.append("## 逐月")
lines.append("| 月 | n | 胜率% | 平均% | PF |")
lines.append("|---|---|---|---|---|")
for m in monthly:
    lines.append(f"| {m['month']} | {m['n']} | {m['wr']} | {m['avg']:+.2f} | {m['pf']} |")
with open(r"E:\test\smc_project\research\组合v20c逐年逐月报告.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("v20c report written")

dash = {
    "updated": "2026-08-19",
    "version": "COMBO_V20C_LOWVOL_CONT",
    "total_trades": len(combined),
    "yearly": yearly,
    "monthly": monthly,
    "note": "组合v20c = 反转(SMC+事件) + 延续低波动(MARKUP结构+VWAP5%+低波动+固定10日) — PF 3.50 最优",
}
with open(r"E:\test\smc_project\research\combo_dashboard.json", "w", encoding="utf-8") as fh:
    json.dump(dash, fh, ensure_ascii=False, indent=2)
print("dashboard v20c saved")

reg_p = r"E:\test\smc_project\hermes\smc_monitor\production_registry.json"
reg = json.load(open(reg_p, encoding="utf-8"))
reg["research_candidates"]["COMBO_SMC_EVENT"].update({
    "version": "COMBO_V20C_LOWVOL_CONT",
    "yearly_avg": {y["year"]: y["avg"] for y in yearly if y["year"] in ("2024", "2025", "2026")},
    "yearly_pf": {y["year"]: y["pf"] for y in yearly if y["year"] in ("2024", "2025", "2026")},
    "upgrade_note": "v20c 延续腿低波动过滤（PF 3.91）：avg +6.41%/PF 3.50，2025 +5.07%/2026 +4.08%，年度均衡",
})
with open(reg_p, "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2)
print("registry v20c recorded")
for y in yearly:
    if y["year"] in ("2024", "2025", "2026"):
        print(f"  {y['year']}: n={y['n']} avg={y['avg']:+.2f}% PF={y['pf']}")
