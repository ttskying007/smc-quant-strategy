# Signal Sequence Pattern Analysis

## 方法论

从V16/V21交易数据中提取每个交易入场点前5个信号的类型序列, 统计各模式的胜率。

**信号类型编码:**
- `F` = FVG (Fair Value Gap) — 公允价值缺口
- `O` = OB (Order Block) — 订单块
- `S` = Sweep (流动性抓取)
- `C` = CHOCH (Change of Character) — 性格转变
- `B` = BPR (Balancing) — 平衡
- `?` = 其他

## 已验证的高/低胜率模式

### 顶级模式 (WR≥85%)

| 模式 | WR | 含义 | 操作 |
|------|-----|------|------|
| **OB→FVG** (最后2个: O然后F) | **90%** | OB确认支撑后FVG确认突破 | Enter, 降共振阈值0.10 |
| **Sweep→FVG** (S在F之前) | **85%** | 流动性抓取后FVG = 强反转 | Enter, 降共振阈值0.08 |
| **FVG→OB** (F然后O) | **100%** | (稀有) FVG后OB = 市场停止寻找流动性 | Enter, 降阈值0.15 |
| **seq≥0.7** (综合评分) | **92%** | 任意高质量序列组合 | Enter (过滤~90%) |
| **res≤0.50** (V22低门槛) | **85%** | 序列好→门槛低→任意入场 | 信号序列辅助决策 |

### 中等级别

| 模式 | WR | 含义 | 操作 |
|------|-----|------|------|
| FVG在末位 | ~77% | 基线略好 | 正常入场 |
| 混合3+类型 | ~78% | 多样化信号 = 健康市场 | 正常入场 |
| seq≥0.6 | 79% | 较好序列 | 正常入场, 略降门槛 |

### 危险模式 (WR<40%)

| 模式 | WR | 含义 | 操作 |
|------|-----|------|------|
| **OOOOO** (5个连续OB) | **17%** | OB噪声泛滥, 无方向 | ❌ SKIP |
| **SOOSO** (Sweep+OB重复) | **0%** | 双流扫, 市场无方向 | ❌ SKIP |
| OB≥4个 | ~17% | 太多OB信号 | ❌ SKIP |
| 全相同类型信号 | ~17-50% | 单方面信号 = 噪声 | ❌ SKIP |

## V22 入场决策集成

```python
# 信号序列评分 → 共振门槛修正
seq_score, seq_pattern, res_mod = score_signal_sequence(sigs_before, entry_type)

# 跳过恐怖模式
if seq_score <= 0.0: return None  # e.g. OOOOO, SOOSO

# 修改共振门槛
base_res = 0.65  # or 0.70 for OB
adjusted_res = base_res + res_mod
# res_mod can be -0.15 (easier entry) to +0.20 (harder)
adjusted_res = max(0.40, min(0.85, adjusted_res))
```

## 关键原则

1. **OB噪声音量 > OB信号量**: 连续OB是噪声, 稀疏OB是好信号
2. **Sweep是确认, 不是入场**: Sweep单独WR低, 但Sweep→FVG是顶级组合
3. **FVG在末位是好信号**: 最后一位是FVG = 刚发生的FV G
4. **多样性 = 健康**: 3+不同类型信号聚类 = 市场形成清晰结构
5. **信号密度适中最好**: 太多(>15/100K线)=噪声, 太少(<5/100K线)=机会不足
