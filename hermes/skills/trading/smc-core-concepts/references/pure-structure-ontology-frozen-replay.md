# Pure-structure ontology admission and frozen replay

Use when continuing local, causal SMC research after scalar/exit branches are exhausted. The objective is to test a genuinely different market story without converting it into another threshold search.

## Required sequence

1. **Freeze a class-level ontology before outcomes**
   - Define event order, visibility/confirmation timing, cancellation, entry eligibility, structural SL and known-liquidity target.
   - State why it adds different information rather than filtering an old setup.
2. **Generate semantic seeds without outcomes**
   - Do not emit entry price, exit, PnL, MFE/MAE, target hit, or winner fields.
   - Enforce one `symbol + eligible_entry_date` identity and strict chronological indexes.
3. **Apply support gate before replay**
   - Default floor: aggregate `n>=300` and each 2023–2026 year `n>=40`.
   - If support fails, do not open outcomes and do not loosen the ontology after seeing scarcity.
4. **Independent raw-bar oracle**
   - Re-derive pivots, event geometry, first-event lifecycle, dates and prices from raw bars using a separate implementation.
   - Require zero mismatches and no forbidden outcome headers.
5. **One frozen strict-T+1 replay**
   - Predeclare entry, structural SL, pre-entry-known liquidity target, maximum hold, fees, gap handling and same-bar collision policy.
   - Run exactly once; do not search thresholds, stops, targets or holding periods after a failure.
6. **Report both aggregate and yearly economics**
   - Gross WR, net success rate, average net PnL, average win/loss, payoff ratio, profit factor, SL rate, realized R and T+1 violations.
   - A high aggregate WR is not promotion evidence if payoff, PF or any year is negative.

## Durable findings from two distinct ontologies

### ICT Unicorn conjunction

`confirmed SSL raid/reclaim -> bull CHOCH -> causal supply OB failure -> overlapping bull displacement FVG -> first retest/reclaim/hold -> next open`

- Full-market semantic seeds: 240; yearly 58/56/68/58 for 2023–2026.
- Chronology failures: 0.
- It failed only the pre-outcome aggregate support floor (`240 < 300`), so outcomes correctly remained unopened.
- Lesson: balanced yearly distribution does not override a frozen aggregate support gate.

### Turtle Soup liquidity-failure reversal

`most-recent confirmed 3L/3R SSL -> >=0.3% wick raid and close-back -> close above raid-candle high within 3 bars -> next open`

- 208,423 semantic seeds; independent oracle passed 208,423/208,423 with zero mismatch.
- Frozen strict-T+1 replay closed 202,721 trades with zero T+1 violations.
- Gross WR 70.6705%, but average net PnL only +0.1977%, payoff 0.5351, PF 1.1007.
- 2023 average net PnL -0.3432% / PF 0.8460; 2026 -0.1213% / PF 0.9361.
- Lesson: a large, semantically correct liquidity pattern can have attractive headline WR while remaining economically unstable because losses are roughly twice wins.

## Metric implementation pitfall

Never classify stops with substring logic such as:

```python
'SL_' in exit_reason
```

It falsely counts target labels containing `BSL_` as stop losses. Use an explicit stop-reason set or exact prefixes that cannot overlap:

```python
STOP_REASONS = {
    'STRUCTURAL_RAID_SL_T1',
    'SL_GAP_T1',
    'SL_TP_COLLISION_CONSERVATIVE_T1',
}
sl_rate = sum(row['exit_reason'] in STOP_REASONS for row in rows) / len(rows)
```

Always rerun and verify the corrected report after changing metric classification; do not merely patch the displayed summary.

## Closure discipline

When an ontology fails a frozen economic gate, close it without variants. Do not rescue it with post-outcome risk bands, year filters, altered TP/SL, shorter holds or cherry-picked market regimes. A subsequent direction must change the causal ontology itself.