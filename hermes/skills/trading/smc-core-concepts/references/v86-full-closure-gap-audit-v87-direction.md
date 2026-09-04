# V86 Full Closure Gap Audit / V87 Direction

Session date: 2026-06-13

## Trigger

Use when the user challenges whether V85/V86 is a complete SMC smart-money tracking system, especially about:

- multi-timeframe confirmation;
- smaller timeframe entry for SL/RR planning;
- TP1/TP2/TP3 and R-multiple design;
- low RR trades;
- whether signal combinations were tested by sequence, timeframe, windows, entry/exit, TP/SL;
- whether the loop is actually closed.

## Key conclusion

The user is correct: V86 is production-quality as a daily-level gate, but it is **not** a complete full-stack SMC research closure.

V86 completed:

- daily-level environment → event → POI → takeover → entry → semantic exit;
- MIXED_ACCUMULATION and continuation production gates;
- basic field and T+1 checks.

V86 did **not** complete:

- real weekly/daily/60min multi-timeframe gating;
- 60min/smaller timeframe entry positioning;
- explicit SL/TP/RR fields in production JSON;
- TP1/TP2/TP3/runner exit legs;
- MFE/MAE/R-multiple postmortem fields;
- full matrix over time windows, timeframe combinations, entry modes, exit modes, and TP/SL modes.

## Evidence from V86 audit

Source: `/root/.hermes/smc_opt_v86_production_gate/v86_trades.json` (532 rows)

Missing production fields:

| Field group | Missing |
|---|---:|
| weekly_state/daily_state/m60_state/mtf_score/resonance_score | 532/532 |
| m60_entry_price/m60_sl/m60_rr | 532/532 |
| explicit sl/tp1/tp2/tp3/rr/rr_realized | 532/532 |
| exit_legs | 532/532 |
| mfe_pct/mae_pct/mfe_r/mae_r/problem_tag | 532/532 |

60min cache exists at `/root/.hermes/kline_cache_60min`, but V86 did not consume it.

## Low RR diagnosis

Derived from entry_price + risk_pct + liquidity_target:

| Metric | Value |
|---|---:|
| rows | 532 |
| min RR | 0.34R |
| p10 RR | 0.9263R |
| median RR | 2.1131R |
| avg RR | 2.5809R |

Low RR buckets:

| Bucket | n | WR | avg pnl |
|---|---:|---:|---:|
| RR < 1 | 69 | 94.20% | +0.8713% |
| RR >= 1 | 463 | 89.20% | +2.9547% |
| RR >= 1.5 | 377 | 88.86% | +3.3254% |
| RR >= 2 | 277 | 88.09% | +3.8772% |

Interpretation: low RR is not a win-rate issue; it is an entry/target efficiency issue. Many trades win but harvest only tiny liquidity targets. Some low-RR rows could improve materially if using lower timeframe/limit entry near the POI instead of daily next-open.

## TP design diagnosis

V86 only uses a single liquidity target. MFE audit shows TP1 leaves substantial money on the table:

| Scope | n | avg pnl | avg 20-bar MFE | median 20-bar MFE |
|---|---:|---:|---:|---:|
| all | 532 | +2.684% | +14.007% | +9.344% |
| TP wins | 477 | +3.269% | +14.635% | +9.981% |

392/477 TP wins had 20-bar MFE at least 2 percentage points above realized PnL. V87 must add TP2/TP3/runner legs and measure MFE capture.

## Effective signal combinations so far

Daily-level combinations are effective:

| Combination | n | WR | avg pnl |
|---|---:|---:|---:|
| BOS + BULL_CONTINUATION + DISCOUNT + continuation | 135 | 93.33% | +2.6926% |
| BOS + MIXED + DISCOUNT + mixed accumulation | 131 | 93.89% | +2.8443% |
| SSL/CHOCH + MIXED + DISCOUNT + mixed accumulation | 110 | 89.09% | +2.5009% |
| BOS + RECOVERY + DISCOUNT | 70 | 81.43% | +2.1983% |

But this is daily-only. It does not prove timeframe combinations, smaller timeframe entry, or exit-leg design are solved.

## Required V87 direction

V87 should not be another narrow filter. It must be a full matrix research pass:

1. Multi-timeframe stack:
   - Weekly: environment permission.
   - Daily: event/POI/candidate generation.
   - 60min: entry/SL/confirmation.

2. Entry modes:
   - next_open baseline;
   - zone_limit;
   - m60_reclaim;
   - m60_higher_low;
   - m60_mss.

3. SL modes:
   - daily zone_low buffer;
   - m60 swing low;
   - m60 reclaim low;
   - hybrid max/min with hard risk bounds.

4. TP/exit modes:
   - TP1 nearest liquidity or min 1R;
   - TP2 daily BSL / prior high / 2R;
   - TP3 runner/trailing;
   - explicit exit_legs;
   - POI close-break, trend damage, m60 structure break, runner trail, time stop.

5. Required output contract:
   - explicit sl/tp1/tp2/tp3/rr/rr_realized;
   - weekly/daily/m60 state fields;
   - mfe/mae in percent and R;
   - problem_tag for every loss/low-RR row;
   - T+1=0, field missing=0;
   - total>=500, yearly n>=50, yearly WR>=65;
   - RR<1 either <5% or all explained/improved by lower-timeframe entry.

## Report file

Full audit written to:

`/root/.hermes/smc_opt_v86_production_gate/v86_full_closure_gap_audit.md`
