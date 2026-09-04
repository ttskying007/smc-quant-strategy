#!/root/scraper_env/bin/python3
"""
技能发现管线 v1.0 — 从每日爬虫数据中自动发现、评分、安装高价值工具为本地skill
流程: 读取crawl → 过滤(GitHub+HN) → 去重(三层) → 五维评分 → 安装 → 验证 → 报告
"""
import json, re, hashlib, sys, os, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

# Unbuffered output for background runs
from math import log10

HERMES_DIR = Path(__file__).parent.parent
CRAWL_DIR = HERMES_DIR / "crawl_data"
SKILLS_DIR = HERMES_DIR / "skills"
DB_PATH = SKILLS_DIR / ".processed_urls.json"
LOG_DIR = HERMES_DIR / "logs" / "skill_install"
LOG_DIR.mkdir(parents=True, exist_ok=True)

THRESHOLD_AUTO = 0.70        # >= 自动安装
THRESHOLD_REVIEW = 0.50     # 0.50-0.70 标记待审
MAX_INSTALLS_PER_RUN = 5    # 每次最多安装5个，防止超时
# ============================================================
# ============================================================
# 1. 数据加载
# ============================================================

def load_latest_crawl():
    """加载最新爬虫结果"""
    files = sorted(CRAWL_DIR.glob("multi_source_*.json"))
    if not files:
        print("ERROR: No crawl data found")
        sys.exit(1)
    latest = files[-1]
    print(f"Loading: {latest.name}")
    return json.loads(latest.read_text()), latest.stem

def load_dedup_db():
    """加载去重数据库"""
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text())
    return {"urls": {}, "skill_names": [], "skill_github_repos": []}

def save_dedup_db(db):
    """保存去重数据库"""
    DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2))

# ============================================================
# 2. 过滤 — 只取有价值的来源
# ============================================================

VALUABLE_SOURCES = {"github", "hackernews", "hn_algolia"}

def filter_candidates(crawl_data):
    """从爬虫结果中过滤出候选"""
    results = crawl_data.get("results", [])
    candidates = []
    for item in results:
        src = item.get("source", "")
        if src in VALUABLE_SOURCES:
            candidates.append(item)
    print(f"Filtered: {len(results)} → {len(candidates)} candidates (from {VALUABLE_SOURCES})")
    return candidates

# ============================================================
# 3. 三层去重
# ============================================================

def url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()

def jaccard_similarity(s1, s2):
    """集合Jaccard相似度"""
    a, b = set(s1.lower().split()), set(s2.lower().split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def normalize_repo_name(name):
    """标准化GitHub仓库名"""
    name = name.lower().strip('/')
    name = re.sub(r'\.git$', '', name)
    name = re.sub(r'^https?://github\.com/', '', name)
    return name

def check_duplicate(item, db):
    """三层去重,返回(是否重复, 原因)
    L1: URL已在DB中且已被处理过(installed/skipped/failed)
    L2: 名称 vs 已有skill/已安装repo
    L3: 标题 vs 已处理标题
    """
    url = item.get("url", "")
    
    # L1: URL去重 — 只有已经处理过的才算重复
    h = url_hash(url)
    url_entry = db.get("urls", {}).get(h, {})
    if url_entry.get("action") in ("installed", "skipped", "failed"):
        return True, f"processed {url_entry['action']} on {url_entry.get('last_seen', '?')}"
    
    # L2: 名称模糊去重 (对GitHub)
    if item.get("source") == "github":
        name = item.get("name", "")
        norm = normalize_repo_name(name)
        for existing in db.get("skill_github_repos", []):
            if jaccard_similarity(norm, existing) > 0.6:
                return True, f"name-similar to existing: {existing}"
        for sn in db.get("skill_names", []):
            # GitHub repo名 vs skill名
            repo_keyword = norm.split('/')[-1] if '/' in norm else norm
            if jaccard_similarity(repo_keyword, sn) > 0.6:
                return True, f"name-similar to skill: {sn}"
    
    # L3: 标题去重
    title = item.get("title") or item.get("name", "") or item.get("text", "")
    titles_db = db.get("titles", set())
    for existing_title in titles_db:
        if jaccard_similarity(title, existing_title) > 0.65:
            return True, f"title-similar to: {existing_title[:50]}"
    
    return False, ""

# ============================================================
# 4. 五维评分引擎
# ============================================================

def score_source_credibility(item):
    """维度1: 源可信度"""
    src = item.get("source", "")
    scores = {"github": 1.0, "hn_algolia": 0.8, "hackernews": 0.7}
    return scores.get(src, 0.0)

def score_community(item):
    """维度2: 社区验证 — stars/points"""
    src = item.get("source", "")
    
    # GitHub stars
    if src == "github":
        stars = item.get("stars", 0) or 0
        if stars >= 100000:
            return 1.0
        if stars >= 1000:
            return 0.6 + (log10(stars) - 3) * 0.2  # 1000→0.6, 10000→0.8
        if stars >= 100:
            return 0.4 + (log10(stars) - 2) * 0.2   # 100→0.4, 1000→0.6
        if stars >= 10:
            return 0.2 + (log10(stars) - 1) * 0.2   # 10→0.2, 100→0.4
        return max(stars / 50, 0.05)  # 0-10 stars → 0-0.2
    
    # HN points
    if src in ("hackernews", "hn_algolia"):
        points = item.get("points", 0) or item.get("engagement", 0) or 0
        return min(points / 100, 1.0)
    
    return 0.0

def score_actionability(item):
    """维度3: 可操作性 — 能装成skill吗?"""
    src = item.get("source", "")
    title = item.get("title", "") or item.get("text", "")
    
    # GitHub仓库: 直接可安装
    if src == "github":
        lang = item.get("language", "")
        if not lang:
            return 0.5  # 无语言信息,不确定
        if lang in ("Python", "JavaScript", "TypeScript", "Go", "Rust"):
            return 0.9
        return 0.7  # 其他语言也可用,但优先
    
    # HN: 检查是否描述工具
    title_lower = title.lower()
    
    # Show HN = 展示工具
    if "show hn" in title_lower:
        return 0.8
    
    # CLI/工具关键词
    tool_keywords = ["cli", "tool", "framework", "library", "sdk", "plugin", "app", "extension"]
    for kw in tool_keywords:
        if kw in title_lower:
            return 0.7
    
    # GitHub链接
    url = item.get("url", "")
    if "github.com" in url:
        return 0.7
    
    # 指南/教程
    guide_keywords = ["tutorial", "guide", "how to", "introduction"]
    for kw in guide_keywords:
        if kw in title_lower:
            return 0.3
    
    # Ask HN
    if "ask hn" in title_lower:
        return 0.1
    
    return 0.2  # 其余HN帖子

def score_novelty(item, db):
    """维度4: 新颖度"""
    url = item.get("url", "")
    h = url_hash(url)
    if h not in db.get("urls", {}):
        return 1.0
    count = db["urls"][h].get("count", 1)
    if count <= 2:
        return 0.7
    if count <= 5:
        return 0.4
    return 0.1

def score_relevance(item):
    """维度5: 主题相关性"""
    direction = item.get("direction", "")
    scores = {
        "skills": 1.0,
        "programming": 0.9,
        "management": 0.9,
        "general-ai": 0.8,
        "visualization": 0.7,
        "ai-video": 0.5,
        "best-models": 0.5,
        "china-stocks": 0.5,
        "ict-smc": 0.4,
        "free-api": 0.4,
        "fortune": 0.2,
    }
    return scores.get(direction, 0.3)

def compute_score(item, db):
    """综合五维评分"""
    s1 = score_source_credibility(item)
    s2 = score_community(item)
    s3 = score_actionability(item)
    s4 = score_novelty(item, db)
    s5 = score_relevance(item)
    
    total = s1 * 0.05 + s2 * 0.35 + s3 * 0.30 + s4 * 0.05 + s5 * 0.25
    
    return {
        "total": round(total, 3),
        "breakdown": {
            "source_credibility": round(s1, 2),
            "community": round(s2, 2),
            "actionability": round(s3, 2),
            "novelty": round(s4, 2),
            "relevance": round(s5, 2),
        }
    }

# ============================================================
# 5. 安装管线
# ============================================================

def extract_github_info(item):
    """从item中提取GitHub仓库信息"""
    src = item.get("source", "")
    url = item.get("url", "")
    
    # 直接是GitHub source
    if src == "github":
        name = item.get("name", "")
        desc = item.get("description", "")
        stars = item.get("stars", 0) or 0
        lang = item.get("language", "")
        return {
            "owner_repo": name,
            "url": url,
            "description": desc,
            "stars": stars,
            "language": lang,
        }
    
    # 从URL提取
    m = re.search(r'github\.com/([^/]+/[^/\s"\')\]\)#]+)', url or "")
    if m:
        name = m.group(1).rstrip('.').rstrip('/')
        return {
            "owner_repo": name,
            "url": f"https://github.com/{name}",
            "description": item.get("description", ""),
            "stars": item.get("stargazers_count") or item.get("engagement", 0) or 0,
            "language": item.get("language", ""),
        }
    
    return None

def install_from_github(gh_info, item, score_info):
    """从GitHub安装一个工具为skill"""
    owner_repo = gh_info["owner_repo"]
    safe_name = owner_repo.replace("/", "_").lower()
    skill_dir = SKILLS_DIR / safe_name
    
    print(f"\n  📦 Installing: {owner_repo} (score={score_info['total']})")
    
    # Step 1: git clone
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    
    clone_cmd = ["git", "clone", "--depth", "1", "--single-branch", gh_info["url"], str(skill_dir)]
    env = os.environ.copy()
    env["GIT_SSL_NO_VERIFY"] = "1"
    env["http_proxy"] = "http://127.0.0.1:7890"
    env["https_proxy"] = "http://127.0.0.1:7890"
    try:
        result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=60, env=env)
        if result.returncode != 0:
            print(f"    ❌ Clone failed: {result.stderr[:200]}")
            return False, f"clone: {result.stderr[:100]}"
        print(f"    ✓ Cloned to {skill_dir}")
    except subprocess.TimeoutExpired:
        print(f"    ❌ Clone timeout (60s)")
        return False, "clone timeout"
    except Exception as e:
        print(f"    ❌ Clone error: {e}")
        return False, str(e)
    
    # Step 2: 检查项目结构
    files = list(skill_dir.glob("*"))
    readme = skill_dir / "README.md"
    setup_py = skill_dir / "setup.py"
    pyproject = skill_dir / "pyproject.toml"
    package_json = skill_dir / "package.json"
    
    has_readme = readme.exists()
    is_python = setup_py.exists() or pyproject.exists()
    is_node = package_json.exists()
    has_code = any(f for f in files if f.suffix in ('.py', '.js', '.ts', '.go', '.rs'))
    
    is_cli = False
    if is_python and setup_py.exists():
        setup_text = setup_py.read_text(errors='ignore')[:2000]
        is_cli = 'entry_points' in setup_text or 'console_scripts' in setup_text
    
    # Step 3: pip install (Python only)
    install_ok = False
    if is_python:
        try:
            install_result = subprocess.run(
                ["/root/scraper_env/bin/pip", "install", "-e", str(skill_dir), "--break-system-packages"],
                capture_output=True, text=True, timeout=60
            )
            install_ok = install_result.returncode == 0
            if install_ok:
                print(f"    ✓ pip install OK")
            else:
                print(f"    ⚠ pip install failed: {install_result.stderr[:100]}")
        except Exception as e:
            print(f"    ⚠ pip install error: {e}")
    
    # Step 4: 生成 SKILL.md
    skill_md = generate_skill_md(gh_info, item, score_info, safe_name, skill_dir,
                                  has_readme, is_python, is_node, has_code, is_cli)
    skill_md_path = skill_dir / "SKILL.md"
    skill_md_path.write_text(skill_md)
    print(f"    ✓ SKILL.md generated ({len(skill_md)} chars)")
    
    # Step 5: 结构验证
    verification = verify_skill(skill_dir, safe_name, gh_info, is_python, install_ok)
    
    return True, verification

def generate_skill_md(gh_info, item, score_info, safe_name, skill_dir, has_readme, is_python, is_node, has_code, is_cli):
    """生成标准的SKILL.md"""
    title = item.get("title") or gh_info["description"] or gh_info["owner_repo"]
    desc = gh_info.get("description", "") or item.get("text", "")[:200] or title
    
    # 确定分类
    direction = item.get("direction", "general")
    category_map = {
        "skills": "automation",
        "programming": "engineering",
        "management": "automation",
        "general-ai": "mlops",
        "visualization": "data-science",
        "ai-video": "creative",
        "best-models": "mlops/models",
    }
    category = category_map.get(direction, "automation")
    
    triggers = []
    if is_cli:
        triggers.append(f"use {gh_info['owner_repo']}")
        triggers.append(f"run {gh_info['owner_repo'].split('/')[-1]}")
    if "agent" in desc.lower():
        triggers.append("build multi-agent")
        triggers.append("agent orchestration")
    if "skill" in desc.lower():
        triggers.append("install skills")
        triggers.append("skill discovery")
    
    md = f"""---
name: {safe_name}
description: {desc}
version: auto-discovered
category: {category}
auto_installed: true
installed_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
source: {gh_info['url']}
source_stars: {gh_info.get('stars', 0)}
source_language: {gh_info.get('language', '')}
score: {score_info['total']}
discovery_query: {item.get('query', '')}
---

# {title}

> Auto-discovered from crawl pipeline. Score: {score_info['total']}/1.0
> Source: [{gh_info['owner_repo']}]({gh_info['url']}) {'⭐ ' + str(gh_info.get('stars', 0)) if gh_info.get('stars') else ''}

## What it is

{desc}

## Installation Status

- **Cloned**: ✓
- **has_readme**: {'✓' if has_readme else '✗'}
- **is_python**: {'✓' if is_python else '✗'}
- **has_code**: {'✓' if has_code else '✗'}
- **is_cli**: {'✓' if is_cli else '✗'}

## Usage

The repository is available at `{skill_dir}`. 

"""
    if has_readme:
        md += "Refer to the [README.md](README.md) in the same directory for full usage instructions.\n"
    else:
        md += "No README found. Explore the code directly.\n"
    
    return md

def verify_skill(skill_dir, safe_name, gh_info, is_python, install_ok):
    """验证安装效果"""
    checks = []
    
    # 检查文件存在
    checks.append(("SKILL.md exists", (skill_dir / "SKILL.md").exists()))
    checks.append(("README exists", (skill_dir / "README.md").exists()))
    if is_python:
        has_py = bool(list(skill_dir.glob("**/*.py")))
        checks.append(("has .py files", has_py))
    checks.append(("has non-empty files", any(f.stat().st_size > 0 for f in skill_dir.glob("*") if f.is_file())))
    checks.append(("pip install OK", install_ok if is_python else "N/A"))
    
    passed = sum(1 for _, v in checks if v is True or v == "N/A")
    total = len(checks)
    
    status = "✓" if passed >= total - 1 else "⚠" if passed >= total * 0.6 else "✗"
    return {
        "status": status,
        "passed": passed,
        "total": total,
        "checks": checks
    }

# ============================================================
# 6. 主流程
# ============================================================

def main():
    print(f"\n{'='*60}")
    print(f"🔍 Skill Discovery Pipeline v1.0 — {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    # Load
    crawl_data, crawl_ts = load_latest_crawl()
    db = load_dedup_db()
    print(f"DB: {len(db['urls'])} URLs, {len(db.get('skill_names', []))} skills")
    
    # Filter
    candidates = filter_candidates(crawl_data)
    
    # Score & dedup
    scored = []
    duplicates = []
    
    for item in candidates:
        is_dup, reason = check_duplicate(item, db)
        if is_dup:
            duplicates.append({"item": item, "reason": reason})
            continue
        
        score = compute_score(item, db)
        scored.append({"item": item, "score": score})
    
    print(f"\nDedup: {len(duplicates)} duplicates removed, {len(scored)} unique")
    
    # Sort by score
    scored.sort(key=lambda x: x["score"]["total"], reverse=True)
    
    # Categorize
    auto_install = [s for s in scored if s["score"]["total"] >= THRESHOLD_AUTO]
    to_review = [s for s in scored if THRESHOLD_REVIEW <= s["score"]["total"] < THRESHOLD_AUTO]
    skipped = [s for s in scored if s["score"]["total"] < THRESHOLD_REVIEW]
    
    print(f"\nAuto-install (>= {THRESHOLD_AUTO}): {len(auto_install)}")
    print(f"To review ({THRESHOLD_REVIEW}-{THRESHOLD_AUTO}): {len(to_review)}")
    print(f"Skipped (< {THRESHOLD_REVIEW}): {len(skipped)}")
    
    # Install
    installed = []
    failed = []
    
    for s in auto_install:
        item = s["item"]
        score = s["score"]
        
        # Cap: 防止超时
        if len(installed) >= MAX_INSTALLS_PER_RUN:
            to_review.append(s)
            print(f"    ⏭ Capped at {MAX_INSTALLS_PER_RUN}, deferred {len(auto_install) - len(installed)} to review")
            break
        
        # Extract GitHub info
        gh_info = extract_github_info(item)
        if not gh_info:
            # Non-GitHub: 标记为待审
            to_review.append(s)
            continue
        
        success, result = install_from_github(gh_info, item, score)
        
        if success:
            installed.append({
                "name": gh_info["owner_repo"],
                "score": score["total"],
                "verification": result,
                "url": gh_info["url"],
                "direction": item.get("direction", ""),
            })
        else:
            failed.append({
                "name": gh_info["owner_repo"],
                "score": score["total"],
                "error": result,
                "url": gh_info["url"],
            })
    
    # Update DB with all processed URLs
    installed_urls = {inst["url"] for inst in installed}
    failed_urls = {f["url"] for f in failed}
    
    for s in scored:
        item = s["item"]
        url = item.get("url", "")
        if not url:
            continue
        h = url_hash(url)
        
        # Determine action
        if url in installed_urls:
            action = "installed"
        elif url in failed_urls:
            action = "failed"
        elif s["score"]["total"] >= THRESHOLD_AUTO:
            action = "skipped_no_github"  # 候选但非GitHub
        else:
            action = "skipped"
        
        if h in db["urls"]:
            db["urls"][h]["count"] += 1
            db["urls"][h]["last_seen"] = crawl_ts
            db["urls"][h]["action"] = action
        else:
            db["urls"][h] = {
                "url": url,
                "first_seen": crawl_ts,
                "last_seen": crawl_ts,
                "count": 1,
                "sources": [item.get("source", "")],
                "direction": item.get("direction", ""),
                "title": item.get("title") or item.get("text", "")[:100],
                "score": s["score"]["total"],
                "action": action
            }
    
    save_dedup_db(db)
    
    # Report
    report = {
        "timestamp": datetime.now().isoformat(),
        "crawl_source": crawl_ts,
        "summary": {
            "total_candidates": len(candidates),
            "duplicates_removed": len(duplicates),
            "scored": len(scored),
            "auto_installed": len(installed),
            "failed": len(failed),
            "to_review": len(to_review),
            "skipped": len(skipped),
        },
        "installed": installed,
        "failed": failed,
        "top_review": [
            {
                "title": s["item"].get("title") or s["item"].get("name", "?"),
                "url": s["item"].get("url", ""),
                "score": s["score"]["total"],
                "breakdown": s["score"]["breakdown"],
                "direction": s["item"].get("direction", ""),
                "source": s["item"].get("source", ""),
            }
            for s in to_review[:10]
        ],
    }
    
    report_path = LOG_DIR / f"install_report_{crawl_ts}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"📊 Pipeline Complete")
    print(f"{'='*60}")
    print(f"  ✅ Installed: {len(installed)} skills")
    for inst in installed:
        print(f"     [{inst['score']:.2f}] {inst['name']} — {inst['verification']['status']}")
    print(f"  ❌ Failed: {len(failed)}")
    for f in failed:
        print(f"     [{f['score']:.2f}] {f['name']} — {f['error']}")
    print(f"  📋 To review: {len(to_review)} candidates")
    print(f"  🗑  Skipped: {len(skipped)}")
    print(f"  📄 Report: {report_path}")
    
    return report

if __name__ == "__main__":
    main()
