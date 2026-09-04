# 2026-05-09 关键会话结论

## 1. 1-bar退出是A股日线本质（不可改变）

99.6% 交易在1根K线退出。这不是bug, 是数据本质:
- SL=0.3% 只是日均波幅(2-4%)的1/10
- 入场bar i收盘 → bar i+1的gap决定胜负
- V35(固定SL/TP=0.5%): WR=36.1%, 63.8%亏损率
- V35.1(延迟trailing到+2%): WR=37.4%
- V28(紧trailing到0.2%breakeven): WR=76.6%

结论: V28紧SL+breakeven trailing把-0.3%亏损变成0.2%微赢, 总P&L为正。

## 2. 信号时序不能提升全局WR

V33(链码): WR=71.3% vs V28基线WR=76.6%
V34(POI+上下文): WR=71.9%

73%的孤立FVG已经是73%WR。时序能识别的**最佳场景**(POI回调87%, OFC 88%)只占35%的交易。

## 3. Python HTML模板运算符优先级bug

```python
# 问题代码 (错误的):
html += "<div>" + f"{value}" if condition else 'N/A' + "</div>"

# Python解析为:
("html += '<div>' + f'{value}'") if condition else ("'N/A' + '</div>'")

# 结果: 条件为真时只输出开头的<div>和数值, 后面的HTML全部丢失!
# 条件为假时只输出'N/A</div>', 缺少开头的<div>!

# 正确写法:
html += f"<div>{value:.1f}%</div>" if isinstance(value, (int,float)) else "<div>N/A</div>"

# 或更安全的(广泛适用):
html = html.replace('{placeholder}', safe_value)
```

**教训**: Python的 `+` 运算符优先级高于 `if-else`。避免在字符串拼接中使用 `if-else` 三元表达式。使用 `{placeholder}` 替换模式或f-strings包裹完整HTML片段。

## 4. ECharts CDN被墙解决方案

jsdelivr.net CDN在国内服务器(特别是DigitalOcean)上不可访问。

解决: 
1. 用Python urllib下载: `urllib.request.urlopen("https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js").read()`
2. 保存到 `/tmp/echarts.min.js`
3. 在HTTP server中路由 `/echarts.min.js` → 读本地文件返回

```python
# 在 do_GET 中添加:
if parsed.path == '/echarts.min.js':
    self.send_response(200)
    self.send_header('Content-type', 'application/javascript')
    self.end_headers()
    self.wfile.write(open('/tmp/echarts.min.js', 'rb').read())
    return
```

## 5. 清理策略

清理25GB废弃数据的经验:
- 保留: V28(最优基线)结果, V34/V35(实验), K线缓存(~/.hermes/kline_cache/)
- 删除: V12-V27, V29-V33 所有结果目录 + checkpoint目录
- 保留规则: 只保留(1)当前最优 (2)最新实验 (3)原始可复现数据
