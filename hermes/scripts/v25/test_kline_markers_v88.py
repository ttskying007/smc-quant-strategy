#!/usr/bin/env python3
import json
import urllib.request

BASE='http://127.0.0.1:8890'

def load(sym):
    return json.loads(urllib.request.urlopen(f'{BASE}/api/kline_full?symbol={sym}&tf=daily&ver=V88', timeout=30).read().decode())

def assert_trade_contract(sym):
    d=load(sym)
    assert not d.get('error'), d.get('error')
    assert d.get('trade_count', 0) >= 1, (sym, d.get('trade_count'))
    assert len(d.get('highlight') or []) >= 1, (sym, d.get('highlight'))
    t=(d.get('trades') or [])[0]
    for k in ['entry_date','entry_price','sl','sl_pct','tp_price','tp_pct','_chart_idx','_combo','zone_type']:
        assert t.get(k) not in (None, '', 0, '0'), (sym, k, t)
    assert float(t['entry_price']) > 0
    assert float(t['sl']) > 0
    assert float(t['tp_price']) > 0
    assert int(t['_chart_idx']) >= 0
    return d

if __name__ == '__main__':
    # Current V91 BEAR_RISK active pick: verifies active overlay and highlights.
    d1=assert_trade_contract('300700.SZ')
    # V88 production pick plus current-month scanner overlay should keep markers.
    d2=assert_trade_contract('002262.SZ')
    print('PASS kline V88 markers', {'300700': (d1['trade_count'], len(d1['highlight'])), '002262': (d2['trade_count'], len(d2['highlight']))})
