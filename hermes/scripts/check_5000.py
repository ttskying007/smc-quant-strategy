#!/usr/bin/env python3
"""Check 5000 result"""
import json
try:
    d=json.load(open('/root/.hermes/smc_opt_v4/stock_results_5000.json'))
except:
    print("No result file yet")
    exit(0)
print(f"Stocks tested: {len(d)}")
valid=[x for x in d if x['n_s']>0]
print(f"With signals: {len(valid)} ({len(valid)/len(d)*100:.1f}%)")
if valid:
    wr=[x['wr_s'] for x in valid]
    print(f"Avg WR_s: {sum(wr)/len(wr):.1f}%")
    print(f"Median WR_s: {sorted(wr)[len(wr)//2]:.1f}%")
    wr80=sum(1 for w in wr if w>=80)
    print(f"WR>=80%: {wr80}/{len(wr)} ({wr80/len(wr)*100:.1f}%)")
    wr100=sum(1 for w in wr if w==100)
    print(f"WR=100%: {wr100}/{len(wr)} ({wr100/len(wr)*100:.1f}%)")
    n_avg=sum(x['n_s'] for x in valid)/len(valid)
    print(f"Avg N(strict): {n_avg:.1f}")
    # WR distribution
    for lo,hi in [(0,20),(20,40),(40,60),(60,80),(80,90),(90,100)]:
        cnt=sum(1 for w in wr if lo<=w<hi)
        print(f"  WR {lo:>3d}-{hi:<3d}%: {cnt:>4d} ({cnt/len(wr)*100:>5.1f}%)")