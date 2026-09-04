# K线信号窗口不同步陷阱 (V20.11修复)

## 问题

前端`smc_unified.py`中`_api_kline_full`方法的序列高亮逻辑与引擎`v19_engine.py`的信号时间窗口是**两套独立代码**。

引擎升级窗口值后，前端未同步更新 → K线图上高亮的信号范围与引擎实际使用的范围不一致。

## 用户报告

"K线图表中显示的关联信号时间长度和你设计的不一样"

## 根因

两处代码维护相同的窗口常量但未集中管理：

**引擎** (`/tmp/v19_engine.py`):
```python
sweeps = [s for s in signals if ... and ob_idx - 20 <= s.idx <= ob_idx]  # 20
chochs = [s for s in signals if ... and ob_idx <= s.idx <= ob_idx + 15]   # 15
fvgs = [s for s in signals if ... and abs(s.idx - ob_idx) <= 3]           # 3
```

**前端** (`smc_unified.py` - 修复前):
```python
if ... and ob.idx-30 <= s.idx <= ob.idx:     # 30 (引擎=20)
elif ... and ob.idx <= s.idx < last_n:        # 无上限 (引擎=15)
elif ... and abs(s.idx - ob.idx) <= 5:        # 5 (引擎=3)
```

## 修复

全部窗口值同步为V20引擎值，并新增MSS/IFVG/OTE渲染。

## 预防

每次修改引擎时间窗口后，**必须同步检查**`smc_unified.py`中`_api_kline_full`的对应窗口值。
