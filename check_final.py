# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
s = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
print(f"scanner: latest={s.get('latest_date')} fresh={s.get('fresh_count')} coverage={s.get('coverage_pct')}%")
