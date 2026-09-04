# V477 扩展缺陷分析 (2026-05-15 追加)

## 背景

V477-structural-defect-analysis.md 记录了6个结构性缺陷。本次session通过全量数据复查和逐bar案例追踪，追加发现7个额外缺陷，合计13个。

## 追加缺陷

### 缺陷7: 单信号类型

V477全量2124笔交易100%为OB_Bull。FVG_Bull/CHOCH_Bull/Sweep_SSL全部被序列+共振+反转OB+MIN_PROJECTED_RR四层过滤剔除。

**影响**: 系统依赖单一信号，缺乏多样性。在OB信号稀疏的市场条件下（如大盘股、低波期），策略完全无信号。

**根因**: MIN_PROJECTED_RR=8.0过高，FVG的RR通常<6.0（gap距离小），导致FVG全被过滤。

### 缺陷8: 零市场状态识别

无牛熊/震荡/趋势判断。所有时段用同一套参数。

**应有**: FVG回补率判断市场状态（expansion/mean_reversion/transition），在不同市场状态下切换SL/TP参数。

### 缺陷9: 无分批止盈

一次全出，无TP1/TP2/余量trailing架构。错失后续行情。

### 缺陷10: 无成交量确认

放量假突破和真突破同等对待。应: 放量跌破trail才退出。

### 缺陷11: 无时间止损

max_hold=80硬设，无基于信号衰减的自适应。SMC信号有效期应为近期结构相关性，超过20bar后信号衰减应加速退出。

### 缺陷12: 无跳空保护

A股T+1下隔夜跳空可穿透SL。应检测gap_risk并调整仓位。

### 缺陷13: Pinbar检测4个代码级Bug

位置: `/root/.hermes/scripts/v11/scan_LD_v6.py` `detect_pinbars()` (行38-53)

| Bug | 描述 | 后果 |
|-----|------|------|
| 1 | `c <= o` 跳过阴线实体Hammer | 真正的长下影Pinbar但close<open被跳过 |
| 2 | `c > (o+l)/2` 判断收盘在上半部非顶部 | Pinbar要求close near HIGH, 非just-above-midpoint |
| 3 | 缺失Shooting Star (bearish pinbar) | 只看涨不看跌 |
| 4 | 无PD Array上下文验证 | 孤立的Pinbar（无OB/FVG附近）不可靠 |

## 回测数据覆盖问题

### 60min数据仅2.5月

V477使用`kline_cache_60min/`中200-bar文件，日期范围2026-02-24~2026-05-08。远未达到"至少一年"的要求。

### 日线有15月但未全量回测

`kline_cache/`中日线300-bar文件覆盖2025-02~2026-05（15个月），但V7.6只精选53只回测。

## 多周期: 零实现

- V477纯60min，V7.6纯日线，完全独立
- 无周线趋势判断（仅V7.6中简单MA20>2%过滤）
- 无60min与日线共振确认
- 无市场状态切换参数
- 无per-stock自适应
