#!/usr/bin/env python3
from v76_environment_hysteresis_engine import (
    annotate_environment_hysteresis,
    passes_v76_entry_gate,
    simulate_v76_exit,
)


def trade(**kw):
    base = {
        'symbol': '000001.SZ',
        'entry_date': '20240110',
        'entry_idx': 2,
        'entry_price': 10.0,
        'sl': 9.5,
        'tp1': 10.8,
        'risk_pct': 4.0,
        'market_state_v74': 'BULL_CONTINUATION',
        'v74_core_gate': True,
        'pnl_pct': 1.0,
    }
    base.update(kw)
    return base


def bar(t, o, h, l, c):
    return {'t': t, 'o': o, 'h': h, 'l': l, 'c': c}


def test_prior_distribution_blocks_single_day_fake_bull_continuation():
    env = {
        '20240102': {'market_state_v74': 'DISTRIBUTION'},
        '20240103': {'market_state_v74': 'DISTRIBUTION'},
        '20240104': {'market_state_v74': 'DISTRIBUTION'},
        '20240105': {'market_state_v74': 'DISTRIBUTION'},
        '20240108': {'market_state_v74': 'DISTRIBUTION'},
        '20240110': {'market_state_v74': 'BULL_CONTINUATION'},
    }
    t = annotate_environment_hysteresis(trade(), env)
    assert t['v76_prior5_distribution_days'] == 5
    assert t['v76_env_hysteresis_ok'] is False
    assert passes_v76_entry_gate(t) is False


def test_stable_environment_with_acceptable_risk_passes_gate():
    env = {
        '20240102': {'market_state_v74': 'RECOVERY'},
        '20240103': {'market_state_v74': 'RECOVERY'},
        '20240104': {'market_state_v74': 'ACCUMULATION'},
        '20240105': {'market_state_v74': 'BULL_CONTINUATION'},
        '20240108': {'market_state_v74': 'BULL_CONTINUATION'},
        '20240110': {'market_state_v74': 'BULL_CONTINUATION'},
    }
    t = annotate_environment_hysteresis(trade(risk_pct=5.2), env)
    assert t['v76_prior5_distribution_days'] == 0
    assert t['v76_env_hysteresis_ok'] is True
    assert passes_v76_entry_gate(t) is True


def test_risk_above_5p2_rejected_even_when_environment_is_stable():
    env = {
        '20240102': {'market_state_v74': 'RECOVERY'},
        '20240103': {'market_state_v74': 'RECOVERY'},
        '20240104': {'market_state_v74': 'ACCUMULATION'},
        '20240105': {'market_state_v74': 'BULL_CONTINUATION'},
        '20240108': {'market_state_v74': 'BULL_CONTINUATION'},
        '20240110': {'market_state_v74': 'BULL_CONTINUATION'},
    }
    t = annotate_environment_hysteresis(trade(risk_pct=5.21), env)
    assert t['v76_env_hysteresis_ok'] is True
    assert passes_v76_entry_gate(t) is False
    assert 'RISK_GT_5P2' in t['v76_reject_reason']


def test_environment_risk_exit_obeys_t1_and_exits_before_later_stop():
    env = {
        '20240110': {'market_state_v74': 'BULL_CONTINUATION'},
        '20240111': {'market_state_v74': 'DISTRIBUTION'},
        '20240112': {'market_state_v74': 'DISTRIBUTION'},
    }
    ks = [
        bar('20240108', 10, 10.2, 9.9, 10.1),
        bar('20240109', 10.1, 10.3, 10.0, 10.2),
        bar('20240110', 10.2, 10.4, 9.8, 10.0),
        bar('20240111', 10.0, 10.2, 9.8, 9.9),
        bar('20240112', 9.9, 10.0, 9.4, 9.45),
    ]
    out = simulate_v76_exit(trade(exit_idx=4, exit_reason='SL_HIT', pnl_pct=-5.0), ks, env)
    assert out['v76_exit_reason'] == 'ENV_RISK_EXIT'
    assert out['v76_exit_date'] == '20240111'
    assert round(out['v76_pnl_pct'], 4) == -1.0


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print(f'PASS {name}')
