---
name: smc-v13-scanner
version: 13.0.0
description: >-
  SMC V13 全量市场扫描引擎。 Scout-only + Bull-only + 固定SL/TP=0.5%/5.0%
  + 阶段过滤。 并行4进程, 批量保存, 断点续传。 全量4800股票, 2168可交易
  (45.2%), 平均WR=69.5%, 平均RR=7.28x, 12,925笔交易验证。
user-invocable: true
metadata:
  category: trading
  emoji: "🔍"
  tags: [smc, v13, full-market, scout-only, bull-only, backtest]
  supersedes: [smc-v11-system]
  requires: v11 signals_v11, v11 sequencer, v11 resonance, v11 adaptive_params
---

# SMC V13 — 全量市场扫描引擎

## 策略
Scout-only + Bull-only + SL=0.5%/TP=5.0%固定 + breakout/volatile阶段

## 全量结果 (4800 A股, 12,925笔交易)
- 可交易: 2168/4800 (45.2%)
- 平均WR: 69.5% | 平均RR: 7.28x | 平均PF: 58.0
- volatile阶段WR=78.6% > breakout阶段WR=66.4%
- WR>=70%: 约500只 | WR>=80%:约205只

## 使用
```bash
cd ~/.hermes/scripts
python3 backtest_v13.py --start 0 --batch 500 --workers 4
```

## 输出
~/.hermes/smc_opt_v13/batch_*.json
