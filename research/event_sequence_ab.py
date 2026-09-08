# -*- coding: utf-8 -*-
"""V1 迭代3: 事件腿时序状态机验证（蓝图 §16/48 —— 时间/顺序是否携带信息）
在事件腿（有真实 OOS edge）上做时序A/B:
  ① 持仓时长(hold_bars)分桶 IS/OOS —— 更快结算是否预测更优 OOS
  ② 退出原因分桶 —— 价格路径(reason)是否携带 OOS 信息
  ③ 真序 vs 随机序置换(§48) —— 时序本身是否携带组合级信息
数据: combo_v20f_trades.csv 逐笔 EVENT(2084)
"""
import csv, io, json, os, random, sys
from collections import Counter
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
OOS = "20250701"
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net_pnl_pct"] = float(r["net_pnl_pct"])
    r["hold_bars"] = int(r.get("hold_bars") or 0)

def _stats(ts, oos):
    sel = [t for t in ts if (t["entry_date"] >= OOS) == oos]
    if not sel:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    pn = [t["net_pnl_pct"] for t in sel]
    w = [x for x in pn if x > 0]
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 3), "wr": round(len(w)/len(pn), 3),
            "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) and sum(x for x in pn if x <= 0) != 0 else 99}

out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"), "oos_from": OOS, "n": len(rows)}

print(f"== 事件腿时序A/B: {len(rows)} 笔 ==")
print("\n① 持仓时长分桶（IS/OOS）")
hb_buckets = {"1-3d": lambda h: 1 <= h <= 3, "4-6d": lambda h: 4 <= h <= 6,
              "7-9d": lambda h: 7 <= h <= 9, "10-15d": lambda h: 10 <= h <= 15}
out["hold_bars"] = {}
for name, f in hb_buckets.items():
    g = [t for t in rows if f(t["hold_bars"])]
    out["hold_bars"][name] = {"IS": _stats(g, False), "OOS": _stats(g, True)}
    print(f"  {name:8s}: all={len(g):4d} IS={_stats(g, False)} OOS={_stats(g, True)}")

print("\n② 退出原因分桶（IS/OOS）")
out["reason"] = {}
for reason in ("TP2_RUNNER", "TIME_STOP", "SL_HIT", "BE", "SL_GAP"):
    g = [t for t in rows if t.get("reason") == reason]
    out["reason"][reason] = {"IS": _stats(g, False), "OOS": _stats(g, True)}
    print(f"  {reason:12s}: all={len(g):4d} IS={_stats(g, False)} OOS={_stats(g, True)}")

print("\n③ 真序 vs 随机序置换（蓝图 §48: 时序是否携带组合级信息）")
random.seed(42)
# 组合净值: 事件腿按 entry_date 逐笔复利（等权）。真序净值 vs 随机打乱 entry_date 后同序列复利。
# 若真序净值终值显著优于随机分布 → 交易时序(聚类/动量)携带组合级信息。
def equity(pnls):
    eq = 1.0
    for p in pnls:
        eq *= (1 + p / 100)
    return eq
ordered = sorted(rows, key=lambda t: t["entry_date"])
pnl_seq = [t["net_pnl_pct"] for t in ordered]
actual_eq = equity(pnl_seq)
perm_eqs = []
for _ in range(1000):
    sh = pnl_seq[:]
    random.shuffle(sh)
    perm_eqs.append(equity(sh))
perm_eqs.sort()
pctile = sum(1 for x in perm_eqs if x <= actual_eq) / 1000
out["permutation"] = {"actual_equity": round(actual_eq, 3),
                      "perm_median": round(perm_eqs[500], 3),
                      "perm_2.5": round(perm_eqs[24], 3), "perm_97.5": round(perm_eqs[974], 3),
                      "actual_pctile": round(pctile * 100, 1),
                      "sequence_carries_info": pctile < 0.025 or pctile > 0.975}
print(f"  真序复利终值={actual_eq:.3f} | 随机序(1000x): 中位={perm_eqs[500]:.3f} 95%CI=[{perm_eqs[24]:.3f},{perm_eqs[974]:.3f}]")
print(f"  真序位于 {pctile*100:.1f} 百分位 → {'时序携带信息(显著偏离随机)' if out['permutation']['sequence_carries_info'] else '时序与随机无异(无组合级时序信息)'}")

print("\n== 预注册结论 ==")
# 时序对单笔EV不变, 但对组合净值(复利)顺序敏感 → 检查真序是否显著异于随机
hb_oos = {k: v["OOS"]["avg"] for k, v in out["hold_bars"].items()}
fast_better = hb_oos.get("1-3d", 0) > hb_oos.get("10-15d", 0)
out["verdict"] = {"hold_fast_vs_slow_OOS": hb_oos,
                  "fast_better_OOS": fast_better,
                  "sequence_info": out["permutation"]["sequence_carries_info"]}
print(f"  快结算(1-3d) vs 慢结算(10-15d) OOS: {hb_oos.get('1-3d')}% vs {hb_oos.get('10-15d')}% → 快优={fast_better}")
print(f"  组合时序信息: {'是' if out['permutation']['sequence_carries_info'] else '否'}")

with open(r"E:\test\smc_project\research\handover\V1迭代3_事件腿时序验证.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/V1迭代3_事件腿时序验证.json")