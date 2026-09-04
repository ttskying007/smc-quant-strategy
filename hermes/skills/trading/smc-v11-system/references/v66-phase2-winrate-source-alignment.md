# V66 Phase2 胜率修复：信号源同源 + 生产门禁闭环

## 触发场景

用户要求“先解决 Phase2 胜率低的问题”，且出现以下任一症状：

- 历史小样本 V66 胜率很高，但当前 Phase2 全市场回测/实盘候选胜率明显偏低；
- 生产扫描与质量回测使用不同信号引擎；
- 只看聚合 WR/RR，未验证 zone/entry/SL/retrace/sweep 等机制桶；
- 前端字段已补齐但用户仍反馈选股页/实时页显示空值或口径混乱。

## 关键结论

Phase2 低胜率优先排查 **同源性**，不要先调参数：

1. 生产扫描、质量回测、前端候选必须使用同一信号源与同一门禁口径。
2. 本次定位到 `daily_scan.py` 使用 V26 `smc_detector`，而质量回测基准使用 V22 `signals_v22.detect_all_signals_v22`；两套 OB/FVG/结构语义不同，导致回放结果从 V22 约 67% WR 掉到 V26 同源约 37% WR。
3. 修复方向是让 Phase2 生产扫描优先使用 V22 信号源，V26 detector 只作为 fallback。

## 推荐执行顺序

1. **先做影响分析**
   - 修改 `scan_last_bars` 前运行 GitNexus impact。
   - 若只影响 `daily_scan.main`，通常是 LOW risk。

2. **重跑全市场质量分桶**
   - 使用 `/root/.hermes/scripts/v25/phase2_quality_backtest.py 0`。
   - 必须记录：zone_type、in_zone、sl_pct、retrace、sweep、state、组合门禁。

3. **用机制桶决定门禁，不用直觉调参**
   - 本次全市场结果显示：
     - sweep=True 低于 sweep=False，不能硬要求 sweep；
     - 深回撤是主要拖累，`retrace >= 60` 需拒绝或降权；
     - `entry_price <= zone_high` 的真实 in-zone 是有效约束；
     - `sl_pct < 1` 是劣质桶；
     - OB 不能在代码里直接跳过，需进入候选后由门禁决定。

4. **生产门禁模板**

   ```text
   Phase2 production gate = V22 signal source
                         + entry_price <= zone_high
                         + entry_price >= zone_low
                         + sl_pct >= 1
                         + retrace_depth_pct < 60
                         + no T+1 gap-down violation
                         + no invalid OB candle
   ```

   不要硬要求：
   - sweep；
   - FVG-only；
   - 固定拒绝 RANGE/HIGH_VOL/TREND_DOWN（除非全市场桶重新验证为负贡献）。

5. **同步链路**
   - 跑 `daily_scan.py` 生成最新候选；
   - 跑 `smc_daily_ops.py` 同步到 `smc_opt_v66/v66_picks.json` 与 `v66_daily_candidates.json`；
   - 如历史 `v26_picks.json` 混入旧 ACTIVE 且字段为空，先按最新 pick_date/entry_date 过滤，避免旧记录污染前端。

6. **验收字段合同**

   当前 ACTIVE 候选必须检查以下字段零空值：

   ```text
   pick_date, join_date, zone_type, zone_low, zone_high,
   cost_line, smart_money_cost, volatility_pct, v25_vol_class
   ```

   选股页和实时页都必须验证；不能只验证文件层或接口层之一。

## 本次验证基准与时间顺序陷阱

**重要更新（2026-06-11）**：旧版“Phase2 quality replay”里的高胜率门禁数字不能直接作为生产承诺，因为原脚本曾允许 `entry_bar` 落在 `conf_bar` 之前或等于确认 bar，本质是未来确认污染。

### 必跑审计：Temporal Leakage Audit

当 Phase2 胜率看起来“异常高”或“异常低”时，先运行同源时间顺序对照，而不是继续调参：

```bash
cd /root/.hermes/scripts
python3 v25/phase2_temporal_audit.py 0
python3 v25/phase2_strict_exit_audit.py 0
```

审计必须同时报告：

| 口径 | 必看字段 | 判定 |
|---|---|---|
| old_quality_temporal_leak | `pre_conf_rate` | 若非 0，旧高胜率不可作为生产依据 |
| strict_after_confirm | `pre_conf_rate == 0` | 真实可交易 Phase2 口径 |
| strict_after_confirm_gate_* | WR/avg/SL率 | 用于判断门禁是否真的有效 |
| v66_like exit | WR/SL率 | 分离“入场错误”与“出场错误” |

2026-06-11 全市场复盘结果：

| 口径 | 笔数 | WR | avg | SL率 | pre_conf_rate |
|---|---:|---:|---:|---:|---:|
| old_quality_temporal_leak | 21,995 | 69.40% | +1.246% | 30.50% | 61.37% |
| old_quality + inzone/sl1/retr60 | 6,542 | 75.22% | +1.712% | 24.53% | 44.33% |
| old_quality OB gate | 91 | 92.31% | +3.844% | 7.69% | 91.21% |
| strict_after_confirm | 17,048 | 63.97% | +0.052% | 35.85% | 0.00% |
| strict_after_confirm + inzone/sl1/retr60 | 6,727 | 64.37% | +0.305% | 35.35% | 0.00% |
| strict_after_confirm FVG gate | 5,890 | 65.04% | +0.349% | 34.63% | 0.00% |
| strict_after_confirm OB gate | 837 | 59.62% | -0.004% | 40.38% | 0.00% |

### 解释规则

- `pre_conf_rate > 0`：不能声称这是可交易的 SMC Phase2 胜率；它可能是 `zone → retrace entry → later BOS/CHOCH` 的未来确认污染。
- V66 历史 90%+ 样本也要检查 `retrace_index/conf_index/entry_index`。若三者相等或 `entry_index <= conf_index`，它不是严格“确认后回撤再入场”。
- 若 strict 口径 WR 降到 60% 左右，不要把结论写成“SMC 胜率低”；应写成“当前代码尚未构造出真正高质量 SMC setup”。
- 下一步优先重建严格 L→D setup：`Sell-side sweep → bullish displacement/CHOCH → demand POI → first retrace → zone rejection/reclaim → T+1 entry`。不要再用旧 quality 高胜率作为晋级证据。

## 原先质量分桶数字的使用限制

旧记录中类似下表的数字只能作为“门禁方向参考”，不能作为 production WR 承诺，除非重新用 strict-after-confirm 口径复算且 `pre_conf_rate == 0`：

| 口径 | 笔数 | WR | avg |
|---|---:|---:|---:|
| BASELINE 全部 | 25,547 | 67.0% | +1.407% |
| in_zone+sl>=1% | 15,399 | 69.5% | +2.401% |
| in_zone+sl>=1%+retr<60 | 7,832 | 78.7% | +2.290% |
| 同门禁 FVG | 7,742 | 78.6% | +2.273% |
| 同门禁 OB | 90 | 91.1% | +3.754% |

这些数字是验证门禁有效性的参考，不是永久承诺；未来行情/数据变更后必须重跑全市场。

## Pitfalls

- 不要把历史 V66 小样本 90%+ WR 当成当前 Phase2 的真实胜率；先确认是否同源同门禁。
- 不要在 `daily_scan.py` 中写死 `if zone_type != 'FVG_Bull': continue`，这会让 OB 永久失效。
- 不要用“sweep 是 SMC 必需”作为硬门禁，必须看全市场桶；本次 sweep 桶是负贡献。
- 不要只修后端字段 fallback。前端看到空值时，要验证：源文件、V66 merge 文件、API、浏览器表格四层。
- 不要保留旧 ACTIVE 历史记录污染最新候选；按最新 pick_date/entry_date 切开历史与当前。
