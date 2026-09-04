# SMC 序列策略引擎 V1.0 设计

## 架构
SIGNAL_CATEGORIES (6类14种信号) → SEQUENCE_PATTERNS (可扩展模式) → detect_sequences() → backtest_sequences() → stats

## 信号分类
LIQUIDITY: Sweep_SSL/EQL/Sweep_BSL/EQH
STRUCTURE: CHOCH/BOS/MSS (Bull+Bear)
ZONE: OB_Bull/FVG_Bull (Demand), OB_Bear/FVG_Bear (Supply)

## 关键结果
L→D: 2638笔 WR=80.1% PnL=+2.76% PF=6.6 (最强)
Combined: 6445笔 WR=75.6% PnL=+2.44% PF=4.9
核心发现: 流动性扫荡→需求区 是最强单模式, 不需要CHOCH结构确认

## 文件
signals_v20.py, smc_sequence_engine.py
