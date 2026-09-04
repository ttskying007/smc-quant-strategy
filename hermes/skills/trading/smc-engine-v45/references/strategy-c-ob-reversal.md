# 策略C — OB反转过滤方案 (V46.3)

## 背景
V45上线后发现两个问题:
1. OB误报54% — 趋势延续的pullback被检测为OB, 不应交易
2. FVG信号质量低于OB, 拉低整体RR

## 诊断方法
分析000001.SZ的13个OB_Bull信号:
- 7个(54%)出现在上涨趋势(trend20=+1%至+7%)
- 仅有6个在下跌趋势(真正的反转OB)
- 根因: detect_ob_v11()只检查"阴线+2阳线+成交量", 无趋势约束

## is_reversal_ob() 设计

```
Bull OB判定流程:
1. 20-bar趋势计算 (trend20)
2. 10bar内SweepDown检测
3. 15bar内CHOCH_Bull检测
4. at_structure (摆动点位置)
5. score = sweep + choch + at_swing + (trend<-1%)
6. trend>+1% → 非反转(除非sweep+choch豁免)
```

## 三方案测试对比

| 方案 | WR | RR | PF | 交易数 |
|------|----|----|----|--------|
| A: V46回踩入场 | 81.5% | 2.44x | 30 | 1,429 |
| B: V45 OB-only | 98.0% | 9.58x | 753 | 946 |
| **C: V45 + 反转OB** | **98.0%** | **10.05x** | **1,394** | **247** |

## 核心教训

1. **每次只改一个变量** — V46同时改3个(反转+回踩+trailing)导致无法定位
2. **OB信号质量天然高于FVG** — 用OB SL(边界)的交易WR=100%
3. **A股日线gap = 立即入场最优** — 99.6%交易1bar退出, 回踩等不到
4. **W/L比率 > 计算RR** — 更真实反映系统质量。V463 W/L=28.8x vs RR=10.05x

## V46.3 最终配置

```
v463_engine.py 相对于 v45_engine.py 的改动:
1. 添加 is_reversal_ob() 函数
2. 修改 evaluate_v45_entry: 只接受OB入口 + 反转过滤
3. FVG_Bull门槛: 0.55 → 0.70
4. 入口类型: OB/FVG → OB_Rev/Sweep→OB
5. 早过滤: 'OB' not in sig_type → skip
```

全量4800扫描: /root/.hermes/scripts/v11/v463_full_scan.py
结果: /root/.hermes/smc_opt_v463/v463_full.json
