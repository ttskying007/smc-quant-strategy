# K线信号渲染架构 — ECharts markArea/markLine/markPoint 模式

> 从旧版 v7_module.py 迁移到新版 smc_unified.py 的完整渲染方案。

## 架构概览

```
Server-side (Python):
  detect_all_signals_v22() → signals_list + swings_list
     ↓
  API /api/kline_full → JSON
     ↓
Client-side (JavaScript):
  ECharts option = candlestick + markArea + markLine + markPoint
```

## 信号→ECharts 映射

### 区域信号 (markArea) — 矩形半透明色块
用于有明确上下边界的信号：FVG, IFVG, OB, BPR, OTE, PO3, BreakerBlock, Rejection

```javascript
// markArea data format:
[{
  name: '1OB',          // {seq}{label}
  xAxis: dates[idx],     // 起始日期
  yAxis: zone_low,       // 下边界
  itemStyle: {
    color: 'rgba(33,150,243,0.16)',     // fill
    borderColor: 'rgba(33,150,243,0.50)', // stroke
    borderWidth: 1, opacity: 0.7
  }
}, {
  xAxis: dates[idx+10],  // 结束日期 (bar+10)
  yAxis: zone_high       // 上边界
}]
```

### 线段信号 (markLine) — 彩色虚线/实线
用于只有价格无范围的信号：CHOCH, BOS, Sweep, MSS, EQL, LiquidityVoid, SL/TP

```javascript
// markLine data format:
[{
  xAxis: dates[idx], yAxis: price,       // 起点
  label: {show: true, formatter: '1CHOCH', color: '#00BCD4', fontSize: 9, position: 'start'}
}, {
  xAxis: dates[idx+20], yAxis: price,    // 终点 (bar+20)
  lineStyle: {color: '#00BCD4', type: 'solid', width: 2, opacity: 0.6}
}]
```

### 点标记 (markPoint) — 交易入场/出场
BUY入场: 绿色图钉 + 信号组合标签
SELL出场: 青色/橙色菱形 + PnL%

```javascript
// Entry markPoint:
{name: combo, coord: [date, price], value: combo,
 itemStyle: {color: '#00e676'}, symbol: 'pin', symbolSize: 32,
 label: {show: true, formatter: combo, fontSize: 9, color: '#fff', position: 'top', fontWeight: 'bold'}}

// Exit markPoint:
{coord: [date, exit_price], value: '+12.9%',
 itemStyle: {color: '#00e5ff'}, symbol: 'diamond', symbolSize: 16,
 label: {show: true, formatter: '+12.9%', fontSize: 9, color: '#00e5ff', position: 'bottom'}}
```

## 信号样式定义 (SIG_STYLE)

区域信号必须同时有 `fill` 和 `stroke`，线段信号只有 `stroke`：

```python
SIG_STYLE = {
    'FVG_Bull':  {'fill': 'rgba(156,39,176,0.18)','stroke': 'rgba(156,39,176,0.55)','label': 'FVG'},
    'OB_Bull':   {'fill': 'rgba(33,150,243,0.16)','stroke': 'rgba(33,150,243,0.50)','label': 'OB'},
    'CHOCH_Bull':{'stroke': '#00BCD4','type':'solid','width':2,'label':'CHOCH'},
    'Sweep_SSL': {'stroke': '#8BC34A','type':'dashed','width':2,'label':'Sweep'},
    # ... 等
}
```

## 信号族切换 (Toggle Filter)

每个信号族有独立 checkbox，渲染时按 `family` 过滤：

```html
<label><input type="checkbox" id="sf-fvg" checked> FVG</label>
<label><input type="checkbox" id="sf-ob" checked> OB</label>
<!-- 16个信号族 + Swings + SL + TP -->
```

```javascript
function activeFamilies() {
    var a = {};
    document.querySelectorAll('.sf').forEach(c => a[c.dataset.f] = c.checked);
    return a;
}
// 过滤: areas.filter(m => af[m.family])
```

## HH/HL/LL/LH 摆动点折线

用 markLine 连接连续摆动点，红色=高点，绿色=低点：

```javascript
function buildSwingLines(af) {
    if (!af['swings']) return [];
    var lines = [];
    for (var i = 0; i < coords.length - 1; i++) {
        var clr = coords[i].label[0] === 'H' ? '#ff6b6b' : '#51cf66';
        lines.push([{
            xAxis: coords[i].coord[0], yAxis: coords[i].coord[1],
            label: {show: true, formatter: coords[i].label, color: clr, fontSize: 9, fontWeight: 'bold'}
        }, {
            xAxis: coords[i+1].coord[0], yAxis: coords[i+1].coord[1],
            lineStyle: {color: clr, width: 1.5, opacity: 0.5, type: 'dashed'}
        }]);
    }
    return lines;
}
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `smc_unified.py` | 前端服务器 (8890端口) |
| `signals_v22.py` | V22信号引擎 |
| `v12_engine.py` | 回测引擎 |
| `echarts.min.js` | ECharts库 (本地缓存, 1MB) |

## 已知ECharts陷阱

1. `init(dom)` 不要传 `"dark"` 参数 — 手动设置 `backgroundColor: '#0d1117'`
2. markPoint 的 `coord` 使用 `[xAxis_category_string, yAxis_value_number]`
3. 不要用 `symbolSize` 函数，用固定数值
4. tooltip 自定义 `formatter` 需遍历 params 找 `componentType === 'markPoint'/'markLine'`
