# V19 Frontend Debugging — ECharts & File Safety (2026-05-13)

## ECharts markArea 数据格式

**错误格式**（不渲染）：
```javascript
markArea: {data: [{data: [{xAxis: ..., yAxis: ...}, {xAxis: ..., yAxis: ...}]}]}
```

**正确格式**：
```javascript
markArea: {data: [[{xAxis: '2025-03-07', yAxis: 1474}, {xAxis: '2025-03-20', yAxis: 1503}], ...]}
```

ECharts 5 markArea 需要 `[[{...},{...}], ...]` 数组对格式。`{data: [...]}` 包裹层会导致整个 markArea 静默失败（无渲染，无报错）。

## ECharts dark 主题

`echarts.init(dom, 'dark')` 在 ECharts 5 中需要单独加载 dark 主题文件。不加载时静默失败或使用默认主题。
修复：使用 `echarts.init(dom)` 并在 chart option 中手动设置 `backgroundColor: '#0d1117'`。

## read_file 截断陷阱

`read_file(path)` 不带 offset/limit 时默认只读 500 行。配合 `write_file` 会完全覆盖文件，导致 500 行后的代码永久丢失。

**灾难案例**：
```python
content = read_file('/path/to/1421-line-file.py')  # 只读了500行！
write_file('/path/to/1421-line-file.py', content + appendix)  # 覆盖了500-1421行！
```

**安全做法**：
1. 大文件修改前先 `cp file file.bak`
2. 使用 `read_file(path, limit=N)` 明确指定行数
3. 或用 `execute_code` 中的 `read_file` 获取完整内容
4. 修改后用 `wc -l` 验证行数
