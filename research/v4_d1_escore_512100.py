# -*- coding: utf-8 -*-
"""v4_d1_escore.py —— V4 D1: 环境门 E-score 原型(研究重放, 不动生产)
第十轮审计 R1 根因: 同 rank3 事件 202606=-3.03% vs 202607=+9.31% —— 买点无环境区分。
E-score 三因子(决策时点可得, 无前视):
  F1 = 全市场 20D 新高占比(广度: 事件股所处的赚钱效应环境)
  F2 = 中证1000(000852) 20D 距高点(小盘风格: 事件股多为中小盘)
  F3 = 上证 20D 动量(大盘方向)
  E = 0.4×z(F1) + 0.4×z(F2) + 0.2×z(F3) → 分位归一 [0,1]
预注册判定(先写死, 跑完对照):
  ①1640 笔按 E 五分位分桶, avg 单调性: Spearman ρ>0.2 → 有效信号
  ②202606 全月 E 分位均值应显著低于 202607(对照验证: 环境门能否分离亏损月)
  ③若五分位不单调 → D1 弃(诚实, 同 Adaptive WFO 先例)
  ④仓位映射预演: E<0.3(底部五分位)仓位系数 0.3 重放 202606 净值改善量
数据: kline_cache_etf 指数日线上证/中证1000(000852 缺则用 000300 替代并标注) + 全市场K线。"""
import glob, io, json, os, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import csv as _csv

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
ETF = r"E:\test\smc_project\hermes\kline_cache_etf"
FEE = 0.2

# ---------- 指数数据 ----------
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
mid = load_index("SH_512100_daily.json") or load_index("000852_SH_day.json") or load_index("000300_SH_day.json")
MID_IS_300 = not (os.path.exists(os.path.join(ETF, "SH_512100_daily.json")) or os.path.exists(os.path.join(ETF, "000852_SH_day.json")))
print(f"指数: 上证 {len(sh)} 根, 中小盘 {'000300替代' if MID_IS_300 else '000852'} {len(mid)} 根")

def idx_at(arr, d8, days=20):
    w = [x for x in arr if x[0] <= d8]
    if len(w) < days + 1:
        return None
    return {"r20": w[-1][1] / w[-1 - days][1] - 1,
            "off_high": w[-1][1] / max(x[1] for x in w[-days * 3:]) - 1}

# ---------- F1: 全市场 20D 新高占比(每日, 决策时点) ----------
files = sorted(glob.glob(KT + os.sep + "*_daily_800.json"))
print(f"全市场 K线: {len(files)} 股")
nh = defaultdict(lambda: [0, 0])       # d8 -> [新高数, 样本数]
for fp in files:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    cl = [(str(b.get("t"))[:8], float(b["c"])) for b in raw if b.get("t")]
    cl.sort()
    for k in range(25, len(cl)):
        d8 = cl[k][0]
        hi20 = max(x[1] for x in cl[max(0, k - 20):k]) if k >= 20 else None
        if hi20:
            nh[d8][1] += 1
            if cl[k][1] >= hi20:
                nh[d8][0] += 1
newhi_pct = {d: (v[0] / v[1] if v[1] >= 200 else None) for d, v in nh.items()}

def f1_at(d8):
    return newhi_pct.get(d8)

# ---------- E-score ----------
def escore(d8):
    f1 = f1_at(d8)
    m = idx_at(mid, d8)
    s = idx_at(sh, d8)
    if f1 is None or m is None or s is None:
        return None
    # 简单固定权重(研究原型; 正式版 z-标准化按滚动 120 日窗口, 此处用固定域映射避免前视)
    e = 0.4 * min(1, max(0, f1 / 0.15)) + 0.4 * min(1, max(0, -m["off_high"] / 0.10)) + \
        0.2 * min(1, max(0, s["r20"] / 0.05))
    return round(e, 4)

# ---------- 1640 笔 EVENT 重放 ----------
rows = [r for r in _csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                        encoding="utf-8-sig")) if r.get("src") == "EVENT"]
have = []
for r in rows:
    e = escore(r["entry_date"])
    if e is not None:
        have.append((r, e))
print(f"可配 E-score 的 EVENT: {len(have)}/{len(rows)}")

# 五分位分桶
have.sort(key=lambda x: x[1])
qn = len(have) // 5
buckets = []
for qi in range(5):
    seg = have[qi * qn:(qi + 1) * qn] if qi < 4 else have[4 * qn:]
    rets = [float(r["net_pnl_pct"]) for r, _ in seg]
    w = sum(x for x in rets if x > 0); l = abs(sum(x for x in rets if x <= 0))
    buckets.append({"q": qi + 1, "n": len(seg), "avg": round(sum(rets) / len(rets), 3),
                    "wr": round(len([x for x in rets if x > 0]) / len(rets) * 100, 1),
                    "pf": round(w / l, 2) if l else 99.0,
                    "e_range": [round(min(e for _, e in seg), 3), round(max(e for _, e in seg), 3)]})

# 单调性 Spearman(手算)
import math
rk = list(range(1, 6))
xs = [b["avg"] for b in buckets]
mx, my = sum(rk) / 5, sum(xs) / 5
cov = sum((a - mx) * (b - my) for a, b in zip(rk, xs))
rho = cov / (math.sqrt(sum((a - mx) ** 2 for a in rk)) * math.sqrt(sum((b - my) ** 2 for b in xs)))
rho = round(rho, 3)

# 亏损月对照
for mth in ("202606", "202607", "202512", "202507"):
    es = [e for r, e in have if r["entry_date"][:6] == mth]
    if es:
        print(f"  {mth}: E均值={sum(es)/len(es):.3f} (n={len(es)})")

# ④ 仓位映射预演: E<0.3 → 系数0.3
e_by_month = defaultdict(list)
for r, e in have:
    e_by_month[r["entry_date"][:6]].append((float(r["net_pnl_pct"]), e))
sim_base, sim_gate = defaultdict(float), defaultdict(float)
for mth, pairs in sorted(e_by_month.items()):
    for ret, e in pairs:
        coef = 0.3 if e < 0.3 else 1.0
        sim_base[mth] += ret
        sim_gate[mth] += ret * coef
print(f"\n202606: 无门累计={sim_base['202606']:.1f}pt  E门(0.3系数)={sim_gate['202606']:.1f}pt")
print(f"202607: 无门={sim_base['202607']:.1f}pt  E门={sim_gate['202607']:.1f}pt(不应大幅损失)")
print(f"全期: 无门={sum(sim_base.values()):.0f}pt  E门={sum(sim_gate.values()):.0f}pt")

out = {"design": "E=0.4*新高达标 + 0.4*中小盘距高 + 0.2*上证动量(决策时点无前视)",
       "mid_proxy": "000300" if MID_IS_300 else "000852",
       "quintiles": buckets, "spearman_rho": rho,
       "month_e": {m: round(sum(e for _, e in v) / len(v), 3) for m, v in
                   sorted((m, [(r, e) for r, e in have if r["entry_date"][:6] == m])
                          for m in ("202606", "202607", "202512", "202507"))},
       "gate_sim": {"202606_base": round(sim_base["202606"], 1), "202606_gate": round(sim_gate["202606"], 1),
                    "202607_base": round(sim_base["202607"], 1), "202607_gate": round(sim_gate["202607"], 1),
                    "total_base": round(sum(sim_base.values()), 0), "total_gate": round(sum(sim_gate.values()), 0)},
       "preregistered_verdict": ("D1有效(五分位单调ρ>0.2)" if rho > 0.2 else "D1弃(不单调)")}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D1_环境门_512100复验.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n五分位:")
for b in buckets:
    print(f"  Q{b['q']}: n={b['n']} avg={b['avg']:+.2f} wr={b['wr']}% pf={b['pf']} E∈{b['e_range']}")
print(f"Spearman ρ={rho} → {out['preregistered_verdict']}")
print("已写 handover/V4_D1_环境门_512100复验.json")