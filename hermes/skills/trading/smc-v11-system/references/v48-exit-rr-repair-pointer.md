# V48 出场/RR 修复教训

当信号合同已通过但 RR/avgPnL 偏低、sold_early_rate 高时，先做出场分诊和 runner 修复候选，不要先改 OB/FVG/组合定义。跳空越过 TP1/TP2 时必须按 open 成交，否则会出现 exit leg price 不在当日 K 线范围内的假成交。

完整步骤、参数候选和逐笔验证清单见：

```text
references/v48-exit-rr-repair-lessons.md
```
