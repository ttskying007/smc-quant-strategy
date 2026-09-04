# V21 信号精度诊断方法

## 诊断流程

1. **选一只典型股票** (如 600519.SH 或 301137.SZ) 作为基准
2. **同时跑 V20 和 V21** 信号检测，统计每类信号计数
3. **对差异大的信号逐类型排查**：
   - 打印信号所在 bar 的 K线数据 (O/H/L/C)
   - 打印周围摆动点 (swing points)
   - 对照 SMC/Pine 标准判断是否误检/漏检
4. **定位代码级根因** (非参数调优)
5. **修复后重新比较**，确认计数合理

## 诊断发现的 V20 问题

### BOS/CHOCH (detect_choch_bos_v20)
- 微小穿刺误触发: `prev_close <= sh.price and close > sh.price` 不要求穿透深度
- 同事件多bar重复: 同一结构断裂在不同bar反复触发 (bars 78-80, 199-200)
- 修复: 要求 `close - sh.price >= ATR*0.3` 穿透确认 + 同方向3bar去重

### Sweep (detect_sweep_v20)
- 同事件重复4-6次: 无cooldown, 相邻bar连续触发
- 扫描过时的旧摆动点: 60bar窗口太大, 应只扫最近25bar
- 修复: 3bar cooldown per direction + 25bar窗口 + ATR*0.08穿刺确认

### MSS (detect_mss_v20)
- 与CHOCH逻辑完全相同, 产生重复信号
- 修复: 要求ATR*0.5强穿透 + 8bar cooldown (比CHOCH更稀有)

### EQL (detect_eql_v20)
- 类型名: 产生 'EQL'/'EQH' 但 SIG_STYLE 期望 'EQL_High'/'EQL_Low'
- O(n²)全对检测: 所有pivot对都生成信号
- 修复: 类型名修正 + 每pivot最近匹配 + 5bar最小间距

### Swing检测 (detect_leg_swings)
- V21简化版使用静态窗口检查, 遗漏大量摆动点
- 正确做法: LuxAlgo leg() 状态机 (从 V20 复制)
- V20: 17 swings, V21(简化): 8 swings → 恢复后一致

## 诊断测试命令

```python
# 对比 V20 vs V21 信号
python3 -c "
from v11.signals_v21 import detect_all_signals_v21
from v11.signals_v20 import detect_all_signals_v20
from collections import Counter
# ... load ohlcv, run both, print comparison table
"

# 单独测试某个检测器
python3 -c "
from v11.signals_v21 import detect_sweep_v21, detect_leg_swings, _calc_atr
# ...
"
```
