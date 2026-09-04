# V28 Unified Pure SMC Engine — Architecture & Operation Guide

## V28 Engine (2026-05-20)
Complete rewrite of the quality/exits layer on top of V27 signal detection.

### A. Signal Quality Stratification (`smc_core_v28.py`)
- **OB**: STRONG / MEDIUM / WEAK (by displacement body ratio, zone age, entry proximity)
- **OTE**: STRONG / MEDIUM / WEAK (by retrace position 0.62-0.79, RR quality, ATR)
- **BPR**: HIGH_TRUST / LOW_TRUST / PENNY (by width ≥1%, FVG overlap quality)
- **Structure**: COMPLETE / PARTIAL / BROKEN (MSS+SWEEP=COMPLETE, CHOCH+BOS OK)
- **MSS**: PRESENT / NONE (with sweep precursor bonus)
- **Sweep**: PRESENT / NONE
- **Cost Proximity**: INSIDE_COST_ZONE / NEAR_COST / FAR
- **Resonance**: ALIGNED / PARTIAL / WEAK / CONFLICT (weekly+daily+market_state)

### B. Adaptive Exits (`smc_core_v28.py`)
- **Structural SL**: nearest swing low before entry (up to 60 bars back)
- **Cost-line SL**: smart money cost proxy (VWAP-style within zone)
- **ATR SL**: ATR-based fallback with market-state expansion
- **Multi-TP**: TP1(40%) / TP2(30%) / TRAIL(30%)
- **Breakeven**: after >breakeven_r progress (0.5-1.0R depending on market state)
- **Market-state adaptive trailing**:
  - TREND_UP: trigger=1.8R, lock=0.60R (let runners run)
  - TREND_DOWN: trigger=1.2R, lock=0.50R (lock faster)
  - HIGH_VOL: trigger=2.0R, lock=0.65R (account for noise)
  - RANGE: trigger=1.0R, lock=0.35R (take profits fast)
  - TRANSITION: trigger=1.3R, lock=0.45R
- **Progressive trailing tightening**: at >4R lock_dist×0.7, at >2.5R lock_dist×0.85

### C. Multi-Timeframe Resonance (`smc_core_v28.py`)
- **Weekly trend**: resampled daily→weekly with 20-week MA vs 40-week MA
- **Daily structure**: most recent BOS/CHOCH/MSS before entry
- **Alignment**: ALIGNED (score≥5) → PARTIAL (≥2) → WEAK (>-2) → CONFLICT
- CONFLICT signals filtered from output

### D. Diagnostics (`smc_diagnostics_v28.py`)
- Cohort decomposition by: exit_reason, market_state, zone_type, quality_grade, resonance
- High-SL-rate group detection (35%+ SL rate)
- High-RR group detection
- Auto-generated fix suggestions with priorities (CRITICAL/HIGH/MEDIUM/LOW)
- Output: `v28_diagnostics.json`

### E. Frontend (`smc_unified.py:8890`)
- V28 is default version (auto-detected if v28_trades.json exists)
- `/diagnostics` page: full cohort analysis with auto-refresh
- `/api/diagnostics`: JSON endpoint
- Nav updated: SMC V28 brand, diagnostic tab
- All normalize functions support V28 engine tag

### F. Auto-Audit Cron (`d04a64ddd736`)
- Schedule: 09:00 Mon-Fri CST
- Pipeline: full scan → diagnostics → verify outputs → apply fixes → reload frontend
- Auto-fixes: SL rate, RANGE skip, BPR threshold, quality threshold

## Key Paths
- Engine: `/root/.hermes/scripts/v25/smc_core_v28.py`
- Scan: `/root/.hermes/scripts/v25/v28_full_scan.py`
- Diagnostics: `/root/.hermes/scripts/v25/smc_diagnostics_v28.py`
- Frontend: `/root/.hermes/scripts/smc_unified.py:8890`
- Output: `/root/.hermes/smc_opt_v28/v28_{trades,picks,metrics,diagnostics}.json`
- Cron: job `d04a64ddd736`

## Quick Commands
```bash
# Full scan
cd /root/.hermes/scripts/v25 && python3 v28_full_scan.py

# Diagnostics only
cd /root/.hermes/scripts/v25 && python3 smc_diagnostics_v28.py

# Frontend (restart)
pkill -f 'python3 smc_unified.py'
cd /root/.hermes/scripts && python3 smc_unified.py &
```

## V28 quality-exit design
- Add an explicit `quality_score` for every setup.
- Penalize BPR and low-ATR environments more aggressively than OB/OTE.
- Add a smart-money cost-line proxy instead of using the zone midpoint blindly.
- Use multi-stage exits:
  - TP1 partial
  - TP2 partial
  - trailing stop for the remainder
  - breakeven after initial progress

