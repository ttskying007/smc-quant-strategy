# V481–V484 双边流动性清洗反转闭环

## 冻结本体

`已确认3L/3R区间高低点 → BSL影线扫损并收回 → 2..10bar后SSL影线扫损同一区间并收回（中间不得收盘突破raid ceiling或range low）→ 3bar内收盘突破SSL raid high → 次日开盘`。

该本体区别于：
- 单次/双次SSL Turtle Soup：先消费上方BSL，再扫下方SSL；
- R4 balance-breaker：不要求Breaker/OB回踩，要求相反两端流动性都被清洗；
- PO3：不使用压缩/成交量状态。

## 验证结果

- 全市场：4,903只。
- 语义种子：12,311；2023/24/25/26分别1,666/3,869/4,833/1,941。
- 独立raw-bar Oracle：12,311/12,311，零差异。
- 语义时序失败0；回放时序失败0；T+1违规0；search count=1。
- 固定执行：确认后次日开盘；SL=SSL raid low×0.99；TP=此前BSL raid high；最长20bar；费率0.2%；gap-aware；同bar冲突按SL。

|范围|n|毛WR|净WR>=0.8%|AvgNet|AvgWin|AvgLoss|Payoff|PF|SL率|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|全体|9,719|57.46%|52.17%|+0.1969%|+4.9187%|-6.0233%|0.8166|1.0758|40.37%|
|2023|1,342|49.25%|43.37%|-0.6576%|+3.9286%|-4.9913%|0.7871|0.7437|49.25%|
|2024|3,257|54.31%|51.06%|+0.0380%|+5.6723%|-6.5535%|0.8655|1.0126|42.98%|
|2025|3,805|65.52%|58.37%|+0.9119%|+4.5416%|-5.7421%|0.7909|1.4499|32.14%|
|2026|1,315|50.34%|45.93%|-0.6060%|+5.3012%|-6.4684%|0.8196|0.8133|48.67%|

另有2,347个setup在次日开盘时目标已被消费，说明A股T+1执行经常错过这种区间内双边清洗的回归空间。

## 结论

本体语义真实且供给充足，但总体AvgNet/PF不达门槛，2023与2026均负。关闭`BSL_THEN_SSL_TWO_SIDED_LIQUIDITY_PURGE_REVERSAL`，禁止raid间距、阈值、SL、TP、hold、年份或regime变体。

Artifacts：`v481_two_sided_liquidity_purge_latest.json`、`v482_two_sided_liquidity_purge_oracle_latest.json`、`v483_two_sided_liquidity_purge_frozen_t1_replay_latest.json`、`v484_two_sided_liquidity_purge_direction_closure_latest.json`。
