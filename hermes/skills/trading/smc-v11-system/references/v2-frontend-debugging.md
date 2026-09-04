# V2 SMC信号前端调试日志

## 架构

V2前端: `smc_trade_viewer_v2.py` (port 8896)
- 13种SMC信号在K线上绘制
- 信号编号标记 + 类型缩写
- 13个筛选checkbox (FVG/IFVG/OB/Sweep/CHOCH/MSS/OTE/EQL/PO3/BPR/LV/RB/BRK)
- 交易明细表 + 信号组合标签
- 数据来源: v28_full_merged.json + kline_cache
- 信号检测: signals_v11.py (1981行, detect_all_signals_v11)

## 关键文件

| 文件 | 位置 |
|------|------|
| V2服务器 | `/root/.hermes/scripts/smc_trade_viewer_v2.py` |
| ECharts本地 | `/tmp/echarts.min.js` (1MB) |
| V1服务器(保留) | `/root/.hermes/scripts/smc_trade_viewer.py` (port 8897) |
| 信号引擎 | `/root/.hermes/scripts/v11/signals_v11.py` |
| 交易数据 | `/root/.hermes/smc_opt_v28/v28_full_merged.json` |
| K线缓存 | `/root/.hermes/kline_cache/*_daily_300.json` |

## 信号渲染方式 (V2最终版, 2026-05-09)

### 原则: 所有信号局部化, 不出现满屏线

用户要求"不要使用竖线，不要满屏" → 所有信号从信号位置向右绘制局部线段/矩形:

| 信号类型 | ECharts功能 | 渲染方式 | 长度 |
|----------|-------------|----------|------|
| FVG, IFVG, OB, BPR | markArea (半透明矩形) | 从idx到idx+10, 竖向范围=信号upper-lower | ~10根K线 |
| OTE | markArea (斐波那契区域) | 同上 | ~10根K线 |
| PO3三阶段 | markArea (3段矩形) | 同上 | ~10根K线 |
| RejectionBlock | markArea (小矩形) | 同上 | ~10根K线 |
| BreakerBlock | markArea (小矩形) | 同上 | ~10根K线 |
| Sweep(BSL/SSL) | markLine (水平虚线) | 从idx到idx+20, 水平虚线@price | ~20根K线 |
| CHOCH(BOS) | markLine (虚线) | 从idx到idx+20, 水平虚线@price | ~20根K线 |
| MSS | markLine (虚线) | 从idx到idx+20, 水平虚线@price | ~20根K线 |
| EQL | markLine (水平实线) | 从idx到idx+20, 水平实线@price | ~20根K线 |
| LiquidityVoid | markLine (虚线) | 从idx到idx+20, 水平虚线@price | ~20根K线 |
| 编号标记 | markPoint (圆点+数字) | 在信号bar的价格位置 | 单点 |

### markLine水平线段实现 (`_pair`格式)

所有线信号(包括之前是垂直线的CHOCH/MSS)现在都是**水平线段**, 使用ECharts markLine的数组对格式:

```python
# 旧版: 满屏水平线(仅设yAxis)或满屏垂直线(仅设xAxis)
mark_lines.append({'yAxis': price, 'lineStyle': {...}})  # 满屏
mark_lines.append({'xAxis': date, 'lineStyle': {...}})    # 竖线

# 新版: 水平线段 (从idx到idx+20)
mark_lines.append({
    '_pair': [
        {'xAxis': dates[idx], 'yAxis': price},
        {'xAxis': dates[idx+20], 'yAxis': price}
    ],
    'lineStyle': {'color': ..., 'type': 'dashed', 'width': ...},
    'label': {'formatter': sname, ...},
})
```

JS端转换:
```javascript
var filteredLines = markLines.filter(function(m) { return active[m.family]; })
    .map(function(m) { return m._pair || m; });
// _pair存在时为水平线段, 不存在时为原始格式(兼容旧数据)
```

## 已知Bug与修复

### Bug 1: Canvas = 0 (chart不渲染)

**症状**: ECharts库加载成功("echarts: 5.6.0"), chart div存在(1280x600), 但canvas元素为0, chart.getOption()报错"not a function"。

**根因**: `function buildSeries() { ... }` 包裹了整个渲染代码, 但从未被调用。JavaScript中的函数定义(无调用)不会执行chart.setOption()。

**诊断命令**:
```
// 在browser console中运行:
document.querySelectorAll('canvas').length
chart.constructor.name  // 'HTMLDivElement' if bug, 'e' if ECharts instance
chart.getOption().series[0].data.length  // 300 if working
```

**修复**: 删除 `function buildSeries() {` 和对应的 `}`, 让渲染代码直接在全局作用域执行。

### Bug 2: Python pyc缓存

**症状**: 修改PY源文件后重启服务器, 但旧代码仍在运行。

**诊断**: 对比源文件与curl输出:
```
grep 'function buildSeries' source.py  # 0 (已修复)
grep 'function buildSeries' /tmp/curl_output.html  # 1 (旧缓存)
```

**修复**: 
```
find / -path '*/__pycache__/*smc_trade_viewer*' -delete
# 或指定路径:
rm /root/.hermes/scripts/__pycache__/smc_trade_viewer_v2.cpython-*.pyc
kill $(lsof -ti:8896) 2>/dev/null
python3 smc_trade_viewer_v2.py &
```

### Bug 3: HTML模板截断

**症状**: stats区域之后的HTML(筛选面板、chart div、交易明细)在浏览器中完全缺失。

**根因**: Python的`+`运算符优先级高于`if-else`:
```python
html += "WR=" + wr if wr else 'N/A' + "%"
# 实际解析为: html += ("WR=" + wr) if wr else ('N/A' + "%")
```

**修复**: 使用`{placeholder}`替换模式:
```python
html += "WR={wr_label}"
html = html.replace('{wr_label}', f'{wr:.1f}%' if wr else 'N/A')
```

### Bug 4: ECharts CDN被墙

**症状**: jsdelivr.net无法访问, 浏览器控制台显示"Failed to load resource" for echarts CDN URL。

**修复**: 
```python
if self.path == '/echarts.min.js':
    self.send_response(200)
    self.send_header('Content-type', 'application/javascript')
    self.end_headers()
    self.wfile.write(open('/tmp/echarts.min.js', 'rb').read())
    return
```

### Bug 5: ECharts 5 markArea格式兼容

**症状**: markArea数据提交到chart.setOption后, chart.getOption().series[0].markArea.data显示有数据(149条), 但canvas上不渲染任何矩形区域。

**根因**: ECharts 5不支持扁平格式`{xAxis, yAxis, xAxis1, yAxis1}`。必须使用数组对格式:
```javascript
// ECharts 5 FAILS:
markArea: { data: [{xAxis: 'd1', yAxis: 10, xAxis1: 'd1', yAxis1: 20, itemStyle: {...}}] }

// ECharts 5 CORRECT:
markArea: { data: [
  [{xAxis: 'd1', yAxis: 10, itemStyle: {...}}, {xAxis: 'd1', yAxis: 20}]
] }
```

**修复**: Python端生成时改为数组对格式:
```python
mark_areas.append({
    'family': family,  # 保留在外层用于筛选
    'data': [
        {'xAxis': dates[idx], 'yAxis': lower, 'itemStyle': {...}},
        {'xAxis': x1, 'yAxis': upper}
    ]
})
```
JS端筛选后通过`.map(function(m) { return m.data; })`提取数组对。

### Bug 6: markLine水平线含xAxis字段 (旧版, 已废弃)

此bug在2026-05-09被新的局部线段渲染方式替代(见上方"信号渲染方式")。所有线信号现在都使用`_pair`格式渲染为水平线段, 不再使用满屏水平/垂直线。

### ⚠️ Bug 7: Patch时意外删除信号append

**症状**: 信号引擎检测到200+信号, 但chart渲染为0线条/0区域。页面显示"Signals: 205 total"但markAreas/markLines/markPoints全为空。

**根因**: 修改Python代码时, patch操作意外删除了关键行 `numbered_signals.append(sig)`:
```python
# 错误: 循环结束后numbered_signals为空列表
for sig in all_signals:
    sig_counter += 1
    sig['seq'] = sig_counter
# ↑ 漏掉了 numbered_signals.append(sig)

# 正确:
for sig in all_signals:
    sig_counter += 1
    sig['seq'] = sig_counter
    numbered_signals.append(sig)
```

**教训**: 使用patch修改循环体时, 必须确保不会意外删除循环体内的关键语句。patch的diff视图可能只显示你添加的行, 但工具会删除old_string中所有不匹配的内容。

**诊断**: 先检查HTML中JS变量的值:
```javascript
markAreas.length  // 0
markLines.length  // 0
markPoints.length // 0
```
再检查信号引擎是否工作:
```python
len(detect_all_signals_v11(ohlcv)['all'])  # >0 表示引擎正常
```
对比可知问题在HTML生成阶段。

## 信号筛选实现

每个signal标记包含`family`字段。筛选checkbox通过`data-family`属性关联:
```javascript
document.querySelectorAll('.sig-filter').forEach(function(cb) {
    active[cb.dataset.family] = cb.checked;
});
var filteredAreas = markAreas.filter(function(m) { return active[m.family]; })
    .map(function(m) { return m.data; });
var filteredLines = markLines.filter(function(m) { return active[m.family]; })
    .map(function(m) { return m._pair || m; });
var filteredPoints = markPoints.filter(function(m) { return active[m.family]; });
```

## ECharts数据结构

### OHLCV格式
ECharts candlestick期望: `[open, close, low, high]` (索引0=开, 1=收, 2=低, 3=高)

```python
# 正确格式
data = [[b['o'], b['c'], b['l'], b['h']] for b in ohlcv]
```
