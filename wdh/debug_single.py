# -*- coding: utf-8 -*-
import io, json, os, sys
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

for sym in ("600519_SH", "000001_SZ", "601857_SH"):
    p = os.path.join(r"E:\test\smc_project\hermes\kline_cache", f"{sym}_daily_750.json")
    if not os.path.exists(p):
        print(sym, "missing"); continue
    daily = we.bars_for(p)
    weekly = we.aggregate_weekly(daily)
    seeds = we.build_seeds(sym, daily)
    print(f"{sym}: daily={len(daily)} weekly={len(weekly)} seeds={len(seeds)}")
    if seeds:
        s = seeds[0]
        print("  sample:", {k: s[k] for k in ("identity", "w_permission", "event_date", "sweep_date", "ob_date", "touch_date", "reclaim_date", "entry_date", "entry_price", "target")})
        tr = we.replay(s, daily)
        print("  replay:", tr)
    print()
