# -*- coding: utf-8 -*-
"""龙虎榜信号初测：机构净买>0（大资金买入）→ 次日开盘入场 → 5/10日表现
用本地 K 线（冻结 8-19）回测近 10 天龙虎榜信号"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LHB = r"E:\test\smc_project\hermes\lhb_cache"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def check(inst_net):
    """Signal: institutional net buy > threshold. Entry next open, hold 10d."""
    trades = []
    for f in sorted(os.listdir(LHB)):
        rows = json.load(open(os.path.join(LHB, f), encoding="utf-8"))
        for r in rows:
            code = str(r.get("SECURITY_CODE", ""))
            # institutional buy amount (机构买入)
            inst = float(r.get("BILLBOARD_BUY_AMT") or 0)
            inst_net_row = float(r.get("BILLBOARD_NET_AMT") or 0)
            if inst_net_row < inst_net:
                continue
            bs = bars_of(code)
            if not bs:
                continue
            dates = [b["t"] for b in bs]
            # entry = next day after trade date
            td = str(r.get("TRADE_DATE", ""))[:10].replace("-", "")
            if td not in dates:
                continue
            i = dates.index(td)
            if i + 1 >= len(bs) or i + 11 >= len(bs):
                continue
            ep = bs[i + 1]["o"]
            if ep <= 0:
                continue
            trades.append({"entry_date": bs[i + 1]["t"], "code": code,
                           "pnl10": round((bs[i + 11]["c"] / ep - 1) * 100 - 0.20, 4),
                           "pnl5": round((bs[i + 6]["c"] / ep - 1) * 100 - 0.20, 4)})
    return trades


print("=== 龙虎榜信号初测（近10天，大资金净买）===")
for th in (0, 1000000, 5000000):
    ts = check(th)
    if ts:
        p10 = [t["pnl10"] for t in ts]
        p5 = [t["pnl5"] for t in ts]
        w10 = sum(1 for x in p10 if x > 0)
        print(f"净买>{th/1e6:.0f}万: n={len(ts)} | 5日 avg={sum(p5)/len(p5):+.2f}% | 10日 avg={sum(p10)/len(p10):+.2f}% WR={100*w10/len(p10):.0f}%")
