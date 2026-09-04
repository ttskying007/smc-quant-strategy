# V45 信号组合测试 (2026-05-10)

## 动机
V44失败(14信号全部入场, WR=79.9%)后V45直接跳到4信号简化版。
需要系统验证: 不同信号组合的效果如何? FVG和OB各自贡献多少?

## 方法
- 100只股票子集 (sorted first 100), 保持运行速度(~5min/7组合)
- 每组合独立启动新Python进程 (del sys.modules + reimport)
- 修改: TRADE_SIGNAL_TYPES, ENTRY_SIGNAL_TYPES, QUALITY_THRESHOLDS
- ENABLE_BEAR=False, ENTRY_AT_ZONE=True (统一环境)
- 测试脚本: /root/.hermes/scripts/v11/v45_combo_test.py

## 7种组合结果

| 组合 | 股票 | 笔数 | WR% | RR | PF | P&L% |
|------|------|------|-----|-----|-----|------|
| A: FVG-only | 89 | 610 | 94.8 | 8.38x | 162 | +2.98 |
| B: OB-only | 84 | 476 | **97.7** | **9.99x** | **816** | **+3.73** |
| C: FVG+OB (V45) | 90 | 1080 | 96.0 | 9.04x | 266 | +3.30 |
| D: FVG+OB+Sweep | 90 | 1080 | 96.0 | 9.04x | 266 | +3.30 |
| E: FVG+OB+CHOCH | 90 | 1080 | 96.0 | 9.04x | 266 | +3.30 |
| F: All 4 | 90 | 1080 | 96.0 | 9.04x | 266 | +3.30 |
| G: All 14 | 90 | 1080 | 96.0 | 9.04x | 266 | +3.30 |

## 关键发现

### 1. OB-only 三指标全面最优
- WR=97.7% (+1.7pp vs FVG+OB)
- RR=9.99x (+10.5% vs FVG+OB)  
- PF=816 (+207% vs FVG+OB)
- 交易数476 (FVG+OB的44%) — 交易机会减少但质量大幅提升

### 2. D/G全部等于C — 硬门限阻塞
D(加Sweep), E(加CHOCH), F(All4), G(All14) 的结果与C(FVG+OB)完全相同。
原因: evaluate_v45_entry() 第512-513行硬编码:
```python
if not (is_fvg or is_ob):
    return None
```
无论ENTRY_SIGNAL_TYPES怎么配, Sweep/CHOCH/MSS/BPR等信号都无法进入。

### 3. FVG拖累OB
FVG-only < OB-only < FVG+OB (所有指标居中)。
说明FVG信号质量不如OB, 混入FVG拉低整体。

## 200只 OB-only 验证

| 指标 | 值 |
|------|-----|
| 股票 | 157/200 |
| 交易 | 946 |
| WR | 98.0% |
| RR | 9.58x |
| PF | 753 |
| P&L | +3.81% |
| 时间 | 7s |

SL: adaptive 66% WR=97.6%, ob_lower 29% WR=99.3%, swing_low 5% WR=95.8%
TP: swing_high 88.6% RR=9.80x, none 8.7% RR=7.24x, choch 2.7% RR=9.83x

## 工程含义

1. 如追求最高质量: 使用 OB-only 配置
2. 如需要更多交易: 使用 FVG+OB (牺牲RR和PF换交易数)
3. 如需真正扩展入口信号: 必须修改 evaluate_v45_entry() 硬门限
4. 信号扩展不可信: TRADE_SIGNAL_TYPES/ENTRY_SIGNAL_TYPES 当前是迷惑项

## 文件
- 测试脚本: /root/.hermes/scripts/v11/v45_combo_test.py
- 200只OB-only结果: /root/.hermes/smc_opt_v45/v45_ob200.json
- 全量OB-only结果: /root/.hermes/smc_opt_v45/v45_ob_full.json (后台扫描中)
