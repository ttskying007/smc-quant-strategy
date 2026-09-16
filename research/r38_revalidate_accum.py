# -*- coding: utf-8 -*-
"""r38_revalidate_accum.py —— 重基线后复核 ACCUM×2 与 rank 门槛 (新基线上).

R38l 在 legacy 基线上得出 ACCUM×2 温和正面(PF 3.21→3.29)。重基线后基线
本身变了, 必须在**新基线**上复核该结论是否仍成立。

stage 数据来源: r38_stage_relax.json (stage_of 只用 ret60 + 量比, 与 ADX 无关,
故可跨口径 join)。按 (symbol, date) 匹配新基线 EVENT 交易。

测试(新基线 EVENT, 组合级, 权重=风险敞口):
  A 等权(现状)        w=1
  B ACCUM×2          w=2(ACCUM)/1(其余)
  C rank>=3 门槛      仅保留 rank>=3
  D rank>=4 门槛      仅保留 rank>=4
  E ACCUM×2 × rank>=3 组合
判据: 每单位收益 / PF / MDD / 逐年。
纯研究, 不修改生产。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = r"E:\test\smc_project\research"

def f(x, d=0.0):
    try: return float(x)
    except: return d

# stage 映射
stage_map = {}
sp = os.path.join(HERE, "r38_stage_relax.json")
if os.path.exists(sp):
    for r in json.load(open(sp, encoding="utf-8")):
        stage_map[(str(r.get("s")), str(r.get("d")))] = r.get("stage")
print("stage 映射条数: %d" % len(stage_map))

rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
print("新基线 EVENT: %d 笔" % len(ev))

recs = []
n_stage_hit = 0
for r in ev:
    sym = str(r.get("symbol") or "").split(".")[0]
    d8 = str(r.get("entry_date") or "").replace("-", "")
    st = stage_map.get((sym, d8))
    if st: n_stage_hit += 1
    try: rk = int(float(r.get("rank") or 0))
    except: rk = 0
    recs.append({"net": f(r["net_pnl_pct"]), "stage": st, "rank": rk, "d": d8})
print("stage 命中: %d / %d (%.1f%%)" % (n_stage_hit, len(recs), 100*n_stage_hit/len(recs)))

def combo(ws):
    if not ws: return None
    contrib = [n*w for n, w in ws]
    wins = [x for x in contrib if x > 0]; loss = [x for x in contrib if x <= 0]
    pf = sum(wins)/abs(sum(loss)) if sum(loss) else 99
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in contrib:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq-peak)
    tw = sum(w for _, w in ws)
    return {"n": len(contrib), "exp": round(tw, 0),
            "avg_exp": round(sum(contrib)/tw, 2) if tw else 0,
            "pf": round(pf, 2), "mdd": round(mdd, 0), "sum": round(sum(contrib), 0)}

SCHEMES = {
    "A 等权(现状)":        lambda t: (t["net"], 1.0),
    "B ACCUM×2":          lambda t: (t["net"], 2.0 if t["stage"] == "ACCUM" else 1.0),
    "C rank>=3 门槛":      lambda t: (t["net"], 1.0) if t["rank"] >= 3 else None,
    "D rank>=4 门槛":      lambda t: (t["net"], 1.0) if t["rank"] >= 4 else None,
    "E ACCUM×2 × rank>=3": lambda t: (t["net"], (2.0 if t["stage"] == "ACCUM" else 1.0)) if t["rank"] >= 3 else None,
}
print("\n" + "=" * 96)
print("新基线上的 ACCUM×2 与 rank 门槛复核")
print("=" * 96)
print("%-22s %7s %10s %8s %8s %9s" % ("方案", "敞口", "每单位%", "PF", "MDD%", "累计%"))
res = {}
for name, fn in SCHEMES.items():
    ws = []
    for t in recs:
        v = fn(t)
        if v is None: continue
        ws.append(v)
    s = combo(ws); res[name] = s
    print("%-22s %7.0f %+9.2f%% %8.2f %8.0f %+9.0f"
          % (name, s["exp"], s["avg_exp"], s["pf"], s["mdd"], s["sum"]))

print("\n逐年 (每单位收益% / PF):")
for y in ("2023", "2024", "2025", "2026"):
    ys = [t for t in recs if t["d"][:4] == y]
    if not ys: continue
    row = "  %s: " % y
    for nm in ("A 等权(现状)", "B ACCUM×2", "C rank>=3 门槛"):
        ws = []
        for t in ys:
            v = SCHEMES[nm](t)
            if v is not None: ws.append(v)
        s = combo(ws) if ws else None
        row += "%-12s " % ("%+.2f%%/%.2f" % (s["avg_exp"], s["pf"]) if s else "—")
    print(row)

print("\nACCUM / DOWNTREND / 其他 stage 质量(新基线):")
bys = defaultdict(list)
for t in recs:
    bys[t["stage"] or "(未匹配)"].append(t["net"])
for k, ps in sorted(bys.items(), key=lambda kv: -len(kv[1])):
    w = [x for x in ps if x > 0]; l = [x for x in ps if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    print("  %-12s n=%4d avg=%+.2f%% PF=%.2f" % (k, len(ps), sum(ps)/len(ps), pf))

print("\n裁定:")
a, b = res["A 等权(现状)"], res["B ACCUM×2"]
print("  ACCUM×2 vs 等权: 每单位 %+.2f%% → %+.2f%% (%+.2fpp), PF %.2f → %.2f (%+.2f)"
      % (a["avg_exp"], b["avg_exp"], b["avg_exp"]-a["avg_exp"], a["pf"], b["pf"], b["pf"]-a["pf"]))
if b["avg_exp"] > a["avg_exp"] and b["pf"] >= a["pf"]:
    print("  → ✅ ACCUM×2 在新基线上**仍成立**")
else:
    print("  → ⚠ ACCUM×2 在新基线上**效果改变**, 需复核")
for k in ("C rank>=3 门槛", "D rank>=4 门槛"):
    s = res[k]
    print("  %s: 每单位 %+.2f%% PF %.2f (敞口 %.0f, 保留 %.0f%%)"
          % (k, s["avg_exp"], s["pf"], s["exp"], 100*s["exp"]/len(recs)))