# -*- coding: utf-8 -*-
"""全面指标审计：paper_sim/continuation_scanner 的核心指标实现检查
1) 行为阶段识别 2) ADX 3) VWAP 4) 结构支撑 5) 波动率 6) 量能比 7) TP/SL 结构"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import paper_sim as ps

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# pick a few stocks with known behavior
tests = ["000651.SZ", "600519.SH", "000404.SZ", "300750.SZ"]

for code in tests:
    sym = code.split(".")[0]
    ex = "SH" if code.startswith("6") else "SZ"
    p = os.path.join(KT, f"{sym}_{ex}_daily_800.json")
    if not os.path.exists(p):
        continue
    bs = ps.bars_of(sym)
    if len(bs) < 100:
        continue
    print(f"\n=== {code} ({len(bs)} bars) ===")
    # test stage detection at last 5 bars
    for i in [len(bs)-1, len(bs)-5, len(bs)-10, 300, 500]:
        if i >= len(bs) or i < 61:
            continue
        d = bs[i]
        # manual stage calc
        w60 = bs[i-60:i]
        w20 = bs[i-20:i]
        ret60 = w60[-1]["c"]/w60[0]["c"]-1
        v20 = sum(x["v"] for x in w20)/20
        v60 = sum(x["v"] for x in bs[i-60:i])/60
        vt = v20/v60 if v60 else 1
        ret20 = w20[-1]["c"]/w20[0]["c"]-1
        adx = ps.adx14_of(bs, i)
        print(f"  bar {i} ({d['t']}): ret60={ret60*100:+.1f}% vol_ratio={vt:.2f} ret20={ret20*100:+.1f}% ADX={adx if adx is None else round(adx,1)}")
    # test structural SL/TP
    sd = str(bs[-30]["t"])
    sltp = ps.structural_sltp(sym, sd)
    print(f"  结构SL/TP @ {sd}: {sltp if sltp else 'None'}")
    # vwap test at last bar
    pv = sum(bs[k]["c"]*bs[k]["v"] for k in range(len(bs)-20, len(bs)))
    vol = sum(bs[k]["v"] for k in range(len(bs)-20, len(bs)))
    vw = pv/vol if vol else 0
    last = bs[-1]
    print(f"  VWAP20={vw:.2f} close={last['c']} 偏离={100*(last['c']/vw-1) if vw else 0:+.1f}%")