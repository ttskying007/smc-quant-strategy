#!/usr/bin/env python3
"""
V29 SMC — High-Quality Pure SMC Engine
═══════════════════════════════════════
V28 root cause analysis findings:

1. 74% of losing trades: zone invalidated BEFORE SL hit → zone strength issue
2. CONFLICT resonance: 44% SL rate → MTF misalignment destroys zones
3. TREND_DOWN/TRANSITION: 34-35% SL → counter-trend trades fail
4. OB candle quality identical winners/losers → detection is fine, CONTEXT is the issue
5. Entry distance from zone_high: losers -2.77% vs winners -1.91%

V29 OPTIMIZATION:
- Hard-filter CONFLICT resonance (skip entirely)
- Hard-filter TREND_DOWN + TRANSITION market states
- Tighten entry proximity: must be within 1% of zone_high
- Only ALIGNED + WEAK resonance passes
- Expected: WR=86.0%, 766 trades (vs baseline 73.8%, 4115)

Built on V27 signal detection + V28 quality scoring.
"""
import sys
sys.path.insert(0, '/root/.hermes/scripts/v25')
import smc_core_v28 as v28
import smc_core_v27 as v27

MIN_QUALITY = 6.0          # Raised from 5.5
MIN_RR = 1.3               # Raised from 1.2
MAX_ENTRY_DIST_PCT = 1.0   # Max entry distance from zone_high (%)
ALLOWED_RESONANCE = {'ALIGNED', 'WEAK'}  # Skip PARTIAL, CONFLICT
SKIP_MARKET_STATES = {'TREND_DOWN', 'TRANSITION', 'RANGE'}  # Only TREND_UP, HIGH_VOL


def v29_enhance_setups(setups, klines):
    """V29 quality pipeline: V28 scoring + V29 hard filters."""
    enhanced = v28.enhance_setups(setups, klines)
    out = []
    for st in enhanced:
        entry_idx = st.get('entry_index', 0)
        # V29 hard filters
        # 1. Skip CONFLICT + PARTIAL resonance
        if st.get('resonance', '') not in ALLOWED_RESONANCE:
            continue
        # 2. Skip TREND_DOWN + TRANSITION
        if st.get('market_state', '') in SKIP_MARKET_STATES:
            continue
        # 3. Tighten entry proximity
        entry = float(st.get('entry_price', 0))
        zh = float(st.get('zone_high', st.get('zone', {}).get('zone_high', 0)))
        if entry and zh:
            dist = abs(entry - zh) / entry * 100
            if dist > MAX_ENTRY_DIST_PCT:
                continue
        st['engine'] = 'V29_HIGH_QUALITY'
        out.append(st)
    return out


def detect_build_backtest(klines, symbol=''):
    """Full V29 pipeline: V27 detect → V28 scoring → V29 hard filters → backtest."""
    r = v27.detect_all_signals_v27(klines)
    setups = v27.build_bullish_setups(r['signals'], klines)

    # Pre-compute cost and market state for V28 scoring
    for st in setups:
        entry_idx = st.get('entry_index', 0)
        zone = st.get('zone', {}) or {'zone_low': st.get('zone_low'), 'zone_high': st.get('zone_high'), 'index': st.get('zone_idx')}
        st['smart_money_cost'] = v28.smart_money_cost_line(zone, klines, entry_idx)
        st['market_state'] = v28.market_state(klines, entry_idx)
        q = v28.quality_score(st, klines)
        st['quality_score'] = q
        if q < MIN_QUALITY: continue
        if float(st.get('rr', 0) or 0) < MIN_RR: continue
        if st.get('zone_type') == 'BPR' and q < 7.5: continue
        grades = v28.classify_signal(st, klines)
        st.update(grades)

    # V28 resonance
    for st in setups:
        res = v28.resonance_score(st, klines, r['signals'])
        st.update(res)

    # V29 hard filters
    enhanced = v29_enhance_setups(setups, klines)

    # Backtest with V28 adaptive exits
    trades = v28.backtest_quality_setups(enhanced, klines)
    for t in trades:
        if symbol: t['symbol'] = symbol
        t['ctx_seq'] = f"{t.get('zone_type','')}→{t.get('source_event','')}→{t.get('conf_type','')}"
        t['seq'] = f"{t.get('zone_type','')}-{t.get('source_event','')}-{t.get('conf_type','')}"
        t['detail'] = t['ctx_seq']
        t['engine'] = 'V29_HIGH_QUALITY'
        t['definition_version'] = 'smc_core_v29'

    return {'signals': r['signals'], 'summary': r['summary'], 'setups': enhanced, 'trades': trades}
