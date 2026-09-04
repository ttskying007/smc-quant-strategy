#!/usr/bin/env python3
# SMC V10 — 多维共振交易系统
"""
V10 is the next-generation SMC system focused on:
1. Swing Points (多周期摆动点) — multi-period pivot detection
2. Signal Sequencing (信号顺序) — Sweep→CHOCH→FVG retest→OB order matters
3. Multi-TF Resonance (大小周期共振) — Daily/4H/1H/15min alignment
4. Multi-Indicator Resonance (多指标共振) — FVG+Sweep+OB+CHOCH+BPR
5. Per-Stock Optimization (每股票参数) — individual param sets per symbol
6. Phase-Aware Trading (阶段感知) — different params for trend/ranging phases

Architecture:
  v10/
  ├── __init__.py          # version + router
  ├── swing_points.py      # pivot high/low multi-scale detector
  ├── signal_sequencer.py  # signal sequence ordering & scoring
  ├── resonance_engine.py  # multi-TF + multi-indicator resonance
  ├── per_stock_opt.py     # per-stock parameter optimizer
  └── smc_webui_v10.py     # enhanced web dashboard
"""

__version__ = '10.0.0'
__author__ = 'Hermes SMC Team'

V10_SIGNAL_TYPES = [
    'FVG', 'IFVG', 'Sweep', 'OB', 'BPR', 'MSB',
    'SwingH', 'SwingL',          # swing points
    'Sweep_CHOCH',                # combo: sweep then structure change
    'Sweep_CHOCH_FVG',           # combo: sweep→CHOCH→FVG retest
    'FVG_OB_Stack',              # combo: FVG overlapping OB
    'MultiTF_Resonance',         # combo: same direction across TFs
]

V10_RESONANCE_WEIGHTS = {
    'sweep_present': 0.25,
    'choch_present': 0.20,
    'fvg_present': 0.15,
    'ob_present': 0.15,
    'bpr_present': 0.10,
    'swing_alignment': 0.10,
    'direction_consistency': 0.05,
}

V10_SEQUENCE_BONUS = {
    ('SweepDown', 'CHOCH_Bull', 'FVG_Retest'): 1.5,  # gold sequence long
    ('SweepUp', 'CHOCH_Bear', 'FVG_Retest'): 1.5,    # gold sequence short
    ('SweepDown', 'CHOCH_Bull'): 1.3,
    ('SweepUp', 'CHOCH_Bear'): 1.3,
    ('SweepDown', 'FVG_Retest'): 1.2,
    ('SweepUp', 'FVG_Retest'): 1.2,
    ('CHOCH_Bull', 'FVG_Retest'): 1.15,
    ('CHOCH_Bear', 'FVG_Retest'): 1.15,
    ('CHOCH_Bull', 'OB_Retest'): 1.1,
    ('CHOCH_Bear', 'OB_Retest'): 1.1,
}

# Market phases for phase-aware trading
PHASE_TRENDING_UP = 'trending_up'
PHASE_TRENDING_DOWN = 'trending_down'
PHASE_RANGING = 'ranging'
PHASE_VOLATILE = 'volatile'
PHASE_BREAKOUT = 'breakout'
