# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
fill = [t for t in led if t.get("status") == "FILLED"]

print("=== FILLED 成交价 vs 挂单价 ===")
lows = 0
for t in fill:
    ep = t.get("entry_price") or 0
    fp = t.get("filled_price") or 0
    if ep and fp:
        diff = (fp / ep - 1) * 100
        if diff < -0.5:
            lows += 1
print(f"成交价<挂单价(回踩成交): {lows}/{len(fill)}")
print(f"成交价≈挂单价(开盘兜底): {len(fill)-lows}/{len(fill)}")

# filled_at 分布（何时成交）
from collections import Counter
times = Counter(str(t.get("filled_at", ""))[11:16] for t in fill if t.get("filled_at"))
print(f"\nfilled_at 时间分布: {dict(sorted(times.items()))}")

# 买点机制对比：模拟 vs 回测
print("\n=== 买点机制 ===")
print("模拟(paper_sim): 回踩挂单 披露收盘×0.99 → 回落成交(挂单价) / 否则 T+1 开盘兜底")
print("回测(gen_v20f): 同机制（回踩×0.99 + 分层 TP/SL）")
print("\n研究依据:")
print("  T+1最低(理论): +9.10% | T+1开盘: +6.52% | 回踩×0.99: +6.98% (+0.47pp)")
print("  回踩成交率 63% + 0.82% 节省（中位）")
