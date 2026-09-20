# -*- coding: utf-8 -*-
"""R58: E4'' 正交性检验 — 结构特征( v21 新列)对 pnl 的信息量 & 对现有 rank 分量的正交性
纯描述统计(READ-ONLY): 不构成采纳依据; 采纳需未来数据 frozen OOS(预注册纪律)。
输出: 各特征分组统计 + Spearman 相关矩阵(pnl, rank, 各结构列)。
"""
import csv, os, sys, io, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from collections import Counter

HERE = r"E:\test\smc_project\research"
rows = [r for r in csv.DictReader(open(os.path.join(HERE, "combo_v21_trades.csv"), encoding="utf-8-sig"))
        if r["src"] == "EVENT"]
print(f"EVENT legs: {len(rows)}")

def fnum(x):
    try: return float(x)
    except Exception: return None

def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 30: return None
    def rank(v):
        idx = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0]*len(v); i = 0
        while i < len(idx):
            j = i
            while j + 1 < len(idx) and v[idx[j+1]] == v[idx[i]]: j += 1
            avg = (i + j)/2 + 1
            for k in range(i, j+1): r[idx[k]] = avg
            i = j + 1
        return r
    rx, ry = rank([p[0] for p in pairs]), rank([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(rx)/n, sum(ry)/n
    cov = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a-mx)**2 for a in rx)); vy = math.sqrt(sum((b-my)**2 for b in ry))
    return round(cov/(vx*vy), 3) if vx and vy else 0.0

pnl = [fnum(r["net_pnl_pct"]) for r in rows]
# rank_score 从 rank_components 重构(与生成端同式)
rc = []
for r in rows:
    try:
        c = json.loads(r["rank_components"]) if r.get("rank_components") else {}
        rc.append(sum(c.values()))
    except Exception:
        rc.append(None)
print("rank 重构覆盖:", sum(1 for x in rc if x is not None))

def grp_stats(key, rs=None):
    rs = rs or rows
    out = {}
    for g in set(str(r[key]) for r in rs):
        sel = [r for r in rs if str(r[key]) == g]
        pn = [fnum(r["net_pnl_pct"]) for r in sel]
        pn = [x for x in pn if x is not None]
        w = [x for x in pn if x > 0]
        out[g] = {"n": len(pn), "avg": round(sum(pn)/len(pn), 2), "wr": round(len(w)/len(pn)*100, 1)}
    return out

print("\n== 结构特征分组统计 (EVENT) ==")
feats = {}
for k in ("trend_state", "zone_90d", "last_event_kind", "sl_below_structure"):
    feats[k] = grp_stats(k)
    print(f"  {k}: {feats[k]}")
# supply_layers / event_gap_bars 分桶
def bucket(v, edges):
    for i, e in enumerate(edges):
        if v <= e: return i
    return len(edges)
lay_edges = [0, 2, 5, 10]
gap_edges = [3, 10, 25]
lay_rows = [{"g": bucket(fnum(r["supply_layers"]), lay_edges) if fnum(r["supply_layers"]) is not None else -1,
             "pnl": fnum(r["net_pnl_pct"])} for r in rows]
gap_rows = [{"g": bucket(fnum(r["event_gap_bars"]), gap_edges) if fnum(r["event_gap_bars"]) is not None else -1,
             "pnl": fnum(r["net_pnl_pct"])} for r in rows]
for name, brs in (("supply_layers桶", lay_rows), ("event_gap桶", gap_rows)):
    out = {}
    for g in sorted(set(x["g"] for x in brs)):
        pn = [x["pnl"] for x in brs if x["g"] == g and x["pnl"] is not None]
        if pn: out[g] = {"n": len(pn), "avg": round(sum(pn)/len(pn), 2)}
    feats[name] = out
    print(f"  {name}: {out}")

print("\n== Spearman 相关 (对 pnl / 对 rank) ==")
corr = {}
for name, series in (
    ("trend_up", [1.0 if r["trend_state"] == "up" else 0.0 for r in rows]),
    ("discount", [1.0 if r["zone_90d"] == "discount" else 0.0 for r in rows]),
    ("supply_layers", [fnum(r["supply_layers"]) for r in rows]),
    ("event_gap", [fnum(r["event_gap_bars"]) for r in rows]),
    ("sl_below", [fnum(r["sl_below_structure"]) for r in rows]),
):
    corr[name] = {"vs_pnl": spearman(series, pnl), "vs_rank": spearman(series, [float(x) if x is not None else None for x in rc])}
    print(f"  {name}: vs_pnl={corr[name]['vs_pnl']} vs_rank={corr[name]['vs_rank']}")

# rank 分量本身对 pnl 的区分力(对照)
print("\n== rank 分量对 pnl (分量=1 vs =0 的 avg 差) ==")
comp_delta = {}
for comp in ("stage", "vr1", "vr2", "span", "adx", "wt_down", "vol_cont", "etype"):
    a, b = [], []
    for r, c in zip(rows, rc):
        p = fnum(r["net_pnl_pct"])
        try:
            cj = json.loads(r["rank_components"])
        except Exception:
            continue
        v = cj.get(comp)
        if p is None or v is None: continue
        (a if v else b).append(p)
    if a and b:
        comp_delta[comp] = round(sum(a)/len(a) - sum(b)/len(b), 2)
print(" ", comp_delta)

out = {"n": len(rows), "feats": feats, "corr": corr, "comp_delta": comp_delta}
json.dump(out, open(os.path.join(HERE, "handover", "r58_e4pp_orthogonality.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n写出 handover/r58_e4pp_orthogonality.json")
