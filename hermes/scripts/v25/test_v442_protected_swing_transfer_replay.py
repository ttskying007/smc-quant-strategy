#!/usr/bin/env python3
"""Contract tests for V442 Protected-Swing Transfer frozen replay."""
from __future__ import annotations
import importlib.util
from pathlib import Path
MODULE=Path(__file__).with_name('v442_protected_swing_transfer_frozen_t1_replay.py')
def load():
    s=importlib.util.spec_from_file_location('v442',MODULE); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def bar(o,h,l,c,t): return {'o':float(o),'h':float(h),'l':float(l),'c':float(c),'t':t}
def test_strict_t1_and_protected_low_stop():
    m=load(); bars=[bar(100,101,99,100,'20260101'),bar(102,104,101,103,'20260102'),bar(105,106,104,105,'20260103'),bar(105,111,103,110,'20260104')]+[bar(110,111,109,110,f'202602{i:02d}') for i in range(1,32)]
    row={'takeover_idx':'1','eligible_entry_idx':'2','new_protected_low_price':'100'}
    result=m.replay(row,bars,[(0,0,110,'20251201')])
    assert result['sl']==99.0 and result['exit_idx']==3 and not result['t1_violation']
def test_entry_chronology_must_be_next_session():
    m=load(); bars=[bar(100,101,99,100,f'202601{i:02d}') for i in range(1,35)]
    assert m.replay({'takeover_idx':'1','eligible_entry_idx':'3','new_protected_low_price':'90'},bars,[])['status']=='INVALID_ENTRY_CHRONOLOGY'
if __name__=='__main__':
    tests=[v for n,v in sorted(globals().items()) if n.startswith('test_')]
    for t in tests:t()
    print(f'PASS: {len(tests)} V442 frozen-replay tests')
