# V20.1 CHOCH标签法检测

## 背景

V20.0 CHOCH/BOS检测使用 `last_cross_dir` 状态追踪:
- 记录上一次穿越方向(+1=bull, -1=bear)
- 当前穿越方向与上次相反 → CHOCH (趋势反转)
- 当前穿越方向与上次相同 → BOS (趋势延续)

问题: `last_cross_dir` 是全局状态，一旦初始化为某个方向，所有后续穿越都被迫沿用该判定。在趋势市场(如A股日线常有单边走势)，`last_cross_dir` 几乎不变 → CHOCH近乎为零。

诊断: V20.0全量4800 CHOCH=9,556 (2.0/只), BOS=23,131。CHOCH/BOS比=41%——理论应接近50-70%。

## V20.1: 摆动点标签法

SMC理论核心:
- CHOCH = Change of Character = 趋势反转
- 下降趋势: LL + LH → 上穿**LH** = 趋势从下降转为上升 = CHOCH_Bull
- 上升趋势: HH + HL → 下穿**HL** = 趋势从上升转为下降 = CHOCH_Bear
- 上穿 HH = 延续上升 = BOS_Bull
- 下穿 LL = 延续下降 = BOS_Bear

关键洞察: **摆动点的HH/HL/LL/LH标签已经编码了趋势信息**。无需额外追踪 `last_cross_dir`。

## 实现

```python
def detect_choch_bos_v20(ohlcv, swings):
    fired_swings = set()
    for i in range(1, n):
        bar_has_high_signal = False
        bar_has_low_signal = False
        
        for sh in swings:
            if sh.type != 'H': continue
            if sh.bar_idx >= i: continue
            if sh.bar_idx in fired_swings: continue
            if bar_has_high_signal: continue  # 1 per bar
            
            if prev_close <= sh.price and close > sh.price:
                if sh.label == 'LH': tag = 'CHOCH_Bull'
                elif sh.label == 'HH': tag = 'BOS_Bull'
                else: tag = 'BOS_Bull'
                
                fired_swings.add(sh.bar_idx)
                bar_has_high_signal = True
        
        # 同理处理 swing lows: HL→CHOCH_Bear, LL→BOS_Bear
```

## 结果 (全量4800)

| 指标 | V20.0 | V20.1 | 变化 |
|------|-------|-------|------|
| CHOCH总数 | 9,556 | 12,934 | +35% |
| 每只CHOCH | 2.0 | 2.7 | +35% |
| BOS总数 | 23,131 | 16,270 | -30% |
| CHOCH/BOS比 | 41% | 79% | 更均衡 |

## 去重策略

- 每个摆动点仅触发一次 (`fired_swings` set)
- 每个bar最多1个high触发 + 1个low触发
- 不检查 "beaten" (被后来摆动超越的旧摆动) — 旧摆动点仍是有效结构参考

## 文件

- 实现: `/root/.hermes/scripts/v11/signals_v20.py` → `detect_choch_bos_v20()`
- 对比脚本: `/root/.hermes/scripts/v11/choch_compare.py`
