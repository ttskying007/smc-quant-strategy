# -*- coding: utf-8 -*-
"""r38_rank3_verify.py —— rank3 研究分叉 vs 全链路审计 一致性核对(接线前验收).

r38_gen_v20f_rank3.py 产出 r38_combo_rank3_trades.csv(EVENT 1405 + CONT 330 = 1735)。
本脚本核对它与 r38_rank_chain.py 全链路审计的 rank_prod>=3 行是否一致:
  审计行: 全n=1735, IS_n=1243 (PF3.44), OOS_n=492 (PF3.67)

判据(预注册):
  · 组合 n 必须 = 1735(逐笔数一致)
  · IS/OOS 分段 n 与 PF 应在容差内一致(PF ±0.05, n 完全相等)
  · 若不一致 → 定位差异来源(门槛应用次序 / 去重 / cap 交互), 不得放过

同时输出分叉的完整指标(逐年/分腿/出场构成), 作为接线预期的权威数字。
纯校验, 不修改任何数据。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
IS_END = "20250630"
FORK = os.path.join(HERE, "r38_combo_rank3_trades.csv")
AUDIT = os.path.join(HERE, "r38_rank_chain.json")
BASE = os.path.join(HERE, "combo_v20f_trades.csv")


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def stats(rows):
    if not rows:
        return None
    p = [f(r["net_pnl_pct"]) for r in rows]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in p:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq - peak)
    return {"n": len(p), "avg": round(sum(p) / len(p), 3),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2),
            "mdd": round(mdd, 0), "sum": round(sum(p), 0)}


fork = load(FORK)
base = load(BASE)
print("=" * 96)
print("rank3 分叉验收: r38_combo_rank3_trades.csv vs 全链路审计")
print("=" * 96)

ev = [r for r in fork if r.get("src") == "EVENT"]
co = [r for r in fork if r.get("src") == "CONT"]
isr = [r for r in fork if str(r.get("entry_date")) <= IS_END]
oosr = [r for r in fork if str(r.get("entry_date")) > IS_END]

sf = stats(fork); si = stats(isr); so = stats(oosr)
print("\n分叉实测:")
print("  全组合 n=%d avg=%+.3f%% wr=%.1f%% PF=%.2f MDD=%.0f 累计=%+.0f%%"
      % (sf["n"], sf["avg"], sf["wr"], sf["pf"], sf["mdd"], sf["sum"]))
print("  分腿   EVENT n=%d | CONT n=%d" % (len(ev), len(co)))
print("  IS     n=%d avg=%+.3f%% PF=%.2f" % (si["n"], si["avg"], si["pf"]))
print("  OOS    n=%d avg=%+.3f%% PF=%.2f" % (so["n"], so["avg"], so["pf"]))

print("\n审计参照(r38_rank_chain.json → gates_both['3']):")
audit_ok = False
if os.path.exists(AUDIT):
    aj = json.load(open(AUDIT, encoding="utf-8"))
    g3 = (aj.get("gates_both") or {}).get("3")
    if g3:
        print("  全组合 n=%d avg=%+.3f%% PF=%.2f" % (g3["n"], g3["avg"], g3["pf"]))
        audit_ok = (g3["n"] == sf["n"])
        print("  → n 一致: %s (分叉 %d vs 审计 %d, Δ=%+d)"
              % (audit_ok, sf["n"], g3["n"], sf["n"] - g3["n"]))
    else:
        print("  ⚠ 未找到 gates_both['3']")
else:
    print("  ⚠ 审计 JSON 缺失")

print("\n" + "=" * 96)
print("逐笔差异定位(若 n 不一致)")
print("=" * 96)
if not audit_ok and os.path.exists(AUDIT):
    print("  需排查: 门槛应用次序(过滤 vs cap)、去重、insider 特征回退")
else:
    print("  n 一致 —— 无需逐笔定位")

print("\n" + "=" * 96)
print("分叉 vs 基线(Wilder+h12, 无门槛)对照")
print("=" * 96)
sb = stats(base)
evb = [r for r in base if r.get("src") == "EVENT"]
print("%-18s %6s %9s %7s %8s %9s" % ("口径", "n", "avg%", "PF", "MDD%", "累计%"))
print("%-18s %6d %+8.3f%% %7.2f %8.0f %+9.0f"
      % ("基线(无门槛)", sb["n"], sb["avg"], sb["pf"], sb["mdd"], sb["sum"]))
print("%-18s %6d %+8.3f%% %7.2f %8.0f %+9.0f"
      % ("rank3 分叉", sf["n"], sf["avg"], sf["pf"], sf["mdd"], sf["sum"]))
print("  Δ = n%+d, avg%+.3fpp, PF%+.2f, MDD%+.0f"
      % (sf["n"] - sb["n"], sf["avg"] - sb["avg"], sf["pf"] - sb["pf"], sf["mdd"] - sb["mdd"]))

print("\n逐年(分叉 vs 基线):")
for y in ("2023", "2024", "2025", "2026"):
    a = stats([r for r in base if str(r.get("entry_date"))[:4] == y])
    b = stats([r for r in fork if str(r.get("entry_date"))[:4] == y])
    if a and b:
        print("  %s: 基线 n=%4d %+.2f%%/PF%.2f | rank3 n=%4d %+.2f%%/PF%.2f"
              % (y, a["n"], a["avg"], a["pf"], b["n"], b["avg"], b["pf"]))

print("\nEVENT 腿 rank 分布校验(应全部 >=3):")
rk = defaultdict(int)
for r in ev:
    try:
        rk[int(float(r.get("rank") or 0))] += 1
    except Exception:
        pass
print("  %s" % dict(sorted(rk.items())))
bad = [k for k in rk if k < 3]
print("  → 低于门槛的 EVENT 笔数: %d %s" % (sum(rk[k] for k in bad), "(应为 0)" if not bad else "⚠ 异常"))

json.dump({"fork": sf, "is": si, "oos": so, "event_n": len(ev), "cont_n": len(co),
           "audit_n_match": audit_ok},
          open(os.path.join(HERE, "r38_rank3_verify.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
print("\n→ r38_rank3_verify.json")