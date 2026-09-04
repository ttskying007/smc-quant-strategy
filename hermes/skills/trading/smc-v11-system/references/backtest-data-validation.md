# Backtest Data Validation Methodology

## Why Validate

Backtest results from complex rolling engines frequently contain bugs — lookahead bias, stale entry prices, incorrect P&L calculations, data cache issues, and more. Trusting raw output numbers is dangerous. Always validate.

## Validation Checklist (7-Point Quick Screen)

### 0. Entry Price Source Trace — THE NEW FIRST CHECK

This is the #1 bug found in this codebase. Always verify before trusting any result.

Trace the entry_price chain:
1. simulate_trades → dec = make_entry_decision_v11() → dec.get('entry_price')
2. make_entry_decision_v11 → seq_result.get('entry_price')
3. analyze_sequence_v11 → last_match['price'] (last signal bar's price)
4. Compare with: ohlcv[i]['c'] (current simulation bar's close)

If (3) != (4), you have stale entry_price = forward-looking bias.
Fix: replace `entry_price = dec.get('entry_price')` with `entry_price = ohlcv[i]['c']`

Impact: V23-V25 ALL results are invalid (WR falsely inflated by 10-30%).

### 1. Hold-Bar Distribution

Check: What percentage of trades exit in 1 bar?
- A-share daily strategy: 80-95% hold=1 is normal (close entry, next bar's action determines outcome)
- But if hold=1 > 99%, something is likely wrong (nearly all trades resolved instantly)

### 2. P&L Distribution Analysis

Check: Are the gains realistic for the asset class and holding period?
- A-share daily (1-bar hold): max gain = daily price limit (10% main board, 20% ChiNext/STAR, 30% BSE)
- Hold=1 with 30%+ gain = IMPOSSIBLE for >99% of A-shares (only BSE can do 30%)

**Red flags:**
- Many trades with gains > daily limit in 1 bar → stale entry_price or lookahead bias
- No losses at all (WR=100%) for a large set → almost certainly overfitting or data leak
- Avg P&L > 10% with hold=1 → suspicious for most A-shares

### 3. Cross-Check Against OHLCV Data

Pick a few trade examples (high gain, low gain, mid gain) and manually verify.

If real P&L differs from reported P&L, the entry_price is stale (see step 0).

### 4. Signal Timing Chain Validation (NEW for V33)

Verify that signal chain codes are correct:
1. Load a specific stock + its V33 backtest trades
2. For each trade, manually trace the preceding signals within lookback=30
3. Check: chain code matches expected pattern? Target signal excluded?
4. Check: auxiliary signals (BPR/LV/RJ) are not polluting the chain?

Use the output of `score_signal_timing()` which returns full chain breakdown.

### 5. RR / PF Sanity Check

- A-share daily: RR > 10x with WR > 70% on 200+ stocks is exceptional
- PF > 100 for a 200+ stock portfolio is suspicious (would mean nearly no losses)
- In practice, even the best strategies rarely exceed PF=30-60 on a broad screen

### 6. Day-to-Day Gap Check

Check if the OHLCV data has abnormal single-bar gaps (exceeding price limits).

## Common Bug Patterns Found Using This Methodology

| Symptom | Root Cause | Likely Versions |
|---------|-----------|-----------------|
| 30%+ gains in 1 bar | Stale entry_price (signal bar vs current bar) | V23-V25 |
| WR=100% on >20 stocks | Per-bar brute force or overfit param scan | V11.3 final |
| Most wins 10-20% but TP=3% | Stale entry_price gives artificial base for TP calc | V23 |
| Avg hold=1 with huge RR variance | Daily bar gap capture — normal mechanism BUT check entry_price | All versions |
| All 200 stocks SKIP | Signal timing filtering too strict (isolated FVGs filtered out) | V33 early version |
