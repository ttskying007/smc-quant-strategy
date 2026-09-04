# V20→V21→V22 信号精度修复完整历程

## V20 初始状态
- 17类信号 (FVG/OB/CHOCH/BOS/Sweep/MSS/EQL/BPR/Pinbar/PO3/OTE/LV/RB)
- Swing检测: LuxAlgo leg(20) 状态机 ✓
- 问题: 信号大量重复/位置错误

## V21 修复 (2026-05-15, session 1)

### BOS/CHOCH
- **问题**: 微小穿刺误触发, 3bar内重复触发多个信号
- **根因**: `prev_close <= sh.price and close > sh.price` 条件太松
- **修复**: 需要 ATR×0.3 穿透确认 + 同方向3bar去重
- **验证**: 茅台 BOS/CHOCH 13→5 (消去62%假信号)

### Sweep
- **问题**: 同事件重复4-6次, 扫旧摆动点非最近
- **根因**: 每bar独立检查所有60bar内摆动点, 无cooldown
- **修复**: 3bar cooldown + 只扫25bar内最近摆动点 + ATR×0.08穿刺
- **验证**: 301137 Sweep 12→2 (消去83%假信号)

### MSS
- **问题**: 与CHOCH重复, 无区分度
- **修复**: ATR×0.5强穿透 + 8bar cooldown (比CHOCH更稀有)
- **验证**: 301137 MSS 9→3 (消去67%)

### EQL
- **问题**: 类型名 `EQL`/`EQH` 不匹配 SIG_STYLE (`EQL_High`/`EQL_Low`)
- **修复**: 修正类型名 + 每pivot最近匹配 + 至少5bar间距

### Swing检测
- **问题**: V21简化版 `range(leg_size, n-leg_size)` 遗漏大量摆动点
- **根因**: 静态窗口 vs V20 LuxAlgo leg() 状态机
- **修复**: 恢复V20完整LuxAlgo leg()实现
- **验证**: 301137 swings 8→17 (恢复所有遗漏摆动点)

## V22 修复 (2026-05-15, session 2)

### OB检测 — 关键根因级Bug
- **问题**: OB位置错误 — 取搜索范围内最高点, 不是最接近break的OB
- **根因**: LuxAlgo OB从 sw_bar→break_bar 向前搜索取max_high
  - 例: BOS_Bear break@79, sw_bar@7 → 范围[7,79]取H@1606 (bar20) → OB在bar20
  - 正确: 从break bar向后搜索最近的reverse candle → OB应更接近break
- **修复**: 从break bar向后搜索 `range(break_bar-1, max(0,break_bar-30), -1)`
  - 取第一个反向K线, 非最高K线

### 缺失信号实现
| 信号 | Pine参考 | V22实现 |
|------|---------|---------|
| IFVG | FVG被回补后反转成反向区 | `detect_ifvg()` — 60bar内C穿越FVG区 |
| Breaker Block | 失败OB变反向支撑/阻力 | `detect_breaker()` — 30bar内C穿越OB区 |
| LV | 价格跳空无交易区 | `detect_liquidity_void()` — b1.L > b0.H+ATR*0.2 |
| RB | 价格拒绝摆动点 | `detect_rejection()` — 接近swing后反转>ATR*0.5 |
| OTE | Fib 61.8%-79% | `detect_ote()` — 相邻swing leg Fib回撤 |
| PO3 | Acc/Manip/Dist | `detect_po3()` — 5bar窄幅→突破→分布(限top-5) |

### SMC2026 OB — 决策
- **启用**: 从swing bar向后搜索(此方向正确)
- **渲染**: V22前端全部显示 (16类信号)
- **交易**: V12引擎仅用高置信OB (confidence≥0.7, 即仅LuxAlgo OB)

## V22验证数据 (600519.SH)

| 信号 | V20 | V21 | V22 | 最终状态 |
|------|-----|-----|-----|---------|
| BOS_Bear | 3 | 2 | 2 | ✅ 固定 |
| CHOCH_Bear | 6 | 4 | 4 | ✅ 固定 |
| MSS_Bear | 5 | 2 | 2 | ✅ 固定 |
| Sweep_SSL | 6 | 0 | 3 | ✅ 参数调优 |
| Sweep_BSL | 3 | 0 | 1 | ✅ 参数调优 |
| EQL_Low | 0 | 5 | 5 | ✅ 类型名修复 |
| IFVG | 0 | 0 | 33 | 🆕 实现 |
| Breaker | 0 | 0 | 22 | 🆕 实现 |
| LV | 0 | 0 | 5 | 🆕 实现 |
| RB | 0 | 0 | 2 | 🆕 实现 |
| OTE | 0 | 0 | 17 | 🆕 实现 |
| PO3 | 0 | 0 | 5 | 🆕 top-5 |
| FVG | 20 | 20 | 40 | 🆕 FVG放宽参数 |
| Pinbar | 26 | 26 | 26 | 不变 |
| OB_Bull | 7 | 1 | 10 | 🆕 SMC2026启用 |
| OB_Bear | 5 | 6 | 15 | 🆕 SMC2026启用 |

## 关键决策
1. **SMC2026 OB默认启用但仅渲染** — 不用于交易(confidence低)
2. **OB LuxAlgo backward search** — 从break向后找最近reverse candle (Pine标准)
3. **PO3限top-5** — 否则每只股票300+ PO3信号淹没其他
4. **Sweep参数**: ATR×0.05 + 3bar cooldown + 30bar窗口 (平衡检测vs过度)
