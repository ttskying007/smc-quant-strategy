#!/usr/bin/env python3
from v71_context_event_poi_state_machine import (
    classify_market_context,
    detect_smc_events,
    build_demand_pois,
    evaluate_entry_window,
    classify_setup_story,
)


def bar(o, h, l, c, t):
    return {'o': o, 'h': h, 'l': l, 'c': c, 't': t, 'v': 1000}


def test_up_continuation_bos_pullback_to_discount_ob_reclaim_is_valid_story():
    ks = [
        bar(10.0, 10.2, 9.8, 10.1, '20260101'),
        bar(10.1, 10.5, 10.0, 10.4, '20260102'),
        bar(10.4, 10.6, 10.2, 10.3, '20260103'),
        bar(10.3, 10.8, 10.25, 10.7, '20260104'),
        bar(10.7, 10.9, 10.45, 10.5, '20260105'),
        bar(10.5, 11.2, 10.48, 11.1, '20260106'),  # BOS over prior high
        bar(11.1, 11.18, 10.62, 10.68, '20260107'), # bearish OB/retrace touch
        bar(10.68, 10.95, 10.55, 10.9, '20260108'), # reclaim
        bar(10.9, 11.1, 10.85, 11.0, '20260109'),
    ]
    ctx = classify_market_context(ks, 7)
    events = detect_smc_events(ks, 7)
    pois = build_demand_pois(ks, events, 7)
    story = classify_setup_story(ks, ctx, events, pois, entry_idx=8)
    assert ctx['context'] == 'UP_CONTINUATION_CONTEXT'
    assert any(e['event_type'] == 'BOS_BULL_CONTINUATION' for e in events)
    assert story['valid_story'] is True
    assert story['story_type'] == 'CONTINUATION_BOS_PULLBACK_POI_RECLAIM'
    assert story['poi_type'] in {'OB_DEMAND', 'OB_FVG_OVERLAP_DEMAND'}


def test_downtrend_without_ssl_sweep_or_choch_rejects_demand_poi():
    ks = [
        bar(12.0, 12.1, 11.7, 11.8, '20260101'),
        bar(11.8, 11.9, 11.2, 11.3, '20260102'),
        bar(11.3, 11.45, 10.9, 11.0, '20260103'),
        bar(11.0, 11.1, 10.6, 10.7, '20260104'),
        bar(10.7, 10.8, 10.2, 10.3, '20260105'),
        bar(10.3, 10.45, 9.9, 10.0, '20260106'),
        bar(10.0, 10.2, 9.7, 9.85, '20260107'),
        bar(9.85, 10.05, 9.6, 9.7, '20260108'),
    ]
    ctx = classify_market_context(ks, 7)
    events = detect_smc_events(ks, 7)
    story = classify_setup_story(ks, ctx, events, [], entry_idx=7)
    assert ctx['context'] in {'DOWN_CONTINUATION_DANGER', 'DOWN_REVERSAL_NEEDED_CONTEXT'}
    assert story['valid_story'] is False
    assert 'NO_VALID_LIQ_OR_STRUCTURE_EVENT' in story['fail_reasons']


def test_ssl_sweep_then_choch_then_ob_reclaim_is_reversal_story():
    ks = [
        bar(12.0, 12.2, 11.8, 12.0, '20260101'),
        bar(12.0, 12.1, 11.2, 11.3, '20260102'),
        bar(11.3, 11.5, 10.8, 11.0, '20260103'),
        bar(11.0, 11.2, 10.4, 10.6, '20260104'),
        bar(10.6, 10.9, 10.1, 10.3, '20260105'),
        bar(10.3, 10.55, 9.7, 10.45, '20260106'), # SSL sweep and reclaim
        bar(10.45, 11.35, 10.35, 11.25, '20260107'), # CHOCH over LH
        bar(11.25, 11.3, 10.42, 10.5, '20260108'), # touch OB
        bar(10.5, 10.95, 10.35, 10.88, '20260109'), # reclaim
        bar(10.88, 11.1, 10.8, 11.0, '20260110'),
    ]
    ctx = classify_market_context(ks, 6)
    events = detect_smc_events(ks, 8)
    pois = build_demand_pois(ks, events, 8)
    entry = evaluate_entry_window(ks, pois[0], 7, 9)
    story = classify_setup_story(ks, ctx, events, pois, entry_idx=9)
    assert any(e['event_type'] == 'SSL_SWEEP_RECLAIM' for e in events)
    assert any(e['event_type'] == 'CHOCH_BULL_REVERSAL' for e in events)
    assert entry['has_reaction'] is True
    assert story['valid_story'] is True
    assert story['story_type'] == 'REVERSAL_SSL_SWEEP_CHOCH_POI_RECLAIM'


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print(f'PASS {name}')
