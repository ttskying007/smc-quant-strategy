# OB组合信号缺失 — 系统排查方法论

## 背景
用户Lei发现CTX→OB组合信号稀少，要求"全面审核，全面重新核对，一步步流程梳理，每个函数确认"。经逐层排查，发现5个根因。

## 诊断流程

### 第1步: sbb逐bar统计
```python
sbb = defaultdict(list)
for s in signals: sbb[s.idx].append(s)
# 统计每根bar上共存信号类型
for bar in sorted(sbb.keys()):
    types = [s.type for s in sbb[bar]]
    if 'OB_Bull' in types:
        # 记录同bar的CTX信号
        same_bar_starts = [t for t in types if t in ALL_START]
```
结果: 1809个OB_Bull中，365(20%)有同bar CTX信号。

### 第2步: gap分布
```python
for prev in range(max(0, ob_bar-10), ob_bar):
    if prev in sbb:
        for s in sbb[prev]:
            if s.type in ALL_START:
                gap = ob_bar - prev
```
结果: 302个OB(17%)在1-10bar内有前序CTX。Sweep_SSL最常见(249个)。

### 第3步: L1/L2 dedup冲突
L1 OB_Bull在bar_i处，entry_bar=i+1。
L2 START→OB_Bull也用同一个entry_bar。
Dedup key=(sym, entry_bar)，L1优先级更高(排序在L2前)。
→ L1永远抢先，START→OB_Bull无法进入L2。

**这是架构级设计决定，非Bug**: OB_Bull本身含91%结构验证(HH/HL/LL/LH)，
前序信号加固有限(+1-2pp WR)，不值得为OB组合创建独立L2交易。

### 第4步: RR≥1过滤器
```python
tpd = abs(tp-ep)/ep*100; sld = abs(sl-ep)/ep*100
if sld == 0 or tpd/sld < 1.0: continue  # 过滤
```
121/310(39%)的START→OB_Bull被RR<1过滤。V19 find_sls返回的结构SL
离入场中位2-5%，与default cap 3%结合后许多combos RR<1。

### 第5步: break bug (V5已修复)
```python
# 旧代码(V5):
for j in range(i+1, i+11):
    if j in sbb:
        zone_cands = [s in sbb[j] if ZONE]
        if zone_cands:
            zone = zone_cands[0]
            break  # ❌ 第一个ZONE就停止！
# 新代码(V6):
for j in range(i+1, i+11):
    if j in sbb:
        for z in [s in sbb[j] if ZONE]:
            z_score = (gap * -1.5) + bonus
            if z_score > best_score:
                best_score = z_score; best_zone = (z, j)
        # ✅ 不break — 继续扫描
```
bug影响: FVG比OB更早出现时，OB被跳过 → 18/310案例

### 第6步: scoring权重
V5: `gap * -1 + bonus` (OB=2, FVG=1, Pinbar=0)
→ Pinbar永远是0分，永远不会被选中(0个Pinbar组合)
V6: `gap * -1.5 + bonus` (OB=3, Pinbar=2, FVG=1)
→ Pinbar gap=1: -1.5+2=0.5 > FVG gap=1: -1.5+1=-0.5 → Pinbar胜

## 最终诊断结论

1. **架构冲突**(根本原因): OB_Bull是明星信号，L1独占entry_point，CTX→OB不能作为独立L2
2. **break bug**(次要原因): 18/310案例遗漏
3. **RR过滤**(次要原因): 39%组合不达标
4. **scoring权重**(设计缺陷): Pinbar bonus=0被完全忽略
5. **正确架构**: CTX→OB作为OB_Bull的上下文标签(ctx_count)，不作为独立交易
