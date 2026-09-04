# V45 Pine-Parameter / Frontend Sync / RR Audit Lessons

Use this reference when auditing SMC engine correctness, TradingView/Pine alignment, frontend synchronization, or low payoff/RR in the V45+ system.

## Pine alignment must be parameter-level, not slogan-level

Do not report "aligned with Pine" just because the implementation contains Pine-like primitives. Verify each parameter and behavior explicitly:

- Market structure swing length
- Internal/swing structure distinction
- OB swing detection length
- OB lookback window
- OB displacement multiplier and whether it is a hard filter or score
- FVG ATR multiplier / minimum gap
- FVG mitigation mode, especially Touch vs close-through
- EQH/EQL pivot length, ATR length, and threshold
- Minimum strength filter
- BOS / CHOCH / MSS trigger semantics
- Strong/Weak High-Low labels

If screenshots are low resolution, treat extracted values as tentative. Do not claim full Pine alignment until the exact Pine source or readable settings are available.

## SMC2026 profile from the reviewed screenshots

The reviewed screenshots suggested this target profile:

```text
Universal Zone:
- Normalize All Zone Heights: on
- Zone Height Method: ATR Based
- Zone Height ATR Multiplier: 0.75
- Zone Height % of Price: 0.3

Market Structure:
- Swing Length: 5
- Show BOS / CHOCH / MSS

Order Blocks:
- OB Swing Detection Length: 7
- OB Lookback: 10
- OB Displacement Multiplier: 1.5
- Max Order Blocks: 10

Fair Value Gaps:
- FVG ATR Filter: on
- FVG ATR Multiplier: 0.5
- FVG Mitigation Type: Touch
- Max FVGs: 5

Liquidity:
- EQH/EQL Pivot Length: 4
- EQH/EQL ATR Length: 200
- EQH/EQL Threshold: 0.1
- Wait For Confirmation: on

Strength:
- Minimum Strength Filter: 3
```

## Frontend synchronization checklist

When promoting or reviewing a new SMC engine version, verify all of these. Do not assume `/v45` and `/api/kline_full` use the same data path.

1. Version selector default points to the intended production version.
2. Navigation label matches the production version.
3. `/api/v45/*` endpoints read the intended bundle.
4. `/api/kline_full?ver=<version>` maps to the intended trade JSON files.
5. K-line trade overlay is populated for a symbol known to have trades.
6. Raw signal overlay source is identified: live detector vs versioned event ledger.
7. Global `/api/picks` is either intentionally legacy or explicitly switched.
8. Strong/Weak High-Low labels are checked separately from BOS/CHOCH markers.

Minimal verification endpoint pattern:

```text
/api/kline_full?symbol=<known_trade_symbol>&tf=daily&ver=<version>
```

Expected fields to inspect:

```text
version, count, signal_count, trade_count, symbol
```

## RR / payoff diagnosis pattern

When the user reports too many stops or low RR, do not only tune TP/SL. First separate signal-quality, entry-location, target-space, and exit-management causes.

Required buckets:

- `zone_type` — FVG vs OB vs IFVG if present
- `sequence_kind` — continuation vs reversal
- `conf_type` — especially two-bar hold vs mid reclaim
- `entry_mode`
- `exit_reason`
- `sl_attribution`
- `market_state` / resonance if available
- MFE / MAE distribution
- average win, average loss, payoff, PF, SL rate
- TP hit distribution, especially TP3 hit rate

Interpretation pattern from V45.4:

- High WR with low payoff can be caused by protective stops converting many trades into small wins.
- If MFE is high but TP3 hit rate is low, the market provides space but exit management or target selection is not capturing runners.
- Reversal trades can have acceptable WR but poor payoff; treat them separately from continuation.
- Mid-reclaim confirmation can have worse SL/payoff than two-bar rejection hold; compare before keeping it.
- Do not simply widen TP or delay protection if WR is being maintained by protective exits. Improve signal quality and target-space filters first.

## Recommended next-step structure

For V46-style audits:

1. Create an explicit Pine-parameter profile rather than mutating defaults silently.
2. Run side-by-side event output for current engine vs Pine-profile engine.
3. For failed/low-RR samples, compare:
   - current OB bar vs Pine-profile OB bar
   - current FVG vs Pine-profile FVG
   - BOS/CHOCH/MSS trigger bar
   - entry point vs raw/execution zone
   - whether price had actually reached the intended entry point
   - liquidity target above entry
4. Only after signal and entry correctness are verified, test exit changes.
