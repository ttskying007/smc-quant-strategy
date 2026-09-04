# Live Price API Strategy (2026-05-18)

Hubble API (43.167.234.49:3101) can go down. Tencent qt.gtimg.cn is more reliable for A-share real-time quotes.

## Multi-source pattern

```python
# Primary: Tencent qt.gtimg.cn (free, no auth, gbk-encoded)
url = f"http://qt.gtimg.cn/q={','.join(tc_codes[:500])}"
# Format: sz000019 → sz prefix for 0/3-series, sh for 6-series, bj for 8/4/9
# Response: v_sz000019="51~name~code~...~price~...~chgPct~..." (fields ~ separated)

# Fallback: Hubble REST API
url = f"http://43.167.234.49:3101/api/v2/cnstock/securities?codes={codes}&fields=..."
headers = {"X-API-Key": "123456"}
```

## Tencent API field mapping

| Tencent field index | Content | Notes |
|---|---|---|
| 1 | Stock name | gbk-encoded |
| 3 | Current price | |
| 5 | Open price | |
| 32 | Change % | |
| 33 | Day high | |
| 34 | Day low | |

## Hubble timeout diagnosis

```bash
# Test connectivity
curl -s --max-time 5 "http://43.167.234.49:3101/api/v2/cnstock/securities?codes=000001&fields=code,name,price" \
  -H "X-API-Key: 123456"

# Ping works but port times out → service down
ping -c2 43.167.234.49  # typically ~80-180ms
```

## Affected systems

- `/api/live-prices` on frontend :8890
- `trading_sim.py` real-time price fetch
- Any script using `Handler.fetch_live_prices()`
