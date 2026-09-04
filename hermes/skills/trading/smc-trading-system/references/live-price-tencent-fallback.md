# Live Price API: Tencent Fallback Pattern (2026-05-18)

## Problem

Hubble API (`43.167.234.49:3101`) 宕机 — 端口可ping但HTTP超时。所有实时报价请求返回空数据，前端显示"休市"或"Hubble API无数据"。

## Solution: Tencent Primary, Hubble Fallback

```python
@classmethod
def fetch_live_prices(cls, codes):
    """Tencent first (stable), Hubble fallback."""
    result = {}
    # Try Tencent
    try:
        tc_codes = []
        for c in codes:
            if c.startswith(('0','3')): tc_codes.append(f'sz{c}')
            elif c.startswith('6'): tc_codes.append(f'sh{c}')
            elif c.startswith(('8','4','9')): tc_codes.append(f'bj{c}')
        url = f"http://qt.gtimg.cn/q={','.join(tc_codes[:500])}"
        # Parse: v_sz000019="51~name~code~...~price~...~chgPct~..."
        # fields[3]=price, fields[32]=chgPct
    except: pass
    
    # Fallback to Hubble
    if not result:
        try:
            url = f"{HUBBLE_BASE}/api/v2/cnstock/securities?codes=..."
        except: pass
    return result
```

## Key Details

- **Tencent URL**: `http://qt.gtimg.cn/q=sz000019,sh600519`
- **Format**: GBK-encoded, `~`-separated fields
- **Field 3**: current price
- **Field 32**: change percent
- **Field 1**: stock name (Chinese)
- **Field 5**: open price
- **Field 33**: high, **Field 34**: low
- **Max**: ~500 codes per request
- **Prefix mapping**: 0/3→sz, 6→sh, 8/4/9→bj
