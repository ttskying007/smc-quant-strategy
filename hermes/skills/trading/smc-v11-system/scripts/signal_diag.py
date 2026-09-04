#!/usr/bin/env python3
"""Deep diagnostic: trace signal detection quality root causes"""
# Location: /root/.hermes/scripts/v11/signal_diag.py
# Run: cd /root/.hermes/scripts && python3 v11/signal_diag.py
#
# Per-stock output:
#   - Swing counts and HH/HL/LL/LH labels
#   - Signal counts by type
#   - CHOCH/BOS utilization (crossed vs uncrossed)
#   - Sweep opportunities vs actual detections
#   - EQL/EQH adjacent-pair comparison count
#   - Uncrossed swing points (potential signals missed)
