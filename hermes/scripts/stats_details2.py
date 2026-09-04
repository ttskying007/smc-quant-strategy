#!/usr/bin/env python3
"""Signal details statistics v2"""
import json, os
from collections import Counter
d = json.load(open(os.path.expanduser('~/.hermes/smc_opt_v4/signal_details_full.json')))
print(f"Total stocks with signals: {len(d)}")

# Performance stats
strict_wrs = []
total_wrs = []
strict_pfs = []
total_pfs = []
for s in d:
    p = s.get('performance', {})
    if 'strict' in p and p['strict']['n'] > 0:
        strict_wrs.append(p['strict']['wr'])
        strict_pfs.append(p['strict']['pf'])
    if 'total' in p and p['total']['n'] > 0:
        total_wrs.append(p['total']['wr'])
        total_pfs.append(p['total']['pf'])

print(f"\nStrict (optimized params):")
print(f"  Stocks with signals: {len(strict_wrs)}")
strict_wr100 = sum(1 for w in strict_wrs if w==100)
strict_wr80 = sum(1 for w in strict_wrs if w>=80)
if strict_wrs:
    print(f"  WR=100%: {strict_wr100}/{len(strict_wrs)} ({strict_wr100/len(strict_wrs)*100:.1f}%)")
    print(f"  WR>=80%: {strict_wr80}/{len(strict_wrs)} ({strict_wr80/len(strict_wrs)*100:.1f}%)")
    print(f"  Avg WR: {sum(strict_wrs)/len(strict_wrs):.1f}%")
    print(f"  Avg PF: {sum(strict_pfs)/len(strict_pfs):.1f}")

print(f"\nTotal (all params):")
print(f"  Stocks with signals: {len(total_wrs)}")
total_wr80 = sum(1 for w in total_wrs if w>=80)
if total_wrs:
    print(f"  WR>=80%: {total_wr80}/{len(total_wrs)} ({total_wr80/len(total_wrs)*100:.1f}%)")
    print(f"  Avg WR: {sum(total_wrs)/len(total_wrs):.1f}%")
    print(f"  Avg PF: {sum(total_pfs)/len(total_pfs):.1f}")

# Signal count distribution
sig_counts = [len(s['signals']) for s in d]
avg_sigs = sum(sig_counts)/len(sig_counts)
print(f"\nAvg signals/stock: {avg_sigs:.1f}")

# Signal type frequency
all_sigs = Counter()
for s in d:
    for sig in s['signals']:
        for t in sig.get('signal_types', []):
            all_sigs[t] += 1
total_sig_types = sum(all_sigs.values())
print(f"\nSignal type frequency:")
for t, c in all_sigs.most_common():
    print(f"  {t}: {c} ({c/total_sig_types*100:.1f}%)")

# Direction
dirs = Counter()
for s in d:
    for sig in s['signals']:
        dirs[sig['direction']] += 1
total_dirs = sum(dirs.values())
print(f"\nDirection:")
for dir, c in dirs.most_common():
    print(f"  {dir}: {c} ({c/total_dirs*100:.1f}%)")

# Top signals
by_score = sorted(d, key=lambda s: max((sig.get('score',0) for sig in s['signals']), default=0), reverse=True)
print(f"\n=== TOP 10 by signal score ===")
for s in by_score[:10]:
    max_sc = max((sig.get('score',0) for sig in s['signals']), default=0)
    top = max(s['signals'], key=lambda sig: sig.get('score',0))
    print(f"  {s['code']} {s['name'][:10]:10s} sc={max_sc:.2f} {top['direction']} @ {top['entry_time']} EP={top['entry_price']:.2f} RR={top['rr_ratio']:.2f} {top['signal_types'][:4]}")

print(f"\n=== Files ===")
print(f"  /root/.hermes/smc_opt_v4/signal_details_full.json (JSON, {len(d)} stocks)")
print(f"  /root/.hermes/smc_opt_v4/signal_details_compact.txt (compact)")
print(f"  /root/.hermes/smc_opt_v4/signal_details_report.txt (full, 5157 lines)")