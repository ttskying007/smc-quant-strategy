#!/usr/bin/env python3
"""技能库索引构建器"""

import json
from pathlib import Path
from collections import defaultdict

hermes_dir = Path("/root/.hermes")
skills_dir = hermes_dir / "skills"
lib_file = skills_dir / "evolution_library.json"
index_file = skills_dir / "skill_index.json"

if not lib_file.exists():
    print("✗ 技能库不存在")
    exit(1)

with open(lib_file) as f:
    data = json.load(f)

skills = data["skills"]

# 构建索引
index = {
    "version": "1.0",
    "built_at": __import__("datetime").datetime.now().isoformat(),
    "total_skills": len(skills),
    "by_type": defaultdict(list),
    "by_language": defaultdict(list),
    "by_popularity": [],
    "by_relevance": [],
    "keywords": set()
}

for skill in skills:
    # 按类型
    for t in skill.get("all_types", []):
        index["by_type"][t].append(skill["name"])
    
    # 按语言
    lang = skill.get("language", "Unknown")
    index["by_language"][lang].append(skill["name"])
    
    # 按流行度
    index["by_popularity"].append({
        "name": skill["name"],
        "popularity": skill.get("popularity", 0)
    })
    
    # 按相关度
    index["by_relevance"].append({
        "name": skill["name"],
        "relevance": skill.get("relevance", 0)
    })
    
    # 关键词
    desc = skill.get("description", "").lower()
    words = set(desc.split())
    index["keywords"].update(words)

# 排序
index["by_popularity"].sort(key=lambda x: x["popularity"], reverse=True)
index["by_relevance"].sort(key=lambda x: x["relevance"], reverse=True)

# 转换集合为列表
index["keywords"] = sorted(list(index["keywords"]))

# 转换defaultdict
index["by_type"] = dict(index["by_type"])
index["by_language"] = dict(index["by_language"])

# 保存
with open(index_file, "w") as f:
    json.dump(index, f, indent=2)

print(f"✓ 索引构建完成")
print(f"  • 总技能: {index['total_skills']}")
print(f"  ✓ 类型数: {len(index['by_type'])}")
print(f"  ✓ 语言数: {len(index['by_language'])}")
print(f"  ✓ 关键词: {len(index['keywords'])}")
