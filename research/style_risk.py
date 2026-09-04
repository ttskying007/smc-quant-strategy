# -*- coding: utf-8 -*-
"""Style risk research: event-stock excess return vs market by month (backtest).
8-19 showed event stocks fell while market rose = style rotation risk.
Check: are there months where event stocks badly underperform market?"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}

trades = []
with open(r"E:\test\smc_project\research\combo_v18_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        if r.get("src") == "EVENT":
            trades.append(r)

# event trade 10d returns by entry month
def bars_of(code):
    p = code2file.get(code)
    if not p:
        return None
    raw = json.load(open(p, encoding="utf-8"))
    bs = []
    for x in raw:
        t = "".join(c for c in str(x.get("t") or "") if c.isdigit())[:8]
        if t and x.get("o") and x.get("c"):
            bs.append({"t": t, "o": float(x["o"]), "c": float(x["c"])})
    bs.sort(key=lambda b: b["t"])
    return bs

by_m = defaultdict(list)
for t in trades:
    ed = str(t.get("entry_date", ""))
    if ed[4:6] != "08":
        continue
    code = str(t.get("symbol", "")).split(".")[0]
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if ed not in dates:
        continue
    i = dates.index(ed)
    if i + 10 >= len(bs):
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    r10 = (bs[i + 10]["c"] / ep - 1) * 100
    by_m[ed[:4]].append(r10)

# market reference: 600519 10d forward per month (proxy)
mk = bars_of("600519")
mk_by_m = defaultdict(list)
if mk:
    dates = [b["t"] for b in mk]
    for i in range(len(mk) - 10):
        m = dates[i][:6]
        if m[4:6] == "08":
            ep = mk[i]["o"]
            if ep > 0:
                mk_by_m[m[:4]].append((mk[i + 10]["c"] / ep - 1) * 100)

print("=== 8 月事件股 10 日 vs 大盘（600519）===")
for y in ("2023", "2024", "2025"):
    ev = by_m.get(y, [])
    mkv = mk_by_m.get(y, [])
    if ev:
        ev_avg = sum(ev) / len(ev)
        mkv_avg = sum(mkv) / len(mkv) if mkv else 0
        print(f"  {y}-08: 事件股 {ev_avg:+.2f}% (n={len(ev)}) vs 大盘 {mkv_avg:+.2f}% = 超额 {ev_avg-mkv_avg:+.2f}%")
