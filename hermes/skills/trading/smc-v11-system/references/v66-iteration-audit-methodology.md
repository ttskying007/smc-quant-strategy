# V66+ Iteration Audit Methodology

Use this methodology when diagnosing V66 or later-version SMC trading systems that show **high WR (90%+) but underlying signal quality issues**. These numbers are typically statistical artifacts from over-filtering, not real signal superiority.

## When to Apply This Audit

Trigger signs that warrant this full audit:
- WR > 85% with <200 trades (likely over-filtered)
- SL_HIT rate > 5% of winning trades
- Many trades have SL exactly equal to zone_low (no buffer)
- Entry position mostly outside zone boundaries (>20% above zone_high)
- No sweep events in the signal chain despite sweep detection existing
- All entries occur at exactly `conf_bar + 1` (no retrace waiting)

## The Audit Protocol

### Step 1: Trace Signal Chain Ordering

For each trade, verify the sequence: `source_event_idx → zone_idx → conf_idx → entry_idx → exit_idx`

```python
se = t.get('source_event_idx')  # OB/FVG created
zn = t.get('zone_idx')           # zone bar
cf = t.get('conf_index')          # BOS/CHOCH confirm
en = t.get('entry_index')         # entry bar
ex = t.get('exit_index')          # exit bar
```

**Red flags**:
- `entry_idx == conf_idx + 1` for 100% of trades → **no retrace waiting**
- `entry_idx < conf_idx` → **entry before confirmation (critical bug)**
- `zone_idx >= conf_idx` → **zone created after confirmation (SMC violation)**

### Step 2: Analyze SL Position vs Zone

Count how many trades have SL at each position relative to zone_low:

```python
sl_at_zone = sum(1 for t in trades if abs(t['sl'] - t['zone_low']) < 0.001)
sl_below_zone = sum(1 for t in trades if t['sl'] < t['zone_low'])
sl_above_zone = sum(1 for t in trades if t['sl'] > t['zone_low'])
```

**Red flags**:
- `sl_at_zone > 30%` → **SL has no buffer, intraday wicks cause premature SL_HIT**
- `sl_at_zone == 0 but sl_below_zone > 0` → already has buffer (good)

### Step 3: Check Entry Position Distribution

Calculate where entry price falls relative to zone:

```python
for t in trades:
    ep = t['entry_price']
    zl = t['zone_low']
    zh = t['zone_high']
    position = (ep - zl) / (zh - zl) * 100
    # position < 0: below zone
    # 0-100: inside zone (0-50 = lower half, 50-100 = upper half)
    # > 100: above zone
```

**Red flags**:
- `>20% above zone` → price never traced back to POI (entry is breakout-chasing)
- `>60% in upper half of zone` → missing best entry opportunity at zone bottom
- `>10% below zone` → zone potentially invalidated

### Step 4: Verify Market State

Check if market_state is actually computed or missing:

```python
missing = sum(1 for t in trades if not t.get('market_state'))
trend_up = sum(1 for t in trades if t.get('market_state') == 'TREND_UP')
trend_down = sum(1 for t in trades if t.get('market_state') == 'TREND_DOWN')
```

**Red flags**:
- `missing == 100%` → market state never computed (can't filter downtrends)
- `trend_down > 30%` → many trades in downtrend (A-share T+1 risk)

### Step 5: Check Sweep Pre-validation

```python
has_sweep = sum(1 for t in trades if t.get('source_event_type') == 'SWEEP' 
                or t.get('sweep_tag') == 'SWEEP_TO_STRUCTURE')
```

**Red flags**:
- `has_sweep == 0` → sweep signals exist but not connected to trade chain

### Step 6: Retrace Tracking

Check if the system waits for price to retrace into zone before entry:

```python
for t in trades:
    entry_idx = t['entry_index']
    conf_idx = t['conf_index']
    # Look at bars between conf and entry
    retrace_bars = klines[conf_idx:entry_idx+1]
    # Check if any bar touched zone
    touched = any(b['low'] <= zone_high and b['high'] >= zone_low 
                  for b in retrace_bars)
```

**Red flags**:
- `100% no retrace` — system enters immediately on confirm bar
- `0% had retrace` — system never waits for price to test zone

## The High WR Illusion

Critical insight from V66 audit: **WR=90% across 137 trades often means the system filtered 50%+ of candidates before backtesting, not that signals are 90% accurate.**

Real signal accuracy for V59 engine (verified by V67 full backtest): **~41%**. V66's 90% comes from:
- V64 post-filter: rejected 45 losing trades
- V65 loss-review gate: rejected 126 trades (47% of V64)
- V66 REENTRY overlay: rejected 6 trades

So 137 "winning" trades are the survivors of 269 V64 trades, which are survivors of V59's ~1500 raw signals.

## Common V66 Code-Level Defects

From the 2026-06-10 audit cycle:

| Defect | Code Location | Fix |
|---|---|---|
| SL exactly at zone_low | `compute_sltp()` in daily_scan.py | Add `hard_floor_sl = zone_lo * 0.995` (0.5% buffer) |
| Entry above zone | `scan_last_bars()` in daily_scan.py | `if (ep/zh-1)*100 > 0.8: continue` |
| No retrace waiting | `scan_last_bars()` daily_scan.py | Architecture change needed (Phase 3) |
| Market state missing | daily_scan.py `_pass_daily_gate()` | Already detected for RANGE, add TREND_DOWN/UP |
| Sweep disconnected | sweep detection exists but not used | Add `sweep_tag` metadata field |
| `entry_idx = c.bar + 1` | daily_scan.py:216 | Architecture change — needs retrace logic |

## Phase 0/1/2 Fix Pattern

When fixing SMC system bugs, follow this order:

### Phase 0 — Quick stop-bleeding (1 day)
- **SL buffer**: ensure SL has 0.5%+ buffer below zone_low
- **Entry validation**: reject extreme entry positions (>0.8% above zone, <97% of zone_low)
- **Apply to all engine variants**: daily_scan.py, full_scan.py, engine_v26.py

### Phase 1 — Add observability (2-3 days)
- **Sweep tagging**: add `sweep_tag` metadata to each pick
- **Market state tracking**: record state (TREND_UP/DOWN/RANGE) for each trade
- **Retrace tracking**: record `had_retrace` and `retrace_depth_pct` metadata
- **Don't filter on metadata yet** — observe first

### Phase 2 — Backtest verification (1 day)
- Run new logic against historical V66 trades
- Count winners/losers rejected by each filter
- Verify net positive: `rejected_losers > rejected_winners`
- Adjust filter thresholds if rejecting too many winners

### Phase 3 — Architecture rewrite (weeks)
Only after Phase 0/1/2 proven. Redesign entry logic:
- Wait for actual price retrace to zone before entry
- Implement full Sweep → Structure → POI → Retrace → Confirm → Entry chain
- Add multi-timeframe alignment (weekly + daily + 60min)

## Reference Files From This Session

- `/root/.hermes/smc_audit/v66_architecture_review.md` — full architecture audit
- `/root/.hermes/smc_audit/v66_comprehensive_gap_analysis.md` — gap analysis
- `/root/.hermes/smc_audit/v66_phase0_phase1_execution_report.md` — fix results

## Key Verification Command

Run after any SMC iteration to verify SL improvement:

```bash
python3 /tmp/phase2_verification.py  # or equivalent test script
```

Look for these metrics improving:
- `SL below zone_low: X/Y (should be 100%)`
- `Entry above zone (>0.8%): X/Y → REJECTED`
- `SL_HIT trades reduced: X → Y`
- `Kept trades WR: >85% (should not drop much)`
