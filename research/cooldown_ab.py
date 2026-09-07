# -*- coding: utf-8 -*-
"""P8-5 同股 N 日冷却 A/B 验证：事件家族重复(同股5日内连发多公告均触发)降重复/集中风险。
问题: 3183 事件中 9.9% 为同股 5 日内重复；每笔都被交易 → 过度交易 + 单股集中。
设计:
  A组(基线) = 现行(无冷却, 每公告触发一笔)
  B组      = 同股 N 日冷却 —— N 日窗口内只保留首个公告(先披露优先), N∈{3,5,10}
  C组      = 同股 N 日合并 —— N 日窗口内只保留 rank 最高者(最强优先), N∈{5}
预注册验收线(看结果前定):
  冷却后若 avg 与基线同向(>0) 且 样本减少 >10%(重复确实多) 且 PF 不显著下降
  → 冷却降重复不减质量, 建议启用; 若冷却后 avg/PF 明显更差 → 维持现状(重复公告携带增量信息)
"""
import csv, io, json, os, sys, datetime as _dt
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net_pnl_pct"] = float(r["net_pnl_pct"])
print(f"事件腿总: {len(rows)}")


def stats(ts):
    if not ts:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    pn = [t["net_pnl_pct"] for t in ts]
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    return {"n": len(ts), "avg": round(sum(pn) / len(pn), 4),
            "wr": round(len(w) / len(ts), 4),
            "pf": round(sum(w) / abs(sum(l)), 3) if l and sum(l) != 0 else 99.0}


def cool_first(rs, win):
    """冷却: 同股 win 日内只保留首个(先披露优先)。按时间排序, 记录每股上次交易日。"""
    out, last = [], {}
    for r in sorted(rs, key=lambda r: r["entry_date"]):
        c, ed = r["symbol"], r["entry_date"]
        try:
            dd = _dt.datetime.strptime(ed, "%Y%m%d")
        except Exception:
            out.append(r); continue
        if c in last and (dd - last[c]).days <= win:
            continue
        last[c] = dd
        out.append(r)
    return out


def cool_strong(rs, win):
    """合并: 同股 win 日内只保留 rank 最高者(最强优先)。按股票+时间窗分组后取最高rank。"""
    # 先按股票分组, 按时间排序
    byc = defaultdict(list)
    for r in rows:
        byc[r["symbol"]].append(r)
    out = []
    for c, lst in byc.items():
        lst = sorted(lst, key=lambda r: r["entry_date"])
        i = 0
        while i < len(lst):
            # 收集从 i 开始的 win 日内窗口
            win_set = [lst[i]]
            j = i + 1
            while j < len(lst):
                try:
                    gap = (_dt.datetime.strptime(lst[j]["entry_date"], "%Y%m%d")
                           - _dt.datetime.strptime(lst[i]["entry_date"], "%Y%m%d")).days
                except Exception:
                    break
                if gap <= win:
                    win_set.append(lst[j]); j += 1
                else:
                    break
            best = max(win_set, key=lambda r: float(r.get("rank") or 0))
            out.append(best)
            i = j
    return out


def split(ts, oos="20250701"):
    return [t for t in ts if t["entry_date"] < oos], [t for t in ts if t["entry_date"] >= oos]


base = stats(rows)
base_is, base_oos = split(rows)
base_is_s, base_oos_s = stats(base_is), stats(base_oos)
print(f"\nA组 基线(无冷却): {base} | IS{base_is_s['n']}avg{base_is_s['avg']}% | OOS{base_oos_s['n']}avg{base_oos_s['avg']}%")

res = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"), "baseline": base}
print("\n== B组 同股N日冷却(先披露优先) ==")
for win in (3, 5, 10):
    c = cool_first(rows, win)
    s = stats(c)
    c_is, c_oos = split(c)
    c_is_s, c_oos_s = stats(c_is), stats(c_oos)
    res[f"cool_first_{win}d"] = {"all": s, "is": c_is_s, "oos": c_oos_s}
    pct_reduce = (1 - s["n"] / base["n"]) * 100
    print(f"  {win}日: {s} | 样本减{pct_reduce:.1f}% | IS{c_is_s['n']}avg{c_is_s['avg']}% | OOS{c_oos_s['n']}avg{c_oos_s['avg']}%")

print("\n== C组 同股5日合并(rank最强优先) ==")
c5 = cool_strong(rows, 5)
s5 = stats(c5)
c5_is, c5_oos = split(c5)
c5_is_s, c5_oos_s = stats(c5_is), stats(c5_oos)
res["strong_merge_5d"] = {"all": s5, "is": c5_is_s, "oos": c5_oos_s}
print(f"  5日合并: {s5} | 样本减{(1-s5['n']/base['n'])*100:.1f}% | IS{c5_is_s['n']}avg{c5_is_s['avg']}% | OOS{c5_oos_s['n']}avg{c5_oos_s['avg']}%")

# 结论
print("\n== 结论（预注册: 冷却降重复不减质量 → 建议启用）==")
rec = "维持现状(重复公告携带增量信息, 冷却降低样本+avg)"
b5 = res.get("cool_first_5d", {}).get("all", {})
if b5.get("n", 0) < base["n"] * 0.9 and b5.get("avg", 0) > 0 and b5.get("pf", 0) >= base["pf"] * 0.85:
    rec = "建议启用 5 日冷却(先披露优先): 样本降10%+ 且 avg>0 / PF 未显著下降"
res["recommendation"] = rec
print(f"  {rec}")
res["verdict"] = {"baseline_avg": base["avg"], "cool5_avg": b5.get("avg"), "cool5_pf": b5.get("pf"),
                  "cool5_n_reduce": round((1 - b5.get("n", base["n"]) / base["n"]) * 100, 1)}

os.makedirs(r"E:\test\smc_project\research\handover", exist_ok=True)
with open(r"E:\test\smc_project\research\handover\同股冷却AB验证.json", "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=2)
print("已写 handover/同股冷却AB验证.json")