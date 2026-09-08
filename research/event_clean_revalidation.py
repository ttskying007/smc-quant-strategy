# -*- coding: utf-8 -*-
"""V1 迭代6: 纯净口径(真回购/增持, n≈1434)重验历史关键结论
污染修复剔除 31% 注销/激励类交易后, 以下结论是否仍成立:
  ① P0-4 分解: 样本量/Top5占比/bootstrap CI/事件后收益
  ② V1迭代3 持有桶: 10-15d 是否仍是 α 核心(单调性)
  ③ V1迭代4 WF: edge 跨窗口持续性 + k 选择稳定性
方法: 交易级披露标题重过新分类器 → 纯净集 → 逐项重跑。
"""
import csv, io, json, random, sqlite3, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import core.events as EV

DB = r"E:\test\smc_project\announce\smc_announce.db"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
OOS = "20250701"

rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net"] = float(r["net_pnl_pct"])
    r["hold_bars"] = int(r.get("hold_bars") or 0)
    r["risk_pct"] = float(r.get("risk_pct") or 0)

# 披露标题匹配(内存版): entry 前0-3天的公告
conn = sqlite3.connect(DB)
cur = conn.cursor()
ann_by_code = defaultdict(list)
cur.execute("SELECT stock_code, date, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for code, d, t in cur.fetchall():
    ann_by_code[str(code)].append((str(d)[:10].replace("-", ""), str(t)))
conn.close()
for c in ann_by_code:
    ann_by_code[c].sort(key=lambda x: x[0], reverse=True)

from datetime import date as _d
clean = []
for r in rows:
    e = _d(int(r["entry_date"][:4]), int(r["entry_date"][4:6]), int(r["entry_date"][6:8]))
    code = r["symbol"].split(".")[0]
    ok_keep = False
    for d8, t in ann_by_code.get(code, [])[:12]:
        dd = _d(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
        if (e - dd).days > 3:
            break
        if 0 <= (e - dd).days <= 3:
            if EV.classify_title(t)[0]:
                ok_keep = True
                break
    if ok_keep:
        clean.append(r)
print(f"纯净集: {len(clean)} / {len(rows)} ({len(clean)/len(rows):.1%})")

def _stats(ts, oos=False):
    sel = [t for t in ts if (t["entry_date"] >= OOS) == oos]
    if not sel:
        return {"n": 0}
    pn = [t["net"] for t in sel]
    w = [x for x in pn if x > 0]
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 3), "wr": round(len(w)/len(pn), 3),
            "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) and sum(x for x in pn if x <= 0) != 0 else 99}

out = {"n_clean": len(clean), "n_total": len(rows)}

print("\n① P0-4 分解重验(纯净)")
pn_all = [t["net"] for t in clean]
total_pnl = sum(pn_all)
pnl_sorted = sorted(pn_all)
top5_sum = sum(pnl_sorted[-5:])
random.seed(42)
boot = []
for _ in range(2000):
    sub = random.choices(pn_all, k=int(len(pn_all) * 0.8))
    boot.append(sum(sub) / len(sub))
boot.sort()
p0_clean = {"n": len(clean),
            "avg": round(total_pnl / len(pn_all), 3),
            "top5_share": round(top5_sum / total_pnl * 100, 1),
            "boot_ci95": [round(boot[int(0.025*len(boot))], 3), round(boot[int(0.975*len(boot))], 3)],
            "ci_positive": boot[int(0.025*len(boot))] > 0,
            "IS": _stats(clean), "OOS": _stats(clean, True)}
out["p0_clean"] = p0_clean
for k in ("n", "avg", "top5_share", "boot_ci95", "ci_positive"):
    print(f"  {k}: {p0_clean[k]}")
print(f"  IS: {p0_clean['IS']} | OOS: {p0_clean['OOS']}")

print("\n② 持有桶重验(纯净) —— 10-15d 是否仍为 α 核心")
hb = {}
for name, f in {"1-3d": lambda h: 1 <= h <= 3, "4-6d": lambda h: 4 <= h <= 6,
                "7-9d": lambda h: 7 <= h <= 9, "10-15d": lambda h: 10 <= h <= 15}.items():
    g = [t for t in clean if f(t["hold_bars"])]
    hb[name] = {"IS": _stats(g), "OOS": _stats(g, True)}
    print(f"  {name:8s}: IS={hb[name]['IS']} OOS={hb[name]['OOS']}")
mono = (hb["1-3d"]["OOS"]["avg"] < hb["4-6d"]["OOS"]["avg"] < hb["10-15d"]["OOS"]["avg"])
out["hold_clean"] = hb
out["hold_monotone_OOS"] = mono
print(f"  单调性(1-3d<4-6d<10-15d): {mono}")

print("\n③ Walk-Forward 重验(纯净) —— edge 跨窗口持续 + k 选择")
# 市场代理(决策时点可得) —— 与迭代4同法
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
snap = json.load(open(KT + r"\.mkt_sample.json", encoding="utf-8"))
code2bars = {}
for f in snap:
    try:
        raw = json.load(open(KT + "\\" + f, encoding="utf-8"))
        b2 = sorted((("".join(c for c in str(x.get("t") or "") if c.isdigit())[:8], float(x["c"]))
                     for x in raw if x.get("c") and x.get("o")), key=lambda x: x[0])
        if len(b2) >= 25:
            code2bars[f] = b2
    except Exception:
        continue
def proxy_on(d8):
    rets = []
    for f, b2 in code2bars.items():
        ds = [x[0] for x in b2]
        i = None
        for k in range(len(ds) - 1, -1, -1):
            if ds[k] <= d8:
                i = k; break
        if i is None or i < 20:
            continue
        rets.append(b2[i][1] / b2[i - 20][1] - 1)
    return sum(rets) / len(rets) if rets else None
for t in clean:
    t["proxy"] = proxy_on(t["entry_date"])

def shift_ym(m, n):
    y, mm = int(m[:4]), int(m[4:6])
    t_ = y * 12 + mm - 1 + n
    return f"{t_//12:04d}{t_%12+1:02d}"
by_month = defaultdict(list)
for t in clean:
    by_month[t["entry_date"][:6]].append(t)
months = sorted(by_month)

def eq_metrics(trs, k):
    eq = 1.0
    n = 0
    contrib = []
    for t in sorted(trs, key=lambda x: x["entry_date"]):
        if t["proxy"] is None or t["risk_pct"] <= 0:
            continue
        w = max(0.3, min(2.0, 1 - k * t["proxy"]))
        pos = min(1.0 / t["risk_pct"] / 100, 0.25)
        c = w * pos * t["net"] / 100
        eq *= (1 + c)
        contrib.append(c)
        n += 1
    return {"n": n, "eq": round(eq, 4), "avg": round(sum(contrib)/len(contrib)*100, 3) if contrib else 0}

wf_windows = []
cur_m = months[0]
KS = [1.0, 1.5, 2.0, 2.5, 3.0]
while True:
    tr_end = shift_ym(cur_m, 12)
    te_start, te_end = tr_end, shift_ym(tr_end, 3)
    if te_start > months[-1]:
        break
    tr_tr = [t for m in months if cur_m <= m < tr_end for t in by_month[m]]
    te_tr = [t for m in months if te_start <= m < te_end for t in by_month[m]]
    if len(tr_tr) >= 25 and len(te_tr) >= 4:
        best_k, best_v = None, -1e18
        for k in KS:
            v = sum(max(0.3, min(2.0, 1 - k * t["proxy"])) * t["net"] * (1.0 / t["risk_pct"] / 100)
                    for t in tr_tr if t["proxy"] is not None and t["risk_pct"] > 0)
            if v > best_v:
                best_k, best_v = k, v
        wf = eq_metrics(te_tr, best_k)
        f1 = eq_metrics(te_tr, 1.0)
        wf_windows.append({"test": f"{te_start}~{te_end}", "n": len(te_tr), "k": best_k,
                          "wf_eq": wf["eq"], "fixed1_eq": f1["eq"]})
    cur_m = shift_ym(cur_m, 3)
prod_wf = 1.0
prod_f1 = 1.0
for w in wf_windows:
    prod_wf *= w["wf_eq"]; prod_f1 *= w["fixed1_eq"]
    print(f"  {w['test']}: n={w['n']:3d} k={w['k']} WF eq={w['wf_eq']:.4f} vs 固定1={w['fixed1_eq']:.4f}")
wf_summary = {"windows": len(wf_windows), "prod_wf": round(prod_wf, 3), "prod_fixed1": round(prod_f1, 3),
              "pos_windows": sum(1 for w in wf_windows if w["wf_eq"] > 1.0),
              "k_hist": {str(k): sum(1 for w in wf_windows if w["k"] == k) for k in KS}}
out["wf_clean"] = {"windows": wf_windows, "summary": wf_summary}
print(f"  汇总: {wf_summary}")

print("\n== 纯净口径重验判定 ==")
v1 = p0_clean["ci_positive"] and p0_clean["top5_share"] < 30
v2 = mono
v3 = prod_wf > 1.0
out["verdict"] = {"P0_4_decomposition_holds": v1, "hold_buckey_alpha_core_holds": v2, "wf_edge_persists": v3}
print(f"  ① P0-4 分解成立(CI正+Top5<30%): {v1}")
print(f"  ② 10-15d 持有桶仍是 α 核心(单调): {v2}")
print(f"  ③ WF edge 跨窗口持续(净值>1): {v3}")

json.dump(out, open(r"E:\test\smc_project\research\handover\V1迭代6_纯净口径重验.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/V1迭代6_纯净口径重验.json")