# T+1监控系统 — 30分钟进场/止损检查 (2026-05-14)

## 文件
- 选股: /root/.hermes/smc_opt_v21/all_signals_picks.json (含OB_Bull及全部信号类型+组合)
- 持仓: /root/.hermes/smc_opt_v21/live_monitor/active_positions.json
- 盈亏日志: /root/.hermes/smc_opt_v21/live_monitor/pnl_log.json
- 脚本: /root/.hermes/scripts/v11/monitor_check.py

## 流程

1. 从all_signals_picks.json读取昨日信号(n-2 bar)
2. 排除已有持仓(去重)
3. 今日开盘买入(T+1), 记录入场+SL+TP
4. 检查持仓: 当前价格触及SL/TP则退出

## T+1合规

- 当日买入不可当日卖出
- 监控只检查picked_date != today的持仓

## 限流: 30只/次

原因: 每只get_current_price()触发一次curl(0.2-0.8s), 30只约6-24s。
1246只全量检查会超时。配置MAX_CHECK_PER_RUN=30。

## cron: 每30分钟

cron ID: 7d268bd6dc08, 命令: cd /root/.hermes/scripts/v11 && python3 monitor_check.py

## 数据刷新

today_refresh_pick.py: 腾讯API 20并发下载最新日线

## 陷阱

- 持仓初始化跳过错失的历史信号(保留最近5bar内信号)
- SL=zone_low*0.995, TP=close*1.03
- 信号价格用信号触发bar的收盘价, 非实时价格
- 腾讯API需-L跟随重定向, 东方财富HTTPS不可靠, 用subprocess+curl
