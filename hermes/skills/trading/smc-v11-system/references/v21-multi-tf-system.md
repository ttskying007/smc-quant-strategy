# V21 多周期选股系统

## 架构
周线SMC趋势 → 日线SMC序列组合 → 60min入场定位

### 周线
- 从日线合成(每5根=1根周线)
- V20信号检测: CHOCH/BOS方向+摆动结构→bullish/bearish/neutral

### 日线
- 三分类: LIQUIDITY/STRUCTURE/ZONE
- 序列: L→D, S→D, L→S→D
- 窗口: full(300)/mid(150)/recent(50)

### 60min
- 腾讯ifzq API, 缓存格式: `{sym}_{mkt}_60min_500.json`

## 文件
- multi_tf_v2.py: 主脚本
- multi_tf_stock_db.json: 1607只数据库
- smc_sequence_engine.py: 可扩展序列引擎

## 核心发现
1. L→D最强: 2638笔 WR=80.1% PnL=+2.76% PF=6.6
2. 熊市L→D占89%, 牛市S→D+L→D各半
3. 窗口稳定性差(36%), 需定期重评估
