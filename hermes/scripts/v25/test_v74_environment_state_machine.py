#!/usr/bin/env python3
"""RED tests for V74 SMC environment state machine."""
import unittest

from v74_environment_state_machine import classify_market_env, classify_setup_story, passes_v74_core_gate


class TestV74EnvironmentStateMachine(unittest.TestCase):
    def test_bullish_breadth_with_negative_slope_and_rising_bear_is_distribution_not_bull(self):
        state = classify_market_env({
            'bull_breadth': 0.47,
            'bear_breadth': 0.39,
            'range_breadth': 0.14,
            'bull_slope20': -0.055,
            'bear_slope20': 0.062,
            'range_slope20': -0.007,
        })
        self.assertEqual(state, 'DISTRIBUTION')

    def test_recovery_requires_bull_breadth_improving_from_compression_without_bear_dominance(self):
        state = classify_market_env({
            'bull_breadth': 0.36,
            'bear_breadth': 0.31,
            'range_breadth': 0.33,
            'bull_slope20': 0.058,
            'bear_slope20': -0.018,
            'range_slope20': -0.04,
        })
        self.assertEqual(state, 'RECOVERY')

    def test_violent_breadth_squeeze_after_bear_risk_is_distribution_not_recovery(self):
        state = classify_market_env({
            'bull_breadth': 0.433,
            'bear_breadth': 0.1421,
            'range_breadth': 0.4218,
            'bull_slope20': 0.2483,
            'bear_slope20': -0.372,
            'range_slope20': 0.1248,
        })
        self.assertEqual(state, 'DISTRIBUTION')

    def test_bear_risk_overrides_discount_poi(self):
        trade = {
            'market_state_v74': 'BEAR_RISK',
            'stock_trend_state': 'UP_CONTINUATION',
            'stock_last_event': 'BULL_BOS',
            'reaction_type': 'RECLAIM_HIGH',
            'pd_zone': 'DISCOUNT',
            'risk_pct': 3.5,
            'zone_type': 'OB_Bull',
        }
        self.assertFalse(passes_v74_core_gate(trade))

    def test_continuation_story_requires_uptrend_bull_bos_and_reclaim(self):
        trade = {
            'market_state_v74': 'BULL_CONTINUATION',
            'stock_trend_state': 'UP_CONTINUATION',
            'stock_last_event': 'BULL_BOS',
            'reaction_type': 'RECLAIM_HIGH',
            'pd_zone': 'OTE_DISCOUNT',
            'risk_pct': 4.2,
            'zone_type': 'OB_Bull',
        }
        self.assertEqual(classify_setup_story(trade), 'UP_CONTINUATION_BOS_POI_RECLAIM')
        self.assertTrue(passes_v74_core_gate(trade))

    def test_reversal_story_requires_recovery_or_accumulation_bull_choch_and_reclaim(self):
        trade = {
            'market_state_v74': 'RECOVERY',
            'stock_trend_state': 'BULL_TRANSITION',
            'stock_last_event': 'BULL_CHOCH',
            'reaction_type': 'RECLAIM_HIGH',
            'pd_zone': 'STRUCTURE_LOW_RISK',
            'risk_pct': 2.8,
            'zone_type': 'OB_FVG_OVERLAP',
        }
        self.assertEqual(classify_setup_story(trade), 'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM')
        self.assertTrue(passes_v74_core_gate(trade))

    def test_fvg_solo_is_not_valid_demand_zone_even_in_good_environment(self):
        trade = {
            'market_state_v74': 'RECOVERY',
            'stock_trend_state': 'BULL_TRANSITION',
            'stock_last_event': 'BULL_CHOCH',
            'reaction_type': 'RECLAIM_HIGH',
            'pd_zone': 'DISCOUNT',
            'risk_pct': 3.0,
            'zone_type': 'FVG_Bull',
        }
        self.assertFalse(passes_v74_core_gate(trade))


if __name__ == '__main__':
    unittest.main(verbosity=2)
