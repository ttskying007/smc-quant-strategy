# 选股交叉验证方法论

## 目的
将当前扫描选股与历史回测(所有版本V12/V13/V15/V16/V16.1/V16.2)交叉对比,按质量评级排序。

## 评级标准
| 评级 | 条件 | 含义 |
|------|------|------|
| A | ≥2笔交易 且 WR≥80% | 已验证优质 |
| B | ≥2笔交易 且 WR≥60% | 有回测记录,一般 |
| C | 1笔交易 | 样本太少 |
| D | 0笔交易 | 无回测记录 |

## 实现

### 1. 生成交叉引用数据
```bash
cd /root/.hermes/scripts && python3 /tmp/crossref_picks.py
```
产出: `/root/.hermes/smc_opt_v16/pick_crossref.json`

### 2. 关键陷阱: 符号格式不匹配 ⚠️
- 回测数据: `000001.SZ` (点分隔)
- 扫描数据: `000001_SZ` (下划线)
- **必须先normalize**: `t['symbol'].replace('.','_')`

### 3. 前端显示
`/compare` 页面展示:
- 版本演进表(WR排序)
- 选股交叉验证表: # | 代码 | 评级 | 引擎 | 序列 | 回撤 | 交易数 | WR | 均盈 | 累计PnL | 最佳版本 | 历史版本 | 近期表现
- 按 `quality(A>B>C>D) → WR desc → trades desc → score desc` 排序
- 评级颜色: A=绿 B=黄 C=蓝 D=灰

## 数据流
```
当前选股(92只) → 遍历所有回测版本 → 按symbol聚合 → 计算WR/PnL → A/B/C/D评级 → 排序 → JSON → /compare页
```

## 实际结果(V16.2, 2026-05-16)
- A级(已验证优质): 44只 (100% WR across multiple versions)
- B级(有记录一般): 14只
- C级(样本少): 29只
- D级(无记录): 5只

Top stock: 002470_SZ — 7 trades across V12-V16.2, 100% WR, avg=+5.67%, best=V13(+10.8%)
