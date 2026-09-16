# -*- coding: utf-8 -*-
"""r38_regime_decomp.py —— regime 归因偏移的机制分解 (ADX 变 vs 持有期变).

r38_regime_ab 确认: legacy PASS → 新基线 FAIL。
  ① legacy(DX,h15): BEAR +4.648  >  BULL +3.669   → PASS
  ② new  (Wilder,h12): BEAR +3.176 < BULL +4.271  → FAIL

两个变量同时变了(ADX: DX→Wilder; 持有期: 15→12), 必须分离出驱动方:
  ③ Wilder,h15 (r38_combo_wilder_h15_trades.csv) —— 只变 ADX
  ④ Wilder,h12 (= 新基线 EVENT 腿)

判据:
  · 若 ③ 的 BEAR 仍高(~4.6) → **持有期(15→12)是驱动方**, ADX 变更中性
  · 若 ③ 的 BEAR 已降至 ~3.2 → **ADX 变更是驱动方**
纯诊断, 不修改任何数据。
"""
import csv, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = r"E:\test\smc_project\research"
sys.path.insert(0, HERE)
from core.regime import market_regime

CACHE = {}
def reg_of(d8):
    if d8 not in CACHE:
        try:
            r = market_regime(d8)
        except Exception:
            r = None
        CACHE[d8] = r["regime"] if r else "?"
    return CACHE[d8]

def buckets(path, label):
    if not os.path.exists(path):
        print("  %s: 缺文件" % label); return None
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig"))
            if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
    by = defaultdict(list)
    for r in rows:
        by[reg_of(r["entry_date"])].append(float(r["net_pnl_pct"]))
    out = {}
    for k, ps in by.items():
        w = [x for x in ps if x > 0]; l = [x for x in ps if x <= 0]
        out[k] = {"n": len(ps), "avg": sum(ps)/len(ps),
                  "pf": (sum(w)/abs(sum(l))) if sum(l) else 99.0}
    return out

CASES = [
    ("① legacy  DX   + h15", os.path.join(HERE, "archive", "combo_v20f_trades_legacy_dx_h15.csv")),
    ("③ Wilder  + h15",      os.path.join(HERE, "r38_combo_wilder_h15_trades.csv")),
    ("④ Wilder  + h12(=新基线)", os.path.join(HERE, "combo_v20f_trades.csv")),
]
res = {}
print("=" * 92)
print("regime 归因分解 (同一 core.regime.market_regime 六态)")
print("=" * 92)
for label, p in CASES:
    b = buckets(p, label)
    if not b: continue
    res[label] = b
    bear = b.get("BEAR", {}); bull = b.get("BULL", {}); panic = b.get("PANIC", {})
    print("\n%s" % label)
    for k in ("BULL", "BEAR", "SIDEWAYS", "PANIC", "RECOVERY", "ROTATION"):
        if k in b:
            print("    %-9s n=%4d avg=%+.3f%% pf=%5.2f" % (k, b[k]["n"], b[k]["avg"], b[k]["pf"]))
    if bear and bull:
        print("    BEAR %+.3f vs BULL %+.3f  → 弱市更优: %s"
              % (bear["avg"], bull["avg"], "PASS" if bear["avg"] > bull["avg"] else "FAIL"))
    if panic:
        print("    PANIC %+.3f (n=%d)" % (panic["avg"], panic["n"]))

print("\n" + "=" * 92)
print("机制判定:")
a = res.get("① legacy  DX   + h15", {})
b3 = res.get("③ Wilder  + h15", {})
b4 = res.get("④ Wilder  + h12(=新基线)", {})
if a and b3 and b4:
    bear_a = a.get("BEAR", {}).get("avg", 0); bear_3 = b3.get("BEAR", {}).get("avg", 0)
    bear_4 = b4.get("BEAR", {}).get("avg", 0)
    bull_a = a.get("BULL", {}).get("avg", 0); bull_3 = b3.get("BULL", {}).get("avg", 0)
    bull_4 = b4.get("BULL", {}).get("avg", 0)
    print("  BEAR: DX+h15 %+.3f → Wilder+h15 %+.3f → Wilder+h12 %+.3f" % (bear_a, bear_3, bear_4))
    print("  BULL: DX+h15 %+.3f → Wilder+h15 %+.3f → Wilder+h12 %+.3f" % (bull_a, bull_3, bull_4))
    d_adx_bear = bear_3 - bear_a
    d_hold_bear = bear_4 - bear_3
    print("  ΔBEAR 由 ADX 变: %+.3f | 由 持有期变: %+.3f" % (d_adx_bear, d_hold_bear))
    d_adx_bull = bull_3 - bull_a
    d_hold_bull = bull_4 - bull_3
    print("  ΔBULL 由 ADX 变: %+.3f | 由 持有期变: %+.3f" % (d_adx_bull, d_hold_bull))
    if abs(d_hold_bear) > abs(d_adx_bear):
        print("\n  → **持有期(15→12) 是 BEAR 变化的主驱动方** (|Δ| %.3f > %.3f)"
              % (abs(d_hold_bear), abs(d_adx_bear)))
    else:
        print("\n  → **ADX 变更是 BEAR 变化的主驱动方** (|Δ| %.3f > %.3f)"
              % (abs(d_adx_bear), abs(d_hold_bear)))
    print("  → 归因偏移是**两个口径修正的合力**, 非单一变量; 详见报告。")