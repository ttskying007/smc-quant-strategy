# -*- coding: utf-8 -*-
"""60min layer test (v676 H-layer real implementation, recent window).
Daily SMC signal (TP2-R20 chain) in 2025-10..2026-05, then 60min confirmation:
60min SSL sweep -> reclaim as entry trigger (vs daily next-open).
Limited window (6 months) - mechanism validation only, not cross-year."""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
KM = r"E:\test\smc_project\hermes\kline_cache_60min"
PIVOT = 3
SWEEP_PCT = 0.003


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def bars60(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:12]
        o, h, l, c = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "d": t[:8]})
    out.sort(key=lambda b: b["t"])
    return out


def is_swing_low(ks, j, p=PIVOT):
    if j < p or j + p >= len(ks):
        return False
    return ks[j]["l"] < min(ks[k]["l"] for k in range(j - p, j)) and ks[j]["l"] <= min(ks[k]["l"] for k in range(j + 1, j + p + 1))


# find daily SMC signals in the 60min window (2025-10..2026-05)
results = []
n = 0
for f in os.listdir(KT):
    if not f.endswith("_daily_800.json"):
        continue
    n += 1
    sym = f.replace("_daily_800.json", "").replace("_", ".", 1)
    daily = bars(os.path.join(KT, f))
    if len(daily) < 400:
        continue
    seeds = we.build_seeds(sym, daily)
    # 60min file
    m60 = os.path.join(KM, f.replace("_daily_800", "_60min_500"))
    if not os.path.exists(m60):
        m60 = os.path.join(KM, f.replace("_daily_800", "_60min_200"))
    if not os.path.exists(m60):
        continue
    m_bars = bars60(m60)
    if len(m_bars) < 100:
        continue
    m_dates = [b["d"] for b in m_bars]
    for sd in seeds:
        entry_date = str(sd["entry_date"])
        # signal entry within 60min window
        if entry_date not in m_dates:
            continue
        # daily entry price (next open after signal)
        ep_daily = we.f(sd["entry_price"])
        # 60min confirmation: SSL sweep + reclaim within entry day's 60min bars (before entry)
        day60 = [b for b in m_bars if b["d"] == entry_date]
        if len(day60) < 4:
            continue
        # find 60min swing low on prior days, then sweep+reclaim on entry day
        conf = False
        prior = [b for b in m_bars if b["d"] < entry_date]
        if len(prior) >= 10:
            # 60min swing low
            lows = [j for j in range(PIVOT, len(prior) - PIVOT) if is_swing_low(prior, j, 3)]
            if lows:
                ssl = min(prior[j]["l"] for j in lows[-3:])
                # sweep on entry day then reclaim
                swept = any(b["l"] <= ssl * (1 - SWEEP_PCT) for b in day60)
                if swept:
                    # reclaim: close back above ssl
                    reclaim = any(b["c"] > ssl for b in day60)
                    conf = swept and reclaim
        results.append({"symbol": sym, "entry_date": entry_date, "ep_daily": ep_daily,
                        "conf60": conf, "zone_low": we.f(sd["zone_low"]), "target": we.f(sd.get("target"))})
    if n % 1500 == 0:
        print(f"  {n} files, results {len(results)}", flush=True)
print(f"daily signals in 60min window: {len(results)}")
conf = [r for r in results if r["conf60"]]
print(f"with 60min sweep+reclaim confirmation: {len(conf)}")

# forward pnl from daily entry (day after) 10 days - need daily bars forward
def fwd_pnl(symbol, entry_date, hold=10):
    daily = bars(os.path.join(KT, symbol.replace(".", "_") + "_daily_800.json"))
    dates = [b["t"] for b in daily]
    if entry_date not in dates:
        return None
    i = dates.index(entry_date)
    if i + hold >= len(daily):
        return None
    ep = daily[i]["o"]
    if ep <= 0:
        return None
    return (daily[i + hold]["c"] / ep - 1) * 100 - 0.20

all_pnl = []
conf_pnl = []
for r in results:
    p = fwd_pnl(r["symbol"], r["entry_date"])
    if p is None:
        continue
    all_pnl.append((r, p))
    if r["conf60"]:
        conf_pnl.append((r, p))

print(f"\n=== 60min 确认对比（2025-10~2026-05 近期窗口）===")
print(f"全部日线信号: n={len(all_pnl)} avg={sum(p for _, p in all_pnl)/len(all_pnl):+.2f}%" if all_pnl else "无")
if conf_pnl:
    cw = sum(1 for _, p in conf_pnl if p > 0)
    print(f"60min确认: n={len(conf_pnl)} avg={sum(p for _, p in conf_pnl)/len(conf_pnl):+.2f}% WR={100*cw/len(conf_pnl):.0f}%")
