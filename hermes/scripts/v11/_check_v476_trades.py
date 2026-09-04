"""检查V476交易格式"""
import json
t = json.load(open('/root/.hermes/smc_opt_v476/v476_full.json'))
print(f"Total trades: {len(t)}")
print(f"Keys in first trade: {list(t[0].keys())}")
print(f"First trade: {json.dumps(t[0], indent=2)[:500]}")
