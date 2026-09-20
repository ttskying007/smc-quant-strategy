# R60 交付: 全因果 SMC 信号链(回测/选股/前端三线打通)

用户指令: 回测与选股都要完整记录当下趋势判断 + BOS/CHoCH/BSL/SSL/OB/FVG/IFVG 的
时间+价格+信号类型 + 前高时间价格 + 突破时间价格 + 回踩价格与信号 + 当前回踩状态,
并在 K 线图上绘制, 全部同步到前端。

## 单源实现
- `research/core/chain.py` — 因果链抽取器(信号日 <=i 截止, 摆动确认 j+PIVOT<=i)
  - build_chain(bs, i) → {trend_state, events_tail[BOS/CHoCH 时间+价格],
    bsl/ssl(时间+价格+swept), ob(需求/供给), fvg_bull/fvg_bear(含 IFVG 反转标注),
    breakout(date/price/kind), retrace(price/state/signal 方向感知)}
  - 因果自检: 688326 全段通过; 688326 实测 trend=down + 4个BOS↓ + 突破57.77@0914
    + 反抽58.75收复(破位失败) + BSL66.79/SSL57.77 swept=True — 全链正确
- 措辞修正: retrace_signal 方向感知(向上突破"回踩跌破(突破失败)",
  向下破位"反抽收复(破位失败)"), 修复首版语义反置

## 三线消费者
1. **回测** gen_v22_chain.py(=v21 复制+链列): combo_v22_trades.csv 1858 腿,
   +7 列(breakout_date/price/kind, retrace_price/state/signal, chain_json 全链)
   验收: 1858/1858 与 v21 重叠 pnl 零不一致; 链列 100% 非空; 年度统计逐位相同
   retrace_state 分布: 到位736 / 失败509 / 未回踩613
2. **选股** paper_sim.py: `_chain_of(bs,i)` 软失败辅助, EVENT 挂单(line~900)与
   CONT 挂单(line~1008)均带 `"chain"` 全链快照 → ledger 留档, 每晚 00:00 生产落地
3. **前端** smc_unified.py /kline(8890):
   - API `/api/kline_full` 新增 `smc_chain` 载荷(含图表日期解析 x 坐标)
   - 图表叠加新系列 "SMC链": BSL蓝虚线(标注扫否)/SSL红虚线/FVG绿红箱(IFVG紫)
     /OB橙色供给绿需求箱/BOS△·CHoCH◇标记/突破橙线/回踩点(到位绿·失败红)
   - 图表下方 "🧬 SMC 信号链(当前)" 面板: 趋势/现价 + 事件/前高/前低/OB/缺口/
     突破/回踩 全链表
   - 已重启 8890 (PID 13600), /kline 页 + API 双端验证 OK

## 未变纪律
引擎零改动(验收证明), canonical v20f 零接触, 审计套件 228 断言全绿。
retrace_state 三分类(736/509/613) 是现成的"回踩是否成立"信号质量维度,
登记进 E4'' 候选池待下一数据周期 frozen OOS。
