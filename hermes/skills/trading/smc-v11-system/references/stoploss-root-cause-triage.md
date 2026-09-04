# Stoploss Root-Cause Triage for SMC

Use this when a stoploss-heavy run needs diagnosis before any parameter change.

## Triage order
1. **Signal definition**
   - Does the signal match the reference definition?
   - OB/FVG located on the correct structural bar?
   - Raw zone and display zone are not mixed?

2. **Entry confirmation**
   - Is the entry too early?
   - Was a required retest / two-bar rejection hold actually present?
   - Is the model entering before the zone is touched?

3. **Target space / room to run**
   - Is there enough liquidity room ahead?
   - Is the nearest target too close or missing?
   - For layered systems, target-space weakness should downgrade or reject before it reaches SL tuning.

4. **Combination / context**
   - Does the setup need strong/weak context or MSS/CHOCH confirmation?
   - Is the sequence valid in time order, or just a same-window signal bundle?

5. **Exit logic**
   - Only after the above are clean, inspect stop logic and trailing.

## Buckets to label per losing trade
- valid signal / bad entry price
- valid signal / no executable retest
- valid signal / wrong combination path
- valid signal / over-strict gate rejection
- valid signal / market-state mismatch

## Practical rules
- If many losses share the same entry-confirmation failure, fix entry before touching SL.
- If many losses share missing/close targets, promote the target-space check into an earlier gate.
- If OB/FVG geometry is wrong, treat it as a signal-definition bug, not a trading bug.
- Never use aggregate WR alone to justify a mechanism fix.
- Re-run the full universe after every change and verify: keep/reject separation, WR, SL rate, and weighted sizing all move in the expected direction.
