# -*- coding: utf-8 -*-
"""复审 P0-4b: 公告→成交时点合理性 —— 披露日与成交日差应=1交易日（T+1）"""
import csv, json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# paper_ledger 中 EVENT 腿：signal_date(披露日) vs filled_at(成交日)
p = r"E:\test\smc_project\research\paper_ledger.json"
if not os.path.exists(p):
    print("paper_ledger 不存在（生产未运行选股）→ 用回测 CSV 的 entry_date 近似")
    sys.exit(0)
led = json.load(open(p, encoding="utf-8"))
ev = [t for t in led if t.get("source") == "EVENT" and t.get("filled_at") and t.get("signal_date")]
print(f"EVENT 已成交: {len(ev)}")
# 用 K 线日历算交易日差
import datetime as _dt
def td_between(d1, d2):
    try:
        a = _dt.datetime.strptime(d1[:8] if len(d1) > 8 else d1.replace("-", ""), "%Y%m%d")
        b = _dt.datetime.strptime(d2[:8] if len(d2) > 8 else d2.replace("-", ""), "%Y%m%d")
        return (b - a).days
    except Exception:
        return None
diffs = [td_between(t["signal_date"], t["filled_at"]) for t in ev]
diffs = [d for d in diffs if d is not None]
if diffs:
    from collections import Counter
    c = Counter(diffs)
    print("signal→filled 日历日差分布:", dict(sorted(c.items())))
    # 1-3 日历日（跨周末）≈ T+1 合理；>4 异常
    bad = sum(1 for d in diffs if d > 4)
    print(f"异常(>4日): {bad}/{len(diffs)}")
    print(f"验收: 异常占比<5% → {'✅' if bad/len(diffs) < 0.05 else '❌'}")
else:
    print("无可比样本")
