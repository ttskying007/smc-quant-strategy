# -*- coding: utf-8 -*-
"""aggregate_weekly bug 回测对比：月份聚合 vs ISO 周 对 SMC 反转腿的影响"""
import io, json, os, sys, datetime
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


def iso_aggregate(daily):
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


def run_all(weekly_mode, limit=600):
    trades = []
    for f in sorted(os.listdir(KT)):
        if not f.endswith("_daily_800.json"):
            continue
        sym = f.replace("_daily_800.json", "").replace("_", ".", 1)
        daily = we.bars_for(os.path.join(KT, f))
        if len(daily) < 300:
            continue
        # patch aggregate_weekly
        if weekly_mode == 'month':
            we.aggregate_weekly = orig_monthly
        else:
            we.aggregate_weekly = iso_aggregate
        for sd in we.build_seeds(sym, daily):
            r20 = sd.get("r20")
            if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
                continue
            tr = we.replay_tp2(sd, daily)
            if tr:
                trades.append({"entry_date": str(tr["entry_date"]), "net_pnl_pct": tr["net_pnl_pct"]})
        if len(trades) > limit:
            break
    return trades


def report(label, trades):
    if len(trades) < 30:
        print(f"{label}: n={len(trades)} (过小)")
        return
    pnls = [t["net_pnl_pct"] for t in trades]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    wr = 100 * len(wins) / len(pnls)
    avg = sum(pnls) / len(pnls)
    pf = (sum(wins) / abs(sum(losses))) if losses else 99
    by_y = defaultdict(list)
    for t in trades:
        by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
    line = f"{label}: n={len(pnls)} WR={wr:.1f}% avg={avg:+.2f}% PF={pf:.2f}"
    for y in ("2024", "2025", "2026"):
        if by_y.get(y):
            line += f" | {y}:{sum(by_y[y])/len(by_y[y]):+.2f}%"
    print(line)


# save original
orig_monthly = we.aggregate_weekly
print("=== 月份聚合（当前）===")
we.aggregate_weekly = orig_monthly
t1 = run_all('month')
report("月份(当前)", t1)

print("\n=== ISO 周聚合（修复）===")
we.aggregate_weekly = iso_aggregate
t2 = run_all('week')
report("ISO周", t2)

we.aggregate_weekly = orig_monthly
print("done")