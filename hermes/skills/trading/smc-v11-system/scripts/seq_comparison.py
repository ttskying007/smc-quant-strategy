#!/usr/bin/env python3
"""V19 Sequence Filter Comparison: baseline vs sequence-only entries"""
# Location: /root/.hermes/scripts/v11/seq_comparison.py
# Run: cd /root/.hermes/scripts && python3 v11/seq_comparison.py
# Output: /root/.hermes/smc_opt_v19/v19_seq_comparison.json
#
# Compares:
#   baseline = all FVG/OB entries (no sequence filter)
#   sequence = only entries that are terminal signals of a detected sequence
#
# Key finding: Sequence filter improves WR (+3.8pp) and PnL (+11%)
# but kills 92% of trades (5,136 → 393).
