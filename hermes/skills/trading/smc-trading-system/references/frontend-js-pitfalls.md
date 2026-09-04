# SMC Frontend K-line Chart JavaScript Pitfalls

## Bug: `Unexpected token ']'` — Extra bracket after `.concat()`

**Root cause**: In the JavaScript series definition, a stray `]` after `.concat()` breaks parsing:
```javascript
// BROKEN:
series:[...].concat(...)]   // extra ] after concat
// FIXED:
series:[...].concat(...)    // no trailing ]
```

**Symptom**: `loadKline is not defined` — the entire script block fails to parse, so no functions are registered.

**Debugging technique**: In browser console:
```javascript
eval(document.querySelectorAll('script')[1].textContent)
```
This will show the exact parse error with line number.

## Bug: `loadKline is not defined`

When the script block has any syntax error, ALL functions in that block become undefined. Check:
```javascript
typeof loadKline  // "undefined" means script didn't parse
```

## CDN: ECharts

Currently using: `https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js`
Verify loaded: `typeof echarts` → `"object"`

## K-line API endpoint

`/api/kline?symbol=600519.SH&tf=daily` returns JSON:
```json
{"klines": [{"date": "20250217", "o": 1429.44, "h": 1443.42, "l": 1415.54, "c": 1420.06}, ...],
 "signals": 122, "signals_list": [...], "trades": [...]}
```
