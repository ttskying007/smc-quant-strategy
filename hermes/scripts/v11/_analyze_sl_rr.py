import json, numpy as np

with open('/root/.hermes/smc_opt_v467/v467_full_trades.json') as f:
    trades = json.load(f)

print("=== SL类型分析 ===")
for sl_type in ['adaptive', 'ob_lower', 'swing_low']:
    sub = [t for t in trades if t.get('sl_type','')==sl_type]
    if not sub:
        continue
    sl_pcts = [t.get('sl_pct',0) for t in sub]
    rrs = [t['rr'] for t in sub if 'rr' in t]
    pnls = [t['pnl_pct'] for t in sub]
    holds = [t.get('hold_bars',0) for t in sub]
    
    print(f"\n{sl_type} (n={len(sub)}):")
    print(f"  SL_PCT: med={np.median(sl_pcts):.3f}%, mean={np.mean(sl_pcts):.3f}%")
    for p in [10,25,50,75,90]:
        print(f"    P{p}={np.percentile(sl_pcts, p):.3f}%")
    print(f"  RR: med={np.median(rrs):.2f}x, mean={np.mean(rrs):.2f}x")
    print(f"  PnL: med={np.median(pnls):+.2f}%, mean={np.mean(pnls):+.2f}%")
    print(f"  Hold: med={np.median(holds):.1f}bar")
    
    # RR distribution
    rr_wins = [r for r in rrs if r >= 0]
    rr_losses = [r for r in rrs if r < 0]
    print(f"  WR: {len(rr_wins)}/{len(rrs)} ({len(rr_wins)/len(rrs)*100:.1f}%)")
    
    # Correlate SL size with RR
    from scipy.stats import pearsonr
    if len(sl_pcts) > 10 and len(rrs) > 10:
        # Align arrays
        min_len = min(len(sl_pcts), len(rrs))
        r_val, _ = pearsonr(sl_pcts[:min_len], rrs[:min_len])
        print(f"  SL-RR correlation: {r_val:.3f}")

# Check: what's the SL_PCT for ob_lower trades that have RR<1?
print("\n\n=== ob_lower trades with RR < 1 ===")
bad_ob = [t for t in trades if t.get('sl_type')=='ob_lower' and t.get('rr',0) < 1]
if bad_ob:
    sls = [t['sl_pct'] for t in bad_ob]
    rrs = [t['rr'] for t in bad_ob]
    print(f"  n={len(bad_ob)}")
    print(f"  SL_PCT: med={np.median(sls):.3f}%, mean={np.mean(sls):.3f}%")
    print(f"  RR: med={np.median(rrs):.2f}x")

# Check adaptive trades that have RR<1
print("\n\n=== adaptive trades with RR < 1 ===")
bad_ad = [t for t in trades if t.get('sl_type')=='adaptive' and t.get('rr',0) < 1]
if bad_ad:
    sls = [t['sl_pct'] for t in bad_ad]
    rrs = [t['rr'] for t in bad_ad]
    print(f"  n={len(bad_ad)}")
    print(f"  SL_PCT: med={np.median(sls):.3f}%, mean={np.mean(sls):.3f}%")
    print(f"  RR: med={np.median(rrs):.2f}x")

# What if ALL trades used adaptive SL?
print("\n\n=== What-if: adaptive SL for all trades ===")
# This is a hypothetical: if we could use adaptive for all, median RR would be ~21x
# But some trades can't use adaptive because ob_lower is preferred
print(f"adaptive trades: {len([t for t in trades if t.get('sl_type')=='adaptive'])}/{len(trades)}")
print(f"non-adaptive trades: {len([t for t in trades if t.get('sl_type')!='adaptive'])}")

# Analysis: does adaptive SL pick trades where it can be tight?
print("\n\n=== SL_PCT comparison: adaptive vs ob_lower ===")
adapt_sls = [t['sl_pct'] for t in trades if t.get('sl_type')=='adaptive']
ob_sls = [t['sl_pct'] for t in trades if t.get('sl_type')=='ob_lower']
swing_sls = [t['sl_pct'] for t in trades if t.get('sl_type')=='swing_low']
print(f"adaptive SL_PCT <= 0.5%: {sum(1 for s in adapt_sls if s<=0.5)}/{len(adapt_sls)} ({sum(1 for s in adapt_sls if s<=0.5)/len(adapt_sls)*100:.1f}%)")
print(f"ob_lower SL_PCT <= 0.5%: {sum(1 for s in ob_sls if s<=0.5)}/{len(ob_sls)} ({sum(1 for s in ob_sls if s<=0.5)/len(ob_sls)*100:.1f}%)")
print(f"swing_low SL_PCT <= 0.5%: {sum(1 for s in swing_sls if s<=0.5)}/{len(swing_sls)} ({sum(1 for s in swing_sls if s<=0.5)/len(swing_sls)*100:.1f}%)")
