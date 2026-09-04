# V26 十年回测发现 (2026-05-19)

## 数据源
- Tencent fqkline API: `web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,750,qfq`
- 4649/4905只成功下载，API实际返回10年+数据(非750bar限制)
- 日期范围: 2015-10-28 → 2026-05-13

## 全量回测结果 (20000采样)
- 1143 trades | WR=83.6% | avgP=+1.77% | Total=+2026.71%
- STRONG MTF: 596t WR=**88.6%** | TREND_DOWN: 171t WR=**93.6%**

## 关键发现
1. **OB_Bull唯一可靠zone**: WR=83.6% vs FVG_Bull=65.4%。排除FVG_Bull
2. **FVG_Bull在A股长期不可靠**: 1869笔 WR=65.4%，需PINBAR+BOS双重确认才勉强可用
3. **TREND_DOWN最高胜率**: 当过滤掉ALIGNED+TREND_DOWN后 WR=93.6%
4. **Inducement最优辅助**: 1018笔 WR=87.1%
5. **STRONG MTF=质量过滤**: 596笔 WR=88.6%
6. **PINBAR≈CHOCH**: 83.6% vs 83.5%，可互换使用
7. **TurtleSoup不可靠**: WR=50%，A股假突破模式无效

## 文件清单
- 引擎: `scripts/v25/v26_engine.py` (支持750bar K线，采样20000 picks)
- 扫描: `scripts/v25/scan_3y.py` (全量4649只，OB_Bull+FVG filter)
- 下载: `scripts/v25/download_750.py` (Tencent fqkline并行下载)
- 数据: `smc_opt_v25/v26_picks_3y.json` (41812 picks)
- 回测: `smc_opt_v25/v26_trades.json` (1143 trades)
- 分析: `smc_opt_v25/v26_autopsy.json`