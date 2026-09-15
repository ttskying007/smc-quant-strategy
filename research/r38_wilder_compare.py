# -*- coding: utf-8 -*-
"""r38_wilder_compare.py —— R38 P1-7 重基线 A/B 对比: 旧版DX基线 vs Wilder基线.

输入: combo_v20f_trades.csv (冻结基线, 旧版单窗DX) vs r38_combo_wilder_trades.csv
      (研究分叉, Wilder ADX; 其余口径完全一致)
产出: 组合级 (n/胜率/avg/中位/PF/MDD/累计) + 逐年 + 逐月 + RR 分布 + 出场构成 + IS/OOS
判据(预注册): Wilder 晋级需 avg/PF 提升且 MDD 不劣化且 OOS 不劣化。
纯研究, 不修改生产冻结线。
"""
import csv, io, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))
def f(x, d=0.0):
    try: return float(x)
    except: return d

base = load(HERE + r"\combo_v20f_trades.csv")
wil = load(HERE + r"\r38_combo_wilder_trades.csv")

def mat(rows):
    p = [f(r["net_pnl_pct"]) for r in rows]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in p:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq-peak)
    sp = sorted(p)
    return {"n": len(p), "wr": 100*len(w)/len(p), "avg": sum(p)/len(p),
            "med": sp[len(sp)//2], "pf": pf, "mdd": mdd, "sum": sum(p)}

print("="*96)
print("P1-7 重基线 A/B: 冻结基线(旧版单窗DX) vs Wilder ADX (其余口径完全一致)")
print("="*96)
b, w = mat(base), mat(wil)
print(f"{'指标':<14}{'冻结基线':>14}{'Wilder':>14}{'Δ':>14}")
for k, lab, fmt in (("n", "笔数", "{:.0f}"), ("wr", "胜率%", "{:.1f}"),
                    ("avg", "平均%", "{:+.2f}"), ("med", "中位%", "{:+.2f}"),
                    ("pf", "PF", "{:.2f}"), ("mdd", "MDD%", "{:.0f}"), ("sum", "累计%", "{:+.0f}")):
    print(f"{lab:<14}{fmt.format(b[k]):>14}{fmt.format(w[k]):>14}{fmt.format(w[k]-b[k]):>14}")

print("\n逐年:")
print(f"{'年':<8}{'n_基线':>8}{'avg_基线':>11}{'PF_基线':>9}  | {'n_W':>7}{'avg_W':>10}{'PF_W':>8}")
for y in sorted({r["entry_date"][:4] for r in base}):
    def _r(rows):
        ys = [r for r in rows if r["entry_date"][:4] == y]
        if not ys: return None
        m = mat(ys); return m
    rb, rw = _r(base), _r(wil)
    if not rb: continue
    rws = f"{rw['n']:>7}{rw['avg']:>+10.2f}{rw['pf']:>8.2f}" if rw else f"{'—':>7}{'—':>10}{'—':>8}"
    print(f"{y:<8}{rb['n']:>8}{rb['avg']:>+10.2f}{rb['pf']:>9.2f}  | {rws}")

print("\n逐月(4/5/6月历史弱势月):")
for mm in ("04", "05", "06"):
    def _m(rows):
        ms = [r for r in rows if r["entry_date"][4:6] == mm]
        return mat(ms) if ms else None
    rb, rw = _m(base), _m(wil)
    if rb and rw:
        print(f"  {mm}月: 基线 n={rb['n']} avg={rb['avg']:+.2f}% PF={rb['pf']:.2f} | "
              f"W n={rw['n']} avg={rw['avg']:+.2f}% PF={rw['pf']:.2f}")

print("\nIS/OOS (IS≤2025-06-30):")
for lab, rows in (("冻结基线", base), ("Wilder", wil)):
    is_r = [r for r in rows if r["entry_date"] <= "20250630"]
    oos_r = [r for r in rows if r["entry_date"] > "20250630"]
    mi, mo = mat(is_r), mat(oos_r)
    print(f"  {lab:<8} IS n={mi['n']:>4} avg={mi['avg']:+.2f}% PF={mi['pf']:.2f} | "
          f"OOS n={mo['n']:>4} avg={mo['avg']:+.2f}% PF={mo['pf']:.2f}")

print("\nRR 分布 (<=-1R 左尾):")
for lab, rows in (("冻结基线", base), ("Wilder", wil)):
    rr = [f(r["rr_exit"], None) for r in rows if r.get("rr_exit")]
    rr = [x for x in rr if x is not None]
    le = 100*sum(1 for x in rr if x <= -1)/len(rr) if rr else 0
    ge = 100*sum(1 for x in rr if x >= 1)/len(rr) if rr else 0
    print(f"  {lab:<8} <=-1R {le:.1f}% | >=1R {ge:.1f}%")

print("\n出场构成:")
for lab, rows in (("冻结基线", base), ("Wilder", wil)):
    by = defaultdict(int)
    for r in rows: by[r.get("reason") or "?"] += 1
    tot = sum(by.values())
    print(f"  {lab:<8} " + " ".join(f"{k}={v}({100*v/tot:.0f}%)"
          for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:5]))

print("\n" + "="*96)
print("裁定(预注册: avg/PF 提升 且 MDD 不劣化 且 OOS 不劣化):")
ok_avg = w["avg"] > b["avg"]
ok_pf = w["pf"] > b["pf"]
ok_mdd = w["mdd"] >= b["mdd"] * 1.1
isb = mat([r for r in base if r["entry_date"] > "20250630"])
isw = mat([r for r in wil if r["entry_date"] > "20250630"])
ok_oos = isw["pf"] >= isb["pf"] * 0.9
print(f"  avg↑ {ok_avg} ({b['avg']:+.2f}→{w['avg']:+.2f}) | PF↑ {ok_pf} ({b['pf']:.2f}→{w['pf']:.2f}) | "
      f"MDD {ok_mdd} ({b['mdd']:.0f}→{w['mdd']:.0f}) | OOS {ok_oos} ({isb['pf']:.2f}→{isw['pf']:.2f})")
print(f"  → {'✅ Wilder 晋级重基线候选(需走完整审计)' if all([ok_avg, ok_pf, ok_mdd, ok_oos]) else '⚠ 部分指标未过线, 需逐项复核'}")