# -*- coding: utf-8 -*-
"""Finalize combo dashboard: add current scanner candidates (SMC + events)."""
import io, json, os, sqlite3, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# load combo stats
data = json.load(open(r"E:\test\smc_project\research\combo_dashboard.json", encoding="utf-8"))

# load scanner result
scan = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))

# current event candidates: last 3 trading days with events
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
events = []
for d in ("2026-08-12", "2026-08-13", "2026-08-14"):
    cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (d,))
    for code, name, title in cur.fetchall():
        events.append({"date": d, "code": code, "name": name, "title": str(title)[:60], "action": "EVENT_T0"})
conn.close()

data["current_scanner"] = {
    "latest_bar_date": scan.get("latest_date"),
    "smc_candidates": scan.get("smc_candidates", []),
    "event_candidates": events,
    "smc_count": len(scan.get("smc_candidates", [])),
    "event_count": len(events),
}
with open(r"E:\test\smc_project\research\combo_dashboard.json", "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
print("dashboard updated")
print(f"SMC 候选: {data['current_scanner']['smc_count']}")
print(f"事件候选: {data['current_scanner']['event_count']}")
for e in events[:8]:
    print(f"  {e['date']} {e['code']} {e['name']}: {e['title']}")
