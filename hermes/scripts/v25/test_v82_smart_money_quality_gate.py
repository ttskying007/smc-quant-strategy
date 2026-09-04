from v82_smart_money_quality_gate import passes_v82_quality_gate, enrich_v82_features


def base_candidate(**overrides):
    row = {
        'market_state': 'BULL_CONTINUATION',
        'pd_zone': 'DEEP_DISCOUNT',
        'zone_low': 100,
        'zone_high': 101.5,
        'entry_price': 103,
        'liquidity_target': 110,
        'equilibrium': 105,
        'prior_structure_low': 99,
        'touch_idx': 10,
        'reclaim_idx': 12,
        'story': 'UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM',
    }
    row.update(overrides)
    return row


def test_accepts_context_first_deep_discount_delayed_reclaim():
    row = enrich_v82_features(base_candidate())
    assert passes_v82_quality_gate(row)


def test_rejects_recovery_and_accumulation_until_true_recovery_is_proven():
    assert not passes_v82_quality_gate(enrich_v82_features(base_candidate(market_state='RECOVERY')))
    assert not passes_v82_quality_gate(enrich_v82_features(base_candidate(market_state='ACCUMULATION')))


def test_rejects_shallow_discount_poi():
    row = base_candidate(pd_zone='DISCOUNT', equilibrium=101.6, zone_high=101.5)
    assert not passes_v82_quality_gate(enrich_v82_features(row))


def test_rejects_same_bar_or_one_bar_reclaim():
    assert not passes_v82_quality_gate(enrich_v82_features(base_candidate(touch_idx=10, reclaim_idx=10)))
    assert not passes_v82_quality_gate(enrich_v82_features(base_candidate(touch_idx=10, reclaim_idx=11)))


def test_rejects_uncontrolled_poi_width_and_bad_risk_band():
    assert not passes_v82_quality_gate(enrich_v82_features(base_candidate(zone_high=108)))
    assert not passes_v82_quality_gate(enrich_v82_features(base_candidate(entry_price=101.2)))
    assert not passes_v82_quality_gate(enrich_v82_features(base_candidate(entry_price=108)))
