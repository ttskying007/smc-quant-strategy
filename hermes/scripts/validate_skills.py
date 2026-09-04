#!/usr/bin/env python3
"""技能库验证器"""

import json
from pathlib import Path

hermes_dir = Path("/root/.hermes")
lib_file = hermes_dir / "skills" / "evolution_library.json"

if not lib_file.exists():
    print("✗ 技能库不存在")
    exit(1)

with open(lib_file) as f:
    data = json.load(f)

skills = data["skills"]

print(f"✅ 技能库验证报告")
print("=" * 50)

# 统计
by_type = {}
by_lang = {}
high_pop = []
high_rel = []

for s in skills:
    # 类型
    for t in s.get("all_types", []):
        by_type[t] = by_type.get(t, 0) + 1
    
    # 语言
    lang = s.get("language", "Unknown")
    by_lang[lang] = by_lang.get(lang, 0) + 1
    
    # 高流行
    if s.get("popularity", 0) > 50:
        high_pop.append(s)
    
    # 高相关度
    if s.get("relevance", 0) > 5:
        high_rel.append(s)

print(f"
📊 基础统计:")
print(f"  总数: {len(skills)}")
print(f"  类型: {len(by_type)}")
print(f"  语言: {len(by_lang)}")

print(f"
📋 类型分布:")
for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
    print(f"  • {t}: {c}")

print(f"
🌐 语言分布:")
for l, c in sorted(by_lang.items(), key=lambda x: -x[1]):
    print(f"  • {l}: {c}")

print(f"
⭐ 高流行技能 ({len(high_pop)}):")
for s in sorted(high_pop, key=lambda x: -x.get("popularity", 0))[:5]:
    print(f"  • {s['name']} ({s.get('popularity', 0)} ⭐)")

print(f"
🔍 高相关度 ({len(high_rel)}):")
for s in sorted(high_rel, key=lambda x: -x.get("relevance", 0))[:5]:
    print(f"  • {s['name']} (rel: {s.get('relevance', 0)})")

print("
" + "=" * 50)
print("✅ 验证完成")
