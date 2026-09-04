# V88 Production Contract Release Lessons

日期：2026-06-13

当出现“实盘多数SL + 盈亏比不足 + 前端/实盘/回测不一致”时，不能继续表面调SL/TP。V88的正确闭环是：

```text
V86信号层
+ V87完整风险合同字段
+ 可执行SL/TP1/TP2/TP3/runner
+ monitor同源执行
+ daily自动任务切换
+ DIAGNOSTIC_ONLY物理隔离
```

## 关键修复点

1. **先固化生产合同，不先改信号层**
   - 采用 V87 balanced combo: `zone_limit|hybrid_tight|liq_then_2r_runner`。
   - 生成脚本：`/root/.hermes/scripts/v25/v88_apply_production_contract.py`。
   - 输出目录：`/root/.hermes/smc_opt_v88_production_contract/`。

2. **必须落盘完整风险字段**
   - 必填：`sl,tp1,tp2,tp3,rr,rr_realized,exit_legs,mfe_pct,mae_pct,mfe_r,mae_r,weekly_state,daily_state,m60_state,mtf_score`。
   - 字段审计必须0缺失；T+1必须0违规；RR<1必须0。

3. **monitor执行门禁必须与生产合同一致**
   - 原缺陷：`smc_monitor_state.py` 对 `risk_pct < 2.5%` 全部 WATCH_ONLY，但V86/V88生产风险常在1-2.5%之间。
   - 修复：V88/V86/V85或带`contract_source`的行使用 `min_risk=0.8`，不要误拒绝生产候选。

4. **monitor/live必须同源过滤**
   - `/monitor` 和 `/api/live-prices` 不能把旧V66仓位混入V88页面。
   - 用 `raw_pick.engine or pos.engine` startswith `ACTIVE_VERSION` 过滤 monitor positions。
   - ledger 同样按 `engine.startswith(ACTIVE_VERSION)` 过滤，避免旧实盘SELL记录污染V88实时页。

5. **DIAGNOSTIC_ONLY必须物理隔离**
   - 仅打标签不够；旧仓位仍会被 `/live` 优先读取。
   - 脚本：`/root/.hermes/scripts/v25/quarantine_diagnostic_monitor_state.py`。
   - 隔离目录示例：`/root/.hermes/smc_monitor/quarantine/20260613_182431/`。

6. **daily selector切换**
   - `smc_daily_ops.py::run_selector()` 从 `v66_engine.py` 改为 `v88_apply_production_contract.py`。
   - ops日志文件键从v66改为v88，避免“前端V88但daily仍V66”的错位。

## V88结果基线

| n | WR | avg_pnl | avg_rr | RR<1 | SL率 | avg_MFE_R |
|---:|---:|---:|---:|---:|---:|---:|
| 532 | 83.65% | +2.8689% | 2.4376R | 0% | 12.97% | 5.1517R |

## 残留问题

- RECOVERY仍弱：80笔/WR 68.75%/SL率23.75%。下一版V89优先拆RECOVERY子状态或要求MTF共振。
- 60min历史不足，不能作为生产硬门禁。
- `liquidity_target`仍继承V86语义，未来应改为入场前已知BSL/prior high。
- V88当前是“生产合同固化版”，还不是真正新的daily full-market scanner。
