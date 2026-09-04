# V279 自适应时间顺序语法审计教训

## 触发场景

用户指出应继续深入研究“按时间顺序发生”的组合方向：参数不应固定，指标间隔周期、先后顺序、大小周期应根据个股 DNA 自适应。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v279_adaptive_temporal_grammar_audit.py`
- 产物：`/root/.hermes/smc_audit/v279_adaptive_temporal_grammar_no_write_20260702_180231/`
- 最新摘要：`/root/.hermes/smc_audit/v279_adaptive_temporal_grammar_latest.json`
- 范围：4655 只 A 股，2023-2026，全量日线 K 线，no-write。
- 生产/前端/watchlist 写入：全部 false。

## 测试的核心假设

在 V278 证明固定 `BOS → 最近阴线Demand → 回踩/收复` 退化为普通突破回踩后，V279 测试更严格的在线语法：

`个股DNA环境 → 已确认SSL Sweep → 突破已确认Swing High(BOS/CHOCH) → 自适应displacement → 真OB(SSL与BOS之间最后有效阴线) → FVG/OB重叠标记 → 回踩OB并reclaim → 次日开盘入场`

自适应部分只使用事件前信息：
- 已确认摆动点间隔 `swing_gap` 决定 `liq_win` 与 `poi_wait`。
- 事件前 80 bar 的 range/body 分布决定 displacement 阈值。
- 事件前成交量均值决定 `VOLCONF` 环境标签。
- pivot 使用 right-confirmed 语义，确认后才可用。

## 全市场结果

| 指标 | V279 base grammar |
|---|---:|
| n | 7,243 |
| WR | 43.77% |
| Avg | +0.16% |
| 2023 WR | 32.54% |
| 2024 WR | 39.05% |
| 2025 WR | 51.57% |
| 2026 WR | 42.11% |
| SL占比 | 44.55% |
| TP占比 | 30.07% |
| T+1违规 | 0 |

单维最好口袋也远不达生产：

| 口袋 | n | WR | Avg | 年度最低WR |
|---|---:|---:|---:|---:|
| risk<=2 | 91 | 51.65% | +0.47% | 44.00% |
| LOW_VOL | 713 | 51.05% | +0.74% | 35.51% |
| reaction_delay<=1 | 1035 | 46.76% | +0.38% | 36.36% |
| OB_FVG_OVERLAP=True | 3632 | 44.63% | +0.26% | 31.25% |

多维组合挖掘最高也只是研究级弱口袋，样本与年度稳定性不足：

| 组合 | n | WR | Avg | 年度最低WR |
|---|---:|---:|---:|---:|
| react<=1 + risk<=8 + ssl_age<=20 | 115 | 59.13% | +1.67% | 58.49% |
| LOW_VOL + overlap=True + ssl_age<=20 | 124 | 58.06% | +1.02% | 35.71% |
| LOW_VOL + ob_age<=3 + react<=1 | 133 | 57.14% | +1.09% | 41.18% |
| LOW_VOL + FVG=False | 261 | 53.64% | +1.05% | 40.00% |

## 结论

1. **自适应时间窗口本身不能解决问题**：按个股 swing_gap 自适应 `liq_win/poi_wait` 后，质量仍与 V278 固定参数同量级，甚至 base WR 仅 43.77%。
2. **“SSL→BOS→OB回踩”仍不是足够的 A 股日线语义**：即使加入 right-confirmed swing、displacement、真OB、OB/FVG overlap、reclaim，仍大量 SL，说明语义仍退化为普通反弹确认。
3. **股票 DNA 不能是后验白名单**：V274 已证明每股历史胜率 DNA walk-forward 失败；V279 的在线 DNA（swing/range/body/vol）也没有产生可生产 frontier。
4. **有效信息缺口在更高层 regime/参与度/订单流，不在日线局部时间参数**：V279 中 LOW_VOL、快速 reaction、近 SSL 有弱增益，但不足以跨年份稳定。
5. **下一步不应继续扩大日线参数网格**：应转为分层状态语法和外部/高低周期信息：市场/板块 regime、60m 候选生成时结构、竞价/资金/行业参与，而不是继续围绕 BOS lookback、SSL window、wait 做调参。

## 后续研究方向

下一步若继续该方向，应构造 V280：

`Market/板块 regime → 个股DNA分型(只用过去窗口) → 语法族选择，而不是参数选择 → 日线候选 → 60m/板块参与度确认 → 结构化出场`

重点验证：
- 同一 SMC 语法在不同 market regime 是否完全不同表现。
- 个股 DNA 是否应选择“语法族”（反转/延续/吸收/突破失败），而不是只调整 lookback/window。
- 当前日线候选是否必须由 60m 先出现 MSS/reaction 才允许次日入场。
- 不能使用后验 per-stock WR 白名单；必须 walk-forward 或 event-time rolling。
