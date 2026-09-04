# SMC Sequence Visualization — V16.2 Final (API-Driven)

## User Requirement

从选股页点击跳转K线后,只标记序列中实际触发的那根K线,不是所有同类型信号。
如 `seq=LIQ→OB→CH` 应在图表上精确定位 ①②③ 三个标记,极其醒目。

## Iteration History

1. **v1**: Diamond markers for all key SMC types → user: "不够明显"
2. **v2**: Rect markers with seq numbering by type → user: "很多信号都这个颜色,名称一样,看不出来触发的是哪个"
3. **v3 (current)**: API returns precise `highlight` array → only specific sequence bars get big red rects

## Architecture

### API (Python `_api_kline_full`)

Reads `seq=LIQ-OB-CH` from query params:

```python
seq_parts = seq_raw.replace('→','-').replace('->','-').split('-')
# Find most recent unbreached OB_Bull
for ob in sorted(obs, key=lambda s: -s.idx):
    # Map sequence elements to nearby signals:
    # LIQ: Sweep_SSL within ob.idx-30..ob.idx
    # OB:  the OB itself
    # CH:   CHOCH_Bull after OB
    # FVG:  FVG_Bull within ±5 bars of OB
    # PB:   Pinbar_Bull within +3 bars of OB
    seq_bars[bar_idx] = (seq_position, type_abbr)
```

Returns JSON:
```json
{"highlight": [{"bar": 201, "num": 1, "type": "LIQ"}, {"bar": 222, "num": 2, "type": "OB"}, ...]}
```

### Frontend JS (buildSignalPoints)

Three-tier marker system:

| Tier | Condition | symbol | size | color | label |
|------|-----------|--------|------|-------|-------|
| **Sequence** | bar in hlMap | roundRect | [52,24] | red#ff0000 + yellow border#ffff00 | white 14px bold ①②③ |
| Key SMC | type in seqLabels (not in seq) | diamond | 8 | red#f85149 | white 7px |
| Other | everything else | circle | 5 | signal color | hidden |

```javascript
var hlMap={};
window._highlight.forEach(function(h){hlMap[h.bar]={n:h.num,t:h.type};});
// Circled numbers: String.fromCharCode(0x245F + hl.n) → ①, ②, ③...
```

## Verification

```bash
curl -s 'http://localhost:8890/api/kline_full?symbol=600132_SH&tf=daily&ver=V16.2&seq=LIQ-OB-CH' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['highlight'])"
```

## Pitfall: seq not passed to API

**Bug**: URL has `&seq=LIQ-OB-CH` but API call does NOT — because `loadKline()` only reads `sym`,`tf`,`ver` from form elements.

**Fix** (line ~190):
```javascript
var seqParam=currentSeq.length>0?'&seq='+encodeURIComponent(currentSeq.join('-')):'';
fetch('/api/kline_full?symbol='+encodeURIComponent(sym)+'&tf='+tf+'&ver='+ver+seqParam)
```

Without this fix, `window._highlight` remains `[]` and no sequence markers appear on the chart.

## User feedback resolution

- "不够明显" → 52×24 red rect + yellow border
- "很多信号都这个颜色" → API bar-level precision, non-sequence signals degraded to small diamond/hidden
