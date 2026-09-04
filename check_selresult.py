# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
r = json.load(open(r"E:\test\smc_project\research\selection_result.json", encoding="utf-8"))
print(f"选股结果: {r.get('selected_at')}")
print(f"统计: {r.get('stats')}")
print(f"新增订单: {len(r.get('new_orders', []))}")
