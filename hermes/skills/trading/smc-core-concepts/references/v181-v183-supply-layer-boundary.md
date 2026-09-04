# V181–V183 supply-layer boundary lesson

Context: after V175 production baseline was validated, the next research goal was to decide whether further improvement should come from slicing existing V167/V128 candidates, exit-layer changes, or a new signal generator.

## Durable conclusion

Do **not** keep slicing V167/V128 with the same scanner-time fields once these boundary checks fail. Treat that as a supply-layer ceiling and move to a new candidate generator or genuinely new pre-entry features.

## Acceptance gates used

### Production upgrade usable
- Combined non-leaking engine `n >= 260`
- `min_year_n >= 40`
- `WR >= 84%`
- `AvgPnL >= 6.2%`
- all-year minimum WR `>= 82%`
- micro-profit pollution `<= 1%`
- `T+1 violations = 0`
- no frontend/watchlist promotion before scanner dry-run + API/frontend smoke pass

### Research child-engine usable
- New child engine `n >= 120`
- `min_year_n >= 20`
- `WR >= 86%`
- `AvgPnL >= 6.5%`
- all-year minimum WR `>= 83%`
- `T+1 violations = 0`
- non-overlap with current production engine `>= 60%`

### Unusable
- Any outcome leak / result field in the selector
- Any T+1 violation
- Low annual stability even if aggregate AvgPnL is high
- Merely relabeling V175/V172 rows as a “new” engine
- Using historical completed trades as current candidates

## V181 result: V167 remainder is not enough

V175 production baseline:
- `n=247`, `WR=83.81%`, `AvgPnL=6.0493%`, `T+1=0`

V167 rows outside V175:
- `n=546`, `WR=81.32%`, `AvgPnL=3.8577%`
- annual WR: `2023=79.28%`, `2024=80.19%`, `2025=83.33%`, `2026=83.33%`

Search result: no scanner-time combination in the V167 remainder met the research child-engine gate. Conclusion: the V167 remainder is not a hidden second production engine.

## V182 result: V128 scanner-time fields are insufficient

A broad non-leaking rule search over V128 parallel candidates did not find a production or research-usable selector from existing scanner-time fields. This rules out continuing to cut the same V128 field set as the main path.

## V183 result: the apparent V128 “holy grail” was outcome leakage

High-performing V128 cuts depended on `exit_reason == TIME_STOP_NO_SEMANTIC_EXIT`, which is a post-trade result field and must never be used in a selector.

Examples of forbidden/leaking rules:

| rule | n | WR | AvgPnL | all-year WR min | why unusable |
|---|---:|---:|---:|---:|---|
| `exit_reason==TIME_STOP_NO_SEMANTIC_EXIT AND entry_chase_above_zone_pct<=0` | 684 | 94.59% | 15.3722% | 92.83% | uses outcome field |
| `exit_reason==TIME_STOP_NO_SEMANTIC_EXIT AND market_state==ACCUMULATION` | 903 | 89.15% | 14.5268% | 84.26% | uses outcome field |

When `exit_reason` was removed, the strongest non-leaking combinations collapsed, e.g.:

| non-leaking rule | n | WR | AvgPnL | all-year WR min | verdict |
|---|---:|---:|---:|---:|---|
| `entry_chase_above_zone_pct<=0 AND v85_zone_width_pct>=4.066` | 130 | 52.31% | 11.2672% | 33.33% | unstable / unusable |
| `entry_chase_above_zone_pct<=0 AND risk_pct>=3.498` | 133 | 54.14% | 11.1195% | 50.0% | unstable / unusable |

## Workflow rule for future SMC research

When a strong rule appears, first classify every field in the selector:

1. **Pre-entry scanner-time field** — allowed.
2. **Entry execution field** — allowed only if known before the actual order decision.
3. **Post-entry path field** — research-only unless it can be transformed into a pre-entry proxy.
4. **Outcome/result field** (`exit_reason`, realized PnL, hit flags, MFE/MAE after entry, final hold outcome) — forbidden for production/research selectors.

If the best edge lives only in outcome/result fields, the next step is **not** more slicing. The next step is to build a new generator or a non-leaking proxy feature available before entry, then rerun the full gates.

## Next valid direction

V184 should focus on a new candidate generator or pre-entry proxy for the phenomenon behind TIME winners, such as:
- entry-before-known structure expansion proxies that do not inspect future bars;
- market breadth / sector confirmation available before entry;
- independent structure lifecycle features, not merely V175/V167 labels;
- full yearly stability and T+1 audit before promotion.
