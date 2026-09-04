# K线双层高亮 V21 (2026-05-18)

## 旧逻辑的问题

V19: 找"最近未击穿OB" → 搜索附近信号 → 标记。问题:
1. 标记的是任意一个OB，与该股票的实际交易无关
2. 位置可能离当前价格很远（用户反馈"离当前是比较远的距离"）
3. trade_map缺少V19/V18/V17，选V19时回退到V13数据

## V21双层高亮

### 第一层: Zone原点 (选股表中的股票)
从V21 picks/trades中查找该股票的zone_bar:
```python
stock_pick = next(p for p in picks if p['symbol'] == symbol)
stock_trade = next(t for t in trades if t['symbol'] == symbol)
zb = stock_trade.get('zone_bar', -1)
highlight.append({'bar': zb, 'num': 1, 'type': f'Z:{seq}'})
```
标注为 `Z:OB→IDM` (红色roundRect)，显示为选股的原因。

### 第二层: 近期信号 (最后50根K线)
扫描最后50bar内signals_list中的关键SMC信号:
```python
short_map = {'OB_Bull':'OB', 'Sweep_SSL':'LIQ', 'CHOCH_Bull':'CH',
             'FVG_Bull':'FVG', 'Pinbar_Bull':'PB', 'IFVG_Bull':'IF'}
for bi in range(max(0, last_n - 50), last_n):
    for st in bar_map.get(bi, []):
        highlight.append({'bar': bi, 'num': n, 'type': short_map.get(st, '')})
```
标注为 `OB`/`CH`/`LIQ`/`FVG` 等(diamond标记)，显示近期是否有新的SMC活动确认Zone有效性。

### 后备逻辑
如果股票不在当前picks中(无zone_bar)，回退到历史trade数据:
```python
sig_date = t.get('signal_date') or t.get('entry_date')
bi = bar_idx[sig_date]
```

## 前端渲染

```javascript
// JS buildSignalPoints() in smc_unified.py
var hlMap = {};
window._highlight.forEach(function(h) {
    hlMap[h.bar] = {n: h.num, t: h.type};
});

// num=1 → ① (U+2460), num=2 → ② ...
var cn = String.fromCharCode(0x245F + hl.n);
fp.push({
    name: cn + hl.t,
    symbol: 'roundRect', symbolSize: [52, 24],
    itemStyle: {color: '#ff0000', borderColor: '#ffff00', borderWidth: 3},
    label: {show: true, formatter: cn + hl.t, color: '#ffffff', fontSize: 14, fontWeight: 'bold'}
});
```

## 验证

所有选股表202只 → K线全部有Zone原点+近期信号标记:
```
003027.SZ: ① Z:OB→IDM(bar=204) + ②CH(260) ③MSS(260) ④LIQ(261) ⑤CH(265) ⑥PB(283) ⑦FVG(286)
605007.SH: ① Z:OB→IDM(bar=225) + ②FVG(262) ③PB(263) ④OB(270) ⑤FVG(284) ⑥IF(285)
```
