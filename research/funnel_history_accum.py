# -*- coding: utf-8 -*-
"""selection_funnel 时序累积器(±2σ 基线前置, 自动化补丁)
现状: paper_sim 每日 00:00 覆写 selection_funnel.json(单日快照), 无历史 → ±2σ 无从计算。
本脚本: 读取当日快照 → 追加进 handover/selection_funnel_history.json(滚动60天),
幂等(同日只记一次)。可挂每日任务(paper_sim 之后)或手动跑。
只读快照, 不动 paper_sim 本身。"""
import json, os, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = r"E:\test\smc_project\research\selection_funnel.json"
HIST = r"E:\test\smc_project\research\handover\selection_funnel_history.json"

try:
    snap = json.load(open(SRC, encoding="utf-8"))
except Exception as e:
    print("无快照:", e); sys.exit(0)

day = str(snap.get("generated_at", ""))[:10]
entry = {"day": day, "raw": snap.get("raw_announcements"),
         "positive": snap.get("classified_positive"),
         "orders": snap.get("orders_created"),
         "reject": snap.get("reject_by_reason", {})}

hist = []
if os.path.exists(HIST):
    try:
        hist = json.load(open(HIST, encoding="utf-8")).get("history", [])
    except Exception:
        hist = []
hist = [h for h in hist if h.get("day") != day]   # 同日覆盖
hist.append(entry)
hist = hist[-60:]
json.dump({"days": len(hist), "history": hist}, open(HIST, "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"累积 {day}: raw={entry['raw']} positive={entry['positive']} orders={entry['orders']} → 共{len(hist)}天")