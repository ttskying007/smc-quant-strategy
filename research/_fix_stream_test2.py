# -*- coding: utf-8 -*-
"""临时: 修正 tests_audit_stream_vs_v697.py —— 尾部补 bar + 日期归一化. """
import ast
import re

p = r"E:\test\smc_project\hermes\scripts\tests_audit_stream_vs_v697.py"
src = open(p, encoding="utf-8").read()

# 1. 日期归一化: 比较前统一转 8 位(去连字符)
norm = '''def _norm(ev):
    """日期归一化为 8 位(去连字符), 便于引擎(20240106)与 V697(2024-01-06)对比."""
    out = set()
    for s in ev:
        out.add(tuple("".join(c for c in d if c.isdigit())[:8] for d in s))
    return out


def engine_events(bars, symbol="T"):'''
src = src.replace("def engine_events(bars, symbol=\"T\"):", norm, 1)

# 2. 所有比较用 _norm
src = src.replace("ok(\"单事件: 引擎与 V697 一致\", ee == ve, (ee, ve))",
                  "ok(\"单事件: 引擎与 V697 一致\", _norm(ee) == _norm(ve), (ee, ve))")
src = src.replace("ok(\"消费场景: 引擎与 V697 一致\", ee2 == ve2, (ee2, ve2))",
                  "ok(\"消费场景: 引擎与 V697 一致\", _norm(ee2) == _norm(ve2), (ee2, ve2))")
src = src.replace("ok(\"多事件: 引擎与 V697 一致\", ee3 == ve3, (ee3, ve3))",
                  "ok(\"多事件: 引擎与 V697 一致\", _norm(ee3) == _norm(ve3), (ee3, ve3))")
src = src.replace("ok(\"无事件: 引擎与 V697 一致\", ee4 == ve4 and ee4 == set(), (ee4, ve4))",
                  "ok(\"无事件: 引擎与 V697 一致\", _norm(ee4) == _norm(ve4) and _norm(ee4) == set(), (ee4, ve4))")

# 3. 每个场景尾部追加 4 根无事件 bar(response 不在最后 2 根)
#    找到每个 make_bars([...]) 列表的结尾 "])" 并在其前插入尾部 bar
tail = ('    ("2024-03-01", 100, 101, 99, 100, 100),\n'
        '    ("2024-03-04", 100, 101, 99, 100, 100),\n'
        '    ("2024-03-05", 100, 101, 99, 100, 100),\n'
        '    ("2024-03-06", 100, 101, 99, 100, 100),\n')

# 场景1 尾部: 2024-01-13 之后
src = src.replace('    ("2024-01-13", 100, 102, 99, 102, 300),\n])',
                  '    ("2024-01-13", 100, 102, 99, 102, 300),\n' + tail + '])', 1)
# 场景2 尾部: 2024-01-14 之后
src = src.replace('    ("2024-01-14", 100, 102, 99, 102, 300),\n])',
                  '    ("2024-01-14", 100, 102, 99, 102, 300),\n' + tail + '])', 1)
# 场景3 尾部: 2024-02-15 之后
src = src.replace('    ("2024-02-15", 105, 107, 104, 107, 300),\n])',
                  '    ("2024-02-15", 105, 107, 104, 107, 300),\n' + tail + '])', 1)
# 场景4 尾部: 2024-01-13(无事件) 之后
src = src.replace('    ("2024-01-13", 100, 101, 99, 99, 300),   # response close 99 < sweep high 100\n])',
                  '    ("2024-01-13", 100, 101, 99, 99, 300),   # response close 99 < sweep high 100\n' + tail + '])', 1)

open(p, "w", encoding="utf-8").write(src)
ast.parse(src)
print("FIXED + SYNTAX OK")