# V12 60min覆盖限制 — 全链路debug分析 (2026-05-11)

## 更新说明

本文件已被重写。之前结论"非代码bug, 是60min固有特性"已被推翻。实际发现了3个代码bug + 2个逻辑缺陷 + 3个功能参数问题。以下为全链路debug记录。

## 问题表象

V12 swing-backward OB在60min上的信号覆盖率只有V11的~42%。

100只对比结果:
- V11: avg 22.6 OB/stock 
- V12: avg 9.4 OB/stock (42%)

在V467引擎全量过滤后（序列+共振+反转OB+趋势+MIN_PROJECTED_RR>=8）:
- V467(V11): 21/200可交易, 46笔, WR=84.8%, RR=14.19x
- V472(V12): 5/200可交易, 11笔, WR=90.9%, RR=15.09x

## Debug方法论: 逐个摆动点trace

每只60min股票有8-16个摆动高点和6-14个摆动低点。V12从每个摆动点向后扫描寻找OB。
全链路trace脚本: `v11/_v12_trace_ob.py` — 对每个摆动点打印扫描步骤和失败原因。

## 根因分类: 代码错误 / 逻辑缺陷 / 功能参数

### 第一类: 代码错误 (BUG) — 3个

#### Bug 1: Bear OB impulse_len >= 2 vs Bull OB >= 1 (不对称)

文件: `signals_v12.py` 第258行 vs 第346行

```python
# Bull (line 258):
if ob_idx is None or impulse_len < 1:  # OK, 1 bar enough
    continue

# Bear (line 346):
if ob_idx is None or impulse_len < 2:  # BUG: needs 2 bars for bear
    continue
```

影响: 60min上大量bearish impulse只有1根阴线(A股急跌就一根), 但要求>=2。600519.SH: 3/12 swing low被砍; 000858.SZ: 4/11; 002415.SZ: 4/14。

修复: 统一为 `>= 1`。

#### Bug 2: Doji被设为OB候选 (bear分支)

文件: `signals_v12.py` 第339-344行

```python
elif phase == 'impulse':
    # ...
    elif is_bull:
        ob_idx = bi
        break
    else:  # doji
        ob_idx = bi  # BUG: doji不是OB
        break
```

scanning向后遇doji(十字星)时立即停止并设为OB, 但doji不是valid OB bar。正确行为应该是 `continue` 继续向后扫。

000858.SZ sl_idx=163/189因此产出错误的impulse_len计数, 最终被body_pct过滤掉。

#### Bug 3: Walrus operator (已修复)

Line 398: `if swing_mode := 'hybrid'` — `:=`始终返回'hybrid'(truthy), hybrid pass始终执行。已删, 替换为constrained forward fallback。

### 第二类: 逻辑缺陷 (LOGIC) — 2个

#### Logic 1: 三阶段模式假定的局限性

V12假定每次从swing high往后扫, 结构一定是: bearish pullback → bull impulse → bear OB bar。60min上这种三阶段模式不普遍:

| 60min典型场景 | V12行为 | 结果 |
|---|---|---|
| 直拉无回调到摆动高点 | phase=skip时遇bull→进入impulse, 但之前的OB太远 | OB被scan截止(25bar)截断 |
| 只有1根阳线脉冲 | impulse_len=1, 通过 | 有时找到OB |
| 摆动点和OB距离<3根K线 | 扫描不足, 无法识别pullback→impulse模式 | OB missed |
| 连续3根阳线后突然阴线 | 阴线=OB, 阳线=都算impulse | 可以, 是标准场景 |

根本矛盾: swing-backward是为日线设计的(结构清晰、摆动点间隔10+根K线)。60min结构更紧凑(摆动点间隔3-8根K线), 三段式模式不完整。

#### Logic 2: V11 per-candle forward本质是"无门槛"

V11的条件: 任何K线 + 后续2根同向K线(impulse) + 成交量OK → OB。不需要靠近任何摆动点。这是V11在60min上多58% OB的根本原因——它不是"更准确", 而是"更宽松"。

V12更严格但牺牲了覆盖率。这本身不是bug, 是一个设计tradeoff。

### 第三类: 功能参数 (FEATURE) — 3个

#### Feature 1: body_pct >= 0.15% 对60min太严格

日线body通常>0.5%, 但60min大量valid OB实体只有0.08-0.14%。

Trace输出显示:
```
[FAIL sh_idx= 21] body_pct=0.092% < 0.15
[FAIL sh_idx= 54] body_pct=0.091% < 0.15
[FAIL sh_idx= 62] body_pct=0.091% < 0.15
```

000001.SZ: 6/15 swing high死于body_pct过滤。建议60min降至0.08%。

#### Feature 2: displacement_mult = 1.3 对60min偏高

SMC 2026 Pine Script 1.3x是针对日线的。60min上摆动幅度小, displacement ratio常为0.8-1.2x:

```
002415.SZ sh_idx=108: dis_ratio=1.10x, 差0.2被砍
600519.SH sl_idx=108: dis_ratio=1.03x
600519.SH sh_idx=123: dis_ratio=1.00x
```

建议60min降至1.0x。

#### Feature 3: Volume filter命中率高

002415.SZ (vol_median=141,991): 7/16 swing high死于volume filter
```
avg_imp_v=44,980-129,022 vs threshold=170,389
```

注意: V11和V12的volume check代码完全一样(`avg_imp_v > median*1.2 OR ob_v > median*1.2`), 问题在V12候选池小(从摆动点出发), volume失败比例显得更高。

## V11 OB vs V12 OB: 硬性数据对比 (100只60min)

| 信号类型 | V11 (avg/stock) | V12 (avg/stock) | V12/V11 |
|----------|:---------------:|:---------------:|:-------:|
| OB | 22.6 | 9.4 | 42% |
| FVG | 21.7 | 23.5 | 108% |
| Sweep | 2.4 | 2.9 | 123% |
| CHOCH | 0.25 | 0.0 | 0% |
| 总信号 | 187.6 | 108.0 | 58% |

关键发现: FVG(不受swing影响)在V11和V12中几乎一致。Sweep在V12中因从摆动点扫描反而更多(123%)。只有OB(因swing-backward)和CHOCH(因状态机<2个摆动点)覆盖下降。

## 修复V12 60min参数后的预期覆盖

| 修复项 | 当前 | 调整 | 预期效果 |
|--------|------|------|---------|
| Bug 1 (bear impulselen) | >=2 | >=1 | bear OB +200% |
| Bug 2 (doji OB) | doji=OB | skip doji | bear OB更多正确候选 |
| Feature 1 (body_pct) | 0.15% | 0.08% | +~40% OB通过 |
| Feature 2 (displacement) | 1.3x | 1.0x | +~10-20% OB通过 |
| Feature 3 (volume) | same | 降至1.0x median | +~80% volume PASS |

三项feature参数调整后预计从42%提升到~70-80% V11覆盖。加上代码bug修复, 有望达到~85%。

确认60min参数调整不影响日线: 日线body通常>0.5%、displacement>2x, 参数放松对日线无影响。

## V12 -> V472引擎适配 (60min)

见 `v11/v472_engine.py`:

1. Import: `signals_v12` alias为 `signals_v11`
2. TRADE_SIGNAL_TYPES: 加 `'Sweep'` (V12产出type='Sweep'而非SweepUp/SweepDown)
3. Sweep方向匹配: `Sweep` + `direction` 字段代替 `SweepUp`/`SweepDown`
4. 参数: ob_displacement_mult=1.3 (60min建议1.0), require_volume=True (60min建议放宽)

## 结论

V12的swing-backward OB在60min覆盖低是**多重因素叠加的结果: 3个bug + 2个逻辑缺陷 + 3个参数不匹配**。不是单一的"60min不适合swing-backward"。

推荐:
- 日线: 直接用V12 (Pine Script参考标准, 结构清晰)
- 60min: 修bug + 调参后使用V12, 或继续用V11 per-candle(理论不纯但实用)

近期不必再做V12 60min覆盖优化——当前V467(V11)已证实有效(WR=82.7%, RR=16.72x, 全量4552)。信号正确性优先于引擎版本统一。

## 参考

- `v11/_v12_debug_comprehensive.py` — V11 vs V12信号对比脚本(100只)
- `v11/_v12_trace_ob.py` — 逐个摆动点OB追踪trace
- `signals_v12.py` 第223-524行 — OB检测核心代码
- `signals_v11.py` 第698-834行 — V11 OB检测代码(per-candle forward)
