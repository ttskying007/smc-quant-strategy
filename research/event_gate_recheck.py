# -*- coding: utf-8 -*-
"""事件腿 P1 门禁复检（第七轮 P2 关键）：修复 ep<sl bug + 统一过滤后重跑 Bootstrap 稳健性。
原门禁(PF7.9/avg+7.07/CI[7.13,8.76])基于带 bug 数据 → 作废，以下为修复后真实门禁。
含: 全样本 + 10×80% bootstrap + 去重(5日窗)后 + 逐年 OOS。
"""
import csv, io, json, os, random, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import datetime as _dt

CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig")) if r.get("src") == "EVENT"]
for r in rows:
    r["net_pnl_pct"] = float(r["net_pnl_pct"]) if r.get("net_pnl_pct") not in (None, "", "None") else None
rows = [r for r in rows if r.get("net_pnl_pct") is not None]
print(f"事件腿: {len(rows)}")


def stats(pn):
    if not pn:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    return {"n": len(pn), "avg": round(sum(pn) / len(pn), 4),
            "wr": round(len(w) / len(pn), 4),
            "pf": round(sum(w) / abs(sum(l)), 3) if l and sum(l) != 0 else 99.0}


def dedup(rs, win=5):
    out, last = [], {}
    for r in sorted(rs, key=lambda r: r["entry_date"]):
        c = r["symbol"]; ed = r["entry_date"]
        try:
            dd = _dt.datetime.strptime(ed, "%Y%m%d")
        except Exception:
            out.append(r); continue
        if c in last and (dd - last[c]).days <= win:
            continue
        last[c] = dd
        out.append(r)
    return out


res = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S")}

# 全样本
all_pn = [r["net_pnl_pct"] for r in rows]
res["full"] = stats(all_pn)
print(f"全样本: {res['full']}")

# 10×80% bootstrap
random.seed(42)
avgs, pfs, cis = [], [], []
for _ in range(10):
    sub = random.sample(rows, int(len(rows) * 0.8))
    pn = [r["net_pnl_pct"] for r in sub]
    s = stats(pn)
    avgs.append(s["avg"]); pfs.append(s["pf"])
res["bootstrap10x80"] = {"avg_mean": round(sum(avgs) / len(avgs), 4),
                          "avg_min": round(min(avgs), 4), "avg_max": round(max(avgs), 4),
                          "pf_mean": round(sum(pfs) / len(pfs), 3),
                          "pf_min": round(min(pfs), 3)}
print(f"bootstrap10×80%: avg[{min(avgs):.4f},{max(avgs):.4f}] PF[{min(pfs):.3f},{max(pfs):.3f}]")

# 去重后
dd = dedup(rows)
res["dedup5d"] = stats([r["net_pnl_pct"] for r in dd])
print(f"去重(5日窗)后: {res['dedup5d']}")

# 逐年
res["yearly"] = {}
for y in sorted({r["entry_date"][:4] for r in rows}):
    yp = [r["net_pnl_pct"] for r in rows if r["entry_date"][:4] == y]
    res["yearly"][y] = stats(yp)
print("逐年:", {y: res['yearly'][y]['avg'] for y in res['yearly']})

# OOS(20250701后)
oos = [r["net_pnl_pct"] for r in rows if r["entry_date"] >= "20250701"]
res["oos"] = stats(oos)
print(f"OOS(>=20250701): {res['oos']}")

# P1 门禁判定：avg>0 且 PF>1.5 且 bootstrap 全为正（非过拟合）
s_full = res["full"]
c_avg = s_full["avg"] > 0
c_pf = s_full["pf"] > 1.5
c_boot = min(avgs) > 0 and min(pfs) > 1.2
c_oos = res["oos"]["avg"] > 0
c_dedup = res["dedup5d"]["avg"] > 0 and res["dedup5d"]["pf"] > 1.5
res["gate"] = {"avg_gt0": c_avg, "pf_gt1.5": c_pf, "bootstrap_pos": c_boot,
               "oos_pos": c_oos, "dedup_pos": c_dedup,
               "PASS": c_avg and c_pf and c_boot and c_oos and c_dedup}
print(f"\n门禁: avg>0:{c_avg} PF>1.5:{c_pf} bootstrap正:{c_boot} OOS正:{c_oos} 去重后正:{c_dedup}")
print(f"P1 门禁复检: {'✅ PASS（修复后事件腿仍满足生产门槛）' if res['gate']['PASS'] else '❌ FAIL（修复后事件腿不达标，需重新评估生产资格）'}")

os.makedirs(r"E:\test\smc_project\research\handover", exist_ok=True)
with open(r"E:\test\smc_project\research\handover\事件腿P1门禁复检.json", "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=2)
print("已写 handover/事件腿P1门禁复检.json")