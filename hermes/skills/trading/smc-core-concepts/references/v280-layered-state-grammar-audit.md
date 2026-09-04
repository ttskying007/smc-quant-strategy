# V280 分层状态语法审计教训

## 触发场景

用户指出：总体交易量偏少；如果假定单个 SMC 指标本身无问题，剩余问题应集中在“组合指标、参数、尤其按时间顺序发生的指标”。前面“每支股票 DNA”的方向不是后验选股白名单，而是应让每只股票产生足够多的在线机会，再验证组合语法是否有效。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v280_layered_state_grammar_audit.py`
- 产物：`/root/.hermes/smc_audit/v280_layered_state_grammar_no_write_20260702_205055/`
- 最新摘要：`/root/.hermes/smc_audit/v280_layered_state_grammar_latest.json`
- 范围：4655 只 A 股，2023-2026，全量日线 K 线，no-write。
- 生产/前端/watchlist 写入：全部 false。

## 测试的核心假设

V279 证明“自适应时间窗口 + 单一路径 SSL→BOS→OB回踩”仍失败。V280 改为分层状态语法：

1. 先用 right-confirmed swing 判断 pre-event regime：`UP / DOWN / RANGE`。
2. 同一套 SMC primitives 生成多个 story family，而不是把所有股票塞进一个固定序列：
   - `REV_SSL_CHOCH_OB`：非 UP 环境下 SSL sweep → swing high break → true OB → retest/reclaim。
   - `UP_CONT_BOS_OB`：BOS displacement → 最近真实 bearish OB → retest/reclaim。
   - `ABSORB_SSL_FAST_MSS`：SSL sweep 后快速局部 MSS，不等完整 swing-high BOS。
   - `RANGE_LOW_SWEEP_RECLAIM`：RANGE 中 range-low sweep/reclaim。
3. 所有 pivot 都使用右确认，所有 DNA/环境字段只用事件前数据。
4. 出场仍用统一 T+1 replay，10bar、1.5R，先 SL 后 TP，验证组合语法本身。

## 全市场结果

| 指标 | V280 all layered events |
|---|---:|
| n | 82,400 |
| 覆盖股票 | 4,643 / 4,655 |
| 每股 3年均机会 | 17.70 |
| 每股机会 P50/P75/P90 | 17 / 22 / 26 |
| WR | 45.54% |
| Avg | +0.48% |
| 2023 WR | 34.84% |
| 2024 WR | 46.00% |
| 2025 WR | 51.31% |
| 2026 WR | 40.17% |
| SL占比 | 41.88% |
| TP占比 | 31.05% |
| T+1违规 | 0 |

## 分语法结果

| Family | n | WR | Avg | 年度最低WR | 结论 |
|---|---:|---:|---:|---:|---|
| ABSORB_SSL_FAST_MSS | 42,122 | 47.62% | +0.76% | 39.74% | 量最大且最好，但仍不够生产 |
| UP_CONT_BOS_OB | 13,847 | 44.88% | +0.28% | 33.38% | continuation 语义仍退化 |
| REV_SSL_CHOCH_OB | 7,646 | 44.25% | +0.18% | 35.29% | 完整反转语法不解决质量 |
| RANGE_LOW_SWEEP_RECLAIM | 18,785 | 41.88% | +0.11% | 29.83% | range sweep 低门槛污染严重 |

## 关键组合口袋

| 组合 | n | WR | Avg | 年度最低WR | 说明 |
|---|---:|---:|---:|---:|---|
| RANGE_SWEEP + risk>8 + LOW_VOL + volratio>=1.2 | 252 | 66.27% | +3.09% | 60.00% | 跨年份最稳，但样本太少 |
| RANGE_SWEEP + risk>8 + LOW_VOL | 318 | 62.58% | +2.58% | 52.38% | 稳定性较好，仍是研究口袋 |
| UP_CONT + DOWN regime + risk>8 + HIGH_VOL | 274 | 63.50% | +2.65% | 51.35% | 说明“DOWN中强BOS”比 UP continuation 更像有效反转 |
| ABSORB + DOWN + liq<=3 + range<=25 + HIGH_VOL | 262 | 66.41% | +3.75% | 41.38% | 2024/2025 很强但 2026 断裂 |

## 结论

1. **交易量少不是原始机会不足**：V280 只用日线就生成 82,400 笔、每股均 17.7 次、P50=17，说明“每支股票大量机会”成立。之前少是因为生产语法过滤太窄。
2. **量放开后质量不自动提升**：全量 WR 只有 45.54%，说明“多机会”大多是普通反弹/波动，不是可直接生产的聪明钱接管。
3. **单一路径不成立，语法族选择方向成立但还不够**：ABSORB_FAST_MSS 明显优于完整 REV_SSL_CHOCH_OB，说明日线 A 股很多有效机会不是完整 ICT 教科书路径，而是 sweep 后快速吸收；但年度最低 WR 仍 < 40%。
4. **稳定口袋来自参与度和风险结构，不来自时间间隔**：最稳组合是 RANGE_SWEEP + 低波 + 放量 + 大 risk，说明市场参与度/波动状态比 `swing_gap/liq_win/wait` 更关键。
5. **下一步不能继续扩大日线顺序网格**：V278/V279/V280 连续证明 lookback/window/顺序组合只把 WR 推到 45-48%。有效前沿必须加入更高层 regime 与参与度：大盘/行业 regime、板块同步、60m reaction/MSS、资金/成交参与度。

## 后续方向

下一版应做 V281：

`Market regime → Sector/industry participation → Stock DNA grammar family → Daily candidate → 60m reaction/MSS confirmation → T+1 execution`

重点不是再调日线参数，而是验证：

- RANGE_SWEEP 稳定口袋是否本质是“低波蓄势 + 放量 sweep”，需要板块同步确认。
- ABSORB_FAST_MSS 在 2024/2025 强、2026/2023 弱的差异是否由大盘/板块 regime 解释。
- 60m 是否能把日线候选中 40%+ SL 的部分提前剔除。
- 生产层不得用后验 per-stock WR DNA；只能用 event-time rolling DNA 或外部 regime/参与度。

## 使用注意

- V280 是 no-write 研究脚本，不得接生产/前端。
- 口袋 n<500 且年度最低样本不足时只能作为研究方向，不得宣传为生产版本。
- 若用户继续追问“交易量少”，先引用 V280 的机会密度：日线机会并不少，少的是同时满足高质量门禁的机会。
