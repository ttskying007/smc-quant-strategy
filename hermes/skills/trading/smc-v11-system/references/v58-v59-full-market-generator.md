# V58/V59 全市场 SMC 交易生成器经验

## 适用场景

当用户指出 SMC 信号不准确、样本太窄、回测/选股/K线/复盘不同步，或要求从全市场信号快照重新生成交易时，优先使用本参考。

## 核心教训

1. **小样本高胜率不能作为生产结论**
   - V56/V57/V58 从 V48/V54 高质量 source trades 继续迭代，只有 36~44 笔，WR 可以到 100%，但不能代表全市场。
   - Release gate 中 `sample_not_too_narrow` 是硬门槛；低于 50 笔不能宣称生产可用。

2. **信号层全量 != 交易层全量**
   - V50 snapshot 可有 4905 只股票、170 万条 signal，但如果交易生成仍从几十笔 source trades 派生，交易样本仍然窄。
   - 必须明确区分：raw signal coverage、trade generation coverage、active picks coverage。

3. **结构破位退出后不要死拿原单**
   - `SOLD_EARLY_NEXT_90D` 很多不是原单退出错误，而是退出后形成了新的 BOS/CHOCH/MSS + 新 OB/FVG/BPR/LV setup。
   - 正确处理是作为 `CONTINUATION_SETUP` 或 `REENTRY_SETUP` 重新入场/纳入监控，而不是简单延长原单。
   - V57 全局延迟退出测试会降低 avg pnl；不要盲目延迟所有结构退出。

4. **V59 主生成器三类交易模型**
   - `PRIMARY_SETUP`: 原始 OB/FVG/BPR/LV + BOS/CHOCH/MSS/Sweep 确认 + retest 入场。
   - `CONTINUATION_SETUP`: BOS/CHOCH/MSS 后出现新 OB/FVG/BPR/LV，再 retest 入场。
   - `REENTRY_SETUP`: 同股票上一笔交易 exit 后，再出现新的可执行 SMC setup。

5. **全量生成后要接受真实分布下降**
   - 全市场扩展会把 WR 从小样本 100% 拉回真实水平。
   - V59 暴露出 primary setup 质量最弱，continuation/reentry 明显优于 primary。
   - 后续优化方向应是分族质量门禁，而不是回到小样本。

## 必做审计

每个新版本必须至少生成并检查：

- `vXX_trades.json`
- `vXX_picks.json`
- `vXX_report.json`
- `vXX_quality_metrics.json`
- `vXX_trade_provenance_audit.json`
- `vXX_signal_sequence_audit.json`
- `vXX_sample_bias_audit.json`
- `vXX_release_gate.json`

审计通过标准：

- provenance fatal = 0
- sequence violations = 0
- hold_over_90 = 0
- small_win_below_2 = 0
- loss_inside_1pct = 0
- win_rr_below_2r = 0
- sample_not_too_narrow = true
- 前端 `/api/summary`、`/backtest`、`/api/picks`、`/api/kline_full?...&ver=VXX` 都能返回新版本数据

## 前端同步要求

后端生成新版本后，必须同步：

1. `ACTIVE_VERSION`
2. `ACTIVE_TRADE_FILE`
3. `ACTIVE_PICK_FILE`
4. version selector HTML
5. `get_version_trades()`
6. `get_version_picks()`
7. `get_version_config()` / engine map
8. K线高亮版本映射
9. 重启 8890 并验证 API

不能只生成后端文件而不更新前端。

## 后续优化方向

V59 之后优先做 `V60 分族质量门禁`：

- PRIMARY_SETUP：只允许 A层 + 高 BQ + 强趋势 + 完美 retest；其它只进入观察。
- CONTINUATION_SETUP：保留 A/B，但加强 no-reclaim、retest hold、post-break trend context。
- REENTRY_SETUP：作为主交易源保留，但限制同股重复入场间隔和过密交易。

## 文件例子

- 引擎：`/root/.hermes/scripts/v25/v59_engine.py`
- 输出：`/root/.hermes/smc_opt_v59/`
- 审计：`/root/.hermes/smc_audit/v59_*`
