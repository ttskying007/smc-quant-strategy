#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

BASE = Path('/root/.hermes/smc_opt_v98_reachable_5r_probability_gate')

def load(name):
    return json.loads((BASE / name).read_text())

def test_v98_active_picks_have_frontend_contract_fields():
    rows = load('v98_active_picks.json')
    assert rows, 'v98 active picks empty'
    required = ['engine','pick_date','join_date','pickDate','joinDate','selectDate','选股日期','加入日期','zone','zone_type','cost_line','volatility','volatility_pct','entry_price','sl','tp1','tp2','tp3','tp2_rr','tp3_rr','rr','production_grade']
    missing = [(r.get('symbol'), k) for r in rows for k in required if r.get(k) in (None, '')]
    assert not missing, missing[:20]
    assert {r.get('engine') for r in rows} == {'V98_REACHABLE_5R_PROBABILITY_GATE'}

def test_v98_a_production_rr_gate():
    rows = load('v98_active_picks.json')
    prod = [r for r in rows if r.get('production_grade') == 'A_PRODUCTION']
    assert prod, 'v98 active A production picks empty'
    assert all(float(r.get('tp2_rr') or 0) >= 5 for r in prod)
    assert all(float(r.get('tp3_rr') or 0) >= 8 for r in prod)
    assert all(float(r.get('tp2_rr') or 0) < 12 for r in prod)

if __name__ == '__main__':
    test_v98_active_picks_have_frontend_contract_fields()
    test_v98_a_production_rr_gate()
    print('PASS V98 frontend fields + production RR gate')
