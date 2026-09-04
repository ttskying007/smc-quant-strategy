# V7.0 Frontend Sync — signal_chain 渲染模式

## 旧版问题 (V6.2)

前端通过匹配 trade.pattern → sequence.pattern 来渲染信号链。
但 trade.pattern = "FVG_immediate" / "OB_retrace"，而 sequence.pattern = "LIQ→FVG" / "CHOCH→OB"。
命名体系完全不同 → 100%匹配失败 → fallback到单信号标记。
导致: K线图表上的买卖点与实际交易历史对应不上。

## 新版方案 (V7.0)

回测引擎在每个trade中写入 `signal_chain` 字段:
```json
{
  "signal_chain": [
    {"type": "Sweep_SSL", "bar": 36, "price": 10.50},
    {"type": "FVG_Bull", "bar": 38, "price": 11.20}
  ],
  "entry_bar": 39,
  "entry_price": 11.30,
  "pattern": "Sweep_SSL→FVG_Bull",
  "pattern_type": "combo"
}
```

前端直接读取 signal_chain:
- 每个链节 → 圆角矩形标记 (A, B, C...)
- 链节间 → 虚线连接
- 最后一个链节 → 虚线连接到 BUY pin
- BUY pin 位置 = dates[entry_bar]

不再依赖 sequence 匹配。100%准确。

## BUY pin 对齐验证

dates[entry_bar] 的实际日期 vs trade.entry_date:
- 已验证: OHLCV index 与 trade entry_date 完全一致
- BUY = pin symbol, 绿色(won) / 红色(lost)
- SELL = diamond symbol, 绿色/红色

## 前端额外可视化 (V7.0新增)

- zone_low 线: 橙色虚线 (仅retrace entry)
- SL线: 红色虚线
- TP线: 绿色虚线
- entry_mode 显示: 🔽回调 / ▶即时
- trade table 新增"模式"列
