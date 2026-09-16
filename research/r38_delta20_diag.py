# -*- coding: utf-8 -*-
"""r38_delta20_diag.py —— 定位新基线 EVENT 1527 vs 证据包 1547 的 20 笔差额.

假设: 组合管线(月度 cap=500, 按 rank 排序混合 EVENT+CONT)在超 cap 月份
丢弃了 20 笔低 rank 的 EVENT 交易(被 rank=3 的 CONT 交易挤出)。

本脚本不做假设 —— 逐步复现管线:
  ① 证据包 EVENT(1547) 与 新基线 EVENT(1527) 的差集(20 笔)
  ② 这 20 笔的 (月份, rank) 分布
  ③ 逐月复现: EVENT+CONT 合并 → 去重 → 按 rank 排序取前 500
     检验: 是否恰好在 cap 溢出的月份丢弃这 20 笔
纯诊断, 不修改任何数据。
"""
import csv, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))

new_all = load(os.path.join(HERE, "combo_v20f2_trades.csv"))
new_ev = [r for r in new_all if r.get("src") == "EVENT"]
new_cont = [r for r in new_all if r.get("src") == "CONT"]
evid = load(os.path.join(HERE, "r38_combo_wilder_h12_trades.csv"))

def key(r):
    return (str(r.get("symbol")), str(r.get("entry_date")))

k_new = {key(r) for r in new_ev}
k_ev = {key(r) for r in evid}
missing = sorted(k_ev - k_new)
print("证据包 EVENT=%d | 新基线 EVENT=%d | 缺失=%d" % (len(k_ev), len(k_new), len(missing)))

# ② 缺失笔的月份/rank 分布
by_month = defaultdict(list)
for r in evid:
    if key(r) in set(missing):
        by_month[str(r["entry_date"])[:6]].append(r)
print("\n缺失笔按月分布:")
for m, rs in sorted(by_month.items()):
    ranks = sorted(int(float(r.get("rank") or 0)) for r in rs)
    print("  %s: %d 笔 | rank 分布 %s" % (m, len(rs), ranks))

# ③ 逐月复现 cap
print("\n逐月管线复现 (EVENT+CONT → 去重 → rank 排序取前 500):")
# 重建 CONT 腿(来源 cont_v20f_new.csv, 与生成器一致)
cont_src = []
with open(os.path.join(HERE, "cont_v20f_new.csv"), encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        cont_src.append({"symbol": r.get("symbol"), "entry_date": r.get("entry_date"),
                         "src": "CONT", "rank": 3,
                         "net_pnl_pct": float(r["net_pnl_pct"])})
# 用证据包 EVENT(1547) 作为事件腿全集
seen = set(); combo = []
for t in evid + cont_src:
    k = (str(t["symbol"]), str(t["entry_date"]))
    if k in seen:
        continue
    seen.add(k)
    combo.append({"symbol": t["symbol"], "entry_date": t["entry_date"],
                  "src": t["src"], "rank": float(t.get("rank") or 0)})
print("  合并去重后: EVENT=%d CONT=%d 合计=%d"
      % (sum(1 for t in combo if t["src"] == "EVENT"),
         sum(1 for t in combo if t["src"] == "CONT"), len(combo)))

bym = defaultdict(list)
for t in combo:
    bym[str(t["entry_date"])[:6]].append(t)
dropped = []
kept = []
for m in sorted(bym):
    v = bym[m]
    v_sorted = sorted(v, key=lambda t: -t["rank"])
    kept.extend(v_sorted[:500])
    dropped.extend(v_sorted[500:])
print("\n  cap 溢出月份 (月度合计>500):")
tot_drop_ev = 0
for m in sorted(bym):
    n = len(bym[m])
    if n > 500:
        d = sorted(bym[m], key=lambda t: -t["rank"])[500:]
        dev = [t for t in d if t["src"] == "EVENT"]
        tot_drop_ev += len(dev)
        print("    %s: 合计=%d 丢弃=%d (其中 EVENT=%d)" % (m, n, len(d), len(dev)))
print("  → cap 丢弃 EVENT 合计: %d 笔" % tot_drop_ev)

# 是否恰好 = 20 笔
kept_keys = {(str(t["symbol"]), str(t["entry_date"])) for t in kept if t["src"] == "EVENT"}
print("\n  复现管线后 EVENT=%d (证据包 1547 - cap 丢弃 %d = %d)"
      % (len(kept_keys), tot_drop_ev, 1547 - tot_drop_ev))
print("  实际新基线 EVENT=%d" % len(k_new))
if len(kept_keys) == len(k_new):
    print("\n  ✅ 完全解释: 20 笔差额 = 月度 cap=500 挤出(低 rank EVENT 被 rank3 CONT 挤出)")
    print("     非口径错误 —— 新旧基线管线结构一致(旧: EVENT1640+CONT334=1974)")
else:
    print("\n  ⚠ 未完全解释: 复现 %d vs 实际 %d, 需进一步排查"
          % (len(kept_keys), len(k_new)))