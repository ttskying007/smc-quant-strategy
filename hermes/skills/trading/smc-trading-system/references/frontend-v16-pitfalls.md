# Frontend V16 Pitfalls — 2026-05-15 Session

## 1. __pycache__ 缓存陷阱 ⚠️⚠️⚠️ (2026-05-15 导致3次前端崩溃)
修改Python文件后, 进程可能加载旧的 `.pyc` 缓存, 即使源文件已修复。
**症状**: 文件中有 `from collections import Counter`, 但运行时仍报 `NameError: name 'Counter' is not defined`。
**根因**: `__pycache__/smc_unified.cpython-*.pyc` 保存了旧版本的字节码, HTTP server进程未重载。
**修复**: 每次重启前端前必须清除:
```bash
find /root/.hermes/scripts/__pycache__ -name "smc_unified*" -delete 2>/dev/null
```
或更彻底:
```bash
find /root/.hermes/scripts/__pycache__ -delete 2>/dev/null
```
**确认**: 重启后验证 `curl http://localhost:8890/backtest` 返回200非000。

## 2. replace_all 双重替换陷阱 (新增)
对 `SMC V16` → `SMC V16.2` 执行 replace_all 时, 已有 `SMC V16.2` 也会被匹配替换成 `SMC V16.2.2`。
**解决方案**: 先用搜索确认匹配次数, 对可能重叠的字符串分步替换:
1. 先将所有 `SMC V16.2` 替换为临时占位符
2. 再将所有 `SMC V16` 替换为 `SMC V16.2`
3. 或直接用 grep 确认只匹配目标行后使用非 replace_all 的 patch

## 2. 变量重命名后残留引用
`V15_PICKS` 被移除后 `__main__` 启动打印仍引用 → NameError崩溃。
**解决方案**: `__main__` 打印段直接引用最新变量(MONITOR), 不使用可能过时的变量名。

## 3. 选股页动态引擎统计
不再硬编码 V13/V12 引擎名, 改用遍历picks动态统计:
```python
eng_stats = {}
for p in picks:
    eng = p.get('engine', 'Other')
    eng_stats[eng] = eng_stats.get(eng, 0) + 1
eng_desc = ' | '.join(f'{eng}:{cnt}只' for eng, cnt in sorted(...))
```

## 4. K-line版本选择器
Version selector 选项列表需与 V16_*_TRADES 数据加载保持同步。
`trade_map` 字典需在API端点处同步更新。

## 5. 前端崩溃恢复标准流程
```bash
# 1. 清除pycache (必须, 否则加载旧.pyc)
find /root/.hermes/scripts/__pycache__ -delete 2>/dev/null
# 2. 验证导入无SyntaxError
cd /root/.hermes/scripts && python3 -c "from smc_unified import build_dashboard; print(build_dashboard()[:100])"
# 3. 如果导入OK则启动
pkill -f "smc_unified.py"; sleep 1; cd /root/.hermes/scripts && python3 -u smc_unified.py 2>&1 &
```
