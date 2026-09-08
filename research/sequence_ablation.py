# -*- coding: utf-8 -*-
"""V1 蓝图第一项：SMC 事件顺序信息验证（Sequence Ablation，蓝图 §48）

问题：顺序本身是否携带信息？（True Sequence > Random Sequence 在 OOS 成立？）

数据：wdh/W1D1D4_seeds.csv —— 每笔带 sweep_date/ob_date/touch_date/reclaim_date/entry_date。
方法：
  ① 对每笔 seed 还原 5 事件的时间顺序（sweep→OB→touch→reclaim）
  ② 分类为严格顺序（sweep≤ob≤touch≤reclaim）/ 乱序
  ③ 对比两类净收益 + OOS 复读这一段分类是否稳定
  ④ 若乱序≥严格或 OOS 不符 → 顺序无信息，状态机无必要（V1 优先级重排）
"""
import csv, io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SEEDS = r"E:\test\smc_project\wdh\W1D1D4_seeds.csv"
TRADES = r"E:\test\smc_project\research\handover\最新回测数据\逐笔交易全明细.json"
OOS = "20250701"

def parse_d(x):
    s = str(x or "").replace("-", "")
    return int(s) if s.isdigit() and len(s) == 8 else None

seeds = list(csv.DictReader(open(SEEDS, encoding="utf-8-sig")))
print(f"seeds: {len(seeds)}")

# 交易匹配（SMC 腿）: 从全明细取 leg=SMC 且 symbol/entry_date 能匹配 seed
import json as _json
trades_all = _json.load(open(TRADES, encoding="utf-8")).get("trades", [])
trades_by = {(t["symbol"], t["entry_date"]): t for t in trades_all if t.get("leg") == "SMC"}
print(f"SMC trades: {len(trades_by)}")

def order_profile(seed):
    """事件时间顺序画像。返回 (strict, order_name, deltas)。"""
    d_sweep = parse_d(seed.get("sweep_date"))
    d_ob = parse_d(seed.get("ob_date"))
    d_touch = parse_d(seed.get("touch_date"))
    d_reclaim = parse_d(seed.get("reclaim_date"))
    d_entry = parse_d(seed.get("entry_date"))
    if not all([d_sweep, d_ob, d_touch, d_reclaim, d_entry]):
        return None, None, None
    # 严格顺序: sweep ≤ ob ≤ touch ≤ reclaim ≤ entry
    strict = d_sweep <= d_ob <= d_touch <= d_reclaim <= d_entry
    # 顺序描述（用于统计哪种顺序最常见）
    seq = [("s", d_sweep), ("o", d_ob), ("t", d_touch), ("r", d_reclaim)]
    seq_sorted = [x[0] for x in sorted(seq, key=lambda x: x[1])]
    order_name = "".join(seq_sorted)
    return strict, order_name, (d_sweep, d_ob, d_touch, d_reclaim, d_entry)


def stats(ts):
    if not ts:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    pn = [t["net_pnl_pct"] for t in ts if t.get("net_pnl_pct") is not None]
    pn = [x for x in pn if x is not None]
    if not pn:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    return {"n": len(pn), "avg": round(sum(pn) / len(pn), 3),
            "wr": round(len(w) / len(pn), 3),
            "pf": round(sum(w) / abs(sum(l)), 2) if l and sum(l) != 0 else 99}

# 分桶：严格顺序 vs 乱序（两用 seed 匹配 trades）
strict_trades, nonstrict_trades = [], []
unmatched = 0
for s in seeds:
    strict, order, deltas = order_profile(s)
    if strict is None:
        unmatched += 1
        continue
    key = (s["symbol"], s["entry_date"])
    t = trades_by.get(key)
    if not t:
        unmatched += 1
        continue
    (strict_trades if strict else nonstrict_trades).append({"t": t, "order": order, "entry_date": s["entry_date"]})

print(f"匹配: strict={len(strict_trades)} nonstrict={len(nonstrict_trades)} unmatched={unmatched}")

def split(ts):
    return [t for t in ts if t["entry_date"] < OOS], [t for t in ts if t["entry_date"] >= OOS]

# 全部/IS/OOS 分桶指标
print("\n== 顺序信息对比 ==")
for name, g in (("严格顺序(s≤o≤t≤r)", strict_trades), ("乱序", nonstrict_trades)):
    s_is, s_oos = split(g)
    print(f"  {name}: 全部={stats([x['t'] for x in g])} | IS n={s_is and stats([x['t'] for x in s_is])['n']} OOS n={s_oos and stats([x['t'] for x in s_oos])['n']}")
    print(f"      IS: {stats([x['t'] for x in s_is])} | OOS: {stats([x['t'] for x in s_oos])}")

# 顺序模式分布（哪些顺序最常见）
from collections import Counter
oc = Counter(x["order"] for x in strict_trades + nonstrict_trades)
print(f"\n顺序模式(前8): {oc.most_common(8)}")

# 预注册结论
strict_all = stats([x["t"] for x in strict_trades])
nonstrict_all = stats([x["t"] for x in nonstrict_trades])
strict_oos = stats([x["t"] for x in strict_trades if x["entry_date"] >= OOS])
nonstrict_oos = stats([x["t"] for x in nonstrict_trades if x["entry_date"] >= OOS])
c1 = strict_all["n"] >= 30
c2 = strict_all["avg"] > nonstrict_all["avg"]
c3 = strict_oos["avg"] > nonstrict_oos["avg"]
c4 = min(strict_oos["n"], nonstrict_oos["n"]) >= 30
verdict = "顺序有信息(严格>OOS乱序)" if (c1 and c2 and c3 and c4) else "顺序无显著信息/样本不足"

print("\n== 预注册结论 ==")
print(f"  ① 严格样本 n≥30: {c1} (n={strict_all['n']})")
print(f"  ② 全部期严格>乱序: {c2} ({strict_all['avg']:.2f}% vs {nonstrict_all['avg']:.2f}%)")
print(f"  ③ OOS 严格>乱序: {c3} ({strict_oos['avg']:.2f}% vs {nonstrict_oos['avg']:.2f}%)")
print(f"  ④ OOS 双侧样本≥30: {c4} ({strict_oos['n']}/{nonstrict_oos['n']})")
print(f"  结论: {verdict}")

out = {"strict_n": strict_all["n"], "nonstrict_n": nonstrict_all["n"],
       "strict_all": strict_all, "nonstrict_all": nonstrict_all,
       "strict_oos": strict_oos, "nonstrict_oos": nonstrict_oos,
       "order_dist": dict(oc.most_common(12)), "verdict": verdict}
with open(r"E:\test\smc_project\research\handover\sequence_ablation.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("\n已写 handover/sequence_ablation.json")