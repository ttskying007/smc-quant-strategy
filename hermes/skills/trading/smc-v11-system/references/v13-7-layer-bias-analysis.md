# V13 Swing-Backward OB 7层偏差分析 (2026-05-12)

## 背景

V13混合引擎(swing-backward primary + forward fallback)在60min数据上永远无法匹配V11 forward-scan OB的纯度。这不是参数问题——是7个层级的系统性架构偏差, 其中5个是设计选择, 不是可调参数。

## Layer 1: Confidence公式差异 (最大杀伤力)

### V11公式 (_calc_ob_confidence_v11, signals_v11.py:871-890)
```python
conf = 0.40  # base
if body_pct > 1.0:   conf += 0.05  # 轻松
if body_pct > 2.0:   conf += 0.10
if body_pct > 3.0:   conf += 0.15
if vol_ok:            conf += 0.15  # 宽松
if at_structure:      conf += 0.20  # 大幅加分
if impulse_bars >= 3: conf += 0.05
if impulse_bars >= 4: conf += 0.10
```
V11典型: 0.40 + 0.15(vol) + 0.20(at_structure) = **0.75**

### V12公式 (signals_v12.py:342)
```python
sig.confidence = min(0.95, 0.35 + dis_ratio * 0.06
                     + (0.10 if vol_ok else 0)
                     + (0.15 if at_structure else 0))
```
V12 dis_ratio=1.0无加分: 0.35 + 0.06 = **0.41**
V12全部加分(vol+structure+dis=2.0): 0.35 + 0.12 + 0.10 + 0.15 = **0.72**

### 对比
| 场景 | V11 | V12 | 差距 |
|------|:---:|:---:|:----:|
| 基础(无加分) | 0.40 | 0.35 | -0.05 |
| vol_ok | 0.55 | 0.45 | -0.10 |
| vol+structure | **0.75** | **0.60** | **-0.15** |
| 全加分 | 0.85 | 0.72 | -0.13 |

引擎质量门槛=0.50 → 大部分V13 OB被直接杀死。

### V13 Fallback公式 (signals_v12.py:1462, 无structure加分)
```python
sig.confidence = min(0.60, 0.20 + dis_ratio * 0.04
                     + (0.05 if vol_ok else 0))
```
即使dis_ratio=3.0x, vol_ok=True: 0.20 + 0.12 + 0.05 = **0.37**
永不能过0.50质量门槛 → **V13 fallback形同虚设。**

## Layer 2: at_structure 永远False (逻辑缺陷)

V12 backward-scan的OB位于摆动点**之前3-15根K线**。但`_near_swing(ob_idx, w=5)`只检查OB是否在摆动点5bar内。

```python
# signals_v12.py:266-267
def _near_swing(idx, w=5):
    return any(abs(idx - si) <= w for si in all_swing_idxs)
```

**悖论**: swing-backward的核心意义就是从摆动点往后找到OB, 但OB位置天然离摆动点远, 永远拿不到at_structure加分。

V11 OB直接在摆动点位置(forward-scan) → at_structure轻松True。

### 修复方向
- 扩大_near_swing窗口到~15(匹配backward scan最大范围25)
- 或取消at_structure在confidence中的依赖, 用其他因子替代

## Layer 3: to_dict() 展平metadata (代码设计缺陷)

`Signal.to_dict()` (signals_v12.py:37-54):
```python
def to_dict(self) -> Dict:
    return {
        'type': self.type, 'idx': self.idx, 'direction': self.direction,
        ...,
        **self.metadata,  # ← 展平到顶层!
    }
```

后果:
- dict中没有`metadata`这个key
- `at_structure`, `body_pct`, `displacement_ratio`变成顶层属性
- 引擎中 `sig.get('metadata', {}).get('at_structure', False)` 永远返回False

### 修复方向
- 改为 `'metadata': self.metadata` 保留嵌套
- 或引擎改用 `sig.get('at_structure', False)` (直接查顶层)

## Layer 4: is_reversal_ob 在uptrend中无差别拦截

v474_engine.py:306-309:
```python
if trend20 > 1.0:
    if has_sweep and has_reversal_choch:
        return True  # 极少数同时成立
    return False  # 杀死所有上升趋势中的OB
```

V11 OB更多出现在结构反转处(forward-scan天然查找到反转点), 更容易通过此检查。
V13 OB可能出现在合理的pullback位置(上升趋势中的回调), 但被无差别拦截。

### 25条K线内的反转性
真正ICT OB应该在20-25bar趋势为"中性或轻微下行"时, 而非严格<0%。建议将趋势判定改为20-bar EMA方向而非绝对价格变动百分比。

## Layer 5: 引擎volume filter硬编码0.6

v474_engine.py:704-710:
```python
if sig_idx > 30 and sig_idx < n:
    bv = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
    avg_vol = sum(ohlcv[j].get('v', ohlcv[j].get('vol', 0))
                 for j in range(max(0, sig_idx-30), sig_idx)) / 30
    if bv < avg_vol * 0.6:  # ← 硬编码60%
        return None
```

V13 OBs检测参数更宽松(body >= 0.08-0.10%, dis >= 0.7-1.0x), 通过的OB平均成交量低于V11, 此处被过滤比例更高。

## Layer 6: MIN_PROJECTED_RR=6.0 偏杀V13

V13 OB位置靠后(backward-scan远离摆动点) → SL距离(entry_price - signal_lower)更大。

projected_rr = tp_pct / sl_pct → 更大分母 → 更低比率 → 更容易被MIN_PROJECTED_RR=6.0杀死。

## Layer 7: 过滤链标准化输入

W437参数灵敏度测试证明: 6组参数(0.10-0.15body, 0.7-1.0dis, 3-5near, 0.3-0.5vol)在200只测试中WR仅波动1.3pp(77.4-78.7%)。

**原因**: 引擎的序列+共振+趋势+反转+volume过滤链吸收并标准化了不同质量的输入——OB检测参数只控制进入过滤链的信号**数量**, 不控制过滤链输出**质量**。

这意味着: 一旦被过滤链接受, 交易的WR/RR与原始OB检测方法关系不大。但V13 OBs低confidence(0.30-0.45)导致它们在过滤链更早被拒绝。

## 总结: 不可修复的偏差

| 层 | 问题类型 | 可修? | 修复后V13接近V11? |
|:--:|---------|:----:|:----------------:|
| 1 | 公式设计 | 是 | 部分(conf可调至0.5-0.7) |
| 2 | 逻辑缺陷 | 是 | 部分(扩大窗口) |
| 3 | 代码设计 | 是 | 辅助(metadata访问) |
| 4 | 引擎逻辑 | 是 | 弱(过滤链主导) |
| 5 | 参数硬编码 | 是 | 弱 |
| 6 | 参数硬编码 | 是 | 弱 |
| 7 | 架构特性 | 否 | 不可改变 |

**结论**: 即使修复Layer 1-6, V13仍然不会比V11好。Layer 7(过滤链主导WR)是根本原因——输入信号在20+过滤层面前被全部拉平。这不是参数问题, 是架构设计决定。

见 `references/v13-param-sensitivity-analysis.md` 参数灵敏度测试数据。
