# -*- coding: utf-8 -*-
"""r38_accum_core.py —— R38 ACCUM 核心精选仓位优化(本轮正面发现下钻).

R38k 发现: ACCUM 桶(缩量吸筹+增持) n=243 avg+4.72% PF3.86, IS2.76→OOS6.87,
是全部 stage 桶中最强的(且样本外未劣化)。基线仅按 1/MAX_POS 等权, 未区分质量。

本脚本测试(组合级, 权重=风险敞口):
  A 等权(现状)              w=1 全部
  B ACCUM 加权 2x           w=2 (ACCUM) / 1 (其余白名单)
  C ACCUM 加权 3x           w=3 / 1
  D ACCUM 独占(只做ACCUM)   w=1 (ACCUM) / 0 (其余)
  E rank 分层(基线CSV rank) w = rank/4 (rank 越高仓越大)
  F ACCUM×rank 组合         w=2 (ACCUM) × (rank>=4 ? 1 : 0.5)

判据: 组合 PF/MDD/累计 PnL 与逐年稳定性(重点 2026)。
输入: r38_stage_relax.json (逐笔含 stage) + combo_v20f_trades.csv (rank)
纯研究, 不修改生产。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
recs = json.load(open(os.path.join(HERE, "r38_stage_relax.json"), encoding="utf-8"))
# 只保留基线白名单 + adx 条件(与冻结基线同口径)
base = [t for t in recs if t["stage"] in ("ACCUM", "DOWNTREND") and t["adx_ok"]]
print(f"基线白名单(ACCUM+DOWNTREND, adx>=20): n={len(base)}")
print(f"  其中 ACCUM={sum(1 for t in base if t['stage']=='ACCUM')} "
      f"DOWNTREND={sum(1 for t in base if t['stage']=='DOWNTREND')}")

# 载入 rank(冻结基线 CSV 按 symbol+date 匹配)
rank_map = {}
try:
    for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
        if r.get("src") != "EVENT":
            continue
        sym = str(r.get("symbol") or "").split(".")[0]
        d8 = str(r.get("entry_date") or "").replace("-", "")
        try:
            rank_map[(sym, d8)] = int(float(r.get("rank") or 0))
        except Exception:
            pass
except Exception as e:
    print(f"rank 载入失败(将跳过 E/F 方案): {e}")
print(f"rank 映射条数: {len(rank_map)}")

def stats(ws):
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
            "avg_raw": round(sum(contrib)/len(contrib), 2),
            "pf": round(pf, 2), "mdd": round(mdd, 0), "sum": round(sum(contrib), 0)}

SCHEMES = {
    "A 等权(现状)":      lambda t: 1.0,
    "B ACCUM×2":        lambda t: 2.0 if t["stage"] == "ACCUM" else 1.0,
    "C ACCUM×3":        lambda t: 3.0 if t["stage"] == "ACCUM" else 1.0,
    "D 仅ACCUM":        lambda t: 1.0 if t["stage"] == "ACCUM" else 0.0,
}
# 需要 rank 的方案
if rank_map:
    SCHEMES["E rank/4 加权"] = lambda t: max(0.25, min(2.0, rank_map.get((t["s"], t["d"]), 3)/3.0))
    SCHEMES["F ACCUM×2×rank闸"] = lambda t: (
        (2.0 if t["stage"] == "ACCUM" else 1.0) *
        (1.0 if rank_map.get((t["s"], t["d"]), 3) >= 4 else 0.5))

print("\n" + "="*100)
print("ACCUM 核心精选仓位方案 (组合级, 权重=风险敞口)")
print("="*100)
print(f"{'方案':<20}{'敞口':>7}{'每单位%':>10}{'原始均值%':>11}{'PF':>7}{'MDD%':>9}{'累计%':>9}")
res = {}
for name, fn in SCHEMES.items():
    ws = [(t["net"], fn(t)) for t in base]
    ws = [(n, w) for n, w in ws if w > 0]
    s = stats(ws); res[name] = s
    print(f"{name:<20}{s['exp']:>7.0f}{s['avg_exp']:>+9.2f}%{s['avg_raw']:>+10.2f}%{s['pf']:>7.2f}{s['mdd']:>9.0f}{s['sum']:>+9.0f}")

# 逐年稳定性(方案 B/D 对比等权)
print("\n逐年对比 (敞口加权 avg / PF):")
for y in ("2023", "2024", "2025", "2026"):
    ys = [t for t in base if t["d"][:4] == y]
    if not ys: continue
    row = f"  {y}: "
    for nm in ("A 等权(现状)", "B ACCUM×2", "D 仅ACCUM"):
        ws = [(t["net"], SCHEMES[nm](t)) for t in ys]
        ws = [(n, w) for n, w in ws if w > 0]
        s = stats(ws) if ws else None
        row += f"{nm[:6]}={s['avg_exp']:+.2f}%/{s['pf']:.2f}  " if s else f"{nm[:6]}=—  "
    print(row)

print("\nACCUM vs DOWNTREND 子集质量对比:")
for st in ("ACCUM", "DOWNTREND"):
    ts = [t for t in base if t["stage"] == st]
    s = stats([(t["net"], 1.0) for t in ts])
    print(f"  {st:<11} n={s['n']:>5} avg={s['avg_raw']:+.2f}% PF={s['pf']:.2f} 累计={s['sum']:+.0f}%")

print("\n裁定:")
b, a = res.get("B ACCUM×2"), res.get("A 等权(现状)")
if b and a and b["pf"] > a["pf"]:
    print(f"  ✅ ACCUM×2 提升 PF {a['pf']}→{b['pf']} (+{b['pf']-a['pf']:.2f}); "
          f"MDD {a['mdd']}→{b['mdd']}")
else:
    print(f"  ❌ ACCUM 加权未提升 PF (等权 {a['pf']} vs B {b['pf'] if b else '—'})")
d = res.get("D 仅ACCUM")
if d: print(f"  D(仅ACCUM) 每单位 {d['avg_exp']:+.2f}% PF {d['pf']:.2f} (n={d['n']}) —— 资金利用率低但质量最高")
json.dump({k: v for k, v in res.items()}, open(os.path.join(HERE, "r38_accum_core.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n→ r38_accum_core.json")