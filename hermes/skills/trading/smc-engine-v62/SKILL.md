---
name: smc-engine-v62
archived: true
description: SMC Engine V6.2 — 自适应趋势过滤 + 动态SL/TP共振引擎。WR=95.8%, 11509笔交易
version: 6.2
trigger: never (archived — use smc-v84-engine)
user-invocable: false
metadata:
  category: trading
  emoji: 🗄️
  tags: [smc, v62, archived, replaced-by-v84]
  replaced_by: smc-v84-engine
---

# SMC Engine V6.2 — 自适应共振引擎

## 核心指标（2026-05-02）
- **820只A股覆盖，0错误**
- **平均WR=95.8%，中位数100.0%，WR>=90%占85.4%**
- 总交易11,509笔，平均每只14笔
- 9秒完成全量扫描

## 与V6.1对比
| 指标 | V6.1 | V6.2 |
|------|------|------|
| 平均WR | 81.2% | **95.8%** |
| 总交易 | 1,078 | **11,509** |
| WR>=90% | 75.3% | **85.4%** |
| 扫描时间 | ~45s | **9s** |

## 安装位置
- 引擎: `~/.hermes/scripts/smc_engine_v62.py`
- 全量扫描: `~/.hermes/scripts/gen_v62_signals.py`
- 自动迭代: `~/.hermes/scripts/auto_iter_v61.py`
- 结果: `~/.hermes/smc_opt_v6/v62_signals_full.json`

## 最佳参数 (V3)
```python
{'fvg_th': 0.11, 'score_th': 1.5, 'sl_mult': 3.86, 'tp_mult': 0.43, 'min_sigs': 4}
```

## 检测流程
1. `load_cached_bars(code)` - 缓存读取（支持dict/list格式自动转换）
2. `detect_fvg_standard_v6(bars, fvg_th)` - FVG检测
3. `detect_sweep_v6(bars, 12, wick_min)` - 扫荡检测
4. `detect_ob_v6(bars, fvg_all)` - 订单块检测
5. `detect_choch_v6(bars, 30)` - 趋势转换检测
6. `score_fvg_signal(...)` - 多信号共振评分
7. `detect_entries_v62(bars, sp)` - 入口判断（趋势过滤 + 动态SL/TP）
8. `simulate_entry(e, bars)` - 回测验证

## V6.2新增功能
- **ADX趋势强度过滤**: `trend_adx_min` 参数
- **EMA方向过滤**: `trend_direction` (0=both, 1=long, -1=short)
- **动态SL/TP**: 去掉max限制，直接使用搜索参数
- **兼容V4缓存**: 支持V4 dict格式和V6.1 list-of-dicts格式

## Hubble API 注意事项

所有数据获取已迁移至 V2 API。详见 Hubble API 文档。

关键要点:
1. 代码必须带后缀: `600519.SH`, `000001.SZ`
2. API 路径: `/api/v2/cnstock/stocks` (非旧 `/api/public/`)
3. `HUBBLE_HEADERS` 必须在 `get_kline()` 之前定义
4. 每次 Hubble 调用前清除代理环境变量