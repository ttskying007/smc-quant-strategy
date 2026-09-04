# ECharts Frontend Debugging Pitfalls (2026-05-13)

## 1. markPoint data format

ECharts markPoint items use `coord` for position, NOT `value`:
```python
# CORRECT:
{'coord': [date_str, price], 'value': 'label_text', ...}

# WRONG (silently fails):
{'value': [date_str, price], ...}
```

Entry marks use `coord` + `value` for label:
```python
{'name': 'E1', 'coord': [dates[ei], ep], 'value': 'E1', 'symbol': 'pin', ...}
```

## 2. markPoint with mixed symbols

When markPoint has a default symbol ('pin') but individual items specify different symbols:
- Items CAN override the series-level symbol
- Swing dots use 'triangle' with symbolRotate
- Entry marks use 'pin'

```python
# Series level:
markPoint: {data: entryMarks.concat(exitMarks).concat(swingDots), symbol: 'pin', symbolSize: 30}
# Individual items override symbol:
swing_dots.append({'coord': [...], 'symbol': 'triangle', 'symbolRotate': 180, ...})
```

## 3. Custom series + renderItem causes JS parse errors

DO NOT use `type: 'custom'` with `renderItem` in ECharts unless absolutely necessary.
It requires complex rendering logic and is prone to parse errors.

Instead, add markLines to the main KLine series:
```javascript
markLine: {silent: true, symbol: 'none', data: slLines.concat(tpLines).concat(sigLines).concat(structArrows)}
```

## 4. JS Error: literal `e.message` in catch block

When you see `JS Error: '+e.message+'</p>` (literal, not interpolated), the JavaScript has a SYNTAX error BEFORE the try block. The catch block never executes.

Common causes:
- Unescaped quotes in template strings
- Malformed JSON data
- Custom series renderItem syntax errors
- Template literal `{{}}` escaping issues in Python f-strings combined with JavaScript objects

## 5. Debugging approach

1. Check the rendered HTML source: `curl ... | grep 'var swingDots'`
2. If JS shows literal error message → syntax error, not runtime
3. Remove complex series (custom, markLine with arrows) one at a time to isolate
4. Test with minimal ECharts config first, then add features incrementally
