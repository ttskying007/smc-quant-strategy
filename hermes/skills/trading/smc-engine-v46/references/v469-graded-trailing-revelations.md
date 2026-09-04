# V469 Graded Trailing — Core Revelations

## The Filter-Stacking Trap

Adding signal_strength scoring (multi-signal cluster analysis) as an ENTRY filter reduces trade count WITHOUT improving quality. On 60min data with 200 bars, signal density is too high — you'll always find 3+ signal types within 8 bars.

**Rule**: Signal grading should ONLY affect trailing tightness, not entry. Entry filters should come from sequence+resonance+reversal_ob+POI alone (V468 baseline).

## G Coefficient Direction for 60min

**Counter-intuitive finding**: On 60min data, Grade C (single signal / tightest trailing) outperforms Grade A (strong resonance / loosest trailing).

200-stock:
| Grade | G | Trades | WR | RR | P&L |
|:-----|:-:|:-----:|:--:|:--:|:---:|
| A (loose, G=1.5) | 1.5 | 23 | 52.2% | 5.41x | +2.04% |
| B (medium, G=1.2) | 1.2 | 19 | 57.9% | 3.95x | +1.73% |
| C (tight, G=1.0) | 1.0 | 22 | **72.7%** | **8.07x** | **+3.03%** |

Full 4552 (confirmed at scale):
| Grade | Trades | WR | RR | P&L |
|:-----|:-----:|:--:|:--:|:---:|
| A | 635 | 56.7% | 5.25x | +2.25% |
| B | 538 | 58.9% | 5.85x | +2.53% |
| C | 650 | **59.4%** | **5.90x** | **+2.50%** |

**Root cause**: 60min data has more noise than daily data. Looser trailing lets false reversals eat into profits. Single-signal trades have cleaner entry patterns and benefit from tighter trailing. Also, the 8-bar cluster scoring is negatively correlated with actual performance — the signals calc_signal_strength grades highest (A) turn out worst.

**Recommendation for V470**: Reverse G coefficients for 60min data:
- Grade A (strong cluster): G=0.8 (tightest — protect profit faster)
- Grade B (moderate): G=1.0 (standard)
- Grade C (single): G=1.2 (loosest — give singles room to run)

## Grade Scoring Inversion (Critical)

The 8-bar cluster-window scoring mechanism is negatively correlated with future trade performance. Three hypotheses:

1. **Congestion not strength**: Dense signal clusters indicate congestion / chop, not directional momentum. A stock with FVG+OB+Sweep+CHOCH within 8 bars is indecisive, not powerful.

2. **Retracement artifact**: Multi-signal clusters are more likely on retracement bars where price revisits old zones. These are precisely the environments where breakouts fail.

3. **Look-ahead cluster**: The 8-bar window extends forward from signal bar. This inadvertently includes post-entry bars, potentially pulling in signals generated after entry.

**Viable alternative**: Use signal-strength scoring from the SIGNAL itself (confidence, gap-size ratio, trend alignment) rather than cluster density. Or skip grading entirely and just use V468 trailing.

## Sequence Direction Matching Bug

The `best_sequence` from `analyze_sequence_v11()` can return a BEAR sequence (e.g., SHORT_BRONZE_D) for a BULL signal OB. The old code used `if 'SCOUT' not in seq_name: return None` which rejected the bull OB when the sequencer found a bear bronze sequence.

**Fix**: After retrieving `best_seq`, check `seq_dir != sig_dir`. If mismatched, search `sequences_found` for a matching-direction sequence. Only reject if none exists.

## Test Stock Selection

First 20 alphabetical stocks (000001.SZ-000029.SZ) are Shenzhen blue-chips — banks, real estate, utilities. These have the fewest OB signals in the database. Always pick OB-rich stocks (688xxx, 002xxx, 300xxx, 603xxx with 13+ OB_Bull signals) for meaningful small-scale testing.

Use `v11/find_top20.py` to find OB-rich stocks by scanning the 60min cache.

## V469_final Full 4552 Results

| Metric | V468 200st | V469_final 200st | V469_final 4552 |
|:-------|:---------:|:---------------:|:---------------:|
| Stocks traded | 16/200 (8%) | 24/200 (12%) | 759/4552 (16.7%) |
| Total trades | 35 | 64 | 1823 |
| WR | 68.6% | 60.9% | 58.3% |
| Avg RR | 6.77x | 6.21x | 5.66x |
| P&L/笔 | +2.54% | +2.28% | +2.42% |
| Avg Hold | 2.4b | 2.3b | 2.9b |
| Total P&L | - | - | +4413.79% |

Key observations at scale:
- 759/4552 (16.7%) stocks are tradeable — consistent with 12-16% from smaller tests
- 1823 trades is the highest count of any 60min version (V465: 1472, V468: ~800 estimated)
- WR drops from 60.9% to 58.3% at scale — ~2.6pp degradation from 200 to 4552 (normal)
- RR drops from 6.21x to 5.66x at scale — ~9% degradation (normal)
- 41.7% of trades have RR <= 1.5x — high proportion of low-RR exits
- 18.0% of trades have RR > 10x — strong tail performance

## V469_final: Best Hybrid

V468 entry logic + graded trailing (even with wrong G direction) = 759 stocks / 1823 trades. The sequence direction matching fix and accepting all sequences (not just SCOUT) is the key improvement.

V468 (SCOUT-only): small sample, tighter selection
V469_final (all sequences + direction match + graded trailing): wider coverage, more trades, slightly lower quality per trade

The trade count tradeoff: V469 finds 2x-5x more trades but with slightly lower WR/RR. Acceptable if you want market coverage over per-trade perfection.
