# V13 60min混合引擎 — swing-backward + forward fallback

## 背景

V12 swing-backward OB在60min上覆盖仅V11的42% (9.4 vs 22.6 OB/stock)。
根因是三层问题的叠加: 代码bug + 逻辑缺陷 + 功能参数不匹配。

## 三层问题分类框架 (可复用)

| 层次 | 定义 | 示例 |
|------|------|------|
| **代码bug** | 语法/逻辑错误, 不符合编写者意图 | walrus operator `:= 'hybrid'`, doji设为OB, impulse_len阈值错误 |
| **逻辑缺陷** | 算法设计假设与数据特征不匹配 | 三阶段(回调→脉冲→OB)模式在60min上不普遍; V11 per-candle无结构门槛 |
| **功能参数** | 阈值/常数偏大或偏小 | body_pct=0.15%, displacement_mult=1.3, volume median*1.2 对60min过严 |

### 诊断流程

1. **广泛对比** (100只): 比较V11 vs V12信号数量, 按类型分类(OB/FVG/Sweep/CHOCH)
2. **深度追溯** (单股票200bar): 逐个摆动点trace backward scan过程, 打印每个失败原因
3. **参数灵敏度测试**: 分别测试 `require_volume=False`, `disp_mult=0.8/0.5`, `body_pct=0.08`
4. **隔离引擎链**: 分别测试纯信号检测(不计入交易), 再逐步加过滤层

### 诊断脚本模式

```python
# 模式1: 广泛对比 (100只, 按信号类型统计)
# 文件: debug_compare_signals.py
for sym in symbols[:100]:
    r11 = detect_all_signals_v11(ohlcv)
    r12 = detect_all_signals_v12(ohlcv)
    print(f"{sym:12s} V11: total={len(r11['all'])} OB={len(r11['OB'])} ... | V12: total={len(r12['all'])} OB={len(r12['OB'])} ...")

# 模式2: 深度追溯 (单股票, 逐个摆动点trace OB扫描)
# 文件: debug_trace_ob_scan.py
for sh_idx, sh_price in swing_highs:
    phase = 'skip'; impulse_len = 0; ob_idx = None
    for bi in range(sh_idx-1, ...):
        bar = ohlcv[bi]
        is_bear = bar['c'] < bar['o']
        if phase == 'skip' and is_bear: continue
        if phase == 'skip' and not is_bear: phase = 'impulse'
        ...
    body_pct = abs(...)
    if body_pct < 0.08: print(f"[FAIL body={body_pct}%]")
    if dis_ratio < 1.0: print(f"[FAIL disp={dis_ratio}x]")
    print(f"[OK] ob_idx={ob_idx}")
```

## V13 60min参数

| 参数 | 日线默认 | V13 60min | 原因 |
|------|---------|-----------|------|
| body_pct_min | 0.15% | 0.08% | 60min实体平均只有日线1/3 |
| displacement_mult | 1.3x | 1.0x | 60min摆动幅度小 |
| require_volume | True | True(primary) / 0.5x(fallback) | 保留volume但放宽 |
| swing_left/right | 8/3 | 8/3 | 不变 |
| forward fallback | 无 | near swing +/-5, disp>=0.8x, imp>=1 | 覆盖补足 |

## V473 引擎架构

```
信号层: V13 (detect_all_signals_v13_60min)
  ├── swing-backward primary (correctness) 
  └── constrained forward fallback (coverage, 仅primary<3时激活)

过滤层: V467 (序列+共振+反转OB+趋势+质量+MIN_RR=8.0)

退出层: V467 (渐进BE锁 + TP距离感知trailing)
```

## 全量结果 (4552 stocks)

| 指标 | V467 (V11) | V473 (V13) | 变化 |
|------|-----------|-----------|------|
| 可交易数 | 630 (13.8%) | 376 (8.3%) | -40% |
| 交易数 | 1472 | 819 | -44% |
| WR | 82.7% | 82.8% | 持平 |
| RR | 16.72x | 16.75x | 持平 |
| P&L | +4.58% | +4.24% | -7% |

## 关键文件

- `/root/.hermes/scripts/v11/signals_v12.py` — `detect_ob_v13_60min()` + `detect_all_signals_v13_60min()`
- `/root/.hermes/scripts/v11/v473_engine.py` — V473引擎 (V13信号 + V467退出)
- `/root/.hermes/smc_opt_v473/` — 全量结果 (stocks/trades/summary)
- `/root/.hermes/scripts/v11/v473_200_test.py` — 200只验证
- `/root/.hermes/scripts/v11/v473_full_scan.py` — 全量扫描

## 被修复的V12 bugs

| Bug | 位置 | 修复 | 影响 |
|-----|------|------|------|
| bearish OB impulse_len >= 2 | line 346 | >= 1 | +50-80% bearish OB |
| doji设为OB (bearish分支) | line 341-344 | continue | 避免indecision bar误判 |
| walrus operator `:= 'hybrid'` | line 398 | 已删 | **78%错误OB的根因** |
| body_pct硬编码 | line 264/351 | 参数化body_pct_min | 60min/日线独立 |
