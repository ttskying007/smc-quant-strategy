# -*- coding: utf-8 -*-
"""评估 aggregate_weekly 月份bug影响：月份 vs 周线对 weekly_permission 的影响"""
import io, json, os, sys, datetime
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# test on 000651
daily = we.bars_for(os.path.join(KT, "000651_SZ_daily_800.json"))
print(f"000651.SZ: {len(daily)} daily bars")

# current (monthly) aggregation
months = we.aggregate_weekly(daily)
print(f"当前（月份聚合）: {len(months)} '周线'（实际月线）")

# proper ISO week aggregation
def iso_weeks(daily):
    weeks = []
    cur = None
    for b in daily:
        t = b["t"]
        try:
            wk = datetime.date(int(t[:4]), int(t[4:6]), int(t[6:8])).strftime("%Y%W")
        except Exception:
            wk = t[:6]
        if cur is None or cur["wk"] != wk:
            if cur:
                weeks.append(cur)
            cur = {"wk": wk, "t": t, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "days": [t]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
            cur["days"].append(t)
    if cur:
        weeks.append(cur)
    return weeks

iso_w = iso_weeks(daily)
print(f"ISO周: {len(iso_w)} 周线")

# compare weekly_permission results
we.PIVOT_L = we.PIVOT_R = 3
we.SWEEP_PCT = 0.003

# test permission on last few weeks
for test_date in ["20260815", "20260810", "20260801", "20260715", "20260701"]:
    wok, wwhy = we.weekly_permission(months, test_date)
    iok, iwhy = we.weekly_permission(iso_w, test_date)
    print(f"  {test_date}: 月份={'通过' if wok else '拒绝'} ({wwhy}) | ISO周={'通过' if iok else '拒绝'} ({iwhy})")