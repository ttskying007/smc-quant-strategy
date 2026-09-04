# Reversal State Machine: Independent Raw-Bar Witness

Use after outcome-blind state-machine generation and before any outcome/replay file is opened.

## Contract under test

```text
confirmed SSL pivot
→ later wick sweep + close reclaim
→ break of a pre-sweep, right-confirmed reference high (CHOCH)
→ post-CHOCH bullish displacement FVG + causal bearish-origin OB
→ pristine first touch
→ same-bar reclaim
→ one hold bar
→ following bar is only the entry identity
```

## Independent witness requirements

The witness must not import the generator. It reads only raw OHLC and terminal chain identities and independently asserts for every valid chain:

1. SSL pivot passes left/right confirmation and confirmation time is strictly before sweep.
2. Reference high passes left/right confirmation and confirmation time is **strictly before** sweep. A high whose confirmation completes on the sweep bar is not eligible.
3. Sweep pierces SSL by the frozen depth and closes back above SSL.
4. CHOCH is the first qualifying close-acceptance break inside the frozen window.
5. FVG occurs after CHOCH and its two raw-bar anchors exactly reproduce zone bounds.
6. Causal OB is the final bearish origin candle before displacement, never the break bar.
7. Recorded touch is the first raw zone intersection after FVG creation.
8. Touch either immediately reclaims or terminates; hold is exactly next bar; entry identity is exactly one bar after hold.
9. `symbol + entry_time` and `symbol + entry_date` are unique.

## Cancellation taxonomy

Never overload a terminal reason across different lifecycle phases. Preserve at least:

- `CANCEL_ZONE_INVALIDATED_FIRST_TOUCH`
- `CANCEL_FIRST_TOUCH_FAILED`
- `CANCEL_ZONE_INVALIDATED_DURING_HOLD`
- `CANCEL_HOLD_FAILED`

A generic invalidation reason makes it impossible to distinguish a failed first touch from a valid reclaim that later loses the zone during hold.

## Gate

A generator self-check is not sufficient. The independent raw-bar witness must have zero semantic failures before chart review or a frozen strict-T+1 replay. A semantic pass proves neither profitability nor production eligibility.
