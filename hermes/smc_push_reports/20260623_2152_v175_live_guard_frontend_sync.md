# V175继续闭环验证报告 2026-06-23 21:53:38

## 1. 本轮已修复并验证
|项|结果|
|---|---:|
|报告顶层指标|已补 n/win_rate/avg_pnl/sl_rate/min_year/T+1/year_counts/year_wr|
|/api/picks 实盘买入过滤|已同步当前价 live_guard，不再把全部历史候选显示为BUY|
|/api/picks BUY/WATCH_ONLY|3 / 23|
|/api/live-prices BUY/WATCH_ONLY|3 / 23|
|K线/回测/分析/复盘/文档|HTTP 200 已验证|
|POST /api/reselect V175|ok=true 已验证，重跑后 /api/picks 仍为3 BUY/23 WATCH_ONLY|
|GitNexus|已停止使用|

## 2. V175总体结果
|指标|值|
|---|---:|
|交易数|247|
|胜率|83.81%|
|平均PnL|6.0493%|
|中位PnL|7.4551%|
|总PnL|1494.17%|
|亏损笔数|40|
|T+1违规|0|

## 3. 逐月统计
|月份|笔数|WR|AvgPnL|TotalPnL|亏损笔数|
|---|---:|---:|---:|---:|---:|
|202308|9|77.78%|6.2467%|56.22%|2|
|202309|2|100.00%|7.8398%|15.68%|0|
|202310|22|90.91%|7.0093%|154.20%|2|
|202311|5|80.00%|5.2153%|26.08%|1|
|202312|9|66.67%|3.0806%|27.73%|3|
|202401|6|50.00%|0.9289%|5.57%|3|
|202402|17|88.24%|7.2578%|123.38%|2|
|202403|3|66.67%|3.6356%|10.91%|1|
|202404|15|86.67%|6.9532%|104.30%|2|
|202405|4|75.00%|5.5815%|22.33%|1|
|202406|3|33.33%|-2.6538%|-7.96%|2|
|202407|11|72.73%|5.2764%|58.04%|3|
|202408|3|100.00%|9.1209%|27.36%|0|
|202409|20|95.00%|7.6930%|153.86%|1|
|202501|19|78.95%|5.8109%|110.41%|4|
|202502|4|100.00%|9.0277%|36.11%|0|
|202504|40|90.00%|5.9637%|238.55%|4|
|202510|4|25.00%|-3.0366%|-12.15%|3|
|202512|13|92.31%|8.9015%|115.72%|1|
|202603|8|75.00%|4.8763%|39.01%|2|
|202604|4|75.00%|4.1843%|16.74%|1|
|202605|1|0.00%|-11.3069%|-11.31%|1|
|202606|25|96.00%|7.3358%|183.40%|1|

## 4. 出场/复盘结构
|出场原因|笔数|占比|
|---|---:|---:|
|TP|160|64.78%|
|TIME|65|26.32%|
|SL|20|8.10%|
|GAP_SL|2|0.81%|

## 5. /api/picks 当前实盘过滤分布
|LiveGuard|数量|含义|
|---|---:|---|
|WATCH_ONLY_TP_ALREADY_HIT|13|当前价已到/越过TP，只观察不追买|
|WATCH_ONLY_PRICE_NOT_NEAR_ENTRY|9|当前价偏离入场>1.5%，只观察|
|BUY_VALID|3|当前价距入场≤1.5%，未触SL/TP，可买入|
|WATCH_ONLY_SL_ALREADY_HIT|1|当前价已触/跌破SL，禁止买入|

## 6. 当前仅3条BUY_VALID
|代码|选股日|入场|现价|偏离%|SL|TP1|操作|
|---|---|---:|---:|---:|---:|---:|---|
|688376.SH|20260616|78.05|78.73|0.87|70.69|89.10|BUY|
|002401.SZ|20260615|12.70|12.81|0.87|12.04|13.69|BUY|
|603568.SH|20260611|15.71|15.50|-1.34|14.93|16.88|BUY|

## 7. 最差20笔逐笔复盘索引
|序|代码|入场日|出场日|PnL|出场|事件|入场方式|SL|TP1|
|---:|---|---|---|---:|---|---|---|---:|---:|
|1|000630.SZ|20260529|20260608|-11.31%|GAP_SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|6.32|7.55|
|2|000591.SZ|20260325|20260331|-8.55%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|5.63|6.95|
|3|600288.SH|20250108|20250113|-8.53%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|8.41|10.38|
|4|688019.SH|20240716|20240724|-8.49%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|63.81|78.62|
|5|601595.SH|20240124|20240131|-8.47%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|21.82|26.87|
|6|301141.SZ|20250409|20250418|-8.07%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|35.39|43.16|
|7|301315.SZ|20240611|20240620|-7.32%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|43.81|52.46|
|8|688600.SH|20240424|20240429|-6.86%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|16.69|19.76|
|9|688399.SH|20240126|20240205|-6.75%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|31.12|36.76|
|10|000702.SZ|20250115|20250122|-6.52%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|6.71|7.88|
|11|605122.SH|20240627|20240709|-6.15%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|9.21|10.71|
|12|300565.SZ|20260408|20260420|-6.09%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|13.88|16.13|
|13|002805.SZ|20231030|20231110|-6.02%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|16.85|19.55|
|14|002724.SZ|20251021|20251029|-5.94%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|7.17|8.30|
|15|603444.SH|20230830|20230906|-5.87%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|356.92|412.61|
|16|002721.SZ|20240124|20240201|-5.78%|GAP_SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|2.63|2.97|
|17|688513.SH|20231228|20240108|-5.66%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|37.21|42.79|
|18|300029.SZ|20260325|20260407|-5.64%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|4.63|5.33|
|19|002586.SZ|20251230|20260113|-5.06%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|4.17|4.72|
|20|002466.SZ|20240904|20240910|-4.56%|SL|DEMAND_OB_TRUE_TAKEOVER_RECLAIM|scanner_reclaim_next_open|24.70|27.65|

## 8. 结论/下一步
- V175不是新经济模型，是V172的语义纠偏版；经济结果不变，但前端不再声称古典SSL/CHOCH。
- 当前最大未闭环点不是WR，而是V172/V175活跃候选仍来自最近45天扫描集合；本轮已在/api/picks和/api/live-prices层按当前价过滤为3条可买、23条观察。
- 下一步应继续做“扫描器源头层”的实时候选重算：让v175_active_picks.json本身只写入BUY_VALID，WATCH_ONLY另存，避免任何下游绕过API guard。
