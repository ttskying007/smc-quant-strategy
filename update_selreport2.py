# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
s = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
rep = {
    "selected_at": "2026-08-25 13:18:27",
    "deadline": "09:00",
    "refresh_completed": True,
    "data_latest_date": s.get("latest_date", ""),
    "data_fresh_count": s.get("fresh_count", 0),
    "data_stale_count": s.get("stale_count", 0),
    "data_coverage_pct": s.get("coverage_pct", 0),
    "note": "8-24 收盘后选股（数据 8-24，覆盖率 95.1%，强市过滤跳过 4 笔）",
}
for p in (r"E:\test\smc_project\research\selection_report.json",
          r"E:\root\.hermes\smc_monitor\selection_report.json",
          r"E:\test\smc_project\hermes\smc_monitor\selection_report.json"):
    json.dump(rep, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"selection_report 更新: selected_at={rep['selected_at']} latest={rep['data_latest_date']} coverage={rep['data_coverage_pct']}%")