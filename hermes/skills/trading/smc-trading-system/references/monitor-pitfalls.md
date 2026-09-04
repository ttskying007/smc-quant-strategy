# SMC前端监控常见问题与修复

## 1. active_positions.json膨胀(>10K条目)

**症状**: 前端显示持仓13,000+条，大量重复符号

**根因**: 
- `monitor_check.py`的`init_positions()`将LD_picks_v6.json中全部picks写入
- 每次运行追加+合并 → 条目数爆炸
- 过滤条件`status != 'closed'`包含了所有'open'+'cancelled'状态

**修复**:
1. 手动重建: 去重+质量过滤+只取唯一symbol
2. 锁定文件: `chmod 444 active_positions.json` 防止覆盖
3. 前端重启: kill旧进程 → 启动新进程

## 2. 持仓数量与预期不符

**症状**: 重建后前端仍显示旧数据

**根因**: smc_unified.py中`MONITOR_POS`路径与实际文件路径不一致，或文件被其他进程覆盖

**诊断**:
```bash
python3 -c "import json; d=json.load(open('/root/.hermes/smc_opt_v21/live_monitor_v6/active_positions.json')); print(len(d))"
curl -s http://127.0.0.1:8890/monitor | grep "当前持仓"
```

## 3. 链接不显示(无`<a href>`)

**症状**: 股票代码显示为纯文本，无法点击跳转K线

**根因**: 
- smc_unified.py中`build_monitor_page()`是inline函数(非import monitor_page.py)
- 修改独立的`monitor_page.py`文件无效 — Python不会重新加载
- 旧版.format()字符串中缺少anchor tag

**修复**:
1. 直接编辑smc_unified.py中的inline函数
2. 使用f-string生成含`<a href="/v21?s={sym_dot}">`的HTML
3. sym_dot需要点格式: `_SH→.SH, _SZ→.SZ, _BJ→.BJ`
4. 删除.pyc缓存: `find /root/.hermes/scripts/__pycache__ -delete`
5. 重启前端

## 4. Module Cache陷阱 (CRITICAL)

**最重要的教训**: 
- `smc_unified.py`约1100行，`build_monitor_page()`定义在第817行
- 不存在独立的monitor_page模块 — 代码全部inline
- 修改任何"独立文件"都不会生效
- Python `.pyc`缓存会使旧代码残留
- **每次修改后必须**: 删除__pycache__ + kill旧进程 + 重启

## 5. 信号线满屏重叠

**症状**: Sweep/CHOCH/BOS/MSS/EQL线横跨整屏，相互重叠

**修复** (V7.4):
- 从`yAxis`单点格式 → `coords: [[date, price], [date+ext, price]]`双点格式
- extension: daily=20bar, 60min=30bar, weekly=10bar
- JS渲染: 遍历visibleLines，检测coords字段，构建双点markLine
