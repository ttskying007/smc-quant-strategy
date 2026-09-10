# -*- coding: utf-8 -*-
"""v4_d1c_wfo.py —— D1 补充: E-score WFO 稳健性检验(预注册判定③)
上一批只做了全期五分位单调(ρ=0.924)。WFO 检验:
  12 个月 IS 窗口内学 E 分位切分点 → 后 3 个月 OOS 用 IS 切分点分桶 → 滚动前推。
若 OOS 各窗 Q1 avg<Q3 avg(单调方向保持) 在 ≥5/7 窗成立 → E-score 稳健(非全期拟合假象)。
预注册: <5/7 窗保持 → D1 判"样本内拟合", 降级为研究特征。"""
import csv, glob, io, json, math, os, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
ETF = r"E:\test\smc_project\hermes\kline_cache_etf"

def load_index(name):
    fp = os.path.join(ETF, name)
    if not os.path.exists(fp):
        return []
    j = json.load(open(fp, encoding="utf-8"))
    bars = j if isinstance(j, list) else j.get("data") or j.get("bars") or []
    out = []
    for b in bars:
        t = str(b.get("t") or b.get("date") or "")[:10].replace("-", "")
        if len(t) == 8:
            out.append((t, float(b["c"])))
    out.sort()
    return out

sh = load_index("000001_SH_day.json")
mid = load_index("000852_SH_day.json") or load_index("000300_SH_day.json")

def idx_at(arr, d8, days=20):
    w = [x for x in arr if x[0] <= d8]
    if len(w) < days + 1:
        return None
    return {"r20": w[-1][1] / w[-1 - days][1] - 1,
            "off_high": w[-1][1] / max(x[1] for x in w[-days * 3:]) - 1}

files = sorted(glob.glob(KT + os.sep + "*_daily_800.json"))
nh = defaultdict(lambda: [0, 0])
for fp in files:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    cl = sorted((str(b.get("t"))[:8], float(b["c"])) for b in raw if b.get("t"))
    for k in range(25, len(cl)):
        if k < 20:
            continue
        nh[cl[k][0]][1] += 1
        if cl[k][1] >= max(x[1] for x in cl[k - 20:k]):
            nh[cl[k][0]][0] += 1

def escore(d8):
    f1 = (nh[d8][0] / nh[d8][1]) if nh.get(d8) and nh[d8][1] >= 200 else None
    m = idx_at(mid, d8)
    s = idx_at(sh, d8)
    if f1 is None or m is None or s is None:
        return None
    return round(0.4 * min(1, max(0, f1 / 0.15)) + 0.4 * min(1, max(0, -m["off_high"] / 0.10))
                 + 0.2 * min(1, max(0, s["r20"] / 0.05)), 4)

rows = [r for r in csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                       encoding="utf-8-sig")) if r.get("src") == "EVENT"]
data = [(r["entry_date"], escore(r["entry_date"]), float(r["net_pnl_pct"]))
        for r in rows]
data = [(d, e, ret) for d, e, ret in data if e is not None]
data.sort()
print(f"可配对 {len(data)} 笔 ({data[0][0][:6]}~{data[-1][0][:6]})")

# WFO: IS=12月 学分位切点 → OOS=3月 用切点分桶
months = sorted({d[:6] for d, _, _ in data})
def qcuts(vals):
    v = sorted(vals)
    return [v[len(v) // 5 * i] for i in range(1, 5)]

wins = []
for w0 in range(0, len(months) - 15, 3):
    is_m = months[w0:w0 + 12]
    oos_m = months[w0 + 12:w0 + 15]
    if not oos_m:
        break
    is_vals = [e for d, e, _ in data if d[:6] in is_m]
    oos = [(e, ret) for d, e, ret in data if d[:6] in oos_m]
    if len(is_vals) < 60 or len(oos) < 15:
        continue
    cuts = qcuts(is_vals)
    def q(e):
        for qi, c in enumerate(cuts):
            if e <= c:
                return qi + 1
        return 5
    oos_q = defaultdict(list)
    for e, ret in oos:
        oos_q[q(e)].append(ret)
    q1 = sum(oos_q[1]) / len(oos_q[1]) if oos_q[1] else None
    q3 = sum(oos_q[3]) / len(oos_q[3]) if oos_q[3] else None
    q5 = sum(oos_q[5]) / len(oos_q[5]) if oos_q[5] else None
    hold = (q1 is not None and q3 is not None and q1 < q3) or (q3 is not None and q5 is not None and q3 < q5)
    wins.append({"oos": f"{oos_m[0]}~{oos_m[-1]}", "n_oos": len(oos),
                 "q1": round(q1, 2) if q1 is not None else None,
                 "q3": round(q3, 2) if q3 is not None else None,
                 "q5": round(q5, 2) if q5 is not None else None,
                 "monotonic_q1_lt_q3_or_q3_lt_q5": hold})

n_hold = sum(1 for w in wins if w["monotonic_q1_lt_q3_or_q3_lt_q5"])
out = {"windows": wins, "n_windows": len(wins), "n_hold": n_hold,
       "preregistered_verdict": ("E-score稳健(WFO通过)" if n_hold >= math.ceil(len(wins) * 0.7)
                                  else "E-score降级为研究特征(WFO不稳健)")}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D1C_EscoreWFO.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
for w in wins:
    print(f"  {w['oos']}: n={w['n_oos']} Q1={w['q1']} Q3={w['q3']} Q5={w['q5']} 单调保持={w['monotonic_q1_lt_q3_or_q3_lt_q5']}")
print(f"\nWFO {n_hold}/{len(wins)} 窗保持 → {out['preregistered_verdict']}")
print("已写 handover/V4_D1C_EscoreWFO.json")