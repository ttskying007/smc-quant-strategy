# R52 修复记账: 周末公告顺延 + TP 锚点守卫补全

日期: 2026-09-20 (周日) · 用户裁决: Q2=a, Q4=先记账→审计→再进生产
性质: **选股管道数据接驳修复**（非信号逻辑变更, 不触碰预注册冻结实验）

## Fix-1: 周末/节假日公告顺延 (paper_sim.py daily_selection EVENT 腿)
- **现象**: 9-19(周六) 44 条公告中 14 条被判 "K线无此日期" 丢弃 (31.8%)
- **根因**: `d8 not in dates` 直接 continue; 周六无 K 线是日历事实, 不是数据缺失
- **修复**: `bisect_left(dates, d8)` 取前一个交易日为信号日 (i = _i0 - 1);
  周末披露 → 周五收盘为决策态 → T+1 (下个交易日) 开盘成交, 时序无前视
- **回滚开关**: 无需开关 — 行为等价于把"日历盲区丢弃"改为"最近可得决策态";
  完全回退 = 还原该 else 分支即可 (git revert)
- **验证**: 手动跑 daily_selection: nodata 14→4 (余 4 条为真无K线),
  被顺延的 10 条进入 stage/ADX 正常过滤 (stage 17 / adx 9), 0 订单误生成

## Fix-2: TP/SL 回退守卫补 tp2/tp3 (旧隐患, 非本次引入)
- **现象**: 验证 Fix-1 时 daily_selection 在 `round(tp3,3)` 崩溃 TypeError
- **根因**: structural_sltp ACCUM/DOWNTREND 分支在 len(highs)<=2 时 tp2/tp3=None;
  旧守卫 `tp1 is None or sl1 is None or tp4 is None or tp4<=close or sl2 is None`
  **漏查 tp2/tp3** → None 直达订单字典构造
- **修复**: 守卫条件补 `tp2 is None or tp3 is None`, 触发即走固定比例回退
  (tp1=+3%/tp2=+6%/tp3=+10%/tp4=+15%/sl1=-4%/sl2=-10%, anchor_note 标注"回退")
- **回滚开关**: 无 (fail-closed 方向, 与审计§6.2 精神一致)

## 审计与提交
- run_audit_tests: 23 文件 / 228 断言 全绿 (修复后)
- 手动验证运行无订单产生, paper_ledger 未受影响;
  selection_funnel/reject_ledger 被周日验证跑刷新 (今晚生产 run 会再覆盖, 无需回滚)
