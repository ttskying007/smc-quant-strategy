# OB未来函数陷阱 & 置信度过滤机制

> 发现日期: 2026-05-15 | 引擎版本: V20→V22

## SMC2026 OB 的未来函数问题

`detect_ob_smc2026()` 从全部swing(包括未来swing)向后扫描找OB，导致：
- 99.95%的OB信号由未来swing确认(中位数24bar之后)
- 回测中WR虚高(97.2%→真实可能更低)
- 实际可用OB数量极少(n≈10)

## 解决方案: 置信度分级

V22给两种OB源分配不同置信度：

| OB源 | 置信度 | 用途 | 检测方式 |
|------|--------|------|----------|
| LuxAlgo OB | 0.75 | **交易** | 从CHOCH/BOS break bar向后搜索最近反向K线 |
| SMC2026 OB | 0.65 | 仅渲染 | 从swing bar向后搜索最近反向K线 |

## V12引擎过滤实现

```python
ob_bulls = [s for s in sigs if s.type == 'OB_Bull'
            and s.idx >= 20 and s.idx < n - 10
            and s.confidence >= 0.7]  # ← 仅高置信
```

## WR演变验证

| 阶段 | OB过滤 | WR | 说明 |
|------|--------|-----|------|
| 全部OB | none | 34.5% | SMC2026低置信OB污染 |
| 部分过滤 | confidence>0 | 52.6% | 仍含大量低质OB |
| 仅高置信 | confidence≥0.7 | 80.9% | 正确结果 |

## 回测注意事项

1. **永远不要用SMC2026 OB做回测** — 未来函数污染
2. **FVG/Pinbar无此问题** — 检测不依赖swing确认
3. **LuxAlgo OB在CHOCH/BOS时检测** — 更安全，无未来数据
4. **FVG也必须确认**: V21的FVG用 `confirmed_at=i` 在信号检测时已经避开未来函数
