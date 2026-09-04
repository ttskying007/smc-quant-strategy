# Frontend Python Pitfalls

## f-string 中不能 slice `.items()` ⚠️
```python
# ❌ TypeError: 'dict_items' object is not subscriptable
ver_rows += f'... {v.get("exit",{}).items()[:3]} ...'

# ✅ 预计算
exit_items = list(v.get('exit',{}).items())[:3]
exit_str = ','.join(f'{k}({c})' for k,c in exit_items)
ver_rows += f'... {exit_str} ...'
```

## 符号格式不匹配 (crossref) ⚠️
- 回测数据: `000001.SZ` (点分隔)
- 扫描数据: `000001_SZ` (下划线)  
- 交叉引用时必须: `t['symbol'].replace('.','_')`

## replace_all 副作用 ⚠️
对含子串匹配的文本执行 replace_all 会误伤:
- `SMC V16` → `SMC V16.2` 也会把 `SMC V16.2` → `SMC V16.2.2`
- 先用搜索确认匹配次数, 对重叠字符串禁用 replace_all

## __pycache__ 缓存陷阱 ⚠️
修改Python文件后必须清除缓存:
```bash
find /root/.hermes/scripts/__pycache__ -delete 2>/dev/null
```
否则进程可能加载旧 `.pyc`, 即使源文件已修复也报错。

## 启动打印中引用已重命名变量
`__main__` 打印段引用旧变量名(如`V15_PICKS`) → NameError崩溃。动态引用最新变量。
