# V27 审计方法论 + 性能优化

## 7-Point Audit Framework

每次修改SMC核心代码后，必须运行全量审计脚本检查7项：

```python
# 1. Anchor 检查
assert ob.anchor_event_idx is not None     # OB必须绑定BOS/CHOCH/MSS
assert bpr.fvg1 and bpr.fvg2               # BPR必须来自opposing FVG overlap
assert bpr.fvg1.direction != bpr.fvg2.direction  # 方向必须相反

# 2. 时间顺序
assert entry_idx > signal_idx
assert zone_idx <= entry_idx
assert retrace_idx > signal_idx
assert conf_idx >= retrace_idx

# 3. 未来函数
assert swing.confirm_idx <= event_idx     # swing右侧确认后才能用
assert impulse_end_idx <= event_idx       # OTE不上扫未来bar

# 4. MSS sweep前置
assert mss.has_sweep_precursor            # MSS必须在20bar内有sweep

# 5. Causality
assert entry_idx > signal_idx             # 入场在信号之后

# 6. 图表同步
# trade数据必须能在chart markers中找到对应event

# 7. 选股同步
# pick.setup_id必须存在，pick.state不能是invalidated
```

## 审计脚本模板

审计脚本应根据V27全量数据运行，检查每笔trade的字段完整性：

```
审计项          通过条件
anchor缺失       = 0
未来函数违规     = 0
时间顺序违规     = 0
trade-chart不匹配 = 0
pick-setup不匹配  = 0
```

## BPR性能优化

**问题**: bpr_signals() 使用 O(n²) 全量比较，199个FVG/只 × 4905只 = 死慢

**修复**: 添加100-bar时间窗口
```python
nearby_bears = [brf for brf in bear_fvgs if abs(brf['index'] - bf_idx) <= max_gap]
```
效果：10只股票从>2分钟降到0.8s，全量4905只从>60分钟降到4.4分钟。

## Python 陷阱：扫描器静默失败

**陷阱1**: `except Exception: pass` — 全量扫描时吞掉所有异常
- 症状: scanner报告 "processed: 6 stocks" 但期望4905只
- 根因: 前6只正常，第7只抛NameError → pass → 循环继续但不计数 → 无限循环
- 修复: 至少前5个异常打印traceback
```python
except Exception as e:
    if processed < 5:
        print(f"  ERROR [{fpath.name}]: {e}", flush=True)
```

**陷阱2**: `processed % 500 == 0` — 首次迭代就打印
- 症状: scanner输出刷屏 "0/4905 stocks (12.5s)"
- 根因: `0 % 500 == 0` 为 True
- 修复: `if processed > 0 and processed % 500 == 0`

**陷阱3**: Python输出缓冲 — 后台进程看不到进度
- 修复: `python3 -u script.py` 或 `print(..., flush=True)`

## zone_idx > entry_idx 保护

setup builder中必须检查zone不能在未来:
```python
# Zone must exist at or before entry (no future zone usage)
if zone_idx > entry_idx:
    continue
```
V27 audit发现279笔zone_idx>entry_idx(0.6%), 全部来自BPR proximity匹配误配。

## 前端缓存架构

**问题**: 每HTTP请求都 json.loads() 61MB v27_trades.json

**修复**: 三层缓存
```python
_TRADES_CACHE = None      # 全量dicts
_TRADES_LITE_CACHE = None  # 去除嵌套zone/struct_event的轻量版
_PICKS_CACHE = None

def _refresh_cache():
    # 仅在文件mtime变化时重新加载
    # 构建lite版: 展开zone.type/zone_low/zone_high/struct_event.type到顶层
    # 去除原始zone和struct_event大dict
```

效果：
- Dashboard: 2.3s → 0.30s (7.7x)
- K-line API: 2.1s → 0.06s (35x)
- Memory: ~1.2GB (61MB JSON × Python dict overhead)
