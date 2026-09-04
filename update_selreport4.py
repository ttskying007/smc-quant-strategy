# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sr = json.load(open(r"E:\test\smc_project\research\selection_result.json", encoding="utf-8"))
s = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
rep = {
    "selected_at": sr.get("selected_at", "2026-08-27 17:09:41"),
    "deadline": "09:00", "refresh_completed": True,
    "data_latest_date": s.get("latest_date", ""),
    "data_fresh_count": s.get("fresh_count", 0), "data_stale_count": s.get("stale_count", 0),
    "data_coverage_pct": s.get("coverage_pct", 0),
    "note": f"选股 {sr.get('selected_at')}（数据 {s.get('latest_date')}，覆盖率 {s.get('coverage_pct')}%）",
}
for p in (r"E:\test\smc_project\research\selection_report.json", r"E:\root\.hermes\smc_monitor\selection_report.json",
          r"E:\test\smc_project\hermes\smc_monitor\selection_report.json"):
    json.dump(rep, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"selection_report: {rep['selected_at']} data={rep['data_latest_date']}")
