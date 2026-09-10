# -*- coding: utf-8 -*-
"""v4_d1b_rank_e_matrix.py —— rank×E 双因子矩阵(D1 核心洞察落地)
假设: 事件腿真 alpha = rank(事件质量) × E(环境质量) 正交互补。
检验(预注册):
  ① 7×5 矩格 avg 的最优格 vs 最差格差 >5pp → 融合有信息
  ② 最差象限(rank≤2 或 E∈Q1) 合计占比与合计贡献 → 若贡献为负即"杀单区"
  ③ E∈Q4/Q5 且 rank≥3 的"黄金格" avg 应 > 全局 avg 一倍以上
用途: 不动生产; 为 D2v2(E 联动 SL 带)和 D3(融合入场)提供格子级证据。"""
import csv, glob, io, json, math, os, sys
from collections import defaultdict
sys.stdout.insert(0, "") if False else None
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
        hi20 = max(x[1] for x in cl[k - 20:k])
        nh[cl[k][0]][1] += 1
        if cl[k][1] >= hi20:
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
pairs = []
for r in rows:
    e = escore(r["entry_date"])
    if e is not None:
        pairs.append((int(r["rank"]), e, float(r["net_pnl_pct"])))
print(f"rank×E 可配对: {len(pairs)}")

es = sorted(e for _, e, _ in pairs)
qcut = [es[len(es) // 5 * i] for i in range(5)] + [es[-1]]
def eq(e):
    for qi in range(5):
        if e <= qcut[qi + 1] or qi == 4:
            return qi + 1
    return 5

M = defaultdict(list)
for rk, e, ret in pairs:
    M[(rk, eq(e))].append(ret)

print("\nrank\\E |" + "".join(f" Q{q}({qcut[q-1]:.2f}-{qcut[q]:.2f})" for q in range(1, 6)))
for rk in range(1, 8):
    line = f"  r{rk}   |"
    for q in range(1, 6):
        v = M.get((rk, q), [])
        line += f" {('n='+str(len(v))+' avg='+(f'{sum(v)/len(v):+.2f}' if v else '-')):>16}"
    print(line)

golden = [x for (rk, q), v in M.items() if rk >= 3 and q >= 4 for x in v]
dead = [x for (rk, q), v in M.items() if (rk <= 2 or q == 1) for x in v]
allv = [x for _, _, x in pairs]
st = lambda v: (round(sum(v) / len(v), 3), round(len([x for x in v if x > 0]) / len(v) * 100, 1),
                len(v)) if v else (None, None, 0)

ga, gw, gn = st(golden)
da, dw, dn = st(dead)
aa, aw, an = st(allv)
best_cell = max(((rk, q) for (rk, q) in M if M[(rk, q)]), key=lambda k: sum(M[k]) / len(M[k]))
worst_cell = min(((rk, q) for (rk, q) in M if M[(rk, q)]), key=lambda k: sum(M[k]) / len(M[k]))
spread = round(sum(M[best_cell]) / len(M[best_cell]) - sum(M[worst_cell]) / len(M[worst_cell]), 2)

out = {"matrix_avg": {f"r{rk}_Q{q}": round(sum(v) / len(v), 3) for (rk, q), v in M.items() if v},
       "matrix_n": {f"r{rk}_Q{q}": len(v) for (rk, q), v in M.items()},
       "golden_quadrant": {"rank>=3&E>=Q4": {"avg": ga, "wr": gw, "n": gn}},
       "dead_zone": {"rank<=2|E==Q1": {"avg": da, "wr": dw, "n": dn}},
       "global": {"avg": aa, "wr": aw, "n": an},
       "best_cell": f"r{best_cell[0]}_Q{best_cell[1]}", "worst_cell": f"r{worst_cell[0]}_Q{worst_cell[1]}",
       "spread_pp": spread,
       "preregistered": {
           "①融合有信息(spread>5pp)": spread > 5,
           "②杀单区贡献为负": da is not None and da < 0,
           "③黄金格>全局一倍": ga is not None and ga > aa * 2}}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D1B_rankE矩阵.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n黄金象限(rank≥3 & E∈Q4/Q5): avg={ga:+.3f} wr={gw}% n={gn}")
print(f"杀单区(rank≤2 或 E∈Q1):   avg={da:+.3f} wr={dw}% n={dn} (占{dn/an*100:.0f}%)")
print(f"全局: avg={aa:+.3f} | 最好格 {out['best_cell']} vs 最差格 {out['worst_cell']} spread={spread}pp")
print(f"预注册: ①{out['preregistered']['①融合有信息(spread>5pp)']} ②{out['preregistered']['②杀单区贡献为负']} ③{out['preregistered']['③黄金格>全局一倍']}")
print("已写 handover/V4_D1B_rankE矩阵.json")