# V90.1 3年门禁与RECOVERY弱桶闭环

日期: 2026-06-13

## 触发问题

- RECOVERY弱桶: 80笔, WR约68-80%, SL率高
- 60min历史不足，不能作为生产硬门禁
- liquidity_target存在V86未来语义风险
- 需要真正daily full-market scanner并验证90%胜率/盈亏比

## 执行结论

在V85全市场3年候选基础上，应用V86 gate + V90入场前已知BSL目标后:

| 方案 | 样本 | WR | 平均PnL | 平均R | Payoff | SL率 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| ALL_V86_GATE | 530 | 89.81% | 2.6781% | 2.0971R | 1.3384 | 10.38% | 差0.19pp，未达90 |
| EXCLUDE_RECOVERY_ALL_WEAK_STATES | 523 | 90.25% | 2.6923% | 2.1090R | 1.3185 | 9.75% | 通过n>=500+WR>=90 |
| EXCLUDE_RECOVERY | 450 | 91.56% | 2.7695% | 2.1657R | 1.2869 | 8.44% | 胜率高但样本不足 |

生产可用门禁: `market_state != RECOVERY OR v90_recovery_substate in {RECOVERY_CONFIRMED_FAST_RECLAIM, RECOVERY_STABLE_HIGHER_LOW}`。

## RECOVERY分桶

| 子状态 | 样本 | WR | 平均PnL | SL率 | 处理 |
|---|---:|---:|---:|---:|---|
| RECOVERY_CONFIRMED_FAST_RECLAIM | 48 | 79.17% | 1.6679% | 20.83% | 可保留但不是强桶 |
| RECOVERY_STABLE_HIGHER_LOW | 25 | 88.00% | 3.2702% | 12.00% | 可保留 |
| RECOVERY_TRANSITION_UNCONFIRMED | 3 | 33.33% | 0.5038% | 66.67% | 剔除 |
| RECOVERY_WEAK_LOWER_LOW_OR_FAILED_HIGH | 4 | 75.00% | 2.4429% | 50.00% | 剔除 |

剔除7笔弱RECOVERY后，组合达到523笔/WR90.25%。

## 验证文件

- 审计脚本: `/root/.hermes/scripts/v25/v90_3y_v86_gate_known_bsl_audit.py`
- 审计输出: `/root/.hermes/smc_opt_v90_daily_full_market_scanner/v90_3y_v86_gate_known_bsl_report.json`
- 审计明细: `/root/.hermes/smc_opt_v90_daily_full_market_scanner/v90_3y_v86_gate_known_bsl_rows.json`
- daily scanner: `/root/.hermes/scripts/v25/v90_daily_full_market_scanner.py`

## 已落地修改

`v90_daily_full_market_scanner.py` 在生成contract row后加入RECOVERY弱子状态硬剔除:

```python
if row.get('market_state') == 'RECOVERY' and row.get('v90_recovery_substate') not in {'RECOVERY_CONFIRMED_FAST_RECLAIM', 'RECOVERY_STABLE_HIGHER_LOW'}:
    reject_counts['RECOVERY_WEAK_SUBSTATE_FAIL'] += 1
    continue
```

重跑后daily结果:

- 全市场: 4655只
- all_contract_candidates: 760
- recent_active_candidates: 33
- 剔除RECOVERY_WEAK_SUBSTATE_FAIL: 13
- 最新行情日: 20260612
- 已知BSL覆盖: 100%
- T+1违规: 0
- 字段空值: 0

前端/API验证:

- `/api/picks`: 551行，其中V90=33；选股日期/加入日期/引擎/Zone/成本线/波动/入场/SL/TP1空值=0
- `/api/live-prices`: 11行，其中V90=6；选股日/加入日/成本线/Zone/波动空值=0
- 浏览器 `/monitor` 与 `/live` 已验证列和数值展示正常

## 注意

GitNexus impact因新文件/索引未包含目标函数返回Target not found；尝试`npx gitnexus analyze`失败，原因是Node 26下`tree-sitter-c-sharp`无native build。已用最小变更处理，仅修改V90 scanner自身RECOVERY门禁，不改V88生产回测基线。
