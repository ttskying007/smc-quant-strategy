# V89 RECOVERY Known-Target Repair Lesson

日期：2026-06-13

用于 V88 之后继续处理：`RECOVERY` 弱桶、`liquidity_target` 未来语义风险、90%胜率门槛、60min历史不足。

## 脚本与输出

- 脚本：`/root/.hermes/scripts/v25/v89_recovery_known_target_repair.py`
- 测试：`/root/.hermes/scripts/v25/test_v89_recovery_known_target_repair.py`
- 输出：`/root/.hermes/smc_opt_v89_recovery_known_target/`
- 总报告：`/root/.hermes/smc_opt_v89_recovery_known_target/v89_summary_report.json`

## 修复原则

1. 不再继承 V86 `liquidity_target`，避免目标来自未来K线语义风险。
2. TP 改为入场前已知固定RR腿：`micro_0_8_1_5_3`。
3. RECOVERY 不做表面调参，按子状态/共振拆桶验证：
   - daily-only 生产近似：去除 `RECOVERY` + `ACCUMULATION`
   - research-only：RECOVERY 要求 M60 bull/mixed 或 MTF>=3/2
4. 60min历史仍不完整，所有依赖 `m60_state`/`mtf_score` 的候选必须标记 research-only，不能晋级生产硬门禁。

## V89候选结果

| 候选 | 规则 | n | WR | avgPnL | avgRR | SL率 | 生产状态 |
|---|---|---:|---:|---:|---:|---:|---|
| V89_A | daily-only：去除 RECOVERY/ACCUMULATION | 432 | 91.67% | +1.9396% | 1.50R | 6.71% | 未晋级：样本<500 |
| V89_B | RECOVERY 要求 M60=BULL/MIXED | 497 | 90.74% | +1.8817% | 1.50R | 7.44% | research-only：60min不完整且样本<500 |
| V89_C | RECOVERY 要求 MTF>=3 | 492 | 91.06% | +1.9118% | 1.50R | 7.32% | research-only：60min不完整且样本<500 |
| V89_D | RECOVERY 要求 MTF>=2 | 525 | 89.90% | +1.8464% | 1.50R | 8.00% | 未达90%，且60min不完整 |

## 结论

V89证明方向正确：RECOVERY弱桶 + 固定RR已知目标可以达到90%+胜率并把SL率降到约7%。但没有一个候选同时满足：

- WR >= 90%
- n >= 500
- avgRR >= 1.5
- RR<1 = 0
- T+1 = 0
- 不依赖不完整60min历史

因此 V89 不应替代 V88 生产；下一步必须做真正 daily full-market scanner，并补全或绕开60min历史依赖。