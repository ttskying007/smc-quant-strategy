from v84_smart_money_path_split_gate import evaluate_v84_path_gate


def base_row(**overrides):
    row = {
        'symbol': 'TEST.SH',
        'story': 'UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM',
        'market_state': 'BULL_CONTINUATION',
        'trend_regime': 'UP_CONTINUATION',
        'event_type': 'BOS_CONTINUATION',
        'v83_takeover_type': 'HOLD_ABOVE_POI',
        'v83_takeover_date': '20260106',
        'entry_date': '20260107',
        'zone_low': 100,
        'zone_high': 102,
        'entry_price': 103,
        'liquidity_target': 112,
        'sweep_level': 99,
        'touch_idx': 10,
        'reclaim_idx': 12,
        'v83_takeover_idx': 14,
    }
    row.update(overrides)
    return row


def test_accepts_continuation_only_when_hold_above_poi_and_market_stays_demand_valid():
    row = base_row()
    env_by_date = {
        '20260106': {'market_state': 'BULL_CONTINUATION'},
        '20260107': {'market_state': 'BULL_CONTINUATION'},
    }
    result = evaluate_v84_path_gate(row, env_by_date)
    assert result['v84_path_gate']
    assert result['v84_path'] == 'CONTINUATION_HOLD_ABOVE_POI'


def test_rejects_continuation_higher_low_takeover_as_weak_smart_money_control():
    row = base_row(v83_takeover_type='POST_RECLAIM_HIGHER_LOW')
    result = evaluate_v84_path_gate(row, {})
    assert not result['v84_path_gate']
    assert result['v84_reject_reason'] == 'CONTINUATION_REQUIRES_HOLD_ABOVE_POI'


def test_rejects_continuation_when_environment_deteriorates_after_takeover():
    row = base_row()
    env_by_date = {
        '20260106': {'market_state': 'MIXED'},
        '20260107': {'market_state': 'BEAR_RISK'},
    }
    result = evaluate_v84_path_gate(row, env_by_date)
    assert not result['v84_path_gate']
    assert result['v84_reject_reason'] == 'POST_TAKEOVER_ENV_NOT_DEMAND_VALID'


def test_reversal_requires_ssl_sweep_story_and_hold_above_poi():
    row = base_row(
        story='DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM',
        market_state='BEAR_RISK',
        trend_regime='DOWN_REVERSAL_REQUIRED',
        event_type='SSL_SWEEP_CHOCH_REVERSAL',
        v83_takeover_type='HOLD_ABOVE_POI',
        sweep_pierce_pct=1.2,
    )
    env_by_date = {'20260107': {'market_state': 'RECOVERY'}}
    result = evaluate_v84_path_gate(row, env_by_date)
    assert result['v84_path_gate']
    assert result['v84_path'] == 'REVERSAL_SSL_CHOCH_HOLD_ABOVE_POI'


def test_rejects_reversal_without_meaningful_ssl_pierce():
    row = base_row(
        story='DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM',
        market_state='BEAR_RISK',
        trend_regime='DOWN_REVERSAL_REQUIRED',
        event_type='SSL_SWEEP_CHOCH_REVERSAL',
        v83_takeover_type='HOLD_ABOVE_POI',
        sweep_pierce_pct=0.2,
    )
    result = evaluate_v84_path_gate(row, {})
    assert not result['v84_path_gate']
    assert result['v84_reject_reason'] == 'REVERSAL_SWEEP_PIERCE_TOO_WEAK'


def test_rejects_mixed_reversal_without_post_takeover_recovery_or_accumulation():
    row = base_row(
        story='DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM',
        market_state='MIXED',
        trend_regime='RANGE_TRANSITION',
        event_type='SSL_SWEEP_CHOCH_REVERSAL',
        v83_takeover_type='HOLD_ABOVE_POI',
        sweep_pierce_pct=1.1,
    )
    env_by_date = {'20260107': {'market_state': 'MIXED'}}
    result = evaluate_v84_path_gate(row, env_by_date)
    assert not result['v84_path_gate']
    assert result['v84_reject_reason'] == 'MIXED_REVERSAL_NEEDS_POST_TAKEOVER_RECOVERY'
