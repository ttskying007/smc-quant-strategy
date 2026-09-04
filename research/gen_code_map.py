# -*- coding: utf-8 -*-
"""交接文档辅助：提取 research + hermes/scripts 全部 Python 文件的功能与函数清单（只读）
输出: handover/code_map.json + handover/functions_*.md
"""
import ast, json, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOTS = [r"E:\test\smc_project\research", r"E:\test\smc_project\hermes\scripts"]
OUT = r"E:\test\smc_project\research\handover"
SKIP_DIRS = {"__pycache__", "crawl_data", "node_modules", ".tmpdir", "kline_cache",
             "smc_audit", "smc_opt_", "skills", "downloads"}

def extract(path):
    """返回 {funcs: [...], classes: [...]}"""
    try:
        src = open(path, encoding='utf-8', errors='replace').read()
        tree = ast.parse(src)
    except Exception:
        return None
    funcs, classes = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name != '__init__':
            doc = ast.get_docstring(node) or ''
            args = [a.arg for a in node.args.args]
            funcs.append({"name": node.name, "args": args[:6],
                          "doc": doc.split('\n')[0][:90] if doc else ''})
        elif isinstance(node, ast.ClassDef):
            classes.append({"name": node.name})
    return {"funcs": funcs, "classes": classes}

code_map = {}
total_files = 0
for root in ROOTS:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('smc_opt_')]
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, r"E:\test\smc_project")
            info = extract(full)
            if info is None:
                continue
            total_files += 1
            code_map[rel] = info

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "code_map.json"), "w", encoding="utf-8") as f:
    json.dump({"total_files": total_files, "files": code_map}, f, ensure_ascii=False, indent=0)

# 生成函数清单 md（按目录分文件）
lines = ["# 代码函数地图（自动提取）", "", f"- 覆盖 Python 文件: {total_files}", ""]
for rel in sorted(code_map.keys()):
    info = code_map[rel]
    lines.append(f"## {rel}")
    if info["classes"]:
        lines.append("- 类: " + ", ".join(c["name"] for c in info["classes"]))
    if info["funcs"]:
        for fn in info["funcs"]:
            arg_s = ', '.join(fn["args"])
            lines.append(f"- `{fn['name']}({arg_s})` — {fn['doc']}")
    lines.append("")

with open(os.path.join(OUT, "code_map_functions.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"完成: {total_files} 个 py 文件 -> code_map.json / code_map_functions.md")
