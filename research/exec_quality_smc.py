# -*- coding: utf-8 -*-
"""Execution quality audit: entry/exit position reasonableness.
Questions: bought too early? sold too early/late?
- SMC leg: entry price vs POI zone, post-entry MAE (did price drop more after entry?)
- Exit: TP hit -> MFE after exit (sold too early?); SL hit -> rebound after stop
- Event leg: T+1 open entry, entry-day low vs entry (better entry available?)"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c, v = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c")), we.f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


# ============ SMC leg: entry position vs POI + exit quality ============
# Rebuild SMC seeds with entry position info (entry vs zone) and replay for exit quality
smc_stats = {"n": 0, "entry_inside_zone": 0, "entry_below_zone": 0, "entry_above_zone": 0,
             "mae_after_entry": [], "mfe_after_tp": [], "sl_rebound": [], "time_exit_after": []}
bar_cache = {}
def get_bars(sym):
    if sym not in bar_cache:
        bar_cache[sym] = bars(os.path.join(KT, sym.replace(".", "_") + "_daily_800.json"))
    return bar_cache[sym]

n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    for sd in we.build_seeds(sym, daily):
        r20 = sd.get("r20")
        if r20 == "" or r20 is None:
            continue
        if not (0 <= float(r20) < 0.15):
            continue
        # stage filter (UPTREND/MARKUP) for fair comparison with v16b SMC leg
        entry_idx = int(sd["entry_idx"])
        if entry_idx < 61:
            continue
        w60 = daily[entry_idx - 60:entry_idx]
        w20 = daily[entry_idx - 20:entry_idx]
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        v20 = sum(x["v"] for x in w20) / len(w20)
        v60 = sum(x["v"] for x in w60) / len(w60)
        vt = v20 / v60 if v60 else 1
        if ret60 < -0.15 and vt < 0.9:
            st = "ACCUM"
        elif ret60 > 0.30 and vt > 1.3:
            st = "DISTRIB"
        elif ret60 > 0.20 and vt > 1.1:
            st = "MARKUP"
        elif ret60 > 0:
            st = "UPTREND"
        else:
            st = "DOWNTREND"
        if st not in ("UPTREND", "MARKUP"):
            continue
        # entry position vs zone
        ep = we.f(sd["entry_price"])
        zl = we.f(sd["zone_low"])
        zh = we.f(sd["zone_high"])
        smc_stats["n"] += 1
        if zl <= ep <= zh:
            smc_stats["entry_inside_zone"] += 1
        elif ep < zl:
            smc_stats["entry_below_zone"] += 1
        else:
            smc_stats["entry_above_zone"] += 1
        # MAE: min low in first 5 days after entry vs entry
        mae = 0
        for k in range(entry_idx + 1, min(len(daily), entry_idx + 6)):
            mae = min(mae, daily[k]["l"] / ep - 1)
        smc_stats["mae_after_entry"].append(mae * 100)
        # exit quality via TP2 replay
        tr = we.replay_tp2(sd, daily)
        if tr:
            reason = tr.get("reason")
            if reason == "TP2_RUNNER" or reason == "BE":
                # MFE after TP1: max high from exit to +5 bars
                ep_i = entry_idx
                ex_i = None
                # find exit bar roughly (hold_bars)
                ex_i = min(entry_idx + int(tr["hold_bars"]), len(daily) - 1)
                mfe = 0
                for k in range(ex_i + 1, min(len(daily), ex_i + 6)):
                    mfe = max(mfe, daily[k]["h"] / daily[ex_i]["c"] - 1)
                smc_stats["mfe_after_tp"].append(mfe * 100)
            elif reason == "SL_HIT":
                # rebound after SL: max high 5 bars after exit
                ex_i = min(entry_idx + int(tr["hold_bars"]), len(daily) - 1)
                reb = 0
                for k in range(ex_i + 1, min(len(daily), ex_i + 6)):
                    reb = max(reb, daily[k]["h"] / daily[ex_i]["c"] - 1)
                smc_stats["sl_rebound"].append(reb * 100)
            elif reason == "TIME_STOP":
                ex_i = min(entry_idx + int(tr["hold_bars"]), len(daily) - 1)
                after = 0
                for k in range(ex_i + 1, min(len(daily), ex_i + 6)):
                    after = max(after, daily[k]["h"] / daily[ex_i]["c"] - 1)
                smc_stats["time_exit_after"].append(after * 100)
    if n % 1500 == 0:
        print(f"  {n} files", flush=True)

print("\n=== SMC 腿执行质量 ===")
s = smc_stats
print(f"n={s['n']}")
print(f"入场位置: 区内 {100*s['entry_inside_zone']/s['n']:.0f}% | 区下 {100*s['entry_below_zone']/s['n']:.0f}% | 区上 {100*s['entry_above_zone']/s['n']:.0f}%")
if s["mae_after_entry"]:
    maes = sorted(s["mae_after_entry"])
    print(f"入场后5日MAE: med={maes[len(maes)//2]:+.2f}% p25={maes[len(maes)//4]:+.2f}% （负=入场后还有更低点=买早）")
if s["mfe_after_tp"]:
    mfes = sorted(s["mfe_after_tp"])
    print(f"TP后5日继续涨: med={mfes[len(mfes)//2]:+.2f}% （正=卖早了） n={len(mfes)}")
if s["sl_rebound"]:
    rebs = sorted(s["sl_rebound"])
    print(f"SL后5日反弹: med={rebs[len(rebs)//2]:+.2f}% （正=止损过早） n={len(rebs)}")
if s["time_exit_after"]:
    tes = sorted(s["time_exit_after"])
    print(f"TIME后5日继续涨: med={tes[len(tes)//2]:+.2f}% n={len(tes)}")
