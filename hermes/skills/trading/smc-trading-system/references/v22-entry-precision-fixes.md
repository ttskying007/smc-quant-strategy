# V22 入场精度修复方法论

## 诊断流程

V500结构回测(39837笔) → 逐维度分析 → 定位5项根因 → V22逐一修复 → V501验证。

## V500发现的核心问题

### SL距离 vs WR

| SL距离 | 占比 | WR |
|--------|------|-----|
| 0-1% | 2.9% | **12.5%** |
| 1-2% | 6.0% | 35.2% |
| 2-3% | 11.9% | 52.2% |
| 4%+ | 64.4% | 66-72% |

最近结构支撑(FVG下沿)在0-1%距离内被击穿率87.5%。根因: 入场位置不在强支撑上。

### 无结构SL

4757笔(12%)入场下方无任何结构支撑 — 但这些交易WR=67.5%高于有结构SL的62.4%。原因: 无支撑=处于强趋势中, 支撑在远处, -8% fallback反而够宽。

## 修复1: Zone回撤用wick判断

**旧** (V21 line 712):
```python
in_zone = dz_low * 0.99 <= closes[j] <= dz_high * 1.01
```
问题: close在zone内但low未刺入 → 回撤不真实。

**新**:
```python
wicked_in = lows[j] < dz_low * 0.995
```
SMC要求价格**刺入**zone (low < zone_low), 不是收盘在zone内。

## 修复2: 删除REV_BOUNCE

旧(V21 line 724-725):
```python
if not confirmed and closes[j] > opens[j] and closes[j] > dz_low:
    confirmed = True; conf_type = 'REV_BOUNCE'
```
任何阳线+收盘>dz_low就算确认 — 最弱的确认, 产生大量低质量入场。

新: 仅保留IDM_BOUNCE(前bar跌破zone+当前bar恢复>1.5%)和PB_BOUNCE(锤子线 wick>2x实体)。

## 修复3: 入场跳空保护

旧: `entry_price = opens[entry_bar]` — 确认后次日开盘无上限。

新: `if entry_price > dz_low * 1.03: continue` — 跳空>3%拒绝入场。

效果: V22 0笔入场距zone>3%, 入场距zone均值0.84%。

## 修复4: FVG zone入场

旧: V21仅遍历ob_bulls做入场。FVG只在上下文中加分但永远不作为需求区入场。

新: 合并OB和FVG zones → 56% FVG入场, 44% OB入场。

## 修复5: 结构SL (仅入场前)

旧SL选择:
```python
if slo['idx'] <= entry_idx + 5:  # 允许入场后结构!
```
SL可选在入场后新形成的摆动低点 — 循环论证。

新:
```python
if slo['idx'] <= entry_idx:  # 仅入场前
```
+ min 2%距离要求 → 0-1% SL从1153笔→0。

## V22 引擎关键代码路径

文件: `/tmp/v22_engine.py`
- `backtest_stock_v22()` — 主回测循环
- `find_structural_sl()` — 结构SL扫描(仅入场前)
- Entry loop: lines ~230-290 — wick穿透+IDM/PB确认+跳空检查
- Zone构建: OB+FVG双源合并

## V501 验证结果

V501 vs V500:
- SL 0-1%: 1153→0笔
- WR: 63.0%→68.2% (+5.2pp)
- 均PnL: +1.11%→+1.35% (+22%)
