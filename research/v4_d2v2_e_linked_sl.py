# -*- coding: utf-8 -*-
"""v4_d2v2_e_linked_sl.py —— D2v2: E 联动 SL 带(D1B 黄金象限放宽宽 SL)
D2v1 教训: 固定 3-8% 带虽 PF 1.90→2.17, 但 >8% 拒单 54.9% 超红线。
D2v2 设计(预注册):
  E 分位(决策时点) → SL 上限带:
    E∈Q4/Q5(黄金环境) → SL 允许至 10%(原 D1B 黄金象限 avg+5.95, 宽 SL 可活)
    E∈Q1/Q2(差环境)   → SL 上限收紧至 6%
    E∈Q3              → 8%(基准)
  SL_new = clip(max(3%, d), lo%, hi%[E])   其中 d=原 SL 距离
  拒单 = d > hi[E](买太远仍拒, 但黄金环境多容忍 2pp)
重放: 同 D2v1 近似法(救活保守记0) + E 逐笔配对(815 笔可配)。
判定(预注册): 拒单率 < 40% 且 OOS PF 提升 ≥0.15 → D2v2 可进 SHADOW;
              拒单率仍 >40% → SL 带与容量矛盾不可调和, 弃。"""
import csv, glob, io, json, os, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
ETF = r"E:\test\smc_project\hermes\kline_cache_etf"
OOS = "20250701"
FEE = 0.2

# ---- E-score(与 v4_d1 同源实现) ----
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

# E 分位切点(全期, 同 D1)
rows = [r for r in csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                       encoding="utf-8-sig")) if r.get("src") == "EVENT"]
pairs = []
for r in rows:
    e = escore(r["entry_date"])
    d = None
    if r.get("sl") and r.get("buy_price"):
        try:
            d = abs(float(r["buy_price"]) - float(r["sl"])) / float(r["buy_price"]) * 100
        except Exception:
            d = None
    if e is not None and d is not None:
        pairs.append((r, e, d))
es_sorted = sorted(e for _, e, _ in pairs)
qcut = [es_sorted[len(es_sorted) // 5 * i] for i in range(5)]
def eq(e):
    for qi in range(4):
        if e <= qcut[qi + 1]:
            return qi + 1
    return 5

def sl_band(q):
    return {1: (3.0, 6.0), 2: (3.0, 6.0), 3: (3.0, 8.0), 4: (3.0, 10.0), 5: (3.0, 10.0)}[q]

res = {"rejected": 0, "kept": 0, "rescued": 0}
sim_old, sim_new = [], []
for r, e, d in pairs:
    ret_old = float(r["net_pnl_pct"])
    mae = float(r.get("mae_pct") or 0)
    lo, hi = sl_band(eq(e))
    d_new = max(lo, min(hi, d))
    if d > hi:
        res["rejected"] += 1
        continue
    if d_new <= d + 0.05:
        res["kept"] += 1
        sim_old.append((r["entry_date"], ret_old)); sim_new.append((r["entry_date"], ret_old))
    else:
        if r["reason"] in ("SL_HIT", "SL_GAP") and abs(mae) < d_new:
            res["rescued"] += 1
            sim_old.append((r["entry_date"], ret_old)); sim_new.append((r["entry_date"], 0.0))
        else:
            res["kept"] += 1
            sim_old.append((r["entry_date"], ret_old)); sim_new.append((r["entry_date"], ret_old))

def stats(seq, oos=True):
    v = [p for d8, p in seq if (not oos or d8 >= OOS)]
    if not v:
        return {"n": 0}
    w = sum(x for x in v if x > 0); l = abs(sum(x for x in v if x <= 0))
    return {"n": len(v), "avg": round(sum(v) / len(v), 3),
            "wr": round(len([x for x in v if x > 0]) / len(v) * 100, 1),
            "pf": round(w / l, 2) if l else 99.0}

S_old, S_new = stats(sim_old), stats(sim_new)
rej_rate = round(res["rejected"] / len(pairs) * 100, 1)
pf_up = (S_new.get("pf") or 0) - (S_old.get("pf") or 0)

out = {"band_by_E": "Q1/Q2→[3,6] Q3→[3,8] Q4/Q5→[3,10]",
       "replay": {"old": S_old, "new": S_new},
       "rejected_rate": rej_rate, "rescued": res["rescued"], "kept": res["kept"],
       "n_pairs": len(pairs),
       "preregistered": {
           "①拒单率<40%": rej_rate < 40,
           "②PF提升≥0.15": pf_up >= 0.15,
           "verdict": ("D2v2可进SHADOW" if (rej_rate < 40 and pf_up >= 0.15)
                       else "D2v2弃(SL带与容量矛盾)")},
       "caveat": "E 用 000300 代理中证1000(000852 缺), 救活保守记0"}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D2V2_E联动SL带.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"可配对 {len(pairs)} 笔 (E×SL 双配)")
print(f"旧: {S_old}")
print(f"新: {S_new}")
print(f"拒单率: {rej_rate}% (D2v1 为 54.9%)  救活: {res['rescued']}")
print(f"预注册: ①{rej_rate < 40} ②PF提升{pf_up:.2f} ≥0.15 → {out['preregistered']['verdict']}")
print("已写 handover/V4_D2V2_E联动SL带.json")