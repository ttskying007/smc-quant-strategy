# read_file 截断陷阱

## 症状

使用 `read_file` 不带 `limit` 参数读取大文件，然后 `write_file` 写回时，文件被截断到默认500行。

## 实例

```python
# 错误: 默认 limit=500
content = read_file('/root/.hermes/scripts/smc_unified.py')
text = content['content']  # 只含前500行，文件原1421行

# 修改 text...
write_file('/root/.hermes/scripts/smc_unified.py', text)
# 文件从1421行变为500行 — 后921行全部丢失!
```

## 正确做法

```python
# 方法1: 指定 limit 参数
content = read_file('/path/to/file.py', limit=5000)

# 方法2: 用 execute_code 的 hermes_tools
from hermes_tools import read_file, write_file
full = read_file('/path/to/file.py')
# full['total_lines'] 确认总行数
# full['content'] 包含完整内容

# 方法3: 修改前备份
terminal('cp file.py file.py.bak')
```

## 恢复

如果已截断:
1. 检查是否有 `.pyc` 缓存或 git 历史
2. 检查进程是否仍在运行旧代码
3. 从对话历史中的 `read_file` 输出重建
