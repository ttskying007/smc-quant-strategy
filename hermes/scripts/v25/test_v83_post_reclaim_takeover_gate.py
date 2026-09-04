from v83_post_reclaim_takeover_gate import evaluate_post_reclaim_takeover, apply_v83_entry


def k(t, o, h, l, c):
    return {'t': str(t), 'o': o, 'h': h, 'l': l, 'c': c}


def base_candidate(**overrides):
    row = {
        'symbol': 'TEST.SH',
        'market_state': 'BULL_CONTINUATION',
        'story': 'UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM',
        'zone_low': 100,
        'zone_high': 102,
        'prior_structure_low': 98,
        'liquidity_target': 112,
        'touch_idx': 4,
        'reclaim_idx': 5,
        'entry_idx': 6,
        'entry_price': 103,
        'entry_date': '20260107',
    }
    row.update(overrides)
    return row


def test_accepts_hold_above_poi_then_delays_entry_to_confirmation_next_open():
    ks = [
        k(20260101, 105, 106, 104, 105),
        k(20260102, 105, 107, 104, 106),
        k(20260103, 106, 108, 105, 107),
        k(20260104, 107, 109, 104, 108),
        k(20260105, 104, 105, 99, 101),   # touch
        k(20260106, 101, 104, 100.5, 103), # reclaim
        k(20260107, 103, 106, 102.2, 105), # hold above zone_high
        k(20260108, 105, 108, 104, 107),   # new entry open after confirmation
    ]
    features = evaluate_post_reclaim_takeover(base_candidate(), ks)
    assert features['v83_takeover_valid']
    assert features['v83_takeover_type'] == 'HOLD_ABOVE_POI'
    updated = apply_v83_entry(base_candidate(), ks, features)
    assert updated['entry_idx'] == 7
    assert updated['entry_date'] == '20260108'
    assert updated['entry_price'] == 105


def test_accepts_higher_low_after_reclaim_even_if_close_not_strong():
    ks = [
        k(1, 105, 106, 104, 105),
        k(2, 105, 107, 104, 106),
        k(3, 106, 108, 105, 107),
        k(4, 107, 109, 104, 108),
        k(5, 104, 105, 99, 101),
        k(6, 101, 104, 100.5, 103),
        k(7, 103, 104, 101.2, 101.8), # higher low over touch low and no POI close break
        k(8, 102, 106, 101.5, 105),
    ]
    features = evaluate_post_reclaim_takeover(base_candidate(), ks)
    assert features['v83_takeover_valid']
    assert features['v83_takeover_type'] == 'POST_RECLAIM_HIGHER_LOW'


def test_rejects_immediate_poi_close_break_after_reclaim():
    ks = [
        k(1, 105, 106, 104, 105), k(2, 105, 107, 104, 106), k(3, 106, 108, 105, 107),
        k(4, 107, 109, 104, 108), k(5, 104, 105, 99, 101), k(6, 101, 104, 100.5, 103),
        k(7, 103, 103.5, 98.5, 99.5),
    ]
    features = evaluate_post_reclaim_takeover(base_candidate(), ks)
    assert not features['v83_takeover_valid']
    assert features['v83_takeover_type'] == 'POI_CLOSE_BREAK_AFTER_RECLAIM'


def test_rejects_micro_hl_break_after_reclaim():
    ks = [
        k(1, 105, 106, 104, 105), k(2, 105, 107, 104, 106), k(3, 106, 108, 105, 107),
        k(4, 107, 109, 104, 108), k(5, 104, 105, 99, 101), k(6, 101, 104, 100.5, 103),
        k(7, 103, 104, 99.2, 102.5), # pierces near touch low without hold/HL
    ]
    features = evaluate_post_reclaim_takeover(base_candidate(), ks)
    assert not features['v83_takeover_valid']
    assert features['v83_takeover_type'] == 'MICRO_HL_BREAK_AFTER_RECLAIM'


def test_rejects_when_no_next_open_after_takeover_confirmation():
    ks = [
        k(1, 105, 106, 104, 105), k(2, 105, 107, 104, 106), k(3, 106, 108, 105, 107),
        k(4, 107, 109, 104, 108), k(5, 104, 105, 99, 101), k(6, 101, 104, 100.5, 103),
        k(7, 103, 106, 102.2, 105),
    ]
    features = evaluate_post_reclaim_takeover(base_candidate(), ks)
    assert not features['v83_takeover_valid']
    assert features['v83_takeover_type'] == 'NO_NEXT_OPEN_AFTER_TAKEOVER'
