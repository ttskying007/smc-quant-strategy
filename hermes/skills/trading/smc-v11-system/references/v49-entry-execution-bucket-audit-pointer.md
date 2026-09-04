# V49 入场执行桶污染审计

参考：`references/v49-entry-execution-bucket-audit.md`

要点：当 Pine/LuxAlgo 对齐后的 OB/FVG 主链路已基本正确，但回测仍被止损率或盈亏比拖累时，先做 `entry_mode` / execution path 分桶审计，不要直接调 SL/TP。V49 发现 `ZONE_MID_EXECUTABLE` 中区提前成交会污染高质量信号；应先隔离弱执行桶，再单独做 runner/trailing 实验。
