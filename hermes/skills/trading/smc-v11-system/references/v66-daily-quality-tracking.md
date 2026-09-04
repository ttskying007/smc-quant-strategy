# V66 每日闭环质量追踪

## 场景
记录 V66 版本各交易日闭环指标，用于趋势追踪和质量退化检测。

## 指标追踪表

### 2026-06-08
- n_trades: 137 ✅（与 06-05 一致）
- raw_wr: 90.51% ✅
- avg_pnl: +20.65% ✅
- avg_R: 5.016x ✅
- release_gate: PASS ✅
- T+1 违规: 0 ✅
- Provenance: 137/137 ✅
- Sequence: 137/137 ✅
- 90d_capture: 0.441 ✅
- 90d 问题: SOLD_EARLY=89 / STRUCTURE_STOP=79 / CAPTURE_LOW=41 / RECOVERED=12

### 2026-06-05
- n_trades: 137
- raw_wr: 90.51%
- release_gate: PASS
- T+1 违规: 0
- Provenance: 137/137
- Sequence: 137/137
- 90d_capture: 0.441

## 退化检测规则
- WR < 88%: 发送告警
- avg_R < 4.0x: 检查出场逻辑
- T+1 违规 > 0: 立即修复
- 90d_capture 连续 3 日下降: 检查 runner/trailing 质量
