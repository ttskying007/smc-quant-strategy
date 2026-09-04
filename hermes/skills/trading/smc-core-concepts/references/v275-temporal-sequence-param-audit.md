# V275 时间顺序组合/参数审计教训

触发场景：当 SMC 交易量偏少，且假定原子 SMC 指标本身无问题时，必须把“时间顺序组合 + 参数”单独拆出来审计，不能只继续加股票 DNA 或行业过滤。

## 已验证结论（2026-07-02）

输入：`/root/.hermes/smc_audit/v262_fresh_bos_retest_generator_no_write_20260702_100027/v262_all_fresh_candidates.csv`
输出：`/root/.hermes/smc_audit/v275_temporal_sequence_signature_audit_no_write_20260702_163534/`
脚本：`/root/.hermes/scripts/v25/v275_temporal_sequence_signature_audit.py`

### 核心结果

- 原始 BOS→Demand→Retest 序列在 2023-2026 有 26,402 笔，覆盖 4,606 股票；中位数仅约 5 笔/股/3年，说明“机会很多”不是由当前严格 BOS 序列自然产生的。
- raw V262：WR 43.49%，avg +0.084%，2023/2024/2025/2026 WR = 35.27/39.44/49.92/41.05。
- 加入时间顺序拆解后，最佳大样本时间桶仍很弱：`SSL_BEFORE_ZONE|ZONE_AGE_2|RETEST_1_2`，n=1,489，WR 48.69%，avg +0.66%，年度 WR 38.79/44.37/53.71/49.63。
- SSL 位置有方向性但不足以构成生产策略：
  - SSL_BEFORE_ZONE：n=17,315，WR 44.42%，avg +0.204%。
  - NO_SSL：n=8,826，WR 41.74%，avg -0.136%。
- SSL 年龄 9-20bar 是相对最好桶：n=6,997，WR 47.26%，avg +0.506%，但仍远低于生产门槛。
- “股票 DNA”非泄漏 walk-forward（V274）失败：in-sample oracle 可到 WR 68.8%，但 prior-year→next-year 只有 WR 45%左右，说明简单 per-stock variant DNA 不稳定。

## 执行原则

1. 不要把 V262/V272/V275 这种 BOS→Demand→Retest 继续当生产加量方向；它只能证明“量可放大但质量塌陷”。
2. 不要用 in-sample 股票 DNA 作为晋级依据；必须 walk-forward 或 out-of-year 验证。
3. 下一轮应重建更广义的事件语法，而不是继续调 BOS lookback / demand lookback / wait_max：
   - Environment / Market State
   - Liquidity Event（SSL/EQL/sweep）
   - Structure Confirmation（CHOCH/BOS/MSS）
   - POI（OB/FVG/OB+FVG）
   - Retest / Reaction（touch、reclaim、two-bar hold）
   - Entry / Exit 语义
4. 对“每支股票大量机会”的验证应使用 funnel 统计：每股每年事件数、每层漏斗通过率、按时间顺序签名分组后的 WR/avg/年度稳定性。

## 最小验收字段

时间顺序审计输出至少包含：
- `ssl_idx`, `ssl_age`, `ssl_vs_zone`
- `zone_age`, `retest_delay`
- `timeline_signature`
- `risk_bucket`, `chase_bucket`, `break_bucket`
- 全局/年度 `n, wr, avg, median, loss, micro, year_wr`
- `per_stock_3y` 或每股每年机会密度

## 当前判断

V275 关闭“只靠时间顺序参数微调解决交易量+质量”的方向。下一步应做全事件语法/漏斗重建，尤其检查是否当前 BOS 硬门槛本身把大多数有效 SMC 机会排除在外。