# -*- coding: utf-8 -*-
"""Finalize combo dashboard: add current scanner candidates (SMC + events)."""
import io, json, os, sqlite3, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as CFG
from core.time_cn import cn_today

# load combo stats
_research = CFG.RESEARCH_DIR
_dashboard = os.path.join(_research, "combo_dashboard.json")
data = json.load(open(_dashboard, encoding="utf-8"))

# load scanner result
scan = json.load(open(os.path.join(_research, "current_scanner_result.json"), encoding="utf-8"))

# current event candidates: last 3 trading days represented in the scanner data
conn = sqlite3.connect(CFG.ANNOUNCE_DB)
cur = conn.cursor()
events = []
_dates = []
try:
    _dates = sorted({str(x.get("signal_date", ""))[:10] for x in scan.get("event_candidates", []) if x.get("signal_date")})[-3:]
except Exception:
    pass
if not _dates:
    cur.execute("SELECT DISTINCT date FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%' ORDER BY date DESC LIMIT 3")
    _dates = [str(row[0]) for row in cur.fetchall() if row and row[0]]
if not _dates:
    _dates = [cn_today("%Y-%m-%d")]
for d in _dates:
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
with open(_dashboard, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
print("dashboard updated")
print(f"SMC 候选: {data['current_scanner']['smc_count']}")
print(f"事件候选: {data['current_scanner']['event_count']}")
for e in events[:8]:
    print(f"  {e['date']} {e['code']} {e['name']}: {e['title']}")
