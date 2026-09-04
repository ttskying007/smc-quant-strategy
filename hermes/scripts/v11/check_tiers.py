#!/usr/bin/env python3
import json
d = json.load(open('/root/.hermes/smc_signals/stock_quality_ratings.json'))
print('total_stocks:', d['total_stocks'])
print('recommended:', d['recommended'])
print('tiers:', d['tier_distribution'])
print('stocks_listed:', len(d['stocks']))
# Count by tier in the actual list
from collections import Counter
tiers = Counter(s['tier'] for s in d['stocks'])
print('Actual tiers in list:', dict(tiers))
