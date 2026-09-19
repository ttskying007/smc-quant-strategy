# R35: 周一开盘前验证报告 (2026-09-20 日 04:50)

## 背景时间线勘误 (关键)
- 9-18 15:30 daily run 失败 (announce=124 超市<600s)
- 9-19 15:58 修复落地 (751ddbe: 索引+并行)
- 失败 run **早于**修复 → 非修复无效, 顺序正常

## 当前验证结果
1. announce puller 实测: **15.5 秒**(修前 >600s 超时) ✅
2. sanity_check: 7 PASS / 1 FAIL (唯一失败=漏斗仅 5 天, 需累计到 8 天, 预期内)
3. daily_audit: 7/9 ("数据完整且最新" FAIL 因 run_status 停留在 9-18 失败态 — 明早 run 后会自动刷新)

## 遗留小风险
- 同一 failed run 中 refresh_60min 也 rc=124 (timeout=3600s)。当日 60min 更新慢可能是因为 announce 卡住后后续步顺序靠后+网络抖动。明天 run 观察是否复现; 若复现则需单独调查 60min 链路。
- run_status.json 的 data_complete=false 是 9-18 残影, 非当前态。

## 明日观察清单 (周一)
1. daily run 全流程(announce 应在 ~30s 内完成, rc=0)
2. funnel_monitor 追加第 6 天
3. PAPER 新订单 → 首笔 CLOSED 应携带 R13 loss_attribution
4. PAPER ledger CLOSED 数从 10 向 30 推进
