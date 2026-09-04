#!/usr/bin/env python3
"""Statistics for signal details"""
import json, os
d = json.load(open(os.path.expanduser('~/.hermes/smc_opt_v4/signal_details_full.json')))
total = len(d)
with_signals = [s for s in d if s.get('signals') and len(s['signals']) > 0]
strict_only = [s for s in with_signals if s.get('perf',{}).get('strict',{}).get('n',0) > 0]

print(f"Full results processed: {total}")
print(f"Stocks with signal details: {len(with_signals)}")

# Strict stats
strict_wr = [s['perf']['strict']['wr'] for s in strict_only]
print(f"Strict signals available: {len(strict_only)}")
print(f"  Strict WR=100%: {sum(1 for w in strict_wr if w==100)}")
print(f"  Strict WR>=80%: {sum(1 for w in strict_wr if w>=80)}")
if strict_wr: print(f"  Avg strict WR: {sum(strict_wr)/len(strict_wr):.1f}%")

# Total stats
total_wr = [s['perf']['total']['wr'] for s in with_signals]
print(f"Total WR>=80%: {sum(1 for w in total_wr if w>=80)}/{len(total_wr)}")
if total_wr: print(f"  Avg total WR: {sum(total_wr)/len(total_wr):.1f}%")

# Top signals
by_score = sorted(with_signals, key=lambda s: max((sig.get('sc',0) for sig in s['signals']), default=0), reverse=True)
print(f"\n=== TOP 10 stocks by highest signal score ===")
for s in by_score[:10]:
    max_sc = max((sig.get('sc',0) for sig in s['signals']), default=0)
    top = max(s['signals'], key=lambda sig: sig.get('sc',0))
    trig = top.get('sigs', [])
    print(f"  {s['code']} {s['name'][:8]:8s} sc={max_sc:.2f}  {top['dir']} @ {top.get('t','')[:10]} EP={top['ep']:.2f} RR={top.get('rr',0):.2f}  {trig}")