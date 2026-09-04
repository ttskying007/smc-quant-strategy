# Structure SL/TP & New Signal Detection (2026-05-09)

## SMC Structure-Based SL/TP

**File:** `v11/structure_sl_tp.py`

Replaces V28's fixed 0.3% trailing with SMC structure-aware SL/TP.

### Priority Chain

```
SL (from most to least preferred):
  1. Swing Low - most recent structural support
  2. FVG Lower - last FVG bottom boundary
  3. OB Bottom - last OB bottom
  4. Sweep Low - last sweep low (tightest)
  5. ATR% - fallback when no structure (0.3×ATR, min 0.5%)

TP (from most to least preferred):
  1. Next Swing High - structural resistance ahead
  2. Next FVG Upper - next gap above
  3. 2R Fixed Target - minimum viable profit
```

### Ideal SL Range
- Minimum: 0.3% (too tight kills WR)
- Sweet spot: 0.5% ~ 1.0×ATR
- Maximum: 2.5×ATR
- When swing/fvg SL is in the sweet spot -> priority kept
- When swing/fvg SL is too wide (>2.5×ATR) -> try next priority

### Files
- `v11/structure_sl_tp.py` — `calc_structure_sl_tp()`, `calc_structure_sl()`, `calc_structure_tp()`, `calc_trailing_structure()`

---

## New SMC Signals Added to signals_v11.py

6 new signal detection functions added on 2026-05-09, bringing total to 14 signal types.

### 1. IFVG (Inversion FVG) — `detect_ifvg_v11`
- **What:** FVG that has been fully mitigated (filled); the FVG zone becomes inverse support/resistance
- **Bull FVG filled** -> IFVG_Bear (lower becomes resistance)
- **Bear FVG filled** -> IFVG_Bull (upper becomes support)
- **Trigger:** At `mitigated_at` index of original FVG
- **Visual:** Purple dashed rectangle

### 2. Breaker Block — `detect_breaker_block_v11`
- **What:** After CHOCH, the last OB in the opposite direction becomes a "broken" order block
- **Bull CHOCH** -> last Bear OB becomes BreakerBlock_Bull
- **Bear CHOCH** -> last Bull OB becomes BreakerBlock_Bear
- **Search:** Up to 30 bars back for last matching OB
- **Visual:** Blue dashed rectangle

### 3. EQL (Equal Highs/Lows) — `detect_eql_v11`
- **What:** Two candles 2-15 bars apart with high/low within 0.3% tolerance
- **EQL_High** = equal high = bearish (resistance)
- **EQL_Low** = equal low = bullish (support)
- **Visual:** Red/green horizontal dashed line

### 4. OTE (Optimal Trade Entry) — `detect_ote_v11`
- **What:** 61.8% Fibonacci retracement from the most recent impulse move
- **Needs:** Swing points with impulse >1%, then retracement enters 61.8% zone
- **OTE_Bull:** uptrend + retracement to 61.8% of impulse up
- **OTE_Bear:** downtrend + retracement to 61.8% of impulse down
- **Visual:** Purple circle marker

### 5. MSS (Market Structure Shift) — `detect_mss_v11`
- **What:** Micro structure break (smaller/faster than CHOCH)
- **How:** Price breaks the 5-bar local high/low by >0.3%
- **MSS_Bull:** close above recent 5-bar high
- **MSS_Bear:** close below recent 5-bar low
- **Visual:** Green/orange small triangle

### 6. PO3 (Power of 3) — `detect_po3_v11`
- **What:** Accumulation-Manipulation-Distribution cycle
- **ACC (Accumulation):** 3-8 narrow-range candles (<3% range) with low volume (<80% avg)
- **MAN (Manipulation):** Immediate breakout beyond ACC range (false break)
- **DIS (Distribution):** Price reverses and moves opposite within 1-7 bars
- **Output:** 3 signals per PO3 pattern (ACC/MAN/DIS)
- **Visual:** Gray/orange/green rectangle markers

---

## Frontend Viewer v2 — Full Signal Visualization

**File:** `smc_trade_viewer_v2.py` | **Port:** 8897

### Signal Statistics Example (000426.SZ, 300 bars)
```
total: 230 | fvg: 39 | sweep: 0 | ob: 11 | choch: 1 | bpr: 37
ifvg: 39 | eql: 28 | ote: 8 | mss: 34 | po3: 33
bull: 108 | bear: 111
```

### Legend Interaction
All signal types are togglable by clicking the legend:
```
FVG | IFVG | OB | BSL/SSL | BOS/CHOCH | BPR | EQL | OTE | BB | PO3 | MSS | SL/TP
```
