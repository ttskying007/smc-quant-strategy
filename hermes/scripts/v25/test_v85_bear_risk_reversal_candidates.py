#!/usr/bin/env python3
"""Regression: V85 must not drop BEAR_RISK SSL->CHOCH reversal setups.

June 2026 market environment is BEAR_RISK. V81 correctly finds reversal
setups, but V85 previously only promoted UP continuation / MIXED accumulation
rows, which erased the whole June active candidate set.
"""
import sys
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts/v25')

from v81_full_market_scan import ENV_PATH, KLINE_DIR, load_json, normalize_env
from v85_mixed_accumulation_generator import generate_v85_candidates


def test_bear_risk_ssl_choch_reversal_is_promoted():
    env_raw = load_json(ENV_PATH)
    env_by_date = {str(k)[:8]: normalize_env(v) for k, v in env_raw.items()}
    ks = load_json(KLINE_DIR / '002050_SZ_daily_750.json')
    rows = generate_v85_candidates('002050.SZ', ks, env_by_date)
    matches = [
        r for r in rows
        if str(r.get('event_date')) == '20260604'
        and r.get('story') == 'DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM'
        and r.get('market_state') == 'BEAR_RISK'
        and r.get('v83_takeover_type') == 'HOLD_ABOVE_POI'
    ]
    assert matches, 'BEAR_RISK SSL->CHOCH reversal candidate was dropped by V85'
    assert matches[0].get('v85_path') == 'BEAR_RISK_SSL_CHOCH_HOLD_ABOVE_POI'


if __name__ == '__main__':
    test_bear_risk_ssl_choch_reversal_is_promoted()
    print('PASS V85 BEAR_RISK reversal candidate promotion')
