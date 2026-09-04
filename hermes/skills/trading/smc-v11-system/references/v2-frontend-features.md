# V2前端新功能 (2026-05-09)

smc_trade_viewer_v2.py 端口8896 — 13 SMC信号查看器

## dataZoom — 缩放拖拽

ECharts dataZoom 组件:
- `type: 'slider'` — 底部滑杆, 可拖拽选择显示范围
- `type: 'inside'` — 鼠标滚轮缩放, 按住拖拽滚动画布
- `xAxisIndex: 0` — 作用于x轴(K线索引)
- 初始range: [0, 100] (显示最后100根K线)

"重置缩放"按钮: `chart.dispatchAction({type:'dataZoom', start:0, end:100})`

## 信号Tooltip

每个markArea/markLine的tooltip显示:
- 信号类型(中文缩写)
- 日期
- 方向(Bull/Bear)
- 强度(strength 0-10)
- 置信度(confidence 0-1)
- 价格范围(upper/lower)

实现: ECharts tooltip.formatter检测params.componentType=='markArea'或'markLine'时渲染自定义HTML。

## 股票搜索

HTML <input> + <div id="suggestions">下拉框。
触发: 输入2+字符, oninput事件。
搜索逻辑:
1. 精确匹配(code="000001")
2. 前缀匹配(code startsWith "000")
3. 子串匹配(code contains "001")
结果按匹配度排序, 前10个显示。
点击: window.location.href = '/?s=' + code。

股票列表(3291只)从v28_full_merged.json加载, 嵌入HTML的<script>中。

## 信号组合筛选

radio按钮组:
- "All signals" — 显示所有已勾选的信号类型
- "Sweep to FVG" — 只显示Sweep和FVG(信号序列模式)
- "FVG only" — 只显示FVG
- "Sweep only" — 只显示Sweep
- "CHOCH/MSS only" — 只显示CHOCH和MSS
- "Custom" — 使用下方的独立checkbox

选择组合自动联动checkbox状态, 触发applyFilters()。

## 60min叠加层

后端: /api/signals_60min?code=XXXXXX — 返回JSON {areas, lines, points}。

前端: "Show 60min" checkbox:
1. 首次选中 -> AJAX fetch /api/signals_60min -> 缓存到变量
2. 解析60min信号bars的日期, 映射到日线xAxis索引(按日期对齐)
3. 用Chart.addMarkArea/addMarkLine/addMarkPoint方法叠加渲染
4. 60min信号样式: 透明度0.3, 虚线, 不同颜色(绿色/蓝色)
5. 取消选中 -> 移除叠加层(用chart.setOption替换)

映射逻辑: 60min信号bar的日期(timestamp)匹配日线数据中相同日期的xAxis索引。

## 渲染陷阱(已有)

见SKILL.md "已知陷阱" #4-#11。
核心: ECharts 5 markArea用`{data: [{xAxis,yAxis}, {xAxis,yAxis}]}`格式。
水平markLine(BSL/SSL/EQL/LV)只设yAxis, 垂直markLine(CHOCH/MSS)只设xAxis。
