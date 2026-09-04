# SSL-sweep reversal state-machine semantic gate

Apply this contract to a bullish intraday reversal research object before replay.

```text
confirmed external SSL
→ later wick sweep below SSL and close reclaim above it
→ close above a sweep-pre-confirmed structural high (CHOCH/MSS)
→ later bullish displacement
→ causal bearish OB plus FVG created by that displacement
→ FRESH → FIRST_TOUCH → RECLAIM → HOLD → next-bar entry identity
```

## Layer rules

### L1: liquidity and reversal background

- Swing SSL must have completed right-side confirmation before the sweep.
- The reference high must be a confirmed pivot before the sweep.
- Require wick penetration and close reclaim. A mere close below SSL is not a bullish sweep/reclaim.

### L2: structure and displacement

- CHOCH is a close above the pre-sweep reference high, not a wick.
- Displacement comes after CHOCH. Reject overnight/session-gap FVGs; a bullish FVG must belong to the identifiable post-CHOCH leg.
- The causal OB is the final bearish candle after sweep and before displacement. Never use the CHOCH bar as OB or select an arbitrary historical red candle.

### L3: irreversible POI lifecycle

```text
FRESH
  └── first interval touch
       ├── low < zone_low    => CANCEL_ZONE_INVALIDATED_ON_FIRST_TOUCH
       ├── close < zone_high => CANCEL_FIRST_TOUCH_FAILED_RECLAIM
       └── close >= zone_high => RECLAIM
RECLAIM
  └── immediate next bar
       ├── low < zone_low    => CANCEL_ZONE_INVALIDATED_BEFORE_HOLD
       ├── close < zone_high => CANCEL_HOLD_FAILED
       └── close >= zone_high => HOLD
HOLD => following unobserved bar is the only entry identity
```

A later second/third touch can never resurrect a zone. Maintain exactly one active chain per symbol; a new sweep cancels the unfinished chain.

## Oracle and replay gates

Use a separate raw-OHLC implementation—do not import the generator—to verify all generated terminal records. Require zero:

- pre-confirmation pivot use;
- event timestamp inversion;
- OB equal to CHOCH bar;
- pre-touch before reported first touch;
- second-touch reclaim admission;
- duplicate `symbol + entry_time` identities.

Review deterministic identity-selected packets for one `VALID_CHAIN`, one first-touch reclaim failure, and one first-touch invalidation. These examples must be selected without returns or future outcome fields.

After semantic review, preregister exactly one strict execution replay. Freeze structural stop, pre-entry target, A-share T+1 exit eligibility, gap/collision handling, and position serialization. A frozen replay failure closes the ontology; it cannot justify post-outcome parameter variants.
