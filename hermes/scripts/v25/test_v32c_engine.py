#!/usr/bin/env python3
import sys
sys.path.insert(0, '/root/.hermes/scripts/v25')
import v32c_engine as e


def bar(t,o,h,l,c): return {'t':t,'o':o,'h':h,'l':l,'c':c,'v':1000}


def test_limit_entry_waits_for_zone_retouch_after_gap_above():
    ks=[bar('1',10,10.2,9.9,10.1), bar('2',11,11.2,10.8,11.1), bar('3',10.9,11.0,10.1,10.5)]
    ent=e.entry_from_limit_retouch(ks,0,{'zone_low':10,'zone_high':10.5},max_wait_bars=3)
    assert ent == (2,10.5,'LIMIT_RETOUCH_ZONE_HIGH')


def test_limit_entry_rejects_no_retouch_chase():
    ks=[bar('1',10,10.2,9.9,10.1), bar('2',11,11.2,10.8,11.1), bar('3',10.9,11.0,10.7,10.8)]
    assert e.entry_from_limit_retouch(ks,0,{'zone_low':10,'zone_high':10.5},max_wait_bars=2) is None


def test_limit_entry_rejects_zone_invalidation_before_retouch():
    ks=[bar('1',10,10.2,9.9,10.1), bar('2',10.8,10.9,9.7,9.8), bar('3',10.4,10.5,10.0,10.2)]
    assert e.entry_from_limit_retouch(ks,0,{'zone_low':10,'zone_high':10.5},max_wait_bars=3) is None


def test_limit_entry_open_inside_zone():
    ks=[bar('1',10,10.2,9.9,10.1), bar('2',10.3,10.8,10.1,10.7)]
    assert e.entry_from_limit_retouch(ks,0,{'zone_low':10,'zone_high':10.5},max_wait_bars=2) == (1,10.3,'LIMIT_OPEN_IN_ZONE')
